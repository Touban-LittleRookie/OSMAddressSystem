"""The project database: an edit log shared by a few editors, with per-editor undo, checkpoints and the computed street ids.

The same code runs on **SQLite** (a file in the project folder, the default: one person or a small team on one machine) and on
**PostgreSQL** (a server shared by 2-3 editors): set ``ADDRESS_DB_URL`` / ``--db`` to a SQLAlchemy URL such as
``postgresql+psycopg://user:password@host/dbname``. Only standard SQL is used and every change is one short transaction.

The model is an **event log**. Every edit (a name, the reference, settings, the road point of a house, an imported road, a connection)
is one row of ``events`` with the editor, the time and the old and new value, and is **saved at once** - everybody sees it, nothing is
lost on a crash. The current state is the fold of all events that are not undone, in id order, so the last edit of a street wins and the
whole history stays readable.

* **Undo / Redo** step back / forward through the edits of one author (all edits when no author is given); a new edit ends the redo chain.
* **Checkpoints** are named, saved states (the full state and the street ids and names computed for it). **Restore** adds a ``restore``
  event with the old state - itself undoable - so history is never rewritten.
* **Conflicts**: ``set_name(..., expected=...)`` refuses (``Conflict``) when somebody else changed the street since the editor loaded it.
* Plain tables for QGIS / DB Browser / scripts: ``street_names`` (current names, who and when) and ``street_ids`` (the computed ids).
* The API supplies verified account IDs. A separate append-only audit retains before/after data and Undo/Redo/checkpoint decisions.
* Undone replay events are retained; ``closed_redo`` ends a redo branch without deleting the evidence. ``meta`` holds the revision counter.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import event

from .project import ADDRESSING_RULE_VERSION, Project, Settings
from .identity import audit_identity

SCHEMA_VERSION = "3"
metadata = sa.MetaData()
meta_t = sa.Table("meta", metadata, sa.Column("key", sa.String(40), primary_key=True), sa.Column("value", sa.Text))
events_t = sa.Table("events", metadata, sa.Column("id", sa.Integer, primary_key=True, autoincrement=True), sa.Column("ts", sa.String(32), nullable=False),
                    sa.Column("user", sa.String(64), nullable=False, default=""), sa.Column("action", sa.String(24), nullable=False),
                    sa.Column("street", sa.Integer), sa.Column("old", sa.Text), sa.Column("new", sa.Text),
                    sa.Column("undone", sa.Boolean, nullable=False, default=False),
                    sa.Index("ix_events_user", "user", "undone"), sa.Index("ix_events_action_street", "action", "street"))
checkpoints_t = sa.Table("checkpoints", metadata, sa.Column("id", sa.Integer, primary_key=True, autoincrement=True), sa.Column("ts", sa.String(32), nullable=False),
                         sa.Column("label", sa.Text), sa.Column("user", sa.String(64)), sa.Column("revision", sa.Integer),
                         sa.Column("state", sa.Text, nullable=False), sa.Column("streets", sa.Text))
street_names_t = sa.Table("street_names", metadata, sa.Column("street_id", sa.Integer, primary_key=True), sa.Column("name", sa.Text, nullable=False),
                          sa.Column("updated", sa.String(32)), sa.Column("user", sa.String(64)))
street_ids_t = sa.Table("street_ids", metadata, sa.Column("street_id", sa.Integer, primary_key=True), sa.Column("original_id", sa.Integer, index=True),
                        sa.Column("part", sa.Integer), sa.Column("name", sa.Text), sa.Column("display_name", sa.Text), sa.Column("status", sa.String(16)),
                        sa.Column("source", sa.String(16)), sa.Column("level", sa.Integer), sa.Column("street_rank", sa.Integer),
                        sa.Column("length_m", sa.Float), sa.Column("parent_id", sa.Integer), sa.Column("root_id", sa.Integer),
                        sa.Column("d_start", sa.Float), sa.Column("d_end", sa.Float))
computed_t = sa.Table("computed", metadata, sa.Column("key", sa.String(40), primary_key=True), sa.Column("value", sa.Text))
audit_t = sa.Table('audit',metadata,sa.Column('id',sa.Integer,primary_key=True,autoincrement=True),
                   sa.Column('ts',sa.String(32),nullable=False),sa.Column('actor',sa.String(64),nullable=False),
                   sa.Column('kind',sa.String(32),nullable=False),sa.Column('event_id',sa.Integer),
                   sa.Column('action',sa.String(40),nullable=False),sa.Column('street',sa.Integer),
                   sa.Column('before',sa.Text),sa.Column('after',sa.Text),sa.Column('details',sa.Text,nullable=False))
closed_redo_t = sa.Table('closed_redo',metadata,sa.Column('event_id',sa.Integer,primary_key=True))


def address_code(n: int, prefix: str = "FTN") -> str:
    """The permanent code of the n-th approved address, with a Luhn check digit (``FTN-000123-0``).

    Args:
        n: Sequence number (from 1; never reused).
        prefix: Community prefix.

    Returns:
        The code.
    """
    digits = f"{int(n):06d}"
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if i % 2 == 0 else 1)
        total += d - 9 if d > 9 else d
    return f"{prefix}-{digits}-{(10 - total % 10) % 10}"


class Conflict(Exception):
    """Somebody else changed the thing being edited since the editor loaded it.

    Attributes:
        current: The value in the database now (a name, or None).
        by: Who made the latest change.
    """

    def __init__(self, current, by: str = ""):
        """Remember the current value.

        Args:
            current: The current value.
            by: The editor who set it.
        """
        super().__init__(f"changed by {by or 'someone else'}: now {current!r}")
        self.current, self.by = current, by


def _now() -> str:
    """Current UTC time as ISO text.

    Returns:
        ``YYYY-MM-DDTHH:MM:SS+00:00``.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_url(root: Path) -> str:
    """The database URL of a project: ``ADDRESS_DB_URL`` or a SQLite file in the project folder.

    Args:
        root: Project folder.

    Returns:
        A SQLAlchemy URL.
    """
    return os.environ.get("ADDRESS_DB_URL") or f"sqlite:///{Path(root).resolve() / 'project.db'}"


