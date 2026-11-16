"""The editable state of a project and the layout of its folder.

A project is **one folder** with everything needed to work on an area::

    <project>/
      project.db              SQLite database: names, reference, history, checkpoints, computed ids (see ``store``)
      input/streets.osm       the OpenStreetMap streets (used by ``setup`` to build the network)
      input/area.gpkg         polygon(s) of the area to process (optional)
      input/points.gpkg       important points: squares, intersections, facilities ... (optional)
      input/buildings.gpkg    the houses to address: points or polygons (optional)
      input/street_edits.csv  community street edits (optional)
      input/edge_edits.csv    community edge edits (optional)
      network/nodes.gpkg      the labelled street network built from the input
      network/edges.gpkg
      network/streets.csv
      exports/                CSV / GeoPackage exports

Names are keyed by the **street id after the community edits**, the id before path numbering cuts a street into parts.
It does not change when the reference or the names change; ``street_id_original`` in the computed state is the same id.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Todo R2: the app gives first-order derived names only (``3-xyz``). Projects saved with more levels are read with this cap;
# raise it to bring back ``4-3-xyz`` names.
APP_MAX_LEVELS = 1
ADDRESSING_RULE_VERSION = 2


@dataclass
class Settings:
    """Parameters of the computation. Numbering is always path numbering.

    Attributes:
        max_levels: Derivation levels of sub-street names, at most ``APP_MAX_LEVELS`` (1 = ``3-xyz`` only; 0 = no derived names).
        house_step_m: Metres per house-number step (Option 2: one metre).
        branch_step_m: Metres per sub-street-number step (Option 2: ten metres).
        addressing_rule_version: Version 2 is the approved metre-based rule. It distinguishes migrated legacy settings from later
            deliberate custom values.
        max_house_distance_m: Houses farther than this from any street get no address.
        connect_backbone: Named streets must be connected to the reference through named streets.
        plan_method: ``"auto"``, ``"exact"`` or ``"greedy"`` (see ``naming_plan``).
        time_limit_s: Time limit of the exact planner.
        second_level_max_drive_m: Second-level names (``4-3-xyz``) only for non-drivable roads and drivable roads shorter than this
            (no effect while ``APP_MAX_LEVELS`` is 1).
        own_name_max_rank: Streets of this rank or more important (0 highway, 1 primary, 2 secondary) always need a name of their
            own (todo R1).
    """

    max_levels: int = APP_MAX_LEVELS
    house_step_m: float = 1.0
    branch_step_m: float = 10.0
    addressing_rule_version: int = ADDRESSING_RULE_VERSION
    max_house_distance_m: float = 60.0
    connect_backbone: bool = True
    plan_method: str = "auto"
    time_limit_s: float = 60.0
    second_level_max_drive_m: float = 1000.0
    own_name_max_rank: int = 2

    def __post_init__(self) -> None:
        self.max_levels = max(0, min(int(self.max_levels), APP_MAX_LEVELS))
        self.house_step_m = float(self.house_step_m)
        self.branch_step_m = float(self.branch_step_m)
        self.addressing_rule_version = int(self.addressing_rule_version)
        if self.house_step_m <= 0 or self.branch_step_m <= 0:
            raise ValueError("house and branch steps must be positive")


@dataclass
class Project:
    """The state the computation needs.

    Attributes:
        root: Project folder.
        name: Display name.
        reference: ``{"lat", "lon", "node"}`` of the reference node, or None until it is chosen.
        settings: Computation parameters.
        names: Street id (after community edits) -> name given by the community.
        access: Building id -> ``{"lat", "lon"}`` of the road point chosen by hand for the numbering of that house
            (used instead of the nearest road point; also for houses too far from any road).
        roads: Missing roads: ``{"imports": [{"id", "file", "features": [...]}], "connections": {node key: target},
            "removed": [edge refs deleted by the editors], "removed_features": [drawn lines deleted], "keep": [existing edges
            that must stay although a new road replaces them]}``; see ``roads.integrate_roads``.
        node_ids: Ids of the drawn-road nodes recorded when they became stable (see ``roads.drawn_node_id``); None for a
            project not opened since, which is replayed as before. Kept by the store outside the edit history.
        replay: How the store orders the network edits (see ``Store._replay_plan``): the frozen part of the history and the
            later edits, applied one after the other. None replays the folded ``roads`` as a whole (an old database).
    """

    root: Path
    name: str = "project"
    reference: dict | None = None
    settings: Settings = field(default_factory=Settings)
    names: dict[int, str] = field(default_factory=dict)
    access: dict[str, dict] = field(default_factory=dict)
    roads: dict = field(default_factory=lambda: {"imports": [], "connections": {}, "removed": [], "removed_features": [], "keep": [], "edge_street": {}, "no_cut": [], "attrs": {}, "edge_access": {}, "point_rank": {}, "geometry_reviews": {}, "reviews": []})
    work_areas: dict = field(default_factory=dict)
    register: dict = field(default_factory=dict)  # approved (frozen) addresses by building id, see Store.approve_addresses
    node_ids: dict | None = None
    replay: dict | None = None

    @property
    def input_dir(self) -> Path:
        """Folder with the input files (OSM streets, area, points, buildings, edits)."""
        return self.root / "input"

    @property
    def network_dir(self) -> Path:
        """Folder with the labelled network built from the input."""
        return self.root / "network"

    @property
    def exports_dir(self) -> Path:
        """Folder for exports."""
        return self.root / "exports"

    def to_dict(self) -> dict:
        """The saveable state (no paths).

        Returns:
            A JSON-serialisable dict.
        """
        return {"name": self.name, "reference": self.reference, "settings": asdict(self.settings),
                "names": {str(k): v for k, v in sorted(self.names.items())},
                "access": {k: self.access[k] for k in sorted(self.access)}, "roads": self.roads, "work_areas": self.work_areas,
                "register": self.register}

    @classmethod
    def from_dict(cls, root: Path, data: dict) -> "Project":
        """Build a project state from :meth:`to_dict` output.

        Args:
            root: Project folder.
            data: Saved state.

        Returns:
            The project.
        """
        saved_settings = dict(data.get("settings") or {})
        # Projects created before the accepted Option 2 decision used 2 m per house number and 20 m per branch prefix. Only those
        # legacy defaults are migrated; custom values survive. Once version 2 is saved, a deliberate 2/20 choice also survives.
        if int(saved_settings.get("addressing_rule_version", 1)) < ADDRESSING_RULE_VERSION:
            if float(saved_settings.get("house_step_m", 2.0)) == 2.0:
                saved_settings["house_step_m"] = 1.0
            if float(saved_settings.get("branch_step_m", 20.0)) == 20.0:
                saved_settings["branch_step_m"] = 10.0
            saved_settings["addressing_rule_version"] = ADDRESSING_RULE_VERSION
        fields = {k: v for k, v in saved_settings.items() if k in Settings.__dataclass_fields__}
        return cls(root=Path(root), name=str(data.get("name", "project")), reference=data.get("reference"),
                   settings=Settings(**fields), names={int(k): str(v) for k, v in (data.get("names") or {}).items()},
                   access={str(k): dict(v) for k, v in (data.get("access") or {}).items()},
                   work_areas=dict(data.get("work_areas") or {}),
                   register=dict(data.get("register") or {}),
                   roads={"imports": list((data.get("roads") or {}).get("imports", [])),
                          "connections": dict((data.get("roads") or {}).get("connections", {})),
                          "removed": list((data.get("roads") or {}).get("removed", [])),
                          "removed_features": list((data.get("roads") or {}).get("removed_features", [])),
                          "keep": list((data.get("roads") or {}).get("keep", [])),
                          "edge_street": dict((data.get("roads") or {}).get("edge_street", {})),
                          "no_cut": list((data.get("roads") or {}).get("no_cut", [])),
                          "attrs": dict((data.get("roads") or {}).get("attrs", {})),
                          "edge_access": {str(k): (None if v is None else str(v)) for k, v in (data.get("roads") or {}).get("edge_access", {}).items()},
                          "geometry": dict((data.get("roads") or {}).get("geometry", {})),
                          "geometry_reviews": dict((data.get("roads") or {}).get("geometry_reviews", {})),
                          "node_moves": dict((data.get("roads") or {}).get("node_moves", {})),
                          "reviews": list((data.get("roads") or {}).get("reviews", [])),
                          "cuts": list((data.get("roads") or {}).get("cuts", [])),
                          "joins": list((data.get("roads") or {}).get("joins", [])),
                          "point_rank": dict((data.get("roads") or {}).get("point_rank", {})),
                          "quartier": dict((data.get("roads") or {}).get("quartier", {})),
                          "check_ok": list((data.get("roads") or {}).get("check_ok", []))})

    def state_hash(self) -> str:
        """Short hash of everything the computation depends on (to tell whether a result is stale).

        Returns:
            A hex digest.
        """
        d = self.to_dict()
        d.pop("name", None)
        d.pop("access", None)                    # the road point of a house only matters for the addresses (see address_hash)
        d.pop("work_areas", None)                # progress labels do not change geography or numbering
        d.pop("register", None)                  # approving an address freezes it; it never changes a computation
        if d.get("roads"):
            d["roads"] = {k: v for k, v in d["roads"].items() if k not in ("point_rank", "check_ok", "quartier")}   # a corrected quartier: addresses only
            if d["roads"].get("attrs"):             # "gives addresses" only matters for the addresses (see address_hash)
                d["roads"]["attrs"] = {k: {kk: vv for kk, vv in v.items() if kk != "addresses"} for k, v in d["roads"]["attrs"].items()
                                       if any(kk != "addresses" for kk in v)}      # the rank of a reference point only matters for the signs (see address_hash); a road check mark changes nothing
        if d.get("reference"):                   # who confirmed the point does not change the computation
            d["reference"] = {k: d["reference"].get(k) for k in ("lat", "lon", "node")}
        return hashlib.sha1(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]

    def address_hash(self) -> str:
        """Hash of everything the house addresses depend on (the network state and the chosen road points).

        Returns:
            A hex digest.
        """
        gives = {k: v["addresses"] for k, v in (self.roads.get("attrs") or {}).items() if "addresses" in v}
        return hashlib.sha1((self.state_hash() + json.dumps(self.access, sort_keys=True) + json.dumps(self.roads.get("point_rank", {}), sort_keys=True)
                             + (json.dumps(gives, sort_keys=True) if gives else "")
                             + (json.dumps(self.roads["quartier"], sort_keys=True) if self.roads.get("quartier") else "")).encode()).hexdigest()[:16]

    def roads_hash(self) -> str:
        """Hash of the drawn roads and their connection choices.

        Returns:
            A hex digest.
        """
        return hashlib.sha1(json.dumps({**{k: v for k, v in self.roads.items() if k not in ("point_rank", "check_ok", "quartier")}, "stable_ids": self.node_ids is not None,
                                        "replay": (self.replay or {}).get("signature")},
                                       sort_keys=True).encode()).hexdigest()[:16]
