"""Automatic checks of the road network of one work area (the Road check list of the Edit streets tab).

The checks run on the current network, with every edit applied (see ``engine.effective_base``). They only report: nothing
is changed. Each problem has a stable id (its kind and position), so an editor can mark it "OK as is" (``roads.check_ok``)
and it is not listed again while it stays where it is.

Kinds:

* ``gap``: a road end stops close to another road (``GAP_M``) without being connected to it.
* ``free_end``: an end of a drawn road that touches nothing (may be a real dead end).
* ``stub``: a very short section (``STUB_M``), often left by a click next to a junction.
* ``overlap``: two sections lying on top of each other over some length (a duplicate, or a road drawn over another).
* ``crossing``: two sections cross without a junction (routing cannot turn there; a bridge is fine).
* ``isolated``: a part of the network not connected to the main part.
* ``drivable_unknown``: the sections of a street whose drivable value is not set yet.
* ``skipped``: a saved edit that does not apply to the network (it must be redone or removed).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.ops import nearest_points, substring, unary_union

from . import roads as roads_mod

GAP_M = 10.0
"""A free end closer than this to another road is reported as a gap."""

STUB_M = 5.0
"""Sections shorter than this are reported."""

OVERLAP_BUFFER_M = 1.5
"""Two sections closer than this to each other over a length count as overlapping."""

OVERLAP_MIN_M = 10.0
"""An overlap is reported from this length (or from half of the shorter section, at least 3 m)."""

JUNCTION_M = 1.0
"""A crossing this close to an end of either section is a junction, not a crossing."""

ORDER = ["skipped", "gap", "overlap", "crossing", "isolated", "stub", "free_end", "drivable_unknown"]
"""Most urgent first."""


def _wgs(geom, crs):
    return gpd.GeoSeries([geom], crs=crs).to_crs(4326).iloc[0]


def _skipped(project, report: dict, crs) -> list[tuple]:
    """The saved edits that do not apply, located from what they saved: ``(geometry, refs, events, what)``."""
    rd = project.roads
    tr = Transformer.from_crs(4326, crs, always_xy=True)

    def line(coords):
        return LineString([tr.transform(*p) for p in coords]) if coords and len(coords) >= 2 else None

    out, seen = [], set()
    for item in report.get("stale_cuts", []) or []:
        item = str(item)
        if item in seen:
            continue
        seen.add(item)
        if item.startswith("connection:"):
            target = item.split(":", 1)[1]
            ops = [j for j in rd.get("joins", []) if j.get("target_ref") == target]
            for j in ops[:1]:
                g = line(j.get("coords"))
                if g is not None:
                    out.append((g.interpolate(min(float(j.get("target_m", 0)), g.length)), [target],
                                sorted({int(o["_event_id"]) for o in ops if o.get("_event_id")}), "connection"))
            continue
        ops = [c for c in rd.get("cuts", []) if c.get("ref") == item]
        if ops:
            g = line(ops[0].get("coords"))
            if g is not None:
                a, b = float(ops[0].get("start_m", 0)), float(ops[0].get("end_m", g.length))
                part = substring(g, max(0.0, a), min(g.length, b))
                out.append((part if part.length > 0 else g, [item], sorted({int(o["_event_id"]) for o in ops if o.get("_event_id")}),
                            "deleted portion"))
            continue
        coords = rd.get("geometry", {}).get(item)
        if coords:
            out.append((line(coords), [item], [], "reshape"))
    for lost in report.get("lost_edits", []) or []:
        if str(lost.get("ref")) in seen:
            for geom, refs, events, what in out:
                if lost["ref"] in refs and lost["event"] not in events:
                    events.append(lost["event"])
    return out


def check_roads(base, report: dict, project, area=None) -> list[dict]:
    """The problems of the road network inside ``area`` (WGS84 polygon; None: everywhere).

    Args:
        base: The effective base data (``engine.effective_base``), projected.
        report: The report of the road integration (``stale_cuts``, ``lost_edits``).
        project: The project (saved cuts and connections, ``roads.check_ok``).
        area: Polygon of the work area in WGS84, or None.

    Returns:
        One dict per problem, most urgent first: ``id``, ``kind``, ``refs``, ``geometry`` (GeoJSON, WGS84), ``lon``/``lat``
        (where to look), ``ok`` (marked "OK as is") and the measure of the kind (``distance_m``, ``length_m``, ``events``...).
    """
    edges = base.edges
    crs = edges.crs
    und = edges[[u < v and k < roads_mod.SYNTHETIC_KEY for u, v, k in edges.index]]
    keys = list(und.index)
    geoms = list(und.geometry)
    refs = [roads_mod.edge_ref(*i) for i in keys]
    osmids = [str(x) for x in und["osmid"]] if "osmid" in und else [""] * len(keys)
    zone = gpd.GeoSeries([area], crs=4326).to_crs(crs).iloc[0].buffer(5) if area is not None else None
    ok = set(project.roads.get("check_ok", []))
    issues: list[dict] = []

    def add(kind, geom, rs, **info):
        if geom is None or geom.is_empty or (zone is not None and not zone.intersects(geom)):
            return
        where = geom if geom.geom_type == "Point" else geom.interpolate(0.5, normalized=True) if geom.geom_type == "LineString" \
            else geom.representative_point()
        w = _wgs(where, crs)
        iid = f"{kind}:{w.x:.5f}:{w.y:.5f}"
        if any(i["id"] == iid for i in issues):
            return
        issues.append({"id": iid, "kind": kind, "refs": list(rs), "lon": round(w.x, 7), "lat": round(w.y, 7), "ok": iid in ok,
                       "geometry": shapely.geometry.mapping(shapely.set_precision(_wgs(geom, crs), 1e-7)),
                       **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in info.items()}})

    incident: dict = {}
    for i, (u, v, _k) in enumerate(keys):
        incident.setdefault(u, []).append(i)
        incident.setdefault(v, []).append(i)
    tree = shapely.STRtree(geoms)
    node_geom = base.nodes.geometry

    for n, own in incident.items():                                            # free ends: gaps, unconnected drawn ends
        if len(own) != 1 or n not in node_geom.index:
            continue
        p = node_geom.loc[n]
        best = None
        for j in tree.query(p.buffer(GAP_M)):
            j = int(j)
            if j in incident[n] or n in keys[j][:2]:
                continue
            d = geoms[j].distance(p)
            if best is None or d < best[1]:
                best = (j, d)
        if best is not None and 0.5 < best[1] <= GAP_M:
            q = nearest_points(geoms[best[0]], p)[0]
            add("gap", LineString([p, q]), [refs[own[0]], refs[best[0]]], distance_m=float(best[1]))
        elif osmids[own[0]].startswith("road"):
            add("free_end", p, [refs[own[0]]])

    for i, g in enumerate(geoms):                                               # short sections
        if g.length < STUB_M:
            add("stub", g, [refs[i]], length_m=float(g.length))

    for i, g in enumerate(geoms):                                               # overlaps and crossings
        for j in tree.query(g.buffer(OVERLAP_BUFFER_M)):
            j = int(j)
            if j <= i:
                continue
            h = geoms[j]
            shared = set(keys[i][:2]) & set(keys[j][:2])
            common = g.intersection(h.buffer(OVERLAP_BUFFER_M))
            if common.length >= max(3.0, min(OVERLAP_MIN_M, 0.5 * min(g.length, h.length))) and common.length > 2 * OVERLAP_BUFFER_M * len(shared):
                add("overlap", common if common.geom_type in ("LineString", "MultiLineString") else g, [refs[i], refs[j]],
                    length_m=float(common.length))
                continue
            if not g.crosses(h):
                continue
            hit = g.intersection(h)
            points = [hit] if hit.geom_type == "Point" else [x for x in getattr(hit, "geoms", []) if x.geom_type == "Point"]
            ends = [Point(c) for c in (g.coords[0], g.coords[-1], h.coords[0], h.coords[-1])]
            for pt in points:
                if min(pt.distance(e) for e in ends) > JUNCTION_M:
                    add("crossing", pt, [refs[i], refs[j]])

    from .engine import disconnected_parts                                     # parts not connected to the main network
    for part in disconnected_parts(base):
        lines = [edges.loc[i].geometry for i in part["edges"] if i[0] < i[1]]
        if lines:
            add("isolated", unary_union(lines), [roads_mod.edge_ref(*i) for i in part["edges"] if i[0] < i[1]][:50],
                length_m=float(part["length_m"]))

    if "access" in und:                                                         # drivable not set, one item per street
        unknown = [i for i, value in enumerate(und["access"]) if value is None or pd.isna(value)]
        streets: dict = {}
        for i in unknown:
            sid = und["street_id"].iloc[i]
            streets.setdefault(None if pd.isna(sid) else int(sid), []).append(i)
        for sid, idx in streets.items():
            inside = [i for i in idx if zone is None or zone.intersects(geoms[i])]
            if inside:
                add("drivable_unknown", MultiLineString([geoms[i] for i in inside]) if len(inside) > 1 else geoms[inside[0]],
                    [refs[i] for i in inside], length_m=float(sum(geoms[i].length for i in inside)), street_id=sid)

    for geom, rs, events, what in _skipped(project, report, crs):              # saved edits that do not apply
        add("skipped", geom, rs, events=events, what=what)

    issues.sort(key=lambda x: (x["ok"], ORDER.index(x["kind"]), -float(x.get("length_m") or x.get("distance_m") or 0)))
    return issues


def area_polygon(project, area_id: str | None):
    """The WGS84 polygon of a work area or quartier of the project, by id (None when not found or not given)."""
    if not area_id:
        return None
    areas = project.work_areas or {}
    for f in list(areas.get("features", [])) + list((areas.get("quartiers") or {}).get("features", [])):
        if str((f.get("properties") or {}).get("id")) == str(area_id) and f.get("geometry"):
            return shape(f["geometry"])
    return None