class Store:
    """The database of one project (see the module docstring)."""

    def __init__(self, root: Path, name: str | None = None, url: str | None = None):
        """Open the project database, creating the tables on first use.

        Args:
            root: Project folder.
            name: Display name used when the database is created.
            url: SQLAlchemy URL (default: :func:`default_url`).
        """
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.url = url or default_url(self.root)
        self.engine = sa.create_engine(self.url, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def _pragmas(dbapi, _rec):
                """Write-ahead logging and a patient busy timeout so a few editors can write at once."""
                cur = dbapi.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.close()
        insp = sa.inspect(self.engine)
        if insp.has_table("checkpoints") and "streets" not in {c["name"] for c in insp.get_columns("checkpoints")}:
            raise RuntimeError(f"{self.url} was made by an older version of the app (single-editor schema); create the project again with 'init'")
        metadata.create_all(self.engine)
        self._cache: tuple[int, dict] | None = None
        with self.engine.begin() as c:
            if c.execute(sa.select(meta_t.c.value).where(meta_t.c.key == "schema")).first() is None:
                c.execute(meta_t.insert(), [{"key": "schema", "value": SCHEMA_VERSION}, {"key": "revision", "value": "0"},
                                           {"key": "name", "value": name or self.root.name}])
                c.execute(checkpoints_t.insert().values(ts=_now(), label="created", user="", revision=0,
                                                         state=json.dumps(self._initial_state(c, name or self.root.name))))
            if c.execute(sa.select(meta_t.c.value).where(meta_t.c.key=='audit_migrated')).first() is None:
                for ev in c.execute(sa.select(events_t).order_by(events_t.c.id)).mappings():
                    self._audit(c,'legacy_edit',ev['action'],ev['user'],event_id=ev['id'],street=ev['street'],
                                before=json.loads(ev['old']) if ev['old'] else None,
                                after=json.loads(ev['new']) if ev['new'] else None,
                                details={'legacy':True,'undone_at_migration':bool(ev['undone']),'original_ts':ev['ts']})
                c.execute(meta_t.insert().values(key='audit_migrated',value='1'))
                c.execute(meta_t.update().where(meta_t.c.key=='schema').values(value=SCHEMA_VERSION))
            if c.execute(sa.select(meta_t.c.value).where(meta_t.c.key == "replay_base")).first() is None:
                # The road edits made so far keep the result they have now (one replay of the whole history); every later
                # edit is applied in order on top of the network it was made on (see ``engine.effective_base``).
                last = c.execute(sa.select(sa.func.max(events_t.c.id)).where(events_t.c.undone.is_(False))).scalar()
                c.execute(meta_t.insert().values(key="replay_base", value=str(int(last or 0))))
        self._plan_cache: tuple[int, dict] | None = None

    # ---- state ----------------------------------------------------------------------------------------------------------
    @staticmethod
    def _initial_state(_c, name: str) -> dict:
        """The state of an empty project.

        Args:
            _c: Open connection (unused, kept for symmetry).
            name: Display name.

        Returns:
            State dict as in ``Project.to_dict``.
        """
        return Project(root=Path("."), name=name).to_dict()

    @staticmethod
    def _apply(state: dict, ev) -> None:
        """Apply one event to a state dict (in place).

        Args:
            state: State as in ``Project.to_dict``.
            ev: Event row (mapping access).
        """
        new = json.loads(ev["new"]) if ev["new"] is not None else None
        act = ev["action"]
        roads = lambda: state.setdefault("roads", {"imports": [], "connections": {}, "removed": [], "removed_features": [], "keep": [], "edge_street": {}, "no_cut": [], "attrs": {}, "edge_access": {}, "point_rank": {}})  # noqa: E731
        if act == "name":
            state["names"][str(ev["street"])] = new
        elif act == "unname":
            state["names"].pop(str(ev["street"]), None)
        elif act == "reference":
            state["reference"] = new
        elif act == "settings":
            state["settings"] = {**state["settings"], **(new or {})}
        elif act == "access":
            state.setdefault("access", {})[new["building"]] = {"lat": new["lat"], "lon": new["lon"]}
        elif act == "unaccess":
            state.setdefault("access", {}).pop(json.loads(ev["old"])["building"], None)
        elif act == "roads_import":
            new = dict(new)
            # Replay metadata is derived from the append-only event log.  It lets
            # geometry replay distinguish a road redrawn after an older cut from
            # the road version that the cut originally targeted.  Checkpoints
            # retain it because they store this folded state.
            new.setdefault("_event_id", int(ev["id"]))
            roads()["connections"].update(new.pop("connections", None) or {})
            roads()["keep"] = sorted(set(roads().get("keep", [])) | set(new.pop("keep", None) or []))
            roads()["imports"].append(new)
        elif act == "roads_unname":
            for imp in roads()["imports"]:
                if imp["id"] == new["id"]:
                    for f in imp["features"]:
                        f["name"] = None
        elif act == "point_rank":
            roads().setdefault("point_rank", {}).update({k: int(v) for k, v in new["ranks"].items()})
        elif act == "house_quartier":                    # the survey quartier of a house, corrected (address trigram)
            q = roads().setdefault("quartier", {})
            for k, v in new["quartier"].items():
                if v:
                    q[k] = v
                else:
                    q.pop(k, None)
        elif act == "street_attrs":
            for sid_, a_ in new["attrs"].items():
                roads().setdefault("attrs", {}).setdefault(str(sid_), {}).update(a_)
        elif act == "edge_access":
            access = roads().setdefault("edge_access", {})
            for ref, value in new["edges"].items():
                access[str(ref)] = value
        elif act == "road_geometry":
            geometry = roads().setdefault("geometry", {})
            if new.get("coords") is None:
                geometry.pop(new["ref"], None)
            else:
                geometry[new["ref"]] = new["coords"]
            reviews = roads().setdefault("geometry_reviews", {})
            if new.get("uncertain_end") is None:
                reviews.pop(new["ref"], None)
            else:
                reviews[new["ref"]] = new["uncertain_end"]
        elif act == "road_stretch":                       # one reshape across several sections: their shapes and the nodes between
            geometry, reviews = roads().setdefault("geometry", {}), roads().setdefault("geometry_reviews", {})
            for ref, coords in new["geometry"].items():
                if coords is None:
                    geometry.pop(ref, None)
                else:
                    geometry[ref] = coords
            moves = roads().setdefault("node_moves", {})
            for node, point in new["nodes"].items():
                if point is None:
                    moves.pop(node, None)
                else:
                    moves[node] = point
            for ref, review in (new.get("reviews") or {}).items():
                if review is None:
                    reviews.pop(ref, None)
                else:
                    reviews[ref] = review
        elif act == "road_check_ok":                      # road check problems marked "OK as is" (or listed again)
            marked = set(roads().get("check_ok", []))
            marked = marked | set(new["ids"]) if new.get("ok", True) else marked - set(new["ids"])
            roads()["check_ok"] = sorted(marked)
        elif act == "road_review":
            roads().setdefault("reviews", []).append(new)
        elif act == "road_review_remove":
            ids = set(new.get("ids", []))
            roads()["reviews"] = [review for review in roads().get("reviews", []) if review.get("id") not in ids]
        elif act == "road_cut":
            roads().setdefault("cuts", []).append({**new, "_event_id": int(ev["id"])})
        elif act == "road_join":
            roads().setdefault("joins", []).append({**new, "_event_id": int(ev["id"])})
        elif act == "road_operations_remove":
            ids = set(new.get("ids", []))
            roads()["cuts"] = [operation for operation in roads().get("cuts", []) if operation.get("id") not in ids]
            roads()["joins"] = [operation for operation in roads().get("joins", []) if operation.get("id") not in ids]
        elif act == "work_areas":
            state["work_areas"] = new
        elif act == "address_approve":                   # a validated address changes only when its change is validated
            reg = state.setdefault("register", {})
            when, who = (ev.get("ts"), ev.get("user")) if hasattr(ev, "get") else (None, None)
            for bid, snap in new["houses"].items():
                cur = reg.get(bid) or {}
                step = {"ts": when, "user": who, "action": "corrected" if cur.get("status") == "approved" else "approved",
                        "address": snap.get("address"), "plate": snap.get("plate"), "reason": new.get("reason") or None}
                if cur.get("status") == "approved":       # before / after, for the list of families to inform
                    step.update({"before_address": cur.get("address"), "before_plate": cur.get("plate")})
                reg[bid] = {**snap, "code": cur.get("code") or snap.get("code"), "status": "approved", "approved_at": when, "approved_by": who,
                            "history": [*cur.get("history", []), step]}
        elif act == "address_retire":                    # a demolished house: the address and its code are never given again
            reg = state.setdefault("register", {})
            when, who = (ev.get("ts"), ev.get("user")) if hasattr(ev, "get") else (None, None)
            for bid in new["ids"]:
                if bid in reg:
                    reg[bid] = {**reg[bid], "status": "retired",
                                "history": [*reg[bid].get("history", []), {"ts": when, "user": who, "action": "retired", "address": reg[bid].get("address"),
                                                                          "reason": new.get("reason") or None}]}
        elif act == "edges_assign":
            roads().setdefault("edge_street", {}).update({k: int(v) for k, v in new["edges"].items()})
            roads()["no_cut"] = sorted(set(roads().get("no_cut", [])) | {int(x) for x in new.get("no_cut", [])})
            for sid_, a_ in (new.get("attrs") or {}).items():
                roads().setdefault("attrs", {}).setdefault(str(sid_), {}).update(a_)
            for sid, nm in (new.get("names") or {}).items():
                state["names"][str(sid)] = nm
        elif act in ("edges_remove", "edges_restore"):
            for field_, key in (("removed", "edges"), ("removed_features", "features")):
                cur = set(roads().get(field_, []))
                cur = cur | set(new.get(key, [])) if act == "edges_remove" else cur - set(new.get(key, []))
                roads()[field_] = sorted(cur)
        elif act == "roads_remove":
            roads()["imports"] = [i for i in roads()["imports"] if i["id"] != new["id"]]
        elif act == "road_connect":
            roads()["connections"][new["node"]] = new["target"]
        elif act == "road_connect_many":
            roads()["connections"].update(new["nodes"])
        elif act == "road_unconnect":
            roads()["connections"].pop(new["node"], None)
        elif act == "restore":
            keep, register = state.get("name"), state.get("register")
            state.clear()
            state.update(copy.deepcopy(new))
            state["name"] = keep or state.get("name")
            if register is not None:                   # restoring a checkpoint never takes back an approved address
                state["register"] = register

    def revision(self, c=None) -> int:
        """The revision counter, increased by every change (edit, undo, redo).

        Args:
            c: Open connection, or None to open one.

        Returns:
            The revision.
        """
        if c is None:
            with self.engine.connect() as c2:
                return self.revision(c2)
        return int(c.execute(sa.select(meta_t.c.value).where(meta_t.c.key == "revision")).scalar_one())

    def _bump(self, c) -> None:
        """Increase the revision in one atomic statement.

        Args:
            c: Open connection (inside a transaction).
        """
        c.execute(meta_t.update().where(meta_t.c.key == "revision").values(
            value=sa.cast(sa.cast(meta_t.c.value, sa.Integer) + 1, sa.String)))

    def _state(self, c) -> dict:
        """The current state: the fold of the events that are not undone (cached per revision).

        Args:
            c: Open connection.

        Returns:
            State dict (a copy).
        """
        rev = self.revision(c)
        if self._cache is None or self._cache[0] != rev:
            name = c.execute(sa.select(meta_t.c.value).where(meta_t.c.key == "name")).scalar_one()
            state = self._initial_state(c, name)
            for ev in c.execute(sa.select(events_t).where(events_t.c.undone.is_(False)).order_by(events_t.c.id)).mappings():
                self._apply(state, ev)
            self._cache = (rev, state)
        return copy.deepcopy(self._cache[1])

    def project(self) -> Project:
        """The current state shared by all editors.

        Returns:
            The :class:`Project` state.
        """
        with self.engine.connect() as c:
            project = Project.from_dict(self.root, self._state(c))
            ids = c.execute(sa.select(meta_t.c.value).where(meta_t.c.key == "node_ids")).scalar()
            project.node_ids = None if ids is None else {str(k): int(v) for k, v in json.loads(ids).items()}
            project.replay = self._replay_plan(c)
            return project

    # The road edits that change the network itself; the others (names, ranks, drivable...) only change the state.
    _NETWORK_ACTIONS = {"roads_import", "road_cut", "road_join", "road_geometry", "road_stretch", "edges_remove", "edges_restore",
                        "edges_assign", "road_operations_remove", "roads_remove", "roads_unname", "road_connect",
                        "road_connect_many", "road_unconnect"}

    def _replay_plan(self, c) -> dict | None:
        """How the road network is rebuilt: the frozen part of the history, then the later network edits in order.

        The edits up to the ``replay_base`` event (or the latest restore after it) are folded and replayed together, as they
        always were; their result does not change. Each later edit refers to the network as it was when it was made (a
        section ``u-v-key``, a node), so it is applied on top of the edits before it, in the order they were made.

        An edit that takes back something of the frozen part (restoring a deleted edge, removing an old cut...) changes the
        frozen part instead; one that takes back a later edit removes that edit from the list.

        Returns:
            ``{"point": event id, "base_roads": roads state of the frozen part, "ops": [{"id", "action", "new"}], "signature"}``,
            or None for a database without ``replay_base``.
        """
        point = c.execute(sa.select(meta_t.c.value).where(meta_t.c.key == "replay_base")).scalar()
        if point is None:
            return None
        rev = self.revision(c)
        if self._plan_cache is not None and self._plan_cache[0] == rev:
            return copy.deepcopy(self._plan_cache[1])
        events = list(c.execute(sa.select(events_t).where(events_t.c.undone.is_(False)).order_by(events_t.c.id)).mappings())
        point = max([int(point)] + [int(ev["id"]) for ev in events if ev["action"] == "restore"])
        name = c.execute(sa.select(meta_t.c.value).where(meta_t.c.key == "name")).scalar_one()
        state = self._initial_state(c, name)
        ops: list[dict] = []

        def amend(action: str, new) -> None:
            self._apply(state, {"action": action, "new": json.dumps(new), "old": None, "street": None, "id": 0})

        def drop(pred) -> None:
            ops[:] = [op for op in ops if not pred(op)]

        for ev in events:
            if int(ev["id"]) <= point:
                self._apply(state, ev)
                continue
            act = ev["action"]
            if act not in self._NETWORK_ACTIONS:
                continue
            new = json.loads(ev["new"]) if ev["new"] is not None else None
            op = {"id": int(ev["id"]), "action": act, "new": new}
            if act == "road_geometry" and new.get("coords") is None:
                amend(act, new)
                drop(lambda o, ref=new["ref"]: o["action"] == "road_geometry" and o["new"]["ref"] == ref)
            elif act == "road_stretch":
                gone = [ref for ref, coords in new["geometry"].items() if coords is None]
                if gone or any(point_ is None for point_ in new["nodes"].values()):
                    amend(act, {"geometry": {ref: None for ref in gone}, "nodes": {n: None for n, p in new["nodes"].items() if p is None}})
                op["new"] = {**new, "geometry": {r: g for r, g in new["geometry"].items() if g is not None},
                             "nodes": {n: p for n, p in new["nodes"].items() if p is not None}}
                ops.append(op)
            elif act == "edges_restore":
                later = {"edges": set(), "features": set()}
                for o in ops:
                    if o["action"] == "edges_remove":
                        for key in ("edges", "features"):
                            mine = set(o["new"].get(key, [])) & set(new.get(key, []))
                            later[key] |= mine
                            o["new"] = {**o["new"], key: [x for x in o["new"].get(key, []) if x not in mine]}
                amend(act, {key: [x for x in new.get(key, []) if x not in later[key]] for key in ("edges", "features")})
            elif act == "road_operations_remove":
                ids = set(new.get("ids", []))
                drop(lambda o: o["action"] in ("road_cut", "road_join") and o["new"].get("id") in ids)
                amend(act, new)
            elif act == "roads_remove":
                mine = any(o["action"] == "roads_import" and o["new"]["id"] == new["id"] for o in ops)
                drop(lambda o: o["action"] == "roads_import" and o["new"]["id"] == new["id"])
                if not mine:
                    amend(act, new)
            elif act == "roads_unname":
                mine = False
                for o in ops:
                    if o["action"] == "roads_import" and o["new"]["id"] == new["id"]:
                        o["new"] = {**o["new"], "features": [{**f, "name": None} for f in o["new"]["features"]]}
                        mine = True
                if not mine:
                    amend(act, new)
            elif act in ("road_connect", "road_connect_many", "road_unconnect"):
                # A connection choice is keyed by the position of a drawn end: it applies to whichever drawn road has an end
                # there, frozen or later (an import only uses the keys of its own ends).
                amend(act, new)
                for o in ops:
                    if o["action"] == "roads_import":
                        conn = dict(o["new"].get("connections") or {})
                        if act == "road_connect":
                            conn[new["node"]] = new["target"]
                        elif act == "road_connect_many":
                            conn.update(new["nodes"])
                        else:
                            conn.pop(new["node"], None)
                        o["new"] = {**o["new"], "connections": conn}
            else:
                ops.append(op)
        base_roads = Project.from_dict(self.root, state).roads
        signature = hashlib.sha1(json.dumps({"point": point, "base": base_roads, "ops": ops}, sort_keys=True).encode()).hexdigest()[:16]
        plan = {"point": point, "base_roads": base_roads, "ops": ops, "signature": signature}
        self._plan_cache = (rev, plan)
        return copy.deepcopy(plan)

    def freeze_node_ids(self, ids: dict) -> None:
        """Record once the ids the drawn-road nodes have now; from then on they never change (see ``roads.drawn_node_id``).

        Kept outside the edit history, so that no undo or checkpoint restore takes it away.

        Args:
            ids: Node key -> node id.
        """
        with self.engine.begin() as c:
            if c.execute(sa.select(meta_t.c.key).where(meta_t.c.key == "node_ids")).first() is None:
                c.execute(meta_t.insert().values(key="node_ids", value=json.dumps({str(k): int(v) for k, v in ids.items()})))

    # ---- editing ----------------------------------------------------------------------------------------------------------
    def _add_event(self, c, action: str, street, old, new, user: str) -> int:
        """Append an event (ending the author's redo chain) and bump the revision.

        Args:
            c: Open connection (inside a transaction).
            action: Event type.
            street: Street id or None.
            old: Previous value (JSON-serialisable).
            new: New value (JSON-serialisable).
            user: Author.

        Returns:
            The event id.
        """
        retired=list(c.execute(sa.select(events_t.c.id).where(sa.and_(events_t.c.user==user,events_t.c.undone.is_(True),
                         ~events_t.c.id.in_(sa.select(closed_redo_t.c.event_id))))).scalars())
        if retired:
            self._audit(c,'redo_branch_closed','redo_branch_closed',user,details={'events':retired})
            c.execute(closed_redo_t.insert(),[{'event_id':eid} for eid in retired])
        res = c.execute(events_t.insert().values(ts=_now(), user=user, action=action, street=street, old=json.dumps(old), new=json.dumps(new),
                                                 undone=False))
        self._bump(c)
        self._audit(c,'edit',action,user,event_id=int(res.inserted_primary_key[0]),street=street, before=old,after=new)
        return int(res.inserted_primary_key[0])

    def _audit(self,c,kind,action,user='',event_id=None,street=None,before=None,after=None,details=None):
        """Append evidence independently of the mutable undo/replay projection."""
        c.execute(audit_t.insert().values(ts=_now(),actor=user,kind=kind,action=action,event_id=event_id,street=street,
                  before=json.dumps(before) if before is not None else None,after=json.dumps(after) if after is not None else None,
                  details=json.dumps({**audit_identity(user),'revision':self.revision(c),**(details or {})})))

    def record_audit(self,action,user='',kind='account',**details):
        with self.engine.begin() as c:
            self._audit(c,kind,action,user,details=details)

    def audit(self,limit=100,before_id=None):
        with self.engine.connect() as c:
            query=sa.select(audit_t).order_by(audit_t.c.id.desc()).limit(max(1,min(int(limit),200)))
            if before_id is not None: query=query.where(audit_t.c.id<int(before_id))
            rows=c.execute(query).mappings().all()
        return [{**dict(r),'before':json.loads(r['before']) if r['before'] else None,
                 'after':json.loads(r['after']) if r['after'] else None,'details':json.loads(r['details'])} for r in rows]

    def _after(self, c) -> None:
        """Keep the plain ``street_names`` table equal to the current state.

        Args:
            c: Open connection (inside a transaction).
        """
        state = self._state(c)
        meta = self._names_meta(c)
        c.execute(street_names_t.delete())
        rows = [{"street_id": int(k), "name": v, "updated": meta.get(int(k), {}).get("ts"), "user": meta.get(int(k), {}).get("user")}
                for k, v in sorted(state["names"].items(), key=lambda kv: int(kv[0]))]
        if rows:
            c.execute(street_names_t.insert(), rows)

    def _names_meta(self, c) -> dict[int, dict]:
        """Who set the current name of every street, and when.

        Args:
            c: Open connection.

        Returns:
            ``street id -> {"user", "ts", "name"}``.
        """
        out: dict[int, dict] = {}
        for ev in c.execute(sa.select(events_t).where(sa.and_(events_t.c.undone.is_(False), events_t.c.action.in_(["name", "unname", "restore"])))
                            .order_by(events_t.c.id)).mappings():
            if ev["action"] == "name":
                out[int(ev["street"])] = {"user": ev["user"], "ts": ev["ts"], "name": json.loads(ev["new"])}
            elif ev["action"] == "unname":
                out.pop(int(ev["street"]), None)
            else:
                out = {int(k): {"user": ev["user"], "ts": ev["ts"], "name": v} for k, v in json.loads(ev["new"]).get("names", {}).items()}
        return out

    def names_meta(self) -> dict[int, dict]:
        """Who set the current name of every street, and when.

        Returns:
            ``street id -> {"user", "ts", "name"}``.
        """
        with self.engine.connect() as c:
            return self._names_meta(c)

    def set_name(self, street_id: int, name: str | None, user: str = "", expected="__unset__") -> bool:
        """Give (or remove, with an empty name) the name of a street.

        Args:
            street_id: Street id after the community edits.
            name: The name; None or blank removes the community name.
            user: Author.
            expected: The name the editor saw when opening the street (``None`` = no name). When given and different from the
                current name, nothing is changed and :class:`Conflict` is raised.

        Returns:
            True when something changed.

        Raises:
            Conflict: If somebody else changed the street in the meantime.
        """
        sid = int(street_id)
        name = (name or "").strip()
        with self.engine.begin() as c:
            old = self._state(c)["names"].get(str(sid))
            if expected != "__unset__" and (expected or None) != (old or None):
                by = self._names_meta(c).get(sid, {}).get("user", "")
                raise Conflict(old, by)
            if name == (old or ""):
                return False
            self._add_event(c, "name" if name else "unname", sid, old, name or None, user)
            self._after(c)
        return True

    def set_reference(self, lat: float, lon: float, node: int, user: str = "", by: str = "", name: str | None = None, default: bool = False) -> None:
        """Choose (or confirm) the reference node.

        Args:
            lat: Latitude of the snapped node.
            lon: Longitude of the snapped node.
            node: Node id.
            user: Author.
            by: Anonymous id of the browser that set or confirmed it (``"default"`` for the project's default point).
            name: Name of the point (the default reference has one).
            default: True when it is the project's default reference, not yet confirmed by anybody.
        """
        with self.engine.begin() as c:
            ref = {"lat": float(lat), "lon": float(lon), "node": int(node), "by": by, "default": bool(default)}
            if name:
                ref["name"] = name
            self._add_event(c, "reference", None, self._state(c)["reference"], ref, user)

    def set_settings(self, changes: dict, user: str = "") -> None:
        """Change computation settings.

        Args:
            changes: Setting name -> value (unknown names are ignored).
            user: Author.
        """
        valid = {k: v for k, v in changes.items() if k in Settings.__dataclass_fields__ and k != "addressing_rule_version"}
        if valid:
            # Persist the migration marker with the first settings edit. This makes later deliberate custom steps distinguishable
            # from an old project that still carries the former 2 m / 20 m defaults.
            valid["addressing_rule_version"] = ADDRESSING_RULE_VERSION
            with self.engine.begin() as c:
                cur = self._state(c)["settings"]
                self._add_event(c, "settings", None, {k: cur.get(k) for k in valid}, valid, user)

    def set_access(self, building_id: str, lat: float, lon: float, user: str = "") -> None:
        """Choose, by hand, the road point used to number a house.

        Args:
            building_id: The house (its ``building_id``).
            lat: Latitude of the chosen point on a road.
            lon: Longitude of the chosen point on a road.
            user: Author.
        """
        with self.engine.begin() as c:
            old = self._state(c).get("access", {}).get(str(building_id))
            self._add_event(c, "access", None, old, {"building": str(building_id), "lat": float(lat), "lon": float(lon)}, user)

    def clear_access(self, building_id: str, user: str = "") -> bool:
        """Go back to the automatic (nearest road) point of a house.

        Args:
            building_id: The house.
            user: Author.

        Returns:
            True when a chosen point was removed.
        """
        with self.engine.begin() as c:
            old = self._state(c).get("access", {}).get(str(building_id))
            if old is None:
                return False
            self._add_event(c, "unaccess", None, {"building": str(building_id), **old}, None, user)
        return True

    def import_roads(self, file: str, features: list[dict], user: str = "", connections: dict | None = None, keep: list | None = None,
                     first_street_id: int | None = None) -> int:
        """Add a file of missing roads (drawn lines) to the project, with the connection choices made while previewing it.

        Args:
            file: File name, for the record.
            features: Drawn lines from ``roads.features_from_lines``.
            user: Author.
            connections: Connection choices by node key (see ``roads.integrate_roads``).
            keep: Existing edges that must stay although a new road replaces them.
            first_street_id: Lowest free street id of the network now; the new roads (except those continuing a street) get
                their ids from it, recorded in the edit.

        Returns:
            The id of the import.
        """
        with self.engine.begin() as c:
            imports = self._state(c)["roads"]["imports"]
            nid = max([i["id"] for i in imports] + [0]) + 1
            if first_street_id is not None:
                # Each new road keeps the street id it gets now, whatever is undone before it later; an id is never given twice.
                kept = c.execute(sa.select(meta_t.c.value).where(meta_t.c.key == "next_street_id")).scalar()
                sid = max(int(first_street_id), int(kept or 0))
                features = [dict(f) for f in features]
                for f in features:
                    if f.get("join") is None and f.get("street_id") is None:
                        f["street_id"], sid = sid, sid + 1
                if kept is None:
                    c.execute(meta_t.insert().values(key="next_street_id", value=str(sid)))
                else:
                    c.execute(meta_t.update().where(meta_t.c.key == "next_street_id").values(value=str(sid)))
            self._add_event(c, "roads_import", None, None, {"id": nid, "file": file, "features": features, "connections": connections or {}, "keep": keep or []}, user)
        return nid

    def unname_roads(self, import_id: int, user: str = "") -> None:
        """Take the names off the roads of an import (the labels of a file are not street names).

        Args:
            import_id: Id of the import.
            user: Author.
        """
        with self.engine.begin() as c:
            self._add_event(c, "roads_unname", None, None, {"id": int(import_id)}, user)

    def remove_roads(self, import_id: int, user: str = "") -> None:
        """Remove an import of missing roads.

        Args:
            import_id: Id from :meth:`import_roads`.
            user: Author.
        """
        with self.engine.begin() as c:
            self._add_event(c, "roads_remove", None, {"id": int(import_id)}, {"id": int(import_id)}, user)

    def set_point_ranks(self, ranks: dict, user: str = "") -> None:
        """Change the rank of reference points for the street signs (one undo step).

        Args:
            ranks: ``{"POINT-n": 0-3}``.
            user: Author.
        """
        if ranks:
            with self.engine.begin() as c:
                self._add_event(c, "point_rank", None, None, {"ranks": {str(k): int(v) for k, v in ranks.items()}}, user)

    def set_house_quartiers(self, quartiers: dict, user: str = "") -> None:
        """Correct the survey quartier of houses (one undo step); an empty value goes back to the survey's.

        Args:
            quartiers: ``{building id: quartier name}``.
            user: Author.
        """
        if quartiers:
            with self.engine.begin() as c:
                old = self._state(c).get("roads", {}).get("quartier", {})
                self._add_event(c, "house_quartier", None, {str(k): old.get(str(k)) for k in quartiers},
                                {"quartier": {str(k): (str(v).strip() or None) if v else None for k, v in quartiers.items()}}, user)

    def set_street_attrs(self, attrs: dict, user: str = "") -> None:
        """Change the rank / drivable / paved flag of streets (one undo step).

        Args:
            attrs: ``{original street id: {"rank": 0-5, "drivable": bool, "paved": bool}}`` (only the keys that change).
            user: Author.
        """
        attrs = {str(k): {kk: vv for kk, vv in v.items() if kk in ("rank", "drivable", "paved", "addresses") and (vv is not None or kk not in ("rank", "addresses"))}
                 for k, v in attrs.items()}
        attrs = {k: v for k, v in attrs.items() if v}
        if attrs:
            with self.engine.begin() as c:
                self._add_event(c, "street_attrs", None, None, {"attrs": attrs}, user)

    def register(self) -> dict:
        """The address register: approved and retired addresses by building id.

        Returns:
            ``{building id: {"code", "address", "number", "street", "street_id", "status", "approved_at", "approved_by", "history", ...}}``.
        """
        with self.engine.connect() as c:
            return self._state(c).get("register", {})

    def approve_addresses(self, houses: dict, user: str = "", reason: str = "", correct: bool = False) -> dict:
        """Validate the current address of houses, in one undoable event.

        A validated address changes only through a validated correction (``correct``), which records the address before and after.
        A house validated for the first time gets the next internal identifier (``FTN-000001-7``, with a check digit; not printed
        on the plaque, which carries the address ``TCK 0575 0230``). The identifier is kept for ever: a correction changes the
        address, never the identifier, and an identifier is never given twice, even when the validation is undone.

        Args:
            houses: ``{building id: snapshot}`` with at least ``address``, ``number``, ``street`` and ``street_id``.
            user: Author.
            reason: Why (required to correct an address that is already approved).
            correct: True to replace an approved address (a correction); otherwise approved houses are left as they are.

        Returns:
            ``{"approved": [...], "corrected": [...], "unchanged": [...]}`` (building ids).

        Raises:
            ValueError: When a correction has no reason.
        """
        if correct and not reason.strip():
            raise ValueError("say why the approved address is corrected")
        out = {"approved": [], "corrected": [], "unchanged": []}
        with self.engine.begin() as c:
            reg = self._state(c).get("register", {})
            kept = c.execute(sa.select(meta_t.c.value).where(meta_t.c.key == "next_address_code")).scalar()
            nxt = int(kept or 1)
            todo = {}
            for bid, snap in houses.items():
                bid = str(bid)
                cur = reg.get(bid)
                same = (cur.get("plate") == snap.get("plate") if cur and cur.get("plate") else cur and cur.get("address") == snap.get("address"))
                if cur and cur.get("status") == "approved" and (not correct or (same and cur.get("address") == snap.get("address"))):
                    out["unchanged"].append(bid)
                    continue
                snap = {k: snap.get(k) for k in ("address", "plate", "street_code", "number", "street", "street_id", "lat", "lon", "district",
                                                 "quartier_code", "road_lat", "road_lon")}
                if not (cur and cur.get("code")):
                    snap["code"], nxt = address_code(nxt), nxt + 1
                todo[bid] = snap
                out["corrected" if cur and cur.get("status") == "approved" else "approved"].append(bid)
            if todo:
                if kept is None:
                    c.execute(meta_t.insert().values(key="next_address_code", value=str(nxt)))
                else:
                    c.execute(meta_t.update().where(meta_t.c.key == "next_address_code").values(value=str(nxt)))
                self._add_event(c, "address_approve", None, {b: reg.get(b) for b in todo}, {"houses": todo, "reason": reason or None}, user)
        return out

    def retire_addresses(self, ids: list, reason: str, user: str = "") -> list:
        """Retire approved addresses (a demolished house), in one undoable event. The code is never given again.

        Args:
            ids: Building ids.
            reason: Why (required).
            user: Author.

        Returns:
            The building ids retired.

        Raises:
            ValueError: Without a reason.
        """
        if not reason.strip():
            raise ValueError("say why the address is retired")
        with self.engine.begin() as c:
            reg = self._state(c).get("register", {})
            ids = sorted({str(i) for i in ids if reg.get(str(i), {}).get("status") == "approved"})
            if ids:
                self._add_event(c, "address_retire", None, None, {"ids": ids, "reason": reason}, user)
        return ids

    def set_check_ok(self, ids: list, ok: bool = True, user: str = "") -> None:
        """Mark road check problems "OK as is" (or list them again) in one undoable event (see ``road_check``).

        Args:
            ids: Problem ids.
            ok: True to mark them, False to list them again.
            user: Author.
        """
        ids = sorted({str(i) for i in ids})
        if ids:
            with self.engine.begin() as c:
                self._add_event(c, "road_check_ok", None, None, {"ids": ids, "ok": bool(ok)}, user)

    def set_edge_access(self, edges: dict, expected_revision: int | None = None, user: str = "") -> None:
        """Mark stable edge references drivable ("car"), not drivable ("foot") or unknown in one undoable event.

        Older projects may hold "moto"; it reads as not drivable but is no longer written.
        """
        allowed = {"car", "foot", None}
        values = {str(ref): value for ref, value in edges.items()}
        if any(value not in allowed for value in values.values()):
            raise ValueError("access must be car, foot or null")
        if not values:
            return
        with self.engine.begin() as c:
            if expected_revision is not None and self.revision(c) != expected_revision:
                raise Conflict("project changed; select the route again")
            self._add_event(c, "edge_access", None, None, {"edges": values}, user)

    def assign_edge_streets(self, mapping: dict, user: str = "", names: dict | None = None, no_cut: list | None = None, attrs: dict | None = None) -> None:
        """Give roads another street id (one undo step), optionally with the name the street takes.

        Args:
            mapping: Edge reference ``"u-v-key"`` -> street id.
            user: Author.
            names: Street id -> name to give at the same time (when two streets are merged and only the street that is joined has a name).
        """
        if mapping or no_cut or names or attrs:
            with self.engine.begin() as c:
                self._add_event(c, "edges_assign", None, None, {"edges": {str(k): int(v) for k, v in mapping.items()},
                                                                  "names": {str(k): v for k, v in (names or {}).items()}, "no_cut": [int(x) for x in (no_cut or [])], "attrs": {str(k): v for k, v in (attrs or {}).items()}}, user)
                self._after(c)

    def set_road_geometry(self, ref: str, coords: list, expected_revision: int, user: str = "", uncertain_end: dict | None = None) -> None:
        """Reshape one edge, retaining its identity; one undoable event."""
        with self.engine.begin() as c:
            if self.revision(c) != expected_revision:
                raise Conflict("project changed; reload the road before saving")
            roads = self._state(c).get("roads", {})
            old = roads.get("geometry", {}).get(ref)
            old_review = roads.get("geometry_reviews", {}).get(ref)
            self._add_event(c, "road_geometry", None, {"ref": ref, "coords": old, "uncertain_end": old_review},
                            {"ref": ref, "coords": coords, "uncertain_end": uncertain_end}, user)

    def set_road_stretch(self, geometry: dict, nodes: dict, expected_revision: int, user: str = "", reviews: dict | None = None) -> None:
        """Reshape several consecutive sections of one road and move the nodes between them; one undoable event.

        Args:
            geometry: Edge reference -> WGS84 coordinates.
            nodes: Node id -> ``[lon, lat]``.
            expected_revision: Refused when the project changed meanwhile.
            user: Author.
            reviews: Edge reference -> "unclear beyond B" mark (or None to clear it).
        """
        with self.engine.begin() as c:
            if self.revision(c) != expected_revision:
                raise Conflict("project changed; reload the road before saving")
            roads = self._state(c).get("roads", {})
            nodes = {str(n): p for n, p in nodes.items()}
            reviews = reviews or {}
            old = {"geometry": {ref: roads.get("geometry", {}).get(ref) for ref in geometry},
                   "nodes": {n: roads.get("node_moves", {}).get(n) for n in nodes},
                   "reviews": {ref: roads.get("geometry_reviews", {}).get(ref) for ref in reviews}}
            self._add_event(c, "road_stretch", None, old, {"geometry": geometry, "nodes": nodes, "reviews": reviews}, user)

    def add_road_review(self, review: dict, expected_revision: int, user: str = "") -> None:
        """Mark one interval of a road as unclear without changing its geometry."""
        with self.engine.begin() as c:
            if self.revision(c) != expected_revision:
                raise Conflict("project changed; select the unclear portion again")
            self._add_event(c, "road_review", None, None, review, user)

    def remove_road_reviews(self, ids: list[str], expected_revision: int, user: str = "") -> None:
        """Resolve selected unclear-road review marks as one undoable event."""
        with self.engine.begin() as c:
            if self.revision(c) != expected_revision:
                raise Conflict("project changed; reload the unclear portions")
            self._add_event(c, "road_review_remove", None, None, {"ids": [str(value) for value in ids]}, user)

    def remove_edges(self, edges: list[str], features: list[str], user: str = "") -> None:
        """Delete street edges (base network edges by reference, drawn lines by key); undoable.

        Args:
            edges: Edge references ``"u-v-key"``.
            features: Drawn-line keys ``"<import>:<id>"``.
            user: Author.
        """
        if edges or features:
            with self.engine.begin() as c:
                self._add_event(c, "edges_remove", None, None, {"edges": list(edges), "features": list(features)}, user)

    def add_road_cut(self, cut: dict, expected_revision: int, user: str = "") -> None:
        self._road_operation('road_cut', cut, expected_revision, user)

    def add_road_join(self, join: dict, expected_revision: int, user: str = "") -> None:
        self._road_operation('road_join', join, expected_revision, user)

    def remove_road_operations(self, ids: list[str], reason: str, expected_revision: int, user: str = "") -> None:
        """Remove invalid saved cuts/joins as one attributed, undoable maintenance edit."""
        ids = sorted({str(value) for value in ids if value})
        if not ids:
            return
        if not isinstance(reason, str) or not 5 <= len(reason.strip()) <= 500:
            raise ValueError('explain why the road operations are removed')
        with self.engine.begin() as c:
            if self.revision(c) != expected_revision:
                raise Conflict('project changed; reload the road warnings')
            current = self._state(c).get('roads', {})
            existing = {operation.get('id') for key in ('cuts', 'joins') for operation in current.get(key, [])}
            if not set(ids) <= existing:
                raise ValueError('one or more road operations no longer exist')
            self._add_event(c, 'road_operations_remove', None, None,
                            {'ids': ids, 'reason': reason.strip()}, user)

    def _road_operation(self, action: str, operation: dict, expected_revision: int, user: str) -> None:
        with self.engine.begin() as c:
            if self.revision(c) != expected_revision:
                raise Conflict('project changed; reload the road')
            rd = self._state(c).get('roads', {})
            orders = [op.get('order', i+1) for i, op in enumerate(rd.get('cuts', []))]
            orders += [op['order'] for op in rd.get('joins', [])]
            operation = {**operation, 'order': max(orders, default=0)+1}
            self._add_event(c, action, None, None, operation, user)

    def set_work_areas(self, areas: dict, expected_revision: int, user: str = "") -> None:
        with self.engine.begin() as c:
            if self.revision(c) != expected_revision:
                raise Conflict('project changed; reload the areas')
            old = self._state(c).get('work_areas', {})
            self._add_event(c, 'work_areas', None, old, areas, user)

    def restore_edges(self, edges: list[str], features: list[str], user: str = "") -> None:
        """Bring back deleted street edges.

        Args:
            edges: Edge references ``"u-v-key"``.
            features: Drawn-line keys.
            user: Author.
        """
        if edges or features:
            with self.engine.begin() as c:
                self._add_event(c, "edges_restore", None, None, {"edges": list(edges), "features": list(features)}, user)

    def connect_road_node(self, node_key: str, target: dict, user: str = "") -> None:
        """Choose how a node of a drawn road is connected.

        Args:
            node_key: Key of the generated node.
            target: ``{"type": "node", "node": id}``, ``{"type": "edge", "u", "v", "key", "lat", "lon"}`` or ``{"type": "none"}``.
            user: Author.
        """
        with self.engine.begin() as c:
            self._add_event(c, "road_connect", None, self._state(c)["roads"]["connections"].get(node_key), {"node": node_key, "target": target}, user)

    def connect_road_nodes(self, targets: dict, user: str = "") -> None:
        """Connect several nodes at once (one undo step).

        Args:
            targets: Node key -> connection target.
            user: Author.
        """
        if targets:
            with self.engine.begin() as c:
                self._add_event(c, "road_connect_many", None, None, {"nodes": targets}, user)

    def clear_road_connection(self, node_key: str, user: str = "") -> bool:
        """Go back to the automatic connection of a node.

        Args:
            node_key: Key of the generated node.
            user: Author.

        Returns:
            True when a choice was removed.
        """
        with self.engine.begin() as c:
            old = self._state(c)["roads"]["connections"].get(node_key)
            if old is None:
                return False
            self._add_event(c, "road_unconnect", None, {"node": node_key, "target": old}, {"node": node_key}, user)
        return True

    # ---- undo / redo (own edits only) -----------------------------------------------------------------------------------------------
    def undo(self, user: str = "", strict: bool = False) -> dict | None:
        """Undo the latest edit *of this editor*.

        Args:
            user: The editor.

        Returns:
            The undone event as a dict, or None when this editor has nothing to undo.
        """
        with self.engine.begin() as c:
            ev = c.execute(sa.select(events_t).where(sa.and_(events_t.c.user == user, events_t.c.undone.is_(False)))
                           .order_by(events_t.c.id.desc()).limit(1)).mappings().first()
            if ev is None:
                return None
            if strict and c.execute(sa.select(events_t.c.id).where(sa.and_(events_t.c.id>ev['id'],events_t.c.user!=user,events_t.c.undone.is_(False))).limit(1)).first():
                raise Conflict('another editor has newer changes; review history before undoing')
            c.execute(events_t.update().where(events_t.c.id == ev["id"]).values(undone=True))
            self._bump(c)
            self._audit(c,'undo',ev['action'],user,event_id=ev['id'],street=ev['street'],before={'undone':False},after={'undone':True})
            self._after(c)
            return dict(ev)

    def redo(self, user: str = "", strict: bool = False) -> dict | None:
        """Redo the earliest undone edit of this editor.

        Args:
            user: The editor.

        Returns:
            The redone event as a dict, or None when there is nothing to redo.
        """
        with self.engine.begin() as c:
            last = c.execute(sa.select(sa.func.coalesce(sa.func.max(events_t.c.id), 0)).where(
                sa.and_(events_t.c.user == user, events_t.c.undone.is_(False)))).scalar_one()
            ev = c.execute(sa.select(events_t).where(sa.and_(events_t.c.user == user, events_t.c.undone.is_(True), events_t.c.id > last,
                                   ~events_t.c.id.in_(sa.select(closed_redo_t.c.event_id))))
                           .order_by(events_t.c.id).limit(1)).mappings().first()
            if ev is None:
                return None
            if strict and c.execute(sa.select(events_t.c.id).where(sa.and_(events_t.c.id>ev['id'],events_t.c.user!=user,events_t.c.undone.is_(False))).limit(1)).first():
                raise Conflict('another editor has newer changes; review history before redoing')
            if strict:
                last_undo=c.execute(sa.select(sa.func.max(audit_t.c.id)).where(sa.and_(audit_t.c.event_id==ev['id'],audit_t.c.kind=='undo'))).scalar_one() or 0
                if c.execute(sa.select(audit_t.c.id).where(sa.and_(audit_t.c.id>last_undo,audit_t.c.actor!=user,
                             audit_t.c.kind.in_(['edit','undo','redo','checkpoint_restore']))).limit(1)).first():
                    raise Conflict('another editor changed the project since this undo; review before redoing')
            c.execute(events_t.update().where(events_t.c.id == ev["id"]).values(undone=False))
            self._bump(c)
            self._audit(c,'redo',ev['action'],user,event_id=ev['id'],street=ev['street'],before={'undone':True},after={'undone':False})
            self._after(c)
            return dict(ev)

    def status(self, user: str = "") -> dict:
        """Where the project stands.

        Args:
            user: The editor asking (for the undo / redo flags).

        Returns:
            ``revision``, ``checkpoints``, ``last_saved`` / ``last_label`` / ``last_saved_by`` (latest checkpoint), ``last_edit``
            (``{"user", "ts", "action"}`` of the latest edit that is not undone), ``can_undo``, ``can_redo``.
        """
        with self.engine.connect() as c:
            mine = events_t.c.user == user
            can_undo = c.execute(sa.select(sa.func.count()).where(sa.and_(mine, events_t.c.undone.is_(False)))).scalar_one() > 0
            last = c.execute(sa.select(sa.func.coalesce(sa.func.max(events_t.c.id), 0)).where(sa.and_(mine, events_t.c.undone.is_(False)))).scalar_one()
            can_redo = c.execute(sa.select(sa.func.count()).where(sa.and_(mine, events_t.c.undone.is_(True), events_t.c.id > last,
                                       ~events_t.c.id.in_(sa.select(closed_redo_t.c.event_id))))).scalar_one() > 0
            cp = c.execute(sa.select(checkpoints_t).order_by(checkpoints_t.c.id.desc()).limit(1)).mappings().first()
            n = c.execute(sa.select(sa.func.count()).select_from(checkpoints_t)).scalar_one()
            le = c.execute(sa.select(events_t.c.user, events_t.c.ts, events_t.c.action).where(events_t.c.undone.is_(False))
                           .order_by(events_t.c.id.desc()).limit(1)).mappings().first()
            return {"revision": self.revision(c), "checkpoints": int(n), "last_saved": cp["ts"], "last_label": cp["label"], "last_saved_by": cp["user"],
                    "last_edit": dict(le) if le else None, "can_undo": can_undo, "can_redo": can_redo}

    # ---- checkpoints -----------------------------------------------------------------------------------------------------------------
    def save(self, label: str = "", user: str = "", streets: list[dict] | None = None) -> int:
        """Make a checkpoint of the current state (and of the computed street ids when given) and update ``street_ids``.

        Args:
            label: Short description.
            user: Author.
            streets: Computed street rows (ids, names, status) to store with the checkpoint, or None.

        Returns:
            The checkpoint id.
        """
        with self.engine.begin() as c:
            state = self._state(c)
            res = c.execute(checkpoints_t.insert().values(ts=_now(), label=label or "saved", user=user, revision=self.revision(c), state=json.dumps(state),
                                                          streets=json.dumps(streets) if streets is not None else None))
            if streets is not None:
                self._write_ids(c, streets)
            self._audit(c,'checkpoint','checkpoint_saved',user,details={'checkpoint':int(res.inserted_primary_key[0]),'label':label or 'saved'})
            return int(res.inserted_primary_key[0])

    def _write_ids(self, c, streets: list[dict]) -> None:
        """Rewrite the plain ``street_ids`` table.

        Args:
            c: Open connection (inside a transaction).
            streets: Computed street rows.
        """
        c.execute(street_ids_t.delete())
        if streets:
            c.execute(street_ids_t.insert(), [{"street_id": s["id"], "original_id": s["original"], "part": s["part"], "name": s.get("name"),
                                              "display_name": s.get("display"), "status": s["status"], "source": s.get("source"), "level": s.get("level"),
                                              "street_rank": s.get("rank"), "length_m": s.get("length"), "parent_id": s.get("parent"),
                                              "root_id": s.get("root"), "d_start": s.get("d0"), "d_end": s.get("d1")} for s in streets])

    def checkpoints(self) -> list[dict]:
        """All checkpoints, newest first.

        Returns:
            ``{"id", "ts", "label", "user", "named_streets", "has_ids"}`` per checkpoint.
        """
        with self.engine.connect() as c:
            rows = c.execute(sa.select(checkpoints_t.c.id, checkpoints_t.c.ts, checkpoints_t.c.label, checkpoints_t.c.user, checkpoints_t.c.state,
                                       checkpoints_t.c.streets).order_by(checkpoints_t.c.id.desc())).mappings().all()
        return [{"id": r["id"], "ts": r["ts"], "label": r["label"], "user": r["user"], "named_streets": len(json.loads(r["state"]).get("names", {})),
                 "has_ids": r["streets"] is not None} for r in rows]

    def restore(self, checkpoint_id: int, user: str = "", expected_revision: int | None = None, reason: str = '') -> int:
        """Go back to an older checkpoint: add a ``restore`` event (undoable) and a checkpoint with its content.

        Args:
            checkpoint_id: The checkpoint to return to.
            user: Author.

        Returns:
            The id of the new checkpoint.

        Raises:
            KeyError: If the checkpoint does not exist.
        """
        with self.engine.begin() as c:
            if expected_revision is not None and self.revision(c)!=expected_revision:
                raise Conflict('project changed; review the current revision before restoring')
            row = c.execute(sa.select(checkpoints_t).where(checkpoints_t.c.id == int(checkpoint_id))).mappings().first()
            if row is None:
                raise KeyError(checkpoint_id)
            self._add_event(c, "restore", None, self._state(c), json.loads(row["state"]), user)
            self._audit(c,'checkpoint_restore','restore',user,details={'checkpoint':checkpoint_id,'reason':reason})
            self._after(c)
            streets = json.loads(row["streets"]) if row["streets"] else None
            res = c.execute(checkpoints_t.insert().values(ts=_now(), label=f"restored #{row['id']} ({row['label']})", user=user, revision=self.revision(c),
                                                          state=row["state"], streets=row["streets"]))
            if streets is not None:
                self._write_ids(c, streets)
            return int(res.inserted_primary_key[0])

    def history(self, limit: int = 200) -> list[dict]:
        """Recent edits, newest first.

        Args:
            limit: Maximum number of rows.

        Returns:
            ``{"id", "ts", "user", "action", "street", "old", "new", "undone"}`` per edit (``restore`` events carry no payload here).
        """
        with self.engine.connect() as c:
            rows = c.execute(sa.select(events_t).order_by(events_t.c.id.desc()).limit(int(limit))).mappings().all()
        return [{"id": r["id"], "ts": r["ts"], "user": r["user"], "action": r["action"], "street": r["street"],
                 "old": None if r["action"] == "restore" or not r["old"] else json.loads(r["old"]),
                 "new": None if r["action"] in ("restore", "roads_import") or not r["new"] else json.loads(r["new"]), "undone": bool(r["undone"])} for r in rows]

    # ---- computed results ------------------------------------------------------------------------------------------------------------------
    def put_computed(self, key: str, value) -> None:
        """Store a computed result (latest only).

        Args:
            key: Name (``summary``, ``plan`` ...).
            value: JSON-serialisable value.
        """
        with self.engine.begin() as c:
            c.execute(computed_t.delete().where(computed_t.c.key == key))
            c.execute(computed_t.insert().values(key=key, value=json.dumps(value)))

    def get_computed(self, key: str, default=None):
        """Read a stored computed result.

        Args:
            key: Name.
            default: Value when missing.

        Returns:
            The stored value.
        """
        with self.engine.connect() as c:
            v = c.execute(sa.select(computed_t.c.value).where(computed_t.c.key == key)).scalar()
        return json.loads(v) if v is not None else default

    def checkpoint_streets(self, checkpoint_id: int) -> list[dict] | None:
        """The street ids and names stored with a checkpoint.

        Args:
            checkpoint_id: The checkpoint.

        Returns:
            The computed street rows, or None.
        """
        with self.engine.connect() as c:
            v = c.execute(sa.select(checkpoints_t.c.streets).where(checkpoints_t.c.id == int(checkpoint_id))).scalar()
        return json.loads(v) if v else None

    def backup(self, target: Path) -> Path:
        """Copy the database to a file (SQLite) - for PostgreSQL use ``pg_dump``.

        Args:
            target: Destination file.

        Returns:
            The path written.

        Raises:
            RuntimeError: When the database is not SQLite.
        """
        if self.engine.dialect.name != "sqlite":
            raise RuntimeError("backup of a server database: use pg_dump")
        import sqlite3

        src = sqlite3.connect(self.engine.url.database)
        dst = sqlite3.connect(str(target))
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        return Path(target)
