"""HTTP API and static front end of the community address app.

``create_app(project_folder)`` returns a FastAPI application. The project database is opened when the app starts
(nothing to load); when a reference node is already set the network is computed in the background so the map opens with
the current result. Computing never blocks the API: ``POST /api/compute`` starts a job and ``GET /api/job`` reports it.

Main endpoints (all JSON unless noted):

* ``GET /api/project`` - name, reference, settings, save status (pending edits, undo / redo), whether the computed
  result is stale, which input layers exist.
* ``GET /api/base/streets``, ``/api/layers/{area|points|buildings}`` - GeoJSON of the inputs.
* ``POST /api/reference`` ``{lat, lon}`` - snap to the nearest drivable node and set it as the reference.
* ``POST /api/names`` ``{street_id, name}``, ``POST /api/settings`` - edits .
* ``POST /api/undo`` / ``/api/redo`` / ``/api/discard``, ``POST /api/save`` ``{label, user}``,
  ``GET /api/checkpoints``, ``POST /api/restore`` ``{id}``, ``GET /api/history``.
* ``POST /api/compute``, ``GET /api/job``, ``GET /api/network`` - street ids, routes, names, plan.
* ``POST /api/addresses/compute``, ``GET /api/addresses`` - house numbers, addresses, street signs.
* ``GET /api/export/{addresses|streets|signs|names}.csv``.
"""

from __future__ import annotations

import base64
import csv
import io
import re
import json
import math
import uuid
import tempfile
import threading
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from pyproj import Transformer
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from ..branches import is_named
from . import engine, exports, roads as roads_mod
from .project import Project
from .store import Conflict, Store
from . import street_ops
from . import households as households_mod
from . import plate as plate_mod
from . import plaque, road_check, work_areas
from .identity import actor_id

def me() -> str:
    """Stable editor ID from the verified request session.

    Returns:
        The editor name.
    """
    return actor_id()


STATIC = Path(__file__).resolve().parent / "static"


class Context:
    """Everything the running app keeps in memory.

    Attributes:
        store: The project database.
        base: Base data (loaded lazily).
        network: The latest :class:`engine.NetworkState` or None.
        network_json: Its GeoJSON form for the map.
        network_hash: ``Project.state_hash`` the network was computed for.
        addresses: The latest :class:`engine.AddressState` or None.
        addresses_hash: Hash the addresses were computed for.
        job: Status of the background computation.
    """

    def __init__(self, root: Path, url: str | None = None):
        """Open the project.

        Args:
            root: Project folder.
            url: Database URL (default: SQLite file in the folder or ``ADDRESS_DB_URL``).
        """
        self.store = Store(root, url=url)
        self.root = Path(root)
        self.base: engine.BaseData | None = None
        self.network: engine.NetworkState | None = None
        self.network_json: dict | None = None
        self.network_hash: str | None = None
        self.addresses: engine.AddressState | None = None
        self.addresses_hash: str | None = None
        self.effective: tuple | None = None
        self.effective_hash: str | None = None
        self.effective_cache: dict[str, tuple] = {}
        self.lock = threading.Lock()
        self.effective_lock = threading.Lock()              # several map requests may need the same expensive replay at once
        self.job = {"state": "idle", "kind": None, "step": "", "error": None}

    def get_base(self) -> engine.BaseData:
        """The base data, loaded on first use.

        Returns:
            The :class:`engine.BaseData`.
        """
        if self.base is None:
            self.base = engine.load_base(self.store.project())
        return self.base

    def get_effective(self, proj: Project | None = None) -> tuple:
        """The network with the project's drawn roads added, cached until the roads change.

        Args:
            proj: The current project state (read from the store when omitted).

        Returns:
            ``(base, roads_result)`` from :func:`engine.effective_base`.
        """
        # /roads, /base/streets, /base/components and the compute worker can arrive together after one edit.  Without
        # this lock they all replay every historical geometry operation in parallel, turning a 10-20 s update into
        # several minutes and racing to replace the cache with the same result.
        with self.effective_lock:
            proj = proj or self.store.project()
            if proj.node_ids is None:
                # First opening since the drawn-road node ids became stable: record the ids they have now, which the saved
                # edits use, and continue with them.
                _base, res = engine.effective_base(self.get_base(), proj, write_cache=False)
                self.store.freeze_node_ids(res.report.get("node_ids", {}) if res is not None else {})
                proj.node_ids = self.store.project().node_ids
            h = proj.roads_hash()
            cached = self.effective_cache.get(h)
            if cached is None:
                cached = engine.effective_base(self.get_base(), proj)
                self.effective_cache[h] = cached
                # A compute worker may still hold the preceding project snapshot while the browser asks for the latest
                # one.  Retaining those two revisions prevents them from repeatedly evicting and rebuilding each other.
                while len(self.effective_cache) > 2:
                    self.effective_cache.pop(next(iter(self.effective_cache)))
            self.effective = cached
            self.effective_hash = h
            return self.effective

    @staticmethod
    def roads_report(proj: Project, result) -> dict:
        """Combine integration warnings with manual uncertainty marks on reshaped roads."""
        report = dict(result.report) if result is not None else {}
        uncertain = list(report.get("uncertain_ends", []))
        for ref, point in proj.roads.get("geometry_reviews", {}).items():
            uncertain.append({"key": f"geometry:{ref}", "ref": ref, "lon": float(point["lon"]),
                              "lat": float(point["lat"]), "source": "geometry_review"})
        if uncertain:
            report["uncertain_ends"] = uncertain
        sections = list(proj.roads.get("reviews", []))
        if sections:
            report["uncertain_sections"] = sections
        return report

    def run_job(self, kind: str, actor: str = 'system:startup') -> bool:
        """Start a background computation unless one is running.

        Args:
            kind: ``"network"`` or ``"addresses"``.

        Returns:
            True when a job was started.
        """
        with self.lock:
            if self.job["state"] == "running":
                return False
            self.job = {"state": "running", "kind": kind, "step": "starting", "error": None}
        self.store.record_audit('computation_requested',actor,kind='computation',computation=kind)
        threading.Thread(target=self._work, args=(kind,), daemon=True).start()
        return True

    def _work(self, kind: str) -> None:
        """Thread body of a computation.

        Args:
            kind: ``"network"`` or ``"addresses"``.
        """
        try:
            proj = self.store.project()
            base, rres = self.get_effective(proj)
            report = self.roads_report(proj, rres)
            if kind == "network":
                state = engine.compute_network(base, proj, progress=lambda s: self.job.update(step=s), roads_report=report,
                                               hint_extra=getattr(self.network, "extra", None), branch_ids=self.store.get_computed("branch_ids"))
                data = engine.network_geojson(state, proj)
                self.network, self.network_json, self.network_hash = state, data, proj.state_hash()
                self.store.put_computed("branch_ids", state.branch_ids)
                self.addresses = None
                self.store.put_computed("summary", {"stats": state.stats, "notes": state.notes, "hash": self.network_hash})
                self.store.put_computed("plan", data["plan"])
            else:
                if self.network is None or self.network_hash != proj.state_hash():
                    self.job.update(step="computing the network first")
                    state = engine.compute_network(base, proj, progress=lambda s: self.job.update(step=s), roads_report=report,
                                               hint_extra=getattr(self.network, "extra", None), branch_ids=self.store.get_computed("branch_ids"))
                    self.network, self.network_json, self.network_hash = state, engine.network_geojson(state, proj), proj.state_hash()
                    self.store.put_computed("branch_ids", state.branch_ids)
                self.job.update(step="addressing the houses")
                self.addresses = engine.compute_addresses(base, self.network, proj)
                self.addresses_hash = proj.address_hash()
            self.job = {"state": "done", "kind": kind, "step": "done", "error": None}
            self.store.record_audit('computation_finished','system:compute',kind='computation',computation=kind,input_hash=proj.state_hash() if kind=='network' else proj.address_hash())
        except Exception as exc:  # reported to the client, never crashes the server
            self.job = {"state": "error", "kind": kind, "step": "failed", "error": f"{exc}", "trace": traceback.format_exc(limit=4)}


def _fc(gdf: gpd.GeoDataFrame, keep: list[str]) -> dict:
    """GeoJSON FeatureCollection of selected columns.

    Args:
        gdf: GeoDataFrame in WGS84.
        keep: Property columns to include.

    Returns:
        The FeatureCollection.
    """
    feats = []
    for _, r in gdf.iterrows():
        if r.geometry is None or r.geometry.is_empty:
            continue
        props = {}
        for c in keep:
            v = r.get(c)
            props[c] = None if v is None or (isinstance(v, float) and v != v) else (v.item() if hasattr(v, "item") else v)
        feats.append({"type": "Feature", "properties": props, "geometry": shapely.geometry.mapping(shapely.set_precision(r.geometry, 1e-6))})
    return {"type": "FeatureCollection", "features": feats}


def _csv(rows: list[dict], columns: list[str]) -> Response:
    """CSV response.

    Args:
        rows: Row dicts.
        columns: Column order.

    Returns:
        A ``text/csv`` response.
    """
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8")


def apply_default_reference(ctx: "Context") -> None:
    """Set the project's default reference point (``input/default_reference.json``: ``{"name", "lat", "lon"}``) when no reference exists yet.

    The browser asks the editor to confirm or move it; areas without a default start with no reference.

    Args:
        ctx: The running app context.
    """
    path = ctx.root / "input" / "default_reference.json"
    if not path.exists() or ctx.store.project().reference:
        return
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        ref = engine.snap_reference(ctx.get_base(), float(d["lat"]), float(d["lon"]))
    except Exception:                                   # no network built yet or a bad file: the editor chooses
        return
    ctx.store.set_reference(ref["lat"], ref["lon"], ref["node"], "", by="default", name=d.get("name"), default=True)


def apply_default_roads(ctx: "Context") -> None:
    """Load ``input/missing_roads.kml`` (the new streets the project comes with) as the first file of the project, once.

    It appears in the list of added files (and in the colour-by-file view) like an uploaded file and can be removed; it is not loaded again
    after that.

    Args:
        ctx: The running app context.
    """
    path = ctx.root / "input" / "missing_roads.kml"
    if path.exists() and ctx.store.get_computed("default_roads") and not ctx.store.get_computed("default_roads_unnamed"):
        try:
            if not any(f.get("name") for f in roads_mod.features_from_lines(roads_mod.read_lines(path))):          # the file carries no names any more
                for imp in ctx.store.project().roads["imports"]:
                    if imp["file"] == path.name and any(f.get("name") for f in imp["features"]):
                        ctx.store.unname_roads(imp["id"], "")
        except Exception:
            pass
        ctx.store.put_computed("default_roads_unnamed", True)
        return
    if not path.exists() or ctx.store.get_computed("default_roads"):
        return
    try:
        feats = roads_mod.features_from_lines(roads_mod.read_lines(path))
    except Exception:                                    # not a readable file: the editors can still upload it by hand
        return
    ctx.store.import_roads(path.name, feats, "")
    ctx.store.put_computed("default_roads", True)


def apply_csv_names(ctx: "Context") -> None:
    """Move the street names of ``input/street_edits.csv`` into the project database, once.

    Names live in the database (one editable, deletable place) and win over the csv names. The csv files stay as they are: they still
    carry the id changes, and the edge file keeps naming the parts of a street that is cut, so the result does not change.

    Args:
        ctx: The running app context.
    """
    if ctx.store.get_computed("csv_names"):
        return
    names: dict[int, str] = {}
    files = [ctx.root / "input" / "street_edits.csv"]           # the edge-level names stay in their file: they name cut parts
    for path in files:
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str).fillna("")
        if "street_name" not in df.columns or "new_street_id" not in df.columns:
            continue
        for sid, name in zip(df["new_street_id"], df["street_name"]):
            if engine._given(name) and sid.strip().isdigit():
                names[int(sid)] = name.strip()
    have = ctx.store.project().names
    for sid, name in sorted(names.items()):
        if sid not in have:
            ctx.store.set_name(sid, name, "csv import")
    ctx.store.put_computed("csv_names", True)


