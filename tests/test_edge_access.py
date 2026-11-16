"""Todo 2.1: drivable yes / no / unknown per edge ("car" / "foot" / null), set along a route from A to B; OSM tracks are drivable."""

import io

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

import app_helpers as H
from osmaddresssystem.app import engine, roads as roads_mod
from test_app_backend import client, compute, root, set_reference  # noqa: F401  (pytest fixtures)


def _point(dx, dy):
    lon, lat = H.lonlat(H.X0 + dx, H.Y0 + dy)
    return {"lat": lat, "lon": lon}


def _route(client, a=(0, 0), b=(240, 0)):  # noqa: F811
    r = client.post("/api/edges/access/path", json={"a": _point(*a), "b": _point(*b)})
    assert r.status_code == 200, r.text
    return r.json()


def _edge_access(net):
    return {f["properties"]["ref"]: f["properties"]["access"] for f in net["edges"]["features"]}


def _geometry(client):  # noqa: F811
    return {f["properties"]["ref"]: f["geometry"]["coordinates"] for f in client.get("/api/roads/geometry").json()["edges"]["features"]}


# ---- the engine rule ---------------------------------------------------------------------------------------

def _edges(access_rank):
    idx = pd.MultiIndex.from_tuples([(i, i + 1, 0) for i in range(len(access_rank))], names=["u", "v", "key"])
    return gpd.GeoDataFrame({"highway": [engine.RANK_HIGHWAY[r] for _, r in access_rank], "drivable_info": pd.array([None] * len(access_rank), dtype="boolean")},
                            geometry=[LineString([(i, 0), (i + 1, 0)]) for i in range(len(access_rank))], index=idx)


def test_only_car_edges_are_drivable_by_default():
    e = _edges([("car", 4), ("moto", 4), ("foot", 4), (None, 4), (None, 5), ("car", 5)])
    over = {roads_mod.edge_ref(u, v, k): a for (u, v, k), (a, _) in zip(e.index, [("car", 4), ("moto", 4), ("foot", 4), (None, 4), (None, 5), ("car", 5)]) if a}
    out = engine.apply_edge_access(e, over)
    assert [None if pd.isna(a) else a for a in out["access"]] == ["car", "moto", "foot", None, None, "car"]
    assert list(out["is_drivable"]) == [True, False, False, True, False, False]      # unknown follows the rank; rank 5 never drives


def test_motorcycle_is_never_drivable_and_has_no_switch():
    from osmaddresssystem.app.project import Settings
    e = _edges([("moto", 4), ("moto", 0)])
    out = engine.apply_edge_access(e, {roads_mod.edge_ref(0, 1, 0): "moto", roads_mod.edge_ref(1, 2, 0): "moto"})
    assert list(out["is_drivable"]) == [False, False]
    assert "moto_is_drivable" not in Settings.__dataclass_fields__                    # decided 5 November: only car is drivable


def test_old_drivable_flags_read_as_car_or_foot():
    e = _edges([(None, 4), (None, 4), (None, 4)])
    e["drivable_info"] = pd.array([True, False, None], dtype="boolean")
    assert [None if pd.isna(a) else a for a in engine.apply_edge_access(e, None)["access"]] == ["car", "foot", None]


# ---- the A to B tool -----------------------------------------------------------------------------------------

def test_route_from_a_to_b_follows_existing_edges(client):  # noqa: F811
    res = _route(client)
    best = res["routes"][0]
    assert len(best["refs"]) == 2 and abs(best["length_m"] - 240) < 1
    assert len(res["routes"]) == 2 and res["routes"][1]["length_m"] > best["length_m"]  # an other route around a block


def test_a_and_b_on_the_same_node_are_refused(client):  # noqa: F811
    r = client.post("/api/edges/access/path", json={"a": _point(0, 0), "b": _point(3, 2)})
    assert r.status_code == 400


def test_classifying_a_stretch_changes_access_only(client):  # noqa: F811
    set_reference(client)
    before = compute(client)
    shapes = _geometry(client)
    res = _route(client)
    refs = res["routes"][0]["refs"]
    r = client.post("/api/edges/access", json={"refs": refs, "access": "foot", "revision": res["revision"]})
    assert r.status_code == 200 and r.json()["changed"] == 2
    after = compute(client)
    access = _edge_access(after)
    assert all(access[ref] == "foot" for ref in refs)
    assert all(access[ref] != "foot" for ref in access if ref not in refs)
    assert _geometry(client) == shapes                                                  # no road moved or split
    assert sorted(f["properties"]["ref"] for f in after["edges"]["features"]) == sorted(f["properties"]["ref"] for f in before["edges"]["features"])
    csv = pd.read_csv(io.StringIO(client.get("/api/export/edges.csv").text))
    assert "access" in csv.columns and (csv["access"] == "foot").sum() >= 2 and not csv.loc[csv["access"] == "foot", "drivable"].any()


def test_classification_is_one_undo_step_and_survives_a_restart(client, root):  # noqa: F811
    res = _route(client)
    refs = res["routes"][0]["refs"]
    client.post("/api/edges/access", json={"refs": refs, "access": "foot", "revision": res["revision"]})
    from fastapi.testclient import TestClient
    from osmaddresssystem.app.server import create_app
    reopened = TestClient(create_app(root, auth_enabled=False, auto_compute=False))
    from osmaddresssystem.app.store import Store
    assert all(Store(root).project().roads["edge_access"][ref] == "foot" for ref in refs)
    assert reopened.post("/api/undo").status_code == 200
    assert all(ref not in Store(root).project().roads.get("edge_access", {}) for ref in refs)


