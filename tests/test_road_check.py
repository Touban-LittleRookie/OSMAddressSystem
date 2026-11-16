"""The road check of the Edit streets tab: gaps, overlaps, crossings, short sections, free ends, edits that do not apply."""

import geopandas as gpd
from shapely.geometry import Point

import app_helpers as H
from test_app_backend import client, root  # noqa: F401  (pytest fixtures)


def _wgs(points, crs):
    return [[p.x, p.y] for p in gpd.GeoSeries(points, crs=crs).to_crs(4326)]


def _draw(client, points, **ends):
    crs = client.app.state.ctx.get_base().crs
    r = client.post("/api/roads/draw", json={"coords": _wgs(points, crs), "start": {"type": "none"}, "end": {"type": "none"}, **ends})
    assert r.status_code == 200, r.text


def _kinds(client, area=None):
    r = client.get("/api/roads/check" + (f"?area={area}" if area else ""))
    assert r.status_code == 200, r.text
    return r.json()


def test_each_kind_of_problem_is_found_where_it_is(client):  # noqa: F811
    assert not {k for k in _kinds(client)["counts"] if k != "drivable_unknown"}            # the grid is clean
    _draw(client, [Point(H.X0 + 60, H.Y0 + 30), Point(H.X0 + 60, H.Y0 + 116)])              # stops 4 m below the next street
    _draw(client, [Point(H.X0 + 130, H.Y0 + 0.5), Point(H.X0 + 200, H.Y0 + 0.5)])           # drawn on top of a street
    _draw(client, [Point(H.X0 + 300, H.Y0 - 40), Point(H.X0 + 300, H.Y0 + 40)])             # crosses a street, no junction
    _draw(client, [Point(H.X0 + 430, H.Y0 + 60), Point(H.X0 + 432, H.Y0 + 60)])             # a 2 m piece on its own
    issues = _kinds(client)["issues"]
    by = {}
    for issue in issues:
        by.setdefault(issue["kind"], []).append(issue)
    gap = by["gap"][0]
    assert 3 < gap["distance_m"] < 5
    assert any(issue["length_m"] > 50 for issue in by["overlap"])
    crossing = min(by["crossing"], key=lambda issue: abs(issue["lat"]))
    assert crossing["geometry"]["type"] == "Point"
    assert by["stub"] and by["isolated"] and by["free_end"]
    assert issues[0]["kind"] in ("gap", "overlap")                                          # most urgent first


def test_an_edit_that_does_not_apply_is_listed_with_its_number(client):  # noqa: F811
    store = client.app.state.ctx.store
    base = client.app.state.ctx.get_base()
    line = [Point(H.X0 + 10, H.Y0), Point(H.X0 + 50, H.Y0)]
    store.add_road_cut({"id": "c1", "ref": "1-999999-0", "coords": _wgs(line, base.crs), "start_m": 5.0, "end_m": 20.0},
                       store.revision(), "mapper")
    skipped = [i for i in _kinds(client)["issues"] if i["kind"] == "skipped"]
    assert len(skipped) == 1 and skipped[0]["what"] == "deleted portion" and skipped[0]["events"]
    assert abs(skipped[0]["lat"] - _wgs([Point(H.X0 + 30, H.Y0)], base.crs)[0][1]) < 1e-4       # where the deleted portion was


def test_ok_as_is_hides_a_problem_until_it_is_listed_again_and_is_one_undo_step(client):  # noqa: F811
    _draw(client, [Point(H.X0 + 60, H.Y0 + 30), Point(H.X0 + 60, H.Y0 + 116)])
    gap = next(i for i in _kinds(client)["issues"] if i["kind"] == "gap")
    stale = client.get("/api/project").json()["stale"]
    assert client.post("/api/roads/check/ok", json={"ids": [gap["id"]]}).status_code == 200
    after = _kinds(client)
    assert "gap" not in after["counts"] and after["ok"] == 1
    assert next(i for i in after["issues"] if i["id"] == gap["id"])["ok"]
    assert client.get("/api/project").json()["stale"] == stale                                  # marking changes neither roads nor ids
    client.post("/api/undo")
    assert _kinds(client)["counts"]["gap"] == 1
    client.post("/api/redo")
    client.post("/api/roads/check/ok", json={"ids": [gap["id"]], "ok": False})
    assert _kinds(client)["counts"]["gap"] == 1


def test_the_check_of_a_work_area_lists_only_its_problems(client):  # noqa: F811
    _draw(client, [Point(H.X0 + 60, H.Y0 + 30), Point(H.X0 + 60, H.Y0 + 116)])              # a gap in the south-west
    store = client.app.state.ctx.store
    areas = client.post("/api/work-areas/grid", json={"cell_m": 250, "revision": store.revision()}).json()["areas"]["features"]
    crs = client.app.state.ctx.get_base().crs
    lon, lat = _wgs([Point(H.X0 + 60, H.Y0 + 116)], crs)[0]
    from shapely.geometry import shape
    inside = next(f["properties"]["id"] for f in areas if shape(f["geometry"]).contains(Point(lon, lat)))
    elsewhere = next(f["properties"]["id"] for f in areas if not shape(f["geometry"]).buffer(0.0005).contains(Point(lon, lat)))
    assert _kinds(client, inside)["counts"].get("gap") == 1
    assert "gap" not in _kinds(client, elsewhere)["counts"]
    assert client.get("/api/roads/check?area=nowhere").status_code == 404