def create_app(root: Path, auto_compute: bool = True, db_url: str | None = None, *, auth_enabled: bool = True) -> FastAPI:
    """Build the application for a project folder.

    Args:
        root: Project folder (created by ``python -m osmaddresssystem.app init``).
        auto_compute: Compute the network in the background at start when a reference node is set.
        db_url: Database URL (SQLite file in the folder by default, or ``ADDRESS_DB_URL``).

    Returns:
        The FastAPI app.
    """
    ctx = Context(Path(root), db_url)

    apply_default_reference(ctx)
    apply_default_roads(ctx)
    apply_csv_names(ctx)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Compute the current network in the background so the map opens with the latest result."""
        if auto_compute and ctx.store.project().reference:
            ctx.run_job("network")
        yield

    app = FastAPI(title="Community address app", lifespan=lifespan)
    app.state.ctx = ctx
    app.state.auth_enabled = auth_enabled
    if auth_enabled:
        from .auth import Accounts
        accounts=Accounts(ctx.store)
        app.state.accounts=accounts
        app.include_router(accounts.router())
        app.middleware('http')(accounts.protect)
    else:
        # Explicit in-process legacy test harness only; serve has no bypass flag.
        @app.get('/api/auth/status')
        def test_identity():
            return {'enabled':False,'user':None,'capabilities':[]}

    MAX_BODY = 60 * 1024 * 1024

    def code_version() -> str:
        """Time of the newest code file (UTC): shown in the page, so it is clear which version runs."""
        files = list(STATIC.glob("*")) + list(STATIC.parent.parent.glob("*.py")) + list(STATIC.parent.glob("*.py"))
        return time.strftime("%m-%d %H:%M", time.gmtime(max(f.stat().st_mtime for f in files)))

    VERSION = code_version()

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        """The page and its scripts are never taken from the browser cache without asking the server first."""
        resp = await call_next(request)
        path=request.scope.get('path','').removeprefix(request.scope.get('root_path',''))
        if not path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-cache"
        else:
            resp.headers['Cache-Control']='no-store'
        return resp

    @app.middleware("http")
    async def limit_uploads(request: Request, call_next):
        """Refuse requests bigger than 60 MB (a roads file is a few hundred KB)."""
        if int(request.headers.get("content-length") or 0) > MAX_BODY:
            return JSONResponse({"detail": "file too large (60 MB at most)"}, status_code=413)
        return await call_next(request)

    @app.get("/api/health")
    def get_health() -> dict:
        """Liveness / readiness for the host: the database answers, the revision, whether a computation runs."""
        try:
            rev = ctx.store.revision()
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=503)
        return {"ok": True, "database": ctx.store.engine.dialect.name, "revision": rev, "job": ctx.job["state"], "computed": ctx.network_json is not None, "version": VERSION}

    @app.get("/api/revision")
    def get_revision() -> dict:
        """Cheap change counter polled by the browsers (status of this editor plus whether the computed network is current)."""
        st = ctx.store.status(me())
        return {"status": st, "user": me(), "fresh": ctx.network_json is not None and ctx.network_hash == ctx.store.project().state_hash(),
                "network_hash": ctx.network_hash, "job": ctx.job}

    def streets_rows() -> list[dict] | None:
        """Computed street rows for a checkpoint, when the result is fresh.

        Returns:
            The rows (``properties`` of the street features) or None.
        """
        if ctx.network_json is None or ctx.network_hash != ctx.store.project().state_hash():
            return None
        return [f["properties"] for f in ctx.network_json["streets"]["features"]]

    @app.get("/api/project")
    def get_project() -> dict:
        """Project state and save status."""
        p = ctx.store.project()
        h = p.state_hash()
        base = None
        try:
            base = ctx.get_base()
        except FileNotFoundError:
            pass
        return {"name": p.name, "reference": p.reference, "settings": p.settings.__dict__, "names": {str(k): v for k, v in p.names.items()},
                "version": VERSION, "status": ctx.store.status(me()), "user": me(), "names_meta": {str(k): {"user": v["user"], "ts": v["ts"]} for k, v in ctx.store.names_meta().items()},
                "network_hash": ctx.network_hash, "network_ready": ctx.network_json is not None,
                "stale": ctx.network_json is not None and ctx.network_hash != h,
                "addresses_ready": ctx.addresses is not None, "addresses_stale": ctx.addresses is not None and ctx.addresses_hash != p.address_hash(),
                "roads": {"imports": [{"id": i["id"], "file": i["file"], "lines": len(i["features"])} for i in p.roads["imports"]],
                          "connections": len(p.roads["connections"])},
                "access": len(p.access), "work_areas": p.work_areas,
                "has": {"network": base is not None, "area": bool(base and base.area is not None), "points": bool(base and base.points is not None),
                        "buildings": bool(base and base.buildings is not None)}}

    @app.get("/api/base/nodes")
    def base_nodes() -> list:
        """Nodes of drivable streets as ``[id, lon, lat]`` - the places the reference point can be (shown while it is moved)."""
        base = ctx.get_base()
        drv = base.edges["is_drivable"].astype(str).str.lower().isin(["true", "1"]) if "is_drivable" in base.edges else None
        e = base.edges[drv] if drv is not None else base.edges
        ids = set(e.index.get_level_values("u")) | set(e.index.get_level_values("v"))
        n = base.nodes[base.nodes.index.isin(ids)]
        lon, lat = Transformer.from_crs(base.crs, 4326, always_xy=True).transform(n["x"].to_numpy(), n["y"].to_numpy())
        return [[int(i), round(float(a), 7), round(float(b), 7)] for i, a, b in zip(n.index, lon, lat)]

    @app.get("/api/base/streets")
    def base_streets() -> dict:
        """The street lines of the base network (to choose the reference on)."""
        base, _res = ctx.get_effective()    # the network with the deleted edges removed and the drawn roads added
        e = base.edges.reset_index()
        e = e[e["u"] < e["v"]]
        e = e.assign(file=[(re.match(r"road(\d+):", str(o)) or [None, None])[1] for o in e["osmid"]])            # the file a road comes from (None: the downloaded network)
        g = gpd.GeoDataFrame(e[["street_id", "street_name", "highway", "file", "geometry"]], crs=base.crs).to_crs(4326)
        aoi = engine.aoi_polygon(base)
        if aoi is not None:                                         # only the streets inside the area of interest
            g = g[g.intersects(aoi)].copy()                         # whole edges that touch the area, never cropped
        return _fc(g, ["street_id", "street_name", "highway", "file"])

    @app.get("/api/base/components")
    def base_components() -> dict:
        """The parts of the network that are cut off from the main part (inside the area): their edges and a summary."""
        base, _res = ctx.get_effective()
        parts = engine.disconnected_parts(base)
        rows = []
        for p in parts:
            sub = base.edges.loc[p["edges"]].reset_index()
            sub = sub.assign(part=p["id"])
            rows.append(sub[["part", "street_id", "geometry"]])
        feats = {"type": "FeatureCollection", "features": []}
        if rows:
            g = gpd.GeoDataFrame(pd.concat(rows), crs=base.crs).to_crs(4326)
            feats = _fc(g, ["part", "street_id"])
        return {"parts": [{"id": p["id"], "streets": p["street_ids"], "edges": len(p["edges"]), "length_m": round(p["length_m"])} for p in parts], "edges": feats}

    @app.post("/api/base/components/delete")
    def post_components_delete(body: dict = Body(...)) -> dict:
        """Delete a whole separate part of the network (one of the parts flagged as not connected; never the main network): one undo step."""
        base, _res = ctx.get_effective()
        parts = {p["id"]: p for p in engine.disconnected_parts(base)}
        part = parts.get(int(body["part"]))
        if part is None:
            raise HTTPException(404, "that part is not a separate part of the network (the main network cannot be deleted)")
        edges, feats = [], []
        for (u, v, k) in part["edges"]:
            osmid = str(base.edges.loc[(u, v, k), "osmid"])
            if osmid.startswith("road"):
                feats.append(osmid[4:])
            else:
                edges.append(roads_mod.edge_ref(u, v, k))
        ctx.store.remove_edges(sorted(set(edges)), sorted(set(feats)), me())
        return {"edges": len(edges), "features": len(set(feats)), "status": ctx.store.status(me())}

    @app.get("/api/base/outside")
    def base_outside() -> dict:
        """The larger road network: the roads that do not touch the area of interest (shown light grey; they carry the routes to the reference points outside)."""
        base, _res = ctx.get_effective()
        aoi = engine.aoi_polygon(base)
        e = base.edges.reset_index()
        e = e[(e["u"] < e["v"]) & (e["key"] < roads_mod.SYNTHETIC_KEY)]
        g = gpd.GeoDataFrame(e[["street_id", "highway", "geometry"]], crs=base.crs).to_crs(4326)
        if aoi is not None:
            g = g[~g.intersects(aoi)].copy()
        g["geometry"] = g.geometry.simplify(0.00001)
        return _fc(g, ["street_id", "highway"])

    @app.get("/api/layers/{name}")
    def layer(name: str) -> dict:
        """GeoJSON of an input layer: ``area``, ``points`` or ``buildings``."""
        base = ctx.get_base()
        gdf = {"area": base.area, "points": base.points, "buildings": base.buildings}.get(name)
        if gdf is None:
            raise HTTPException(404, f"no {name} layer in this project")
        if name == "area" and "kind" in gdf.columns and gdf["kind"].astype(str).str.contains("aoi", case=False).any():
            gdf = gdf[gdf["kind"].astype(str).str.contains("aoi", case=False)]                 # only the boundary around the buildings
        return _fc(gdf, [c for c in gdf.columns if c != "geometry"][:8])

    @app.post("/api/reference")
    def post_reference(body: dict = Body(...)) -> dict:
        """Choose the reference node by clicking near it (``client`` = the anonymous id of the browser)."""
        ref = engine.snap_reference(ctx.get_base(), float(body["lat"]), float(body["lon"]))
        ctx.store.set_reference(ref["lat"], ref["lon"], ref["node"], me(), by=str(body.get("client") or "anonymous"))
        return {"reference": ref, "status": ctx.store.status(me())}

    @app.post("/api/reference/confirm")
    def post_reference_confirm(body: dict = Body(default={})) -> dict:
        """Confirm the current reference point (the default one, or one set by another editor): it is saved again under this browser."""
        cur = ctx.store.project().reference
        if not cur:
            raise HTTPException(409, "no reference point yet")
        if auth_enabled:
            # Acknowledging the origin is local UI state, not permission to
            # rewrite a shared reference or create an undoable geometry edit.
            return {'reference':cur,'status':ctx.store.status(me())}
        ctx.store.set_reference(cur["lat"], cur["lon"], cur["node"], me(), by=str(body.get("client") or "anonymous"), name=cur.get("name"))
        return {"reference": ctx.store.project().reference, "status": ctx.store.status(me())}

    @app.post("/api/names")
    def post_name(body: dict = Body(...)) -> dict:
        """Give or remove a street name ."""
        try:
            changed = ctx.store.set_name(int(body["street_id"]), body.get("name"), me(), body.get("expected", "__unset__"))
        except Conflict as e:
            raise HTTPException(409, {"message": str(e), "current": e.current, "by": e.by})
        return {"changed": changed, "status": ctx.store.status(me())}

    @app.post("/api/access/snap")
    def post_access_snap(body: dict = Body(...)) -> dict:
        """Snap a click to the nearest road point (used to choose the road point of a house); nothing is stored yet."""
        if ctx.network is None:
            raise HTTPException(409, "compute the network first")
        snapped = engine.snap_to_street(ctx.network, float(body["lat"]), float(body["lon"]))
        if snapped is None:
            raise HTTPException(404, "no street within 60 m of that point")
        return snapped

    @app.post("/api/access")
    def post_access(body: dict = Body(...)) -> dict:
        """Use a chosen road point for the numbering of a house, or go back to the automatic point (``clear: true``)."""
        if body.get("clear"):
            changed = ctx.store.clear_access(str(body["building_id"]), me())
        else:
            ctx.store.set_access(str(body["building_id"]), float(body["lat"]), float(body["lon"]), me())
            changed = True
        return {"changed": changed, "status": ctx.store.status(me())}

    @app.get("/api/roads")
    def get_roads() -> dict:
        """The drawn (missing) roads as they are connected now: lines, nodes with their state and suggestions."""
        p = ctx.store.project()
        base, res = ctx.get_effective(p)
        report = ctx.roads_report(p, res)
        if res is None:
            reviews = [{"type": "Feature", "properties": {k: v for k, v in review.items() if k != "geometry"}, "geometry": review["geometry"]}
                       for review in p.roads.get("reviews", [])]
            return {"imports": [{"id": i["id"], "file": i["file"], "lines": len(i["features"])} for i in p.roads["imports"]], "edges": {"type": "FeatureCollection", "features": []}, "nodes": {"type": "FeatureCollection", "features": []},
                    "reviews": {"type": "FeatureCollection", "features": reviews}, "report": report}
        feats = [{"type": "Feature", "properties": {"street_id": int(r["street_id"]), "feature": r["feature"], "name": r["name"],
                                                     "u_state": r["u_state"], "v_state": r["v_state"]},
                  "geometry": shapely.geometry.mapping(shapely.set_precision(r.geometry, 1e-6))} for _, r in res.new_edges.iterrows()]
        nodes = [{"type": "Feature", "properties": {k: v for k, v in n.items() if k not in ("lat", "lon")},
                  "geometry": {"type": "Point", "coordinates": [n["lon"], n["lat"]]}} for n in res.report["nodes"]]
        rep = {k: v for k, v in report.items() if k != "nodes"}
        reviews = [{"type": "Feature", "properties": {k: v for k, v in review.items() if k != "geometry"}, "geometry": review["geometry"]}
                   for review in p.roads.get("reviews", [])]
        return {"imports": [{"id": i["id"], "file": i["file"], "lines": len(i["features"])} for i in p.roads["imports"]],
                "edges": {"type": "FeatureCollection", "features": feats}, "nodes": {"type": "FeatureCollection", "features": nodes},
                "reviews": {"type": "FeatureCollection", "features": reviews}, "report": rep}

    def read_features(body: dict) -> tuple[str, list[dict]]:
        """The drawn lines of a request: the uploaded file, or the lines the browser already holds.

        Args:
            body: ``{"filename", "content_b64"}`` or ``{"filename", "features"}``.

        Returns:
            ``(file name, features)``.
        """
        name = Path(str(body.get("filename") or "roads")).name
        if body.get("features"):
            return name, body["features"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_bytes(base64.b64decode(body["content_b64"]))
            try:
                gdf = roads_mod.read_lines(path if path.suffix.lower() != ".zip" else f"zip://{path}")
            except Exception as exc:
                raise HTTPException(400, f"cannot read the roads from {name}: {exc}")
        return name, roads_mod.features_from_lines(gdf)

    def free_street_id() -> int:
        """The lowest street id above every id of the current network (and of the community edge edits)."""
        base, _res = ctx.get_effective()
        top = [int(pd.to_numeric(base.streets["street_id"]).max())]
        if base.edge_edits:
            ee = pd.read_csv(base.edge_edits, dtype=str)
            if "new_street_id" in ee and len(ee):
                top.append(int(pd.to_numeric(ee["new_street_id"], errors="coerce").max() or 0))
        return max(top) + 1

    @app.post("/api/roads/preview")
    def post_roads_preview(body: dict = Body(...)) -> dict:
        """Show how an uploaded roads file would be merged, without changing the project.

        Body: ``{"filename", "content_b64"}`` (first call) or ``{"filename", "features"}``, plus the staged ``connections`` (node key -> target)
        and ``keep`` (existing road references that must stay). The new roads win over duplicates (same end nodes, length within 10 %).

        Returns:
            ``features`` (to send back), ``edges`` (new roads), ``nodes`` (their nodes with the state), ``replaced`` (existing roads the
            new roads replace) and a ``summary``.
        """
        name, feats = read_features(body)
        p = ctx.store.project()
        staged = {"id": "p", "file": name, "features": feats}
        if p.replay is not None:                       # applied after the edits so far, as it will be once saved
            p.replay = {**p.replay, "ops": [*p.replay["ops"], {"id": 0, "action": "roads_import",
                                                                "new": {**staged, "connections": body.get("connections") or {}, "keep": body.get("keep") or []}}],
                        "signature": None}
        p.roads = {**p.roads, "imports": [*p.roads["imports"], staged], "connections": {**p.roads["connections"], **(body.get("connections") or {})},
                   "keep": sorted(set(p.roads.get("keep", [])) | set(body.get("keep") or []))}
        _base, res = engine.effective_base(ctx.get_base(), p, write_cache=False)
        rep = res.report
        mine = lambda keys: any(k.startswith("p:") for k in keys)  # noqa: E731
        new_edges = [{"type": "Feature", "properties": {"feature": r["feature"].split(":", 1)[1], "name": r["name"], "street_id": int(r["street_id"]),
                                                          "u_state": r["u_state"], "v_state": r["v_state"]},
                      "geometry": shapely.geometry.mapping(shapely.set_precision(r.geometry, 1e-6))}
                     for _, r in res.new_edges.iterrows() if r["feature"].startswith("p:")]
        nodes = [{"type": "Feature", "properties": {k: v for k, v in n.items() if k not in ("lat", "lon")},
                  "geometry": {"type": "Point", "coordinates": [n["lon"], n["lat"]]}} for n in rep["nodes"] if mine(n["features"])]
        replaced = [{"type": "Feature", "properties": {k: v for k, v in r.items() if k != "geometry"}, "geometry": r["geometry"]}
                    for r in rep.get("replaced", []) if r["feature"].startswith("p:")]
        mine_dangling = {n["properties"]["key"] for n in nodes if n["properties"]["key"] in set(rep["dangling"])}
        summary = {"lines": len(feats), "connected": sum(1 for n in nodes if n["properties"]["state"] == "connected"),
                   "auto": sum(1 for n in nodes if n["properties"]["state"] == "connected" and not n["properties"].get("manual")),
                   "not_connected": len(mine_dangling), "replaced": sum(len(r["properties"]["removed"]) for r in replaced),
                   "isolated": sum(1 for f in rep["isolated"] if f.startswith("p:")), "split_edges": rep["split_edges"]}
        return {"filename": name, "features": feats, "edges": {"type": "FeatureCollection", "features": new_edges},
                "nodes": {"type": "FeatureCollection", "features": nodes}, "replaced": {"type": "FeatureCollection", "features": replaced},
                "dangling": sorted(mine_dangling), "summary": summary}

    @app.post("/api/roads/import")
    def post_roads_import(body: dict = Body(...)) -> dict:
        """Add the previewed roads to the project: ``{"filename", "features" | "content_b64", "connections", "keep"}``."""
        name, feats = read_features(body)
        iid = ctx.store.import_roads(name, feats, me(), body.get("connections") or {}, body.get("keep") or [], first_street_id=free_street_id())
        return {"id": iid, "lines": len(feats), "status": ctx.store.status(me())}

    @app.post("/api/roads/snap")
    def post_roads_snap(body: dict = Body(...)) -> dict:
        """Turn a click into a connection target (an existing node, else a point of an existing road) without storing anything.

        Body: ``{"lat", "lon"}`` and optionally ``max_m`` (largest distance to a road, default 60) and ``node_m`` (a node this close wins, default 10).
        """
        _b, res = ctx.get_effective()
        base = _b
        used = set(base.edges.index.get_level_values("u")) | set(base.edges.index.get_level_values("v"))      # nodes of deleted roads are not targets
        target = roads_mod.snap_click(base.nodes[base.nodes.index.isin(used)], base.edges, float(body["lat"]), float(body["lon"]), float(body.get("node_m", 10.0)), float(body.get("max_m", 60.0)))
        if target is None:
            raise HTTPException(404, "no road or node near that point")
        return {"target": target}

    @app.get("/api/base/ends")
    def base_ends() -> list:
        """Dead ends of the road network (nodes where only one road ends) as ``[node, lon, lat, street id]`` - the roads that can be prolonged."""
        base, _res = ctx.get_effective()
        e = base.edges.reset_index()
        e = e[(e["key"] < roads_mod.SYNTHETIC_KEY) & (e["u"] < e["v"])]
        deg: dict = {}
        street: dict = {}
        for u, v, sid in zip(e["u"], e["v"], e["street_id"]):
            for n in (u, v):
                deg[int(n)] = deg.get(int(n), 0) + 1
                street[int(n)] = None if pd.isna(sid) else int(sid)
        ends = [n for n, d in deg.items() if d == 1 and n in base.nodes.index]
        aoi = engine.aoi_polygon(base)
        pts = base.nodes.loc[ends].to_crs(4326) if ends else base.nodes.iloc[:0].to_crs(4326)
        out = []
        for n, g in zip(ends, pts.geometry):
            if aoi is None or aoi.buffer(0.001).contains(g):
                out.append([n, round(g.x, 7), round(g.y, 7), street[n]])
        return out

    @app.post("/api/roads/draw")
    def post_roads_draw(body: dict = Body(...)) -> dict:
        """Add roads drawn by hand (one undo step): ``{"pieces": [{"coords": [[lon, lat], ...], "start", "end"}], "name", "highway", "join"}``.

        ``start`` / ``end`` are the snap targets (node or road point) of a piece's ends, or null; ``join`` is the street id the road continues.
        """
        pieces = body.get("pieces") or [{"coords": body.get("coords"), "start": body.get("start"), "end": body.get("end")}]
        feats = []
        for i, pc in enumerate(pieces):
            coords = pc.get("coords") or []
            if len(coords) < 2:
                raise HTTPException(400, "a road needs at least two points")
            f = {"id": i, "coords": [[round(float(x), 7), round(float(y), 7)] for x, y in coords], "name": (body.get("name") or None),
                 "highway": body.get("highway") or None}
            if body.get('end_review') == 'uncertain' and i == len(pieces)-1:
                f['end_review'] = 'uncertain'
                f['end'] = {'type': 'none'}
            for k, v in (("start", pc.get("start")), ("end", pc.get("end")), ("join", body.get("join")), ("rank", body.get("rank"))):
                if v is not None:
                    f[k] = v
            if f.get('end_review') == 'uncertain':
                f['end'] = {'type': 'none'}
            for k in ("drivable", "paved"):
                if k in body:
                    f[k] = None if body[k] is None else bool(body[k])           # null = unknown
            feats.append(f)
        iid = ctx.store.import_roads("drawn by hand", feats, me(), {}, [], first_street_id=free_street_id())
        # Return the saved trace itself.  The browser can display it immediately while the effective graph and street ids
        # are rebuilt in the background; seeing a saved line must never depend on a full recomputation.
        edges = [{"type": "Feature", "properties": {"feature": f"{iid}:{f['id']}", "name": f.get("name"),
                                                        "street_id": f.get("join")},
                  "geometry": {"type": "LineString", "coordinates": f["coords"]}} for f in feats]
        return {"id": iid, "status": ctx.store.status(me()), "edges": {"type": "FeatureCollection", "features": edges}}

    @app.get("/api/edges")
    def get_edges() -> dict:
        """Every street edge that can be deleted (network edges and drawn lines) and the deleted ones, as GeoJSON for the delete tool."""
        p = ctx.store.project()
        base = ctx.get_base()
        und = base.edges[[u < v for u, v, _ in base.edges.index]]
        und = und[[k < roads_mod.SYNTHETIC_KEY for _, _, k in und.index]].to_crs(4326)
        aoi = engine.aoi_polygon(base)
        if aoi is not None:
            und = und[und.intersects(aoi)]
        und_all = base.edges[[u < v for u, v, _ in base.edges.index]]
        und_all = und_all[[k < roads_mod.SYNTHETIC_KEY for _, _, k in und_all.index]].to_crs(4326)
        outside = []
        if aoi is not None:                                                     # the larger network can be edited too (a road that goes out of the area)
            for (u, v, k), r in zip(und_all.index, und_all.itertuples()):
                if not r.geometry.intersects(aoi):
                    outside.append({"type": "Feature", "properties": {"ref": roads_mod.edge_ref(u, v, k), "street_id": None if r.street_id != r.street_id else int(r.street_id),
                                                                       "name": "", "highway": r.highway, "length": round(float(r.length), 1)},
                                    "geometry": shapely.geometry.mapping(shapely.set_precision(r.geometry, 1e-6))})
        gone = set(p.roads.get("removed", []))
        live, dead = [], []
        for (u, v, k), r in zip(und.index, und.itertuples()):
            ref = roads_mod.edge_ref(u, v, k)
            nm = r.street_name if isinstance(r.street_name, str) and r.street_name else (r.name if isinstance(r.name, str) else "")
            f = {"type": "Feature", "properties": {"ref": ref, "street_id": None if r.street_id != r.street_id else int(r.street_id), "name": nm,
                                                    "highway": r.highway, "length": round(float(r.length), 1)},
                 "geometry": shapely.geometry.mapping(shapely.set_precision(r.geometry, 1e-6))}
            (dead if ref in gone else live).append(f)
        removed_feats = set(p.roads.get("removed_features", []))
        drawn = []
        for imp in p.roads["imports"]:
            for f in imp["features"]:
                key = f"{imp['id']}:{f['id']}"
                drawn.append({"type": "Feature", "properties": {"ref": key, "file": imp["file"], "name": f.get("name"), "removed": key in removed_feats},
                              "geometry": {"type": "LineString", "coordinates": f["coords"]}})
        fc = lambda x: {"type": "FeatureCollection", "features": x}  # noqa: E731
        return {"edges": fc(live), "removed": fc(dead), "drawn": fc(drawn), "outside": fc(outside)}

    @app.get("/api/roads/geometry")
    def get_road_geometry() -> dict:
        """Current editable edge shapes, retaining IDs and fixed junctions."""
        revision = ctx.store.revision()
        base, _ = ctx.get_effective()
        e = base.edges
        degrees = {}
        for u,v,k in e.index:
            if k >= roads_mod.SYNTHETIC_KEY: continue
            for n in (u,v): degrees.setdefault(int(n),set()).add(roads_mod.edge_ref(u,v,k))
        e = e[[u < v and k < roads_mod.SYNTHETIC_KEY for u, v, k in e.index]].to_crs(4326)
        aoi = engine.aoi_polygon(base)
        if aoi is not None:
            e = e[e.intersects(aoi)]
        features = []
        for (u, v, k), row in e.iterrows():
            if row.geometry.geom_type != "LineString":
                continue
            features.append({"type": "Feature", "properties": {"ref": roads_mod.edge_ref(u, v, k),
                            "street_id": None if pd.isna(row.street_id) else int(row.street_id),
                            "u":int(u), "v":int(v), "degree_u":len(degrees.get(int(u),())), "degree_v":len(degrees.get(int(v),())),
                            "drawn":str(row.osmid).startswith('road'), "length_m":round(float(row['length']),2)},
                             "geometry": shapely.geometry.mapping(row.geometry)})
        return {"revision": revision, "edges": {"type": "FeatureCollection", "features": features}}

    @app.post("/api/roads/geometry")
    def post_road_geometry(body: dict = Body(...)) -> dict:
        """Save a shape correction without replacing roads or moving junctions."""
        try:
            revision = int(body["revision"])
            ref = str(body["ref"])
            coords = [[float(x), float(y)] for x, y in body["coords"]]
            if not 2 <= len(coords) <= 5000 or any(not math.isfinite(x) or not math.isfinite(y) or abs(x) > 180 or abs(y) > 90 for x, y in coords):
                raise ValueError("invalid coordinates")
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, "provide a road reference, revision and 2-5000 valid lon/lat points")
        if ctx.store.revision() != revision:
            raise HTTPException(409, "project changed; reload the road before saving")
        base, _ = ctx.get_effective()
        matches = [(idx, row) for idx, row in base.edges.iterrows()
                   if idx[0] < idx[1] and idx[2] < roads_mod.SYNTHETIC_KEY and roads_mod.edge_ref(*idx) == ref]
        if not matches:
            raise HTTPException(404, "road is no longer available; reload the map")
        idx, row = matches[0]
        line = shapely.geometry.LineString(coords)
        line = gpd.GeoSeries([line], crs=4326).to_crs(base.crs).iloc[0]
        original = list(row.geometry.coords)
        pts = list(line.coords)
        if any(shapely.geometry.Point(a).distance(shapely.geometry.Point(b)) > 1 for a, b in [(pts[0], original[0]), (pts[-1], original[-1])]):
            raise HTTPException(400, "junction endpoints must stay fixed; reshape the points between them")
        pts[0], pts[-1] = original[0], original[-1]
        line = shapely.geometry.LineString(pts)
        if line.length < 0.5 or not line.is_simple:
            raise HTTPException(400, "road must be at least 0.5 m long and must not cross itself")
        coords = list(map(list, gpd.GeoSeries([line], crs=base.crs).to_crs(4326).iloc[0].coords))
        try:
            ctx.store.set_road_geometry(ref, coords, revision, me())
        except Conflict:
            raise HTTPException(409, "project changed; reload the road before saving")
        return {"status": ctx.store.status(me())}

    def partial_geometry_selection(body: dict):
        """Resolve two clicks to ordered points on one current road section."""
        try:
            ref = str(body["ref"])
            points = [[float(x), float(y)] for x, y in body["points"]]
            if len(points) != 2 or any(not math.isfinite(x) or not math.isfinite(y) or abs(x) > 180 or abs(y) > 90 for x, y in points):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, "choose two valid anchor points on the same road section")
        base, _ = ctx.get_effective()
        idx = next((idx for idx in base.edges.index if idx[0] < idx[1] and idx[2] < roads_mod.SYNTHETIC_KEY
                    and roads_mod.edge_ref(*idx) == ref), None)
        if idx is None:
            raise HTTPException(404, "road section changed; select it again")
        geom = base.edges.loc[idx].geometry
        transform = Transformer.from_crs(4326, base.crs, always_xy=True)
        clicks = [shapely.geometry.Point(*transform.transform(*point)) for point in points]
        # B may be on a following section of the same road: the section nearest to it (the selected one when about as near).
        clicks.sort(key=geom.distance)
        far = clicks[1]
        if far.distance(geom) > 2:
            real = [(i, g) for i, g in zip(base.edges.index, base.edges.geometry) if i[0] < i[1] and i[2] < roads_mod.SYNTHETIC_KEY]
            near_idx, near_geom = min(real, key=lambda pair: pair[1].distance(far))
            if near_idx != idx and near_geom.distance(far) + 1 < far.distance(geom):
                if far.distance(near_geom) > 25 or clicks[0].distance(geom) > 25:
                    raise HTTPException(400, "choose anchor points closer to the road")
                stretch = stretch_selection(ref, base, idx, geom, clicks[0], near_idx, near_geom, far)
                if stretch is not None:
                    return stretch
                # An intentionally off-line anchor can be nearer to an unrelated road.  In that case the
                # unrelated road must not hijack the selection: keep resolving both anchors against the road
                # the user selected below.
        if any(point.distance(geom) > 25 for point in clicks):
            raise HTTPException(400, "choose anchor points closer to the selected road")
        clicks.sort(key=geom.project)
        start_m, end_m = (geom.project(point) for point in clicks)
        if end_m - start_m < 2:
            raise HTTPException(400, "choose anchor points at least 2 metres apart")
        from shapely.ops import substring
        selected = substring(geom, start_m, end_m)
        # An anchor clicked more than 2 m off the old line stays exactly where it was clicked. Inside the section the new trace
        # rejoins the old line straight from there; at an end of the section that node (junction or dead end) moves to it.
        anchors = [click if click.distance(geom) > 2 else geom.interpolate(m) for click, m in zip(clicks, (start_m, end_m))]
        wgs = gpd.GeoSeries([*anchors, selected], crs=base.crs).to_crs(4326)
        return ref, geom, start_m, end_m, anchors, wgs, base, idx

    def stretch_selection(ref, base, idx_a, geom_a, click_a, idx_b, geom_b, click_b):
        """Resolve A and B across connected sections, or return ``None`` when the nearer section is unrelated."""
        import networkx as nx
        from shapely.ops import substring
        street_a = base.edges.loc[idx_a, "street_id"]
        street_b = base.edges.loc[idx_b, "street_id"]
        if pd.isna(street_a) or pd.isna(street_b) or int(street_a) != int(street_b):
            return None
        graph = nx.Graph()
        for i, g in zip(base.edges.index, base.edges.geometry):
            same_street = not pd.isna(base.edges.loc[i, "street_id"]) and int(base.edges.loc[i, "street_id"]) == int(street_a)
            if i[0] < i[1] and i[2] < roads_mod.SYNTHETIC_KEY and i not in (idx_a, idx_b) and same_street:
                if not graph.has_edge(i[0], i[1]) or graph[i[0]][i[1]]["w"] > g.length:
                    graph.add_edge(i[0], i[1], w=g.length, idx=i)
        ma, mb = geom_a.project(click_a), geom_b.project(click_b)
        best = None
        for na, la in ((idx_a[0], ma), (idx_a[1], geom_a.length - ma)):
            for nb, lb in ((idx_b[0], mb), (idx_b[1], geom_b.length - mb)):
                if na == nb:
                    lp, path = 0.0, [na]
                else:
                    try:
                        lp, path = nx.single_source_dijkstra(graph, na, nb, weight="w")
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        continue
                if best is None or la + lp + lb < best[0]:
                    best = (la + lp + lb, na, nb, path)
        if best is None or best[0] > 3000 or len(best[3]) > 40:
            return None
        _, na, nb, path = best

        def coords(line):
            return list(line.coords)
        part_a = coords(substring(geom_a, ma, geom_a.length)) if na == idx_a[1] else coords(substring(geom_a, 0, ma))[::-1]
        part_b = coords(substring(geom_b, 0, mb)) if nb == idx_b[0] else coords(substring(geom_b, mb, geom_b.length))[::-1]   # node nb to B
        middle = []
        for p, q in zip(path, path[1:]):
            i = graph[p][q]["idx"]
            c = coords(base.edges.loc[i].geometry)
            middle.append((i, c if i[0] == p else c[::-1]))
        old = part_a + [pt for _, c in middle for pt in c[1:]] + part_b[1:]
        old_line = shapely.geometry.LineString(dedupe(old))
        def anchor(click, g, m):                                       # more than 2 m off the old line: where it was clicked
            return click if click.distance(g) > 2 else g.interpolate(m)
        anchors = [anchor(click_a, geom_a, ma), anchor(click_b, geom_b, mb)]
        wgs = gpd.GeoSeries([*anchors, old_line], crs=base.crs).to_crs(4326)
        stretch = {"idx_a": idx_a, "idx_b": idx_b, "ma": ma, "mb": mb, "na": na, "nb": nb, "path": path, "middle": middle,
                   "part_a": part_a, "part_b": part_b, "old": old_line}
        return ref, geom_a, 0.0, old_line.length, anchors, wgs, base, stretch

    def dedupe(points):
        out = []
        for p in points:
            if not out or shapely.geometry.Point(p).distance(shapely.geometry.Point(out[-1])) > 1e-6:
                out.append(tuple(p))
        return out

    def save_stretch(stretch, anchors, coords, base, revision, end_review):
        """Cut the new trace at the nodes between the sections, move those nodes onto it and reshape every section."""
        from shapely.ops import substring
        trace = shapely.geometry.LineString(dedupe(coords))
        length = trace.length
        old, path = stretch["old"], stretch["path"]
        old_d = [old.project(shapely.geometry.Point(base.nodes.geometry.loc[n].coords[0])) for n in path]
        at = [trace.project(base.nodes.geometry.loc[n]) for n in path]
        if any(b - a < .5 for a, b in zip([0.0] + at, at + [length])):
            at = [d / old.length * length for d in old_d]               # a winding trace: share it out in proportion
        def run(points):
            return sum(math.dist(p, q) for p, q in zip(points, points[1:]))
        if run(stretch["part_a"]) < .5:
            at[0] = 0.0                                                # A was on the node itself
        if run(stretch["part_b"]) < .5:
            at[-1] = length
        def seg(a, b):
            return list(substring(trace, a, b).coords) if b - a > 1e-6 else [tuple(trace.interpolate(a).coords[0])]
        geom_a, geom_b = base.edges.loc[stretch["idx_a"]].geometry, base.edges.loc[stretch["idx_b"]].geometry
        ia, ib, ma, mb = stretch["idx_a"], stretch["idx_b"], stretch["ma"], stretch["mb"]
        shapes, ends_moved = {}, {}
        # An off-line anchor at the far end of its section takes that end's node along (instead of a link back to it).
        far_a, a_far = (ia[0], ma < .5) if stretch["na"] == ia[1] else (ia[1], ma > geom_a.length - .5)
        if a_far and anchors[0].distance(geom_a.interpolate(ma)) > .01:
            ends_moved[far_a] = anchors[0]
        far_b, b_far = (ib[1], mb > geom_b.length - .5) if stretch["nb"] == ib[0] else (ib[0], mb < .5)
        if b_far and anchors[1].distance(geom_b.interpolate(mb)) > .01:
            ends_moved[far_b] = anchors[1]
        keep_a = [] if far_a in ends_moved else None
        keep_b = [] if far_b in ends_moved else None
        if stretch["na"] == ia[1]:
            shapes[ia] = (list(substring(geom_a, 0, ma).coords) if keep_a is None else keep_a) + seg(0, at[0])
        else:
            shapes[ia] = seg(0, at[0])[::-1] + (list(substring(geom_a, ma, geom_a.length).coords) if keep_a is None else keep_a)
        for j, (i, _c) in enumerate(stretch["middle"]):              # section j runs from path[j] to path[j + 1]
            piece = seg(at[j], at[j + 1])
            shapes[i] = piece if i[0] == path[j] else piece[::-1]
        if stretch["nb"] == ib[0]:
            shapes[ib] = seg(at[-1], length) + (list(substring(geom_b, mb, geom_b.length).coords) if keep_b is None else keep_b)
        else:
            shapes[ib] = (list(substring(geom_b, 0, mb).coords) if keep_b is None else keep_b) + seg(at[-1], length)[::-1]
        to_wgs = Transformer.from_crs(base.crs, 4326, always_xy=True)
        geometry = {}
        for i, pts in shapes.items():
            pts = dedupe(pts)
            line = shapely.geometry.LineString(pts) if len(pts) > 1 else None
            if line is None or line.length < .3 or not line.is_simple:
                raise HTTPException(400, "the corrected road must not cross itself; trace it again")
            geometry[roads_mod.edge_ref(*i)] = [list(to_wgs.transform(x, y)) for x, y in pts]
        nodes = {}
        for n, a in zip(path, at):
            p = trace.interpolate(a)
            nodes[int(n)] = list(to_wgs.transform(p.x, p.y))
        for n, p in ends_moved.items():
            nodes[int(n)] = list(to_wgs.transform(p.x, p.y))
        reviews = None
        if end_review:
            lon, lat = to_wgs.transform(anchors[1].x, anchors[1].y)
            reviews = {roads_mod.edge_ref(*ib): {"lon": lon, "lat": lat, "note": "path beyond B is unclear"}}
        try:
            ctx.store.set_road_stretch(geometry, nodes, revision, me(), reviews=reviews)
        except Conflict:
            raise HTTPException(409, "project changed; select the road portion again")
        return {"status": ctx.store.status(me()), "replaced_m": round(old.length, 2), "uncertain": bool(end_review), "sections": len(geometry)}

    @app.post("/api/roads/geometry/partial/preview")
    def post_partial_geometry_preview(body: dict = Body(...)) -> dict:
        """Preview the exact portion that will be replaced between two anchors."""
        _, _, start_m, end_m, _, wgs, _, _ = partial_geometry_selection(body)
        return {"type": "Feature", "properties": {
            "selected_m": round(end_m - start_m, 2),
            "anchors": [[wgs.iloc[0].x, wgs.iloc[0].y], [wgs.iloc[1].x, wgs.iloc[1].y]],
        }, "geometry": shapely.geometry.mapping(wgs.iloc[2])}

    @app.post("/api/roads/geometry/partial")
    def post_partial_geometry(body: dict = Body(...)) -> dict:
        """Replace only the road geometry between two fixed interior anchors."""
        try:
            revision = int(body["revision"])
            replacement_coords = [[float(x), float(y)] for x, y in body["coords"]]
            if not 2 <= len(replacement_coords) <= 5000 or any(
                not math.isfinite(x) or not math.isfinite(y) or abs(x) > 180 or abs(y) > 90
                for x, y in replacement_coords
            ):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, "provide a revision and 2-5000 valid replacement points")
        if ctx.store.revision() != revision:
            raise HTTPException(409, "project changed; select the road portion again")
        ref, geom, start_m, end_m, anchors, _, base, idx = partial_geometry_selection(body)
        replacement = gpd.GeoSeries(
            [shapely.geometry.LineString(replacement_coords)], crs=4326
        ).to_crs(base.crs).iloc[0]
        direct = shapely.geometry.Point(replacement.coords[0]).distance(anchors[0]) + shapely.geometry.Point(replacement.coords[-1]).distance(anchors[1])
        reverse = shapely.geometry.Point(replacement.coords[0]).distance(anchors[1]) + shapely.geometry.Point(replacement.coords[-1]).distance(anchors[0])
        coords = list(replacement.coords)
        if reverse < direct:
            coords.reverse()
            direct = reverse
        if direct > 4:
            raise HTTPException(400, "the replacement must start and finish at the two fixed anchors")
        coords[0], coords[-1] = anchors[0].coords[0], anchors[1].coords[0]
        if isinstance(idx, dict):                  # A and B on different sections of the road
            return save_stretch(idx, anchors, coords, base, revision, body.get("end_review") == "uncertain")
        from shapely.ops import substring
        before = list(substring(geom, 0, start_m).coords)
        after = list(substring(geom, end_m, geom.length).coords)
        moves = {}                                 # an off-line anchor at an end of the section: that node moves to it
        if start_m < .5 and anchors[0].distance(geom.interpolate(start_m)) > .01:
            before, moves[idx[0]] = [coords[0]], anchors[0]
        if geom.length - end_m < .5 and anchors[1].distance(geom.interpolate(end_m)) > .01:
            after, moves[idx[1]] = [coords[-1]], anchors[1]
        def off(point, joint):                     # where an off-line anchor rejoins the old line
            return [] if shapely.geometry.Point(joint).distance(point) < .01 else [joint]
        combined = before[:-1] + off(anchors[0], before[-1]) + coords + off(anchors[1], after[0]) + after[1:]
        line = shapely.geometry.LineString(combined)
        if line.length < .5 or not line.is_simple:
            raise HTTPException(400, "the corrected road must not cross itself")
        full_wgs = gpd.GeoSeries([line], crs=base.crs).to_crs(4326).iloc[0]
        uncertain_end = None
        if body.get("end_review") == "uncertain":
            point = gpd.GeoSeries([anchors[1]], crs=base.crs).to_crs(4326).iloc[0]
            uncertain_end = {"lon": float(point.x), "lat": float(point.y), "note": "path beyond B is unclear"}
        try:
            if moves:
                to_wgs = Transformer.from_crs(base.crs, 4326, always_xy=True)
                ctx.store.set_road_stretch({ref: list(map(list, full_wgs.coords))},
                                           {int(n): list(to_wgs.transform(p.x, p.y)) for n, p in moves.items()},
                                           revision, me(), reviews={ref: uncertain_end})
            else:
                ctx.store.set_road_geometry(ref, list(map(list, full_wgs.coords)), revision, me(), uncertain_end=uncertain_end)
        except Conflict:
            raise HTTPException(409, "project changed; select the road portion again")
        return {"status": ctx.store.status(me()), "replaced_m": round(end_m - start_m, 2), "uncertain": uncertain_end is not None}

    def cut_preview(body: dict) -> tuple[dict, dict]:
        try:
            ref = str(body['ref'])
            points = [[float(x), float(y)] for x, y in body['points']]
            if len(points) != 2 or any(not math.isfinite(x) or not math.isfinite(y) or abs(x) > 180 or abs(y) > 90 for x, y in points):
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise HTTPException(400, 'choose two valid cut points on the same road section')
        base, _ = ctx.get_effective()
        idx = next((idx for idx in base.edges.index if idx[0] < idx[1] and idx[2] < roads_mod.SYNTHETIC_KEY and roads_mod.edge_ref(*idx) == ref), None)
        if idx is None:
            raise HTTPException(404, 'road section changed; select it again')
        geom = base.edges.loc[idx].geometry
        tr = Transformer.from_crs(4326, base.crs, always_xy=True)
        pts = [shapely.geometry.Point(*tr.transform(*p)) for p in points]
        if any(p.distance(geom) > 25 for p in pts):
            raise HTTPException(400, 'choose cut points closer to the selected line')
        a, b = (0.0, geom.length) if body.get('whole') is True else sorted(geom.project(p) for p in pts)
        a = 0.0 if a < .5 else a
        b = geom.length if b > geom.length-.5 else b
        if b-a < .5:
            raise HTTPException(400, 'the cut must remove at least 0.5 metres')
        from shapely.ops import substring
        removed = gpd.GeoSeries([substring(geom, a, b)], crs=base.crs).to_crs(4326).iloc[0]
        source = gpd.GeoSeries([geom], crs=base.crs).to_crs(4326).iloc[0]
        cut = {'ref': ref, 'coords': list(map(list, source.coords)), 'start_m': a, 'end_m': b}
        preview = {'type': 'Feature', 'properties': {'removed_m': round(b-a, 2), 'retained_parts': int(a >= .5)+int(geom.length-b >= .5)}, 'geometry': shapely.geometry.mapping(removed)}
        return cut, preview

    @app.post('/api/roads/cut/preview')
    def post_cut_preview(body: dict = Body(...)):
        _, preview = cut_preview(body)
        return preview

    @app.post('/api/roads/cut')
    def post_cut(body: dict = Body(...)):
        if body.get('revision') != ctx.store.revision():
            raise HTTPException(409, 'project changed; select the section again')
        cut, preview = cut_preview(body)
        cut['id'] = uuid.uuid4().hex
        try:
            ctx.store.add_road_cut(cut, int(body['revision']), me())
        except Conflict:
            raise HTTPException(409, 'project changed; select the section again')
        return {'status': ctx.store.status(me()), 'removed_m': preview['properties']['removed_m']}

    @app.post('/api/roads/review')
    def post_road_review(body: dict = Body(...)):
        """Mark an interval on a road as unclear without changing its geometry."""
        if body.get('revision') != ctx.store.revision():
            raise HTTPException(409, 'project changed; select the unclear portion again')
        _, preview = cut_preview(body)
        review = {'id': uuid.uuid4().hex, 'ref': str(body['ref']), 'selected_m': preview['properties']['removed_m'],
                  'note': str(body.get('note') or 'Road or path unclear in imagery')[:500], 'geometry': preview['geometry']}
        try:
            ctx.store.add_road_review(review, int(body['revision']), me())
        except Conflict:
            raise HTTPException(409, 'project changed; select the unclear portion again')
        return {'status': ctx.store.status(me()), 'review': review}

    @app.post('/api/roads/review/remove')
    def post_road_review_remove(body: dict = Body(...)):
        """Resolve unclear-road interval marks without changing road geometry."""
        ids = [str(value) for value in body.get('ids', [])]
        if not ids:
            raise HTTPException(400, 'choose at least one unclear portion')
        try:
            ctx.store.remove_road_reviews(ids, int(body['revision']), me())
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, 'provide the current project revision')
        except Conflict:
            raise HTTPException(409, 'project changed; reload the unclear portions')
        return {'status': ctx.store.status(me()), 'removed': len(ids)}

    def join_preview(body: dict):
        try:
            source_node = int(body['source_node'])
            source_ref, target_ref = str(body['ref']),str(body['target_ref'])
            lon, lat = float(body['lon']),float(body['lat'])
            if not math.isfinite(lon) or not math.isfinite(lat) or abs(lon)>180 or abs(lat)>90: raise ValueError()
        except (KeyError,ValueError,TypeError):
            raise HTTPException(400,'select a road endpoint and a target road')
        base,_ = ctx.get_effective()
        source_idx = next((i for i in base.edges.index if i[0]<i[1] and roads_mod.edge_ref(*i)==source_ref),None)
        target_idx = next((i for i in base.edges.index if i[0]<i[1] and roads_mod.edge_ref(*i)==target_ref),None)
        if source_idx is None or target_idx is None: raise HTTPException(404,'road section changed; select it again')
        if source_node not in source_idx[:2]: raise HTTPException(400,'choose an endpoint of the selected road')
        if source_ref == target_ref: raise HTTPException(400,'choose another road to connect to')
        if source_node in target_idx[:2]: return None,{'already_connected':True,'gap_m':0}
        incident = {roads_mod.edge_ref(*i) for i in base.edges.index if source_node in i[:2] and i[2]<roads_mod.SYNTHETIC_KEY}
        if len(incident) != 1: raise HTTPException(409,'this endpoint already belongs to a junction; choose a free endpoint')
        tr = Transformer.from_crs(4326,base.crs,always_xy=True)
        point = shapely.geometry.Point(*tr.transform(lon,lat))
        line = base.edges.loc[target_idx].geometry
        if point.distance(line)>25: raise HTTPException(400,'click closer to the target road')
        distance = line.project(point)
        distance = 0.0 if distance<.5 else line.length if distance>line.length-.5 else distance
        target_point = line.interpolate(distance)
        gap = base.nodes.loc[source_node].geometry.distance(target_point)
        if gap>60: raise HTTPException(400,'the target is over 60 m away; trace a connecting road instead')
        coords = list(map(list,gpd.GeoSeries([line],crs=base.crs).to_crs(4326).iloc[0].coords))
        source_point = gpd.GeoSeries([base.nodes.loc[source_node].geometry],crs=base.crs).to_crs(4326).iloc[0]
        op = {'id':uuid.uuid4().hex,'source_node':source_node,'source_point':[source_point.x,source_point.y],
              'source_osmid':str(base.edges.loc[source_idx].osmid),'ref':source_ref,'target_ref':target_ref,'coords':coords,'target_m':distance}
        try:
            _,preview_edges,_ = roads_mod.join_endpoint(base.nodes.copy(),base.edges.copy(),op)
            for i,row in preview_edges.iterrows():
                if i not in base.edges.index and (not row.geometry.is_simple or row.geometry.length<.5):
                    raise ValueError('the connection would collapse or cross the road itself')
        except ValueError as exc:
            raise HTTPException(409,str(exc))
        return op,{'already_connected':False,'gap_m':round(gap,2),
                  'point':shapely.geometry.mapping(gpd.GeoSeries([target_point],crs=base.crs).to_crs(4326).iloc[0])}

    @app.post('/api/roads/join/preview')
    def post_join_preview(body: dict = Body(...)):
        _,preview = join_preview(body)
        return preview

    @app.post('/api/roads/join')
    def post_join(body: dict = Body(...)):
        if body.get('revision') != ctx.store.revision(): raise HTTPException(409,'project changed; select the endpoints again')
        op,preview = join_preview(body)
        if op is None: return {**preview,'changed':False,'status':ctx.store.status(me())}
        try: ctx.store.add_road_join(op,int(body['revision']),me())
        except Conflict: raise HTTPException(409,'project changed; select the endpoints again')
        return {**preview,'changed':True,'status':ctx.store.status(me())}

    @app.post('/api/work-areas/grid')
    def post_area_grid(body: dict = Body(...)):
        p = ctx.store.project()
        if work_areas.grid_collection(p.work_areas).get('features'):
            raise HTTPException(409, 'a work grid already exists; keep its review history')
        base = ctx.get_base()
        aoi = engine.aoi_polygon(base)
        if aoi is None and base.area is not None and not base.area.empty:
            aoi = base.area.to_crs(4326).geometry.union_all()
        if aoi is None:
            raise HTTPException(400, 'this project needs an area boundary before creating a grid')
        try:
            size = body.get('cell_m', 'auto')
            grid = work_areas.make_grid(aoi, base.crs, 'auto' if size == 'auto' else float(size))
            quartiers = work_areas.quartier_collection(p.work_areas)
            areas = work_areas.make_hierarchy(grid, quartiers, base.crs) if quartiers.get('features') else grid
            ctx.store.set_work_areas(areas, int(body['revision']), me())
        except Conflict:
            raise HTTPException(409, 'project changed; reload the areas')
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc) or 'invalid area settings')
        return {'areas': areas, 'status': ctx.store.status(me())}

    def project_aoi():
        """WGS84 boundary used by either work-area generator."""
        base = ctx.get_base()
        aoi = engine.aoi_polygon(base)
        if aoi is None and base.area is not None and not base.area.empty:
            aoi = base.area.to_crs(4326).geometry.union_all()
        if aoi is None:
            raise HTTPException(400, 'this project needs an area boundary before creating work areas')
        return base, aoi

    def quartier_content(body: dict) -> bytes:
        try:
            return base64.b64decode(body['content_b64'], validate=True)
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(400, 'provide a valid CSV file') from exc

    @app.post('/api/work-areas/quartiers/preview')
    def post_quartier_preview(body: dict = Body(...)):
        """Inspect quartier spellings and point coverage without saving private CSV rows."""
        _base, aoi = project_aoi()
        try:
            return work_areas.preview_quartiers(quartier_content(body), aoi,
                                                body.get('district_column', 'district'), body.get('lat_column', 'latitude'), body.get('lon_column', 'longitude'),
                                                body.get('use_fotouni_catalog', True))
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc) or 'invalid quartier CSV')

    @app.post('/api/work-areas/quartiers')
    def post_quartiers(body: dict = Body(...)):
        """Save human-reviewed provisional quartier polygons as the work areas (one undoable edit)."""
        p = ctx.store.project()
        if work_areas.quartier_collection(p.work_areas).get('features') and body.get('replace') is not True:
            raise HTTPException(409, 'quartier areas already exist; explicitly confirm their replacement')
        base, aoi = project_aoi()
        try:
            quartiers = work_areas.make_quartiers(quartier_content(body), aoi, base.crs, body.get('mapping'),
                                                  body.get('district_column', 'district'), body.get('lat_column', 'latitude'), body.get('lon_column', 'longitude'),
                                                  body.get('use_fotouni_catalog', True))
            quartiers['source']['filename'] = Path(str(body.get('filename') or 'quartiers.csv')).name[:200]
            grid = work_areas.grid_collection(p.work_areas)
            if not grid.get('features'):
                grid = work_areas.make_grid(aoi, base.crs, 'auto')
            areas = work_areas.make_hierarchy(grid, quartiers, base.crs)
            ctx.store.set_work_areas(areas, int(body['revision']), me())
        except Conflict:
            raise HTTPException(409, 'project changed; preview the quartiers again')
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc) or 'invalid quartier settings')
        return {'areas': areas, 'status': ctx.store.status(me())}

    @app.post('/api/work-areas/status')
    def post_area_status(body: dict = Body(...)):
        import copy
        areas = copy.deepcopy(ctx.store.project().work_areas)
        cell = next((f for f in areas.get('features', []) if f['properties']['id'] == body.get('id')), None)
        if cell is None:
            raise HTTPException(404, 'no such work area')
        if not isinstance(body.get('note', ''), str) or len(body.get('note', '')) > 2000:
            raise HTTPException(400, 'area note must be at most 2000 characters')
        stages = work_areas.ensure_stages(cell['properties'])
        if isinstance(body.get('stages'), dict):
            for name, value in body['stages'].items():
                if name not in work_areas.STAGE_STATUSES or value not in work_areas.STAGE_STATUSES[name]:
                    raise HTTPException(400, f'invalid {name} review status')
                stages[name] = value
        elif body.get('status') in work_areas.STATUSES:             # compatibility with the earlier one-status interface/API
            stages['geometry'] = {'unreviewed': 'not_started', 'in_progress': 'in_progress', 'reviewed': 'reviewed', 'needs_review': 'needs_review'}[body['status']]
        else:
            raise HTTPException(400, 'provide the review stages')
        cell['properties'].update(status=work_areas.overall_status(stages), stages=stages, note=body.get('note', ''))
        try:
            ctx.store.set_work_areas(areas, int(body['revision']), me())
        except (KeyError, ValueError, TypeError):
            raise HTTPException(400, 'provide the current revision')
        except Conflict:
            raise HTTPException(409, 'project changed; reload the areas')
        return {'status': ctx.store.status(me())}

    @app.get('/api/work-areas/boundaries')
    def get_area_boundaries(area_id: str):
        """List the selected quartier's shared borders, ready for topology-safe editing."""
        try:
            options = work_areas.boundary_options(work_areas.quartier_collection(ctx.store.project().work_areas), area_id, ctx.get_base().crs)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {'area_id': area_id, 'neighbours': options, 'revision': ctx.store.revision()}

    @app.get('/api/work-areas/shared-boundaries')
    def get_shared_area_boundaries():
        """Unique hoverable boundaries carrying the names of both adjacent quartiers."""
        return work_areas.shared_boundaries(work_areas.quartier_collection(ctx.store.project().work_areas), ctx.get_base().crs)

    @app.post('/api/work-areas/boundary')
    def post_area_boundary(body: dict = Body(...)):
        """Reshape one shared quartier border without changing the combined covered area."""
        try:
            current = ctx.store.project().work_areas
            quartiers = work_areas.reshape_boundary(work_areas.quartier_collection(current), str(body['area_id']),
                                                     str(body['neighbour_id']), body['coords'], body.get('reason', ''),
                                                     ctx.get_base().crs)
            grid = work_areas.grid_collection(current)
            areas = work_areas.make_hierarchy(grid, quartiers, ctx.get_base().crs)
            ctx.store.set_work_areas(areas, int(body['revision']), me())
        except Conflict:
            raise HTTPException(409, 'project changed; reload the quartier boundary')
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc) or 'invalid quartier boundary')
        return {'areas': areas, 'status': ctx.store.status(me())}

    @app.get('/api/roads/check')
    def get_road_check(area: str | None = None):
        """The road check of a work area or quartier (``area`` id; none: the whole map), see ``road_check``."""
        p = ctx.store.project()
        polygon = road_check.area_polygon(p, area)
        if area and polygon is None:
            raise HTTPException(404, 'no such work area')
        base, res = ctx.get_effective(p)
        issues = road_check.check_roads(base, res.report if res is not None else {}, p, polygon)
        counts: dict = {}
        for issue in issues:
            if not issue['ok']:
                counts[issue['kind']] = counts.get(issue['kind'], 0) + 1
        return {'revision': ctx.store.revision(), 'area': area, 'issues': issues, 'counts': counts,
                'ok': sum(1 for issue in issues if issue['ok'])}

    @app.post('/api/roads/check/ok')
    def post_road_check_ok(body: dict = Body(...)):
        """Mark road check problems "OK as is" (``{"ids": [...], "ok": true}``) or list them again (``"ok": false``)."""
        ids = [str(value) for value in body.get('ids', [])]
        if not ids:
            raise HTTPException(400, 'choose at least one problem')
        ctx.store.set_check_ok(ids, body.get('ok', True) is not False, me())
        return {'status': ctx.store.status(me())}

    @app.post('/api/roads/stale/clear')
    def post_clear_stale_roads(body: dict = Body(...)):
        """Remove reviewed stale cut/join operations as one traceable maintenance edit."""
        try:
            ctx.store.remove_road_operations(body['ids'], body.get('reason', ''), int(body['revision']), me())
        except Conflict:
            raise HTTPException(409, 'project changed; recompute and review the stale roads again')
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc) or 'invalid stale-road cleanup')
        ctx.invalidate()
        return {'status': ctx.store.status(me())}

    @app.post("/api/streets/assign")
    def post_streets_assign(body: dict = Body(...)) -> dict:
        """Change the street id of the roads at a node (from the node popup of the Street IDs tab).

        Body: ``{"ref": "u-v-key"}`` the road clicked and either ``{"mode": "merge", "target": <street id>}`` (all roads of its street take the
        id of the target street) or ``{"mode": "split", "node": <node id>}`` (the branch that leaves the node on that road, as far as the
        street goes, gets a new id; only when the street leaves the node by more than one road). Applied at the next Compute.
        """
        if ctx.network is None:
            raise HTTPException(409, "compute the network first")
        st = ctx.network
        es = st.edges.reset_index()
        es = es[(es["key"] < roads_mod.SYNTHETIC_KEY) & es["street_id"].notna()]
        es = es.assign(ref=[roads_mod.edge_ref(u, v, k) for u, v, k in zip(es["u"], es["v"], es["key"])]).drop_duplicates("ref").set_index("ref")
        ref = str(body["ref"])
        if ref not in es.index:
            raise HTTPException(404, "that road is not part of the computed network")
        proj = ctx.store.project()
        done = proj.roads.get("edge_street", {})                    # earlier changes that are not computed yet: several ids can be changed before one recomputation
        if done:
            es["street_id"] = [int(done[r]) if r in done else int(i) for r, i in zip(es.index, es["street_id"])]
        fid = int(es.loc[ref, "street_id"])
        orig = {int(a): int(b) for a, b in zip(st.streets["street_id"], st.streets["street_id_original"])}
        for v in done.values():
            orig.setdefault(int(v), int(v))
        if body.get("mode") == "merge":
            target = int(body["target"])
            if target not in orig or not (es["street_id"].astype(int) == target).any():
                raise HTTPException(404, "no such street id")
            # Use current membership and pending attributes, including new IDs
            # created since the last computation. Force never bypasses rank or
            # topology constraints.
            root = orig[target]
            mine = es[es["street_id"].astype(int) == fid].index
            members = set(mine) | {r for r, sid in zip(es.index, es["street_id"]) if orig.get(int(sid), int(sid)) == root}
            ranks = {int(row.street_id): int(row.street_rank) for row in st.streets.itertuples()}
            parts = {int(row.street_id): int(getattr(row, "street_part", 0)) for row in st.streets.itertuples()}
            previous = st.edges.reset_index()
            original_by_ref = {roads_mod.edge_ref(u, v, k): int(sid) for u, v, k, sid in zip(previous.u, previous.v, previous.key, previous.street_id) if pd.notna(sid)}
            attrs = proj.roads.get("attrs", {})

            def rank_at(r):
                old_sid = original_by_ref[r]
                sid = int(es.loc[r, "street_id"])
                old_root = orig.get(old_sid, old_sid)
                rank = ranks[old_sid]
                rank = attrs.get(str(old_root), {}).get("rank", rank)
                rank = attrs.get(f"{old_root}:{parts.get(old_sid, 0)}", {}).get("rank", rank)
                new_root = orig.get(sid, sid)
                return int(attrs.get(str(new_root), {}).get("rank", rank) if new_root != old_root else rank)

            joined_ranks = {rank_at(r) for r in members}
            if len(joined_ranks) != 1:
                raise HTTPException(409, f"cannot join streets with different ranks ({', '.join(map(str, sorted(joined_ranks)))}): set the same rank first")
            try:
                street_ops.validate_path(es, members, root)
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            if orig[target] == orig[fid]:                          # two parts of one street that were cut at a minimum of the distance
                if not body.get("force"):
                    raise HTTPException(409, "these are parts of the same street, cut automatically at a minimum of the distance to the reference: join them with the red option")
                ctx.store.assign_edge_streets({}, me(), None, [orig[target]])      # never cut it again: the next computation joins the parts
                return {"changed": 0, "id": orig[target], "name": None, "status": ctx.store.status(me())}
            own = {int(r.street_id): re.sub(r" \([A-Z]+\)$", "", str(r.street_name).strip()) for r in st.streets.itertuples() if is_named(r.street_name)}
            name_from, name_to = own.get(fid), own.get(target)
            names = {}
            if name_from and not name_to:                          # only the street that is joined has a name: the merged street takes it
                names[orig[target]] = name_from                    # (when both have names, the street whose id is kept keeps its name)
            rank_new = next(iter(joined_ranks))
            ctx.store.assign_edge_streets({r: orig[target] for r in mine}, me(), names, [orig[target]],
                                          {orig[target]: {"rank": rank_new}})                  # (a join chosen by the editors is never cut again at a minimum)
            return {"changed": len(mine), "id": orig[target], "name": names.get(orig[target]) or name_to, "status": ctx.store.status(me())}
        if body.get("mode") == "split":
            node = int(body["node"])
            mine = es[es["street_id"].astype(int) == fid]
            try:
                take = street_ops.split_refs(mine, ref, node)
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            used = [int(x) for x in st.streets["street_id_original"]] + [int(x) for x in st.streets["street_id"]] + [int(v) for v in proj.roads.get("edge_street", {}).values()]
            used += [int(v) for v in ctx.store.get_computed("branch_ids", {}).values()]
            used += [int(v) for v in proj.names]
            new_id = max(used) + 1
            ctx.store.assign_edge_streets({r: new_id for r in take}, me(), no_cut=[new_id])
            return {"changed": len(take), "id": new_id, "status": ctx.store.status(me())}
        raise HTTPException(400, "mode must be merge or split")

    def current_attrs() -> dict:
        """The rank / drivable / paved of every original street as computed now."""
        out: dict = {}
        for r in tables()["streets"].itertuples():
            out.setdefault(int(r.original_id), {"rank": int(r.rank), "drivable": None if pd.isna(r.drivable) else bool(r.drivable),
                                                "paved": None if pd.isna(r.paved) else bool(r.paved)})
        return out

    def street_edge_refs(original: int, part: int | None = None) -> list[str]:
        """Stable references of every real edge currently displayed as one street or cut part."""
        if ctx.network is None:
            raise HTTPException(409, "compute the network first")
        streets = ctx.network.streets_gdf
        mask = streets["street_id_original"].astype(int) == int(original)
        if part is not None:
            mask &= streets["street_part"].astype(int) == int(part)
        ids = set(streets.loc[mask, "street_id"].astype(int))
        if not ids:
            raise HTTPException(404, "street or part not found")
        edges = ctx.network.edges.reset_index()
        edges = edges[(edges["key"] < roads_mod.SYNTHETIC_KEY) & edges["street_id"].isin(ids)]
        return sorted({roads_mod.edge_ref(int(r.u), int(r.v), int(r.key)) for r in edges.itertuples()})

    def access_routes(a: dict, b: dict) -> dict:
        """Two shortest node-distinct routes after snapping A and B to network nodes."""
        import itertools
        import networkx as nx

        base, _ = ctx.get_effective()
        rows = base.edges.reset_index()
        rows = rows[rows["key"] < roads_mod.SYNTHETIC_KEY].copy()
        rows["ref"] = [roads_mod.edge_ref(int(u), int(v), int(k)) for u, v, k in zip(rows.u, rows.v, rows.key)]
        rows = rows.drop_duplicates("ref")
        touched = sorted(set(rows.u.astype(int)) | set(rows.v.astype(int)))
        if not touched:
            raise HTTPException(409, "the network has no edges")
        nodes = base.nodes.loc[touched]
        transform = Transformer.from_crs(4326, base.crs, always_xy=True)

        def snap(point: dict) -> int:
            x, y = transform.transform(float(point["lon"]), float(point["lat"]))
            dist = (nodes["x"].astype(float) - x) ** 2 + (nodes["y"].astype(float) - y) ** 2
            return int(dist.idxmin())

        start, end = snap(a), snap(b)
        if start == end:
            raise HTTPException(400, "A and B snap to the same network node")
        graph = nx.Graph()
        by_ref = {}
        for row in rows.itertuples():
            ref, length = str(row.ref), float(row.geometry.length)
            by_ref[ref] = row
            if graph.has_edge(int(row.u), int(row.v)) and graph[int(row.u)][int(row.v)]["length"] <= length:
                continue
            graph.add_edge(int(row.u), int(row.v), length=length, ref=ref)
        try:
            node_paths = list(itertools.islice(nx.shortest_simple_paths(graph, start, end, weight="length"), 2))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            raise HTTPException(409, "there is no route between A and B")
        back = Transformer.from_crs(base.crs, 4326, always_xy=True)
        routes = []
        for index, nodes_path in enumerate(node_paths):
            refs = [graph[u][v]["ref"] for u, v in zip(nodes_path, nodes_path[1:])]
            features = []
            for ref in refs:
                row = by_ref[ref]
                geom = gpd.GeoSeries([row.geometry], crs=base.crs).to_crs(4326).iloc[0]
                value = getattr(row, "access", None)
                value = None if value is None or pd.isna(value) else str(value)
                features.append({"type": "Feature", "properties": {"ref": ref, "access": value},
                                 "geometry": shapely.geometry.mapping(shapely.set_precision(geom, 1e-6))})
            routes.append({"index": index, "refs": refs, "nodes": nodes_path,
                           "length_m": round(sum(float(graph[u][v]["length"]) for u, v in zip(nodes_path, nodes_path[1:])), 1),
                           "geometry": {"type": "FeatureCollection", "features": features}})
        sx, sy = float(nodes.loc[start, "x"]), float(nodes.loc[start, "y"])
        ex, ey = float(nodes.loc[end, "x"]), float(nodes.loc[end, "y"])
        slon, slat = back.transform(sx, sy); elon, elat = back.transform(ex, ey)
        return {"revision": ctx.store.revision(), "a": {"node": start, "lat": slat, "lon": slon},
                "b": {"node": end, "lat": elat, "lon": elon}, "routes": routes}

    @app.post("/api/edges/access/path")
    def post_edge_access_path(body: dict = Body(...)) -> dict:
        return access_routes(body["a"], body["b"])

    @app.post("/api/edges/access")
    def post_edge_access(body: dict = Body(...)) -> dict:
        value = body.get("access")
        if value not in ("car", "foot", None):                 # car = drivable, foot = not drivable (todo 2.1)
            raise HTTPException(400, "access must be car (drivable), foot (not drivable) or null")
        refs = [str(ref) for ref in body.get("refs", [])]
        if not refs:
            raise HTTPException(400, "choose at least one edge")
        base, _ = ctx.get_effective()
        available = {roads_mod.edge_ref(u, v, k) for u, v, k in base.edges.index if k < roads_mod.SYNTHETIC_KEY}
        if not set(refs) <= available:
            raise HTTPException(409, "the route changed; select A and B again")
        try:
            ctx.store.set_edge_access({ref: value for ref in refs}, int(body["revision"]), me())
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        return {"changed": len(set(refs)), "access": value, "status": ctx.store.status(me())}

    @app.post("/api/streets/attrs")
    def post_street_attrs(body: dict = Body(...)) -> dict:
        """Change the rank (0-5), the drivable flag or the paved flag of a street: ``{"original": id, "part"?, "rank"?, "drivable"?, "paved"?}`` (``part``: only that part of a cut street)."""
        a: dict = {}
        if body.get("rank") is not None:
            if int(body["rank"]) not in engine.RANK_HIGHWAY:
                raise HTTPException(400, "rank must be 0 to 5")
            a["rank"] = int(body["rank"])
        if "paved" in body:
            a["paved"] = None if body["paved"] is None else bool(body["paved"])
        if "addresses" in body:                                      # False: a path whose houses take the number where it leaves the street
            a["addresses"] = body["addresses"] is not False
        key = str(int(body["original"])) + (f":{int(body['part'])}" if body.get("part") is not None else "")        # "114:2": only part 2 of street 114
        ctx.store.set_street_attrs({key: a}, me())
        if "drivable" in body:
            value = None if body["drivable"] is None else ("car" if bool(body["drivable"]) else "foot")
            refs = street_edge_refs(int(body["original"]), int(body["part"]) if body.get("part") is not None else None)
            ctx.store.set_edge_access({ref: value for ref in refs}, None, me())
        return {"status": ctx.store.status(me())}

    @app.post("/api/streets/attrs/import")
    def post_street_attrs_import(body: dict = Body(...)) -> dict:
        """Apply a street data CSV (downloaded streets file, edited): columns ``original_id`` (or ``street_id``), ``rank``, ``drivable``, ``paved``.

        Only the values that differ from the current ones are stored (one undo step).
        """
        raw = base64.b64decode(body["content_b64"]).decode("utf-8-sig")
        df = pd.read_csv(io.StringIO(raw), dtype=str).fillna("")
        df.columns = [c.strip().lower() for c in df.columns]
        key = "original_id" if "original_id" in df.columns else "street_id" if "street_id" in df.columns else None
        if key is None:
            raise HTTPException(400, "the file needs an original_id (or street_id) column")
        t = tables()["streets"]
        to_orig = {int(a): int(b) for a, b in zip(t["street_id"], t["original_id"])}
        cur = current_attrs()
        truth = {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}
        changes: dict = {}
        for _, r in df.iterrows():
            try:
                oid = int(float(r[key]))
            except ValueError:
                continue
            oid = to_orig.get(oid, oid) if key == "street_id" else oid
            if oid not in cur:
                continue
            new: dict = {}
            if "rank" in df.columns and str(r["rank"]).strip() != "":
                v = int(float(r["rank"]))
                if v in engine.RANK_HIGHWAY and v != cur[oid]["rank"]:
                    new["rank"] = v
            for k in ("drivable", "paved"):
                if k not in df.columns:
                    continue
                txt = str(r[k]).strip().lower()
                val = truth.get(txt) if txt in truth else (None if txt in ("", "none", "unknown", "nan") else "bad")
                if val != "bad" and val != cur[oid][k]:
                    new[k] = val
            if new:
                changes[oid] = new
        ctx.store.set_street_attrs(changes, me())
        return {"changed": len(changes), "status": ctx.store.status(me())}

    @app.get("/api/points/ranks")
    def get_point_ranks() -> list:
        """The reference points inside the area with their rank for the street signs (1 landmark ... 3 local, 0 not on the signs)."""
        base = ctx.get_base()
        rows = engine.reference_point_rows(base, ctx.store.project().roads.get("point_rank"))
        return [{"id": r.building_id, "name": r.name, "info": r.info, "rank": int(r.sign_rank), "lat": r.geometry.y, "lon": r.geometry.x} for r in rows.itertuples()]

    @app.post("/api/points/rank")
    def post_point_rank(body: dict = Body(...)) -> dict:
        """Change the sign rank (0-3) of one reference point (``{"id", "rank"}``) or of several (``{"ids": [...], "rank"}``)."""
        rank = int(body["rank"])
        if rank not in (0, 1, 2, 3):
            raise HTTPException(400, "rank must be 0 to 3")
        ids = body.get("ids") or [body["id"]]
        ctx.store.set_point_ranks({str(i): rank for i in ids}, me())
        return {"status": ctx.store.status(me())}

    @app.post("/api/houses/quartier")
    def post_house_quartier(body: dict = Body(...)) -> dict:
        """Correct the survey quartier of houses: ``{"ids": [...], "quartier": "Mving"}`` (a catalogue name; empty: back to the survey)."""
        ids = [str(i) for i in body.get("ids") or []]
        q = str(body.get("quartier") or "").strip()
        if not ids:
            raise HTTPException(400, "choose houses")
        if q and plate_mod.quartier_trigram(q) is None:
            raise HTTPException(400, f"{q} is not a quartier of the list (Overview Abbreviations)")
        ctx.store.set_house_quartiers({i: q or None for i in ids}, me())
        return {"status": ctx.store.status(me())}

    @app.post("/api/edges/remove")
    def post_edges_remove(body: dict = Body(...)) -> dict:
        """Delete street edges: ``{"edges": ["u-v-key", ...], "features": ["<import>:<id>", ...]}`` (one undo step)."""
        ctx.store.remove_edges([str(x) for x in body.get("edges", [])], [str(x) for x in body.get("features", [])], me())
        return {"status": ctx.store.status(me())}

    @app.post("/api/edges/restore")
    def post_edges_restore(body: dict = Body(...)) -> dict:
        """Bring deleted street edges back."""
        ctx.store.restore_edges([str(x) for x in body.get("edges", [])], [str(x) for x in body.get("features", [])], me())
        return {"status": ctx.store.status(me())}

    @app.post("/api/roads/remove")
    def post_roads_remove(body: dict = Body(...)) -> dict:
        """Remove an import of missing roads."""
        ctx.store.remove_roads(int(body["id"]), me())
        return {"status": ctx.store.status(me())}

    @app.post("/api/roads/connect")
    def post_roads_connect(body: dict = Body(...)) -> dict:
        """Connect a node of a drawn road: to the node or road point nearest to the click, to a given target, or not at all."""
        key = str(body["node"])
        if body.get("clear"):
            return {"changed": ctx.store.clear_road_connection(key, me()), "status": ctx.store.status(me())}
        if body.get("none"):
            target = {"type": "none"}
        elif "target" in body:
            target = body["target"]
        else:
            base = ctx.get_base()
            target = roads_mod.snap_click(base.nodes, base.edges, float(body["lat"]), float(body["lon"]))
            if target is None:
                raise HTTPException(404, "no road or node within 60 m of that point")
        ctx.store.connect_road_node(key, target, me())
        return {"target": target, "status": ctx.store.status(me())}

    @app.post("/api/roads/connect-suggested")
    def post_roads_connect_suggested(body: dict = Body(default={})) -> dict:
        """Accept the suggestion of every unconnected end that has one within ``max_m`` (one undo step)."""
        max_m = float(body.get("max_m", 25.0))
        _base, res = ctx.get_effective()
        picks = {n["key"]: n["suggestion"] for n in (res.report["nodes"] if res else [])
                 if n.get("suggestion") and n["key"] in set(res.report["dangling"]) and n["suggestion"]["distance_m"] <= max_m}
        ctx.store.connect_road_nodes(picks, me())
        return {"connected": len(picks), "status": ctx.store.status(me())}

    @app.post("/api/settings")
    def post_settings(body: dict = Body(...)) -> dict:
        """Change computation settings."""
        ctx.store.set_settings(body, me())
        return {"status": ctx.store.status(me())}

    @app.post("/api/undo")
    def post_undo() -> dict:
        """Undo the latest pending edit."""
        try: result=ctx.store.undo(me(),strict=auth_enabled)
        except Conflict: raise HTTPException(409,'Another editor has newer changes. Review history before undoing.')
        return {"undone": result, "status": ctx.store.status(me())}

    @app.post("/api/redo")
    def post_redo() -> dict:
        """Redo the earliest undone edit."""
        try: result=ctx.store.redo(me(),strict=auth_enabled)
        except Conflict: raise HTTPException(409,'Another editor has newer changes. Review history before redoing.')
        return {"redone": result, "status": ctx.store.status(me())}

    @app.post("/api/save")
    def post_save(body: dict = Body(default={})) -> dict:
        """Save: pending edits become a checkpoint and the street ids / names tables are updated."""
        cid = ctx.store.save(body.get("label", ""), me(), streets_rows())
        return {"checkpoint": cid, "status": ctx.store.status(me()), "ids_saved": streets_rows() is not None}

    @app.get("/api/checkpoints")
    def get_checkpoints() -> list:
        """All checkpoints, newest first."""
        return ctx.store.checkpoints()

    @app.post("/api/restore")
    def post_restore(body: dict = Body(...)) -> dict:
        """Go back to an older checkpoint (appends a new checkpoint with its content)."""
        reason=str(body.get('reason','')).strip()
        if auth_enabled and (type(body.get('revision')) is not int or not 5<=len(reason)<=1000):
            raise HTTPException(400,'Restore needs the current revision and a reason (5-1000 characters).')
        try:
            cid = ctx.store.restore(int(body["id"]), me(),expected_revision=body.get('revision') if auth_enabled else None,reason=reason)
        except KeyError:
            raise HTTPException(404, "no such checkpoint")
        except Conflict:
            raise HTTPException(409,'Project changed. Review the current state before restoring.')
        return {"checkpoint": cid, "status": ctx.store.status(me())}

    @app.get("/api/history")
    def get_history(limit: int = 200) -> list:
        """Recent edits."""
        return ctx.store.history(limit)

    @app.get('/api/audit')
    def get_audit(limit:int=100,before:int | None=None):
        return ctx.store.audit(limit,before)

    @app.post("/api/compute")
    def post_compute() -> dict:
        """Start recomputing ids, routes and names."""
        if not ctx.store.project().reference:
            raise HTTPException(400, "choose the reference node first")
        return {"started": ctx.run_job("network",me()), "job": ctx.job}

    @app.get("/api/job")
    def get_job() -> dict:
        """Status of the background computation."""
        return ctx.job

    @app.get("/api/network")
    def get_network():
        """The computed network (street ids, names, status, plan)."""
        if ctx.network_json is None:
            return JSONResponse({"detail": "not computed yet"}, status_code=409)
        no_addr = engine.no_address_streets(ctx.network.streets_gdf, ctx.store.project().roads.get("attrs")) if ctx.network is not None else set()
        for f in ctx.network_json["streets"]["features"]:
            f["properties"]["addresses"] = f["properties"]["id"] not in no_addr
        return ctx.network_json

    @app.post("/api/addresses/compute")
    def post_addresses() -> dict:
        """Start computing house numbers, addresses and street signs."""
        if not ctx.store.project().reference:
            raise HTTPException(400, "choose the reference node first")
        return {"started": ctx.run_job("addresses",me()), "job": ctx.job}

    @app.get("/api/addresses")
    def get_addresses():
        """House addresses and street signs."""
        if ctx.addresses is None:
            return JSONResponse({"detail": "not computed yet"}, status_code=409)
        a = registered()
        reg = ctx.store.project().register
        hs = a.houses.copy()
        hs["plaque_name"] = plaque_names(hs)
        return {"houses": _fc(hs, ["building_id", "address", "plate", "street_code", "quartier_code", "plaque_name", "number", "street_id", "street", "side", "side_source", "road_lat", "road_lon", "azimuth", "status", "distance_m", "address_id", "source", "district", "survey_district", "survey_type", "use", "name", "service", "residents", "workers", "review", "sign_rank",
                                    "access_lat", "access_lon", "via_path", "code", "register_status", "computed_address", "computed_plate", "changed", "approved_at", "approved_by"]),
                "register": {"approved": sum(1 for r in reg.values() if r.get("status") == "approved"),
                             "retired": sum(1 for r in reg.values() if r.get("status") == "retired"),
                             "changed": int(a.houses["changed"].sum())},
                "signs": {"type": "FeatureCollection", "features": [
                    {"type": "Feature", "properties": {"node_id": int(r.node_id), "labels": list(r.labels), "rank": r["rank"], "pois": list(r.pois), "spokes": list(r.spokes), "street_ids": str(r.street_ids or "")},
                     "geometry": shapely.geometry.mapping(r.geometry)} for _, r in a.signs.iterrows()]},
                "stats": a.stats, "warnings": a.warnings}

    def registered(reopen: set | None = None) -> engine.AddressState:
        """The computed addresses with the register applied: approved addresses never change (see ``engine.apply_register``).

        Args:
            reopen: Building ids treated as not approved (to correct them: they get the address computed now).
        """
        a = ctx.addresses
        reg = ctx.store.project().register
        if reopen:
            reg = {k: v for k, v in reg.items() if k not in reopen}
        return engine.AddressState(engine.apply_register(a.houses, reg), a.signs, a.stats, a.warnings)

    def household_table() -> dict:
        """The survey rows of ``input/households.csv`` (family names and private contacts), re-read when the file changes."""
        path = ctx.store.project().input_dir / households_mod.FILE
        stamp = path.stat().st_mtime if path.exists() else None
        if getattr(ctx, "_households_stamp", "unset") != stamp:
            ctx._households, ctx._households_stamp = households_mod.load(ctx.store.project().root), stamp
        return ctx._households

    def plaque_names(h) -> list:
        """The name printed on each house's plaque (family name, else business or public place name)."""
        t = household_table()
        return [households_mod.plaque_name(households_mod.for_building(t, b), nm if isinstance(nm, str) else None)
                for b, nm in zip(h["building_id"], h["name"] if "name" in h.columns else [None] * len(h))]

    def house_rows(ids: set | None = None, reopen: bool = False) -> list[dict]:
        """Current addresses (register applied) as plain rows, optionally only some buildings (``reopen``: as computed now)."""
        if ctx.addresses is None:
            raise HTTPException(409, "compute the addresses first (Addresses tab)")
        h = registered(ids if reopen else None).houses
        if ids is not None:
            h = h[h["building_id"].astype(str).isin(ids)]
        pts = h.geometry.apply(lambda g: g if g.geom_type == "Point" else g.representative_point())
        names = plaque_names(h)
        cat = {e["code"]: e["name"] for e in work_areas.fotouni_catalog()["entries"]}
        rows = []
        for (_, r), pt, nm in zip(h.iterrows(), pts, names):
            b = str(r["building_id"])
            clean = lambda v: None if v is None or (isinstance(v, float) and v != v) else (v.item() if hasattr(v, "item") else v)  # noqa: E731
            rows.append({"building_id": b, "address": clean(r.get("address")), "plate": clean(r.get("plate")), "street_code": clean(r.get("street_code")),
                         "number": clean(r.get("number")), "street": clean(r.get("street")),
                         "street_id": clean(r.get("street_id")), "status": clean(r.get("status")), "register_status": clean(r.get("register_status")),
                         "code": clean(r.get("code")), "computed_address": clean(r.get("computed_address")), "computed_plate": clean(r.get("computed_plate")),
                         "changed": bool(r.get("changed")), "district": clean(r.get("district")), "quartier_code": clean(r.get("quartier_code")),
                         "quartier_name": cat.get(clean(r.get("quartier_code"))), "plaque_name": nm, "use": clean(r.get("use")),
                         "address_id": clean(r.get("address_id")), "lat": round(float(pt.y), 7), "lon": round(float(pt.x), 7),
                         "road_lat": clean(r.get("road_lat")), "road_lon": clean(r.get("road_lon"))})
        return rows

    def houses_in_area(area_id: str) -> set:
        """Building ids inside a work area (grid cell or quartier)."""
        areas = ctx.store.project().work_areas
        feats = work_areas.grid_collection(areas).get("features", []) + work_areas.quartier_collection(areas).get("features", [])
        cell = next((f for f in feats if f["properties"].get("id") == area_id), None)
        if cell is None:
            raise HTTPException(404, "no such work area")
        shape = shapely.geometry.shape(cell["geometry"])
        h = ctx.addresses.houses
        pts = h.geometry.apply(lambda g: g if g.geom_type == "Point" else g.representative_point())
        return {str(b) for b, pt in zip(h["building_id"], pts) if shape.covers(pt)}

    @app.get("/api/register")
    def get_register() -> dict:
        """The address register: every approved or retired address, with its history, and the approved ones the map would now change."""
        reg = ctx.store.project().register
        now = {r["building_id"]: r for r in house_rows(set(reg))} if ctx.addresses is not None else {}
        rows = [{"building_id": b, **{k: v for k, v in r.items() if k != "history"}, "history": r.get("history", []),
                 "computed_address": now.get(b, {}).get("computed_address"), "changed": now.get(b, {}).get("changed", False)}
                for b, r in sorted(reg.items(), key=lambda kv: str(kv[1].get("code") or ""))]
        return {"rows": rows, "approved": sum(1 for r in rows if r["status"] == "approved"), "retired": sum(1 for r in rows if r["status"] == "retired"),
                "changed": [r for r in rows if r["changed"] and r["status"] == "approved"]}

    @app.get("/api/register.csv")
    def get_register_csv() -> Response:
        """The register as CSV (one row per approved or retired address)."""
        rows = get_register()["rows"]
        cols = ["plate", "code", "building_id", "status", "address", "number", "street", "street_id", "quartier_code", "lat", "lon", "approved_at",
                "approved_by", "computed_address", "changed"]
        return _csv([{c: r.get(c) for c in cols} for r in rows], cols)

    def change_rows() -> list[dict]:
        """Address changes: those waiting for validation (the map now gives a validated house another address) and those validated."""
        reg = ctx.store.project().register
        now = {r["building_id"]: r for r in house_rows(set(reg))} if ctx.addresses is not None else {}
        t = household_table()
        out = []
        for b, r in reg.items():
            hh = households_mod.for_building(t, b) or {}
            base = {"building_id": b, "code": r.get("code"), "address_id": now.get(b, {}).get("address_id"),
                    "plaque_name": now.get(b, {}).get("plaque_name") or households_mod.plaque_name(hh),
                    "contact_name": hh.get("contact_name") or None, "contact_phone": hh.get("contact_phone") or hh.get("commerce_phone") or None,
                    "lat": r.get("lat"), "lon": r.get("lon"), "quartier_code": r.get("quartier_code")}
            if r.get("status") == "approved" and now.get(b, {}).get("changed"):
                out.append({**base, "state": "to_validate", "before_plate": r.get("plate"), "after_plate": now[b].get("computed_plate"),
                            "before_address": r.get("address"), "after_address": now[b].get("computed_address"), "when": None, "by": None, "reason": None})
            for step in r.get("history", []):
                if step.get("action") == "corrected":
                    out.append({**base, "state": "validated", "before_plate": step.get("before_plate"), "after_plate": step.get("plate"),
                                "before_address": step.get("before_address"), "after_address": step.get("address"), "when": step.get("ts"),
                                "by": step.get("user"), "reason": step.get("reason")})
        return sorted(out, key=lambda x: (x["state"] != "to_validate", str(x["when"] or ""), str(x["before_plate"] or "")))

    @app.get("/api/register/changes")
    def get_register_changes() -> dict:
        """Address changes, without the private contacts (see ``/api/register/changes.csv`` for the list to inform families)."""
        rows = [{k: v for k, v in r.items() if k not in ("contact_name", "contact_phone")} for r in change_rows()]
        return {"rows": rows, "to_validate": sum(1 for r in rows if r["state"] == "to_validate"),
                "validated": sum(1 for r in rows if r["state"] == "validated")}

    @app.get("/api/register/changes.csv")
    def get_register_changes_csv() -> Response:
        """Address changes before / after, with the family name, contact and position: the list to inform each family (administrators)."""
        cols = ["state", "plaque_name", "contact_name", "contact_phone", "before_plate", "after_plate", "before_address", "after_address", "quartier_code",
                "lat", "lon", "address_id", "code", "building_id", "when", "by", "reason"]
        return _csv([{c: r.get(c) for c in cols} for r in change_rows()], cols)

    @app.get("/api/households/{building_id}")
    def get_household(building_id: str) -> dict:
        """The survey details of one building, contacts included (administrators only: never printed or put in the QR code)."""
        row = households_mod.for_building(household_table(), building_id)
        if row is None:
            raise HTTPException(404, "no survey record for this building (import the survey export: import-households)")
        return {**row, "plaque_name": households_mod.plaque_name(row)}

    @app.post("/api/register/approve")
    def post_register_approve(body: dict = Body(...)) -> dict:
        """Validate addresses: ``{"ids": [...]}`` or ``{"area": "R03C07"}``; ``correct`` + ``reason`` to validate a change of a
        validated address (``changed``: every such change, or those of the ids / area given).

        Only complete addresses can be validated: a house without a road, or whose quartier has no trigram, is skipped.
        """
        if ctx.addresses is None:
            raise HTTPException(409, "compute the addresses first (Addresses tab)")
        if ctx.addresses_hash != ctx.store.project().address_hash():
            raise HTTPException(409, "the addresses are out of date: compute them again before approving")
        ids = {str(i) for i in body.get("ids") or []}
        if body.get("area"):
            ids |= houses_in_area(str(body["area"]))
        if body.get("changed"):                                    # every validated address the map would now change
            rh = registered().houses
            changed = {str(b) for b, c, s in zip(rh["building_id"], rh["changed"], rh["register_status"]) if c and s == "approved"}
            ids = (ids & changed) if (body.get("ids") or body.get("area")) else changed
        if not ids:
            raise HTTPException(400, "choose houses or a work area")
        rows = house_rows(ids, reopen=bool(body.get("correct")))
        ready = {r["building_id"]: r for r in rows if r["plate"] and r["use"] != "reference"}
        skipped = sorted(set(ids) - set(ready))
        try:
            out = ctx.store.approve_addresses(ready, me(), reason=str(body.get("reason") or ""), correct=bool(body.get("correct")))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {**{k: len(v) for k, v in out.items()}, "skipped": len(skipped), "skipped_ids": skipped[:50], "status": ctx.store.status(me())}

    @app.post("/api/register/retire")
    def post_register_retire(body: dict = Body(...)) -> dict:
        """Retire approved addresses (a demolished house): ``{"ids": [...], "reason": "..."}``. The code is never given again."""
        try:
            done = ctx.store.retire_addresses(body.get("ids") or [], str(body.get("reason") or ""), me())
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"retired": len(done), "status": ctx.store.status(me())}

    @app.get("/api/plaque/{building_id}.svg")
    def get_plaque(building_id: str) -> Response:
        """The plaque of a house as SVG at real size (200 x 250 mm). A house that is not approved gets a draft plaque."""
        rows = house_rows({str(building_id)})
        if not rows:
            raise HTTPException(404, "no such house")
        r = rows[0]
        if not r["number"]:
            raise HTTPException(409, "this house has no address yet")
        svg = plaque.plaque_svg(r["plate"], r["plaque_name"], r["lat"], r["lon"], quartier=r["quartier_code"], draft=r["register_status"] != "approved")
        name = (r["plate"] or str(building_id)).replace(" ", "_").replace("(", "").replace(")", "")
        return Response(svg, media_type="image/svg+xml", headers={"Content-Disposition": f'inline; filename="plaque_{name}.svg"'})

    @app.get("/api/card/{building_id}.svg")
    def get_card(building_id: str) -> Response:
        """The address card of a house (85.6 x 54 mm), same content as the plaque; a draft until the address is validated."""
        rows = house_rows({str(building_id)})
        if not rows:
            raise HTTPException(404, "no such house")
        r = rows[0]
        if not r["number"]:
            raise HTTPException(409, "this house has no address yet")
        svg = plaque.card_svg(r["plate"], r["plaque_name"], r["lat"], r["lon"], quartier=r["quartier_code"], quartier_name=r["quartier_name"],
                              draft=r["register_status"] != "approved")
        name = (r["plate"] or str(building_id)).replace(" ", "_").replace("(", "").replace(")", "")
        return Response(svg, media_type="image/svg+xml", headers={"Content-Disposition": f'inline; filename="carte_{name}.svg"'})

    @app.get("/api/export/edges.kml")
    def export_edges_kml() -> Response:
        """Every street edge (network edges and drawn lines, deleted ones left out) as KML, to edit in Google Earth and upload again.

        One placemark per edge, named after its street (empty when it has none). A line uploaded again with the same end nodes and about
        the same length replaces the edge it came from; a changed or new line is merged as a new street.
        """
        from xml.sax.saxutils import escape

        e = get_edges()
        marks = []
        for f in e["edges"]["features"]:
            q = f["properties"]
            desc = f"street {q['street_id']}, {q['highway']}, {q['length']} m, edge {q['ref']}" if q["street_id"] is not None else f"edge {q['ref']}"
            marks.append((q["name"], desc, f["geometry"]["coordinates"]))
        for f in e["drawn"]["features"]:
            q = f["properties"]
            if not q["removed"]:
                marks.append((q["name"] or "", f"drawn line {q['ref']} ({q['file']})", f["geometry"]["coordinates"]))
        body = "".join(f"<Placemark><name>{escape(n or '')}</name><description>{escape(d)}</description><LineString><tessellate>1</tessellate>"
                       f"<coordinates>{' '.join(f'{x},{y},0' for x, y in c)}</coordinates></LineString></Placemark>" for n, d, c in marks)
        xml = (f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>{escape(ctx.store.project().name)} streets</name>'
               f"{body}</Document></kml>")
        return Response(xml, media_type="application/vnd.google-earth.kml+xml",
                        headers={"Content-Disposition": f'attachment; filename="{ctx.store.project().name}_streets.kml"'})

    def tables() -> dict:
        """The export tables of the computed network (cached until the network is computed again)."""
        if ctx.network is None:
            raise HTTPException(409, "compute the network first (Street IDs tab)")
        key = (ctx.network_hash, ctx.store.project().names.__repr__())
        if getattr(ctx, "_tables_key", None) != key:
            proj = ctx.store.project()
            base = ctx.get_base()
            edges = exports.edge_table(ctx.network, base)
            eb, _r = ctx.get_effective()                                   # parts cut off from the main network are not exported
            off = {roads_mod.edge_ref(u, v, k) for p in engine.disconnected_parts(eb) for (u, v, k) in p["edges"]}
            if off:
                edges = edges[[roads_mod.edge_ref(u, v, k) not in off for u, v, k in zip(edges["u"], edges["v"], edges["key"])]].copy()
            streets = exports.street_table(ctx.network, proj, base, edges)
            if off:
                streets = streets[streets["street_id"].isin(set(edges["street_id"].dropna().astype(int)))].copy()
            ctx._tables = {"streets": streets, "edges": exports.with_street_columns(edges, streets), "nodes": exports.node_table(ctx.network, base, edges)}
            ctx._tables_key = key
        return ctx._tables

    def serve_table(gdf: gpd.GeoDataFrame, name: str, fmt: str) -> Response:
        """A table as CSV (geometry as WKT) or GeoPackage (EPSG:4326).

        Args:
            gdf: The table.
            name: File name without extension.
            fmt: ``csv`` or ``gpkg``.

        Returns:
            The download.
        """
        if fmt == "csv":
            return Response(exports.to_csv(gdf), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
        if fmt == "gpkg":
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{name}.gpkg"
                gdf.to_file(path, layer=name, driver="GPKG")
                return Response(path.read_bytes(), media_type="application/geopackage+sqlite3",
                                headers={"Content-Disposition": f'attachment; filename="{name}.gpkg"'})
        raise HTTPException(404, f"unknown format {fmt}")

    @app.get("/api/export/{kind}.{fmt}")
    def export(kind: str, fmt: str):
        """Downloads: ``streets`` / ``edges`` / ``nodes`` / ``buildings`` / ``signs`` as ``csv`` or ``gpkg``, ``osm`` as an OSM change file, ``names`` as csv.

        Every geometry is in EPSG:4326; see ``exports`` for the columns and flags.
        """
        if kind == "names" and fmt == "csv":
            p = ctx.store.project()
            return _csv([{"street_id": k, "name": v} for k, v in sorted(p.names.items())], ["street_id", "name"])
        if kind == "reference":
            if ctx.network is None:
                raise HTTPException(409, "compute the network first (Street IDs tab)")
            return serve_table(exports.reference_table(ctx.network, ctx.store.project()), "reference", fmt)
        if kind in ("streets", "edges", "nodes"):
            return serve_table(tables()[kind], kind, fmt)
        if kind in ("buildings", "addresses", "signs"):
            if ctx.addresses is None:
                raise HTTPException(409, "compute the addresses first (Addresses tab)")
            if kind == "signs":
                return serve_table(exports.signs_table(ctx.addresses, ctx.network), "signs", fmt)
            return serve_table(exports.buildings_table(registered(), ctx.get_base().points), "buildings", fmt)
        if kind == "osm" and fmt == "osm":
            t = tables()
            path = ctx.store.project().input_dir / "streets.osm"
            if not path.exists():
                raise HTTPException(404, "the project has no input/streets.osm to compare with")
            xml, stats = exports.osm_changes(ctx.network, ctx.get_base(), ctx.store.project(), t["edges"], t["streets"], path)
            return Response(xml, media_type="application/xml", headers={"Content-Disposition": 'attachment; filename="osm_changes.osm"',
                                                                         "X-Osm-Stats": json.dumps(stats)})
        raise HTTPException(404, f"{kind}.{fmt}")

    @app.get("/")
    def index() -> FileResponse:
        """The single-page front end."""
        return FileResponse(STATIC / "index.html")

    @app.get("/simple")
    @app.get("/simple/")
    def simple() -> FileResponse:
        """The simplified page: street names and addresses only."""
        return FileResponse(STATIC / "simple.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