def test_a_classified_road_keeps_its_access_when_a_new_road_splits_it(client):  # noqa: F811
    set_reference(client)
    res = _route(client, (0, 0), (120, 0))
    refs = res["routes"][0]["refs"]
    assert len(refs) == 1
    client.post("/api/edges/access", json={"refs": refs, "access": "foot", "revision": res["revision"]})
    hit = client.post("/api/roads/snap", json={**_point(60, 0), "node_m": 2, "max_m": 12}).json()["target"]
    assert hit["type"] == "edge"
    far = _point(60, -100)
    r = client.post("/api/roads/draw", json={"coords": [[far["lon"], far["lat"]], [hit["lon"], hit["lat"]]], "start": None, "end": hit, "name": "Branch"})
    assert r.status_code == 200, r.text
    net = compute(client)
    assert client.app.state.ctx.get_effective()[1].report["split_edges"] >= 1
    lon0, lat0 = H.lonlat(H.X0 + 1, H.Y0)
    lon1, lat1 = H.lonlat(H.X0 + 119, H.Y0)
    pieces = [f for f in net["edges"]["features"] if f["geometry"]["type"] == "LineString"
              and all(min(lat0, lat1) - 1e-5 <= c[1] <= max(lat0, lat1) + 1e-5 and lon0 - 2e-5 <= c[0] <= lon1 + 2e-5 for c in f["geometry"]["coordinates"])]
    assert len(pieces) == 2
    assert [p["properties"]["access"] for p in pieces] == ["foot", "foot"]


def test_the_kept_pieces_of_a_partly_deleted_road_keep_its_access(client):  # noqa: F811
    from test_road_sections import cut_request
    set_reference(client)
    res = _route(client, (0, 0), (120, 0))
    ref = res["routes"][0]["refs"][0]
    client.post("/api/edges/access", json={"refs": [ref], "access": "foot", "revision": res["revision"]})
    body, _idx, _line = cut_request(client, ref=ref)
    assert client.post("/api/roads/cut", json=body).status_code == 200
    base, _ = client.app.state.ctx.get_effective()
    pieces = base.edges[[isinstance(x, str) and x.split("|")[0] == ref for x in base.edges.get("ref_lineage", [None] * len(base.edges))]]
    assert len(pieces) == 4                                                          # two kept pieces, both directions
    access = {f["properties"]["ref"]: f["properties"]["access"] for f in compute(client)["edges"]["features"]}
    kept = {roads_mod.edge_ref(*i) for i in pieces.index}
    assert all(access[r] == "foot" for r in kept if r in access) and kept & set(access)


def test_a_stale_route_is_refused(client):  # noqa: F811
    res = _route(client)
    client.post("/api/edges/access", json={"refs": res["routes"][0]["refs"], "access": "car", "revision": res["revision"]})
    r = client.post("/api/edges/access", json={"refs": res["routes"][0]["refs"], "access": "foot", "revision": res["revision"]})
    assert r.status_code == 409


def test_bad_access_value_is_refused(client):  # noqa: F811
    res = _route(client)
    r = client.post("/api/edges/access", json={"refs": res["routes"][0]["refs"], "access": "truck", "revision": res["revision"]})
    assert r.status_code == 400
    r = client.post("/api/edges/access", json={"refs": res["routes"][0]["refs"], "access": "moto", "revision": res["revision"]})
    assert r.status_code == 400                                                       # only drivable yes / no / unknown


# ---- OSM tracks ------------------------------------------------------------------------------------------------

def test_tracks_are_rank_4_and_drivable():
    from osmaddresssystem import path_numbering
    from osmaddresssystem.default_values import DEFAULT_NON_DRIVABLE_HIGHWAYS
    assert path_numbering.highway_rank("track") == 4 and "track" not in DEFAULT_NON_DRIVABLE_HIGHWAYS
    assert path_numbering.highway_rank("['track', 'path']") == 4                     # the better rank wins, as before


def test_tracks_stored_as_not_drivable_by_an_older_network_now_drive(tmp_path):
    idx = pd.MultiIndex.from_tuples([(0, 1, 0), (1, 2, 0), (2, 3, 0), (3, 4, 0)], names=["u", "v", "key"])
    e = gpd.GeoDataFrame({"highway": ["track", "path", "['track', 'path']", "residential"], "is_drivable": [False, False, False, True],
                          "osmid": ["1", "2", "3", "4"], "paved": pd.array([None] * 4, dtype="boolean")},
                         geometry=[LineString([(i, 0), (i + 1, 0)]) for i in range(4)], index=idx)
    flags = engine.add_flag_columns(e, tmp_path / "none.osm")
    assert list(flags["drivable_info"]) == [True, False, False, True]                 # a track mixed with a path stays as stored
    out = engine.apply_edge_access(flags, {roads_mod.edge_ref(0, 1, 0): "foot"})
    assert list(out["is_drivable"]) == [False, False, False, True]                    # a mapper's "no" still wins


def test_street_drivable_dropdown_still_sets_every_edge_of_the_street(client):  # noqa: F811
    set_reference(client)
    net = compute(client)
    street = net["streets"]["features"][0]["properties"]["original"]
    client.post("/api/streets/attrs", json={"original": street, "drivable": False})
    access = [f["properties"]["access"] for f in compute(client)["edges"]["features"] if f["properties"]["original"] == street]
    assert access and all(a == "foot" for a in access)
