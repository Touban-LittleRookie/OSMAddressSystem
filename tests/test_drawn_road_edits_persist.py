"""Edits saved on a road stay applied when roads are drawn afterwards.

1. A portion deleted to be redrawn stays deleted when the new road is drawn between the cut ends.
2. A reshape of a drawn road stays when another road touching the network is drawn (the node ids no longer shift).
"""

import geopandas as gpd
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Point

import app_helpers as H
from osmaddresssystem.app.roads import cuts_before_drawn_roads, edge_ref, integrate_roads
from osmaddresssystem.app.server import create_app
from test_app_backend import client, root  # noqa: F401  (pytest fixtures)


def _wgs(points, crs):
    return [[p.x, p.y] for p in gpd.GeoSeries(points, crs=crs).to_crs(4326)]


def _section_at(base, x, y):
    p = Point(x, y)
    return min((i for i in base.edges.index if i[0] < i[1]), key=lambda i: base.edges.loc[i].geometry.distance(p))


def _node_at(base, x, y):
    p = Point(x, y)
    return min(base.nodes.index, key=lambda n: base.nodes.geometry.loc[n].distance(p))


def test_only_cuts_on_sections_created_or_targeted_by_a_join_wait_for_that_join():
    join = {"id": "join-1", "source_node": 1, "ref": "1-4-0", "target_ref": "2-3-0", "order": 1}
    exact_target = {"ref": "2-3-0", "order": 2}
    created_source = {"ref": "2-4-0", "order": 3}
    adjacent = {"ref": "3-5-0", "order": 4}  # shares one junction node, but the join did not create this section
    early, late = cuts_before_drawn_roads([exact_target, created_source, adjacent], [join])
    assert [cut["ref"] for cut in early] == ["3-5-0"]
    assert [cut["ref"] for cut in late] == ["2-3-0", "2-4-0"]


def test_targeting_a_saved_drawn_node_recreates_its_split_on_the_base_road(client):  # noqa: F811
    base, _ = client.app.state.ctx.get_effective()
    idx = next(i for i in base.edges.index if i[0] < i[1])
    line = base.edges.loc[idx].geometry
    on_road = line.interpolate(line.length / 2)
    dx, dy = line.coords[-1][0] - line.coords[0][0], line.coords[-1][1] - line.coords[0][1]
    norm = (dx * dx + dy * dy) ** .5
    saved = Point(on_road.x - dy / norm * 4, on_road.y + dx / norm * 4)
    free = Point(saved.x - dy / norm * 20, saved.y + dx / norm * 20)
    saved_wgs, free_wgs = _wgs([saved, free], base.crs)
    node = -123456789
    feature = {'id': 0, 'key': '1:0', 'coords': [saved_wgs, free_wgs], 'name': None, 'highway': None,
               'start': {'type': 'node', 'node': node, 'lon': saved_wgs[0], 'lat': saved_wgs[1]},
               'end': {'type': 'none'}}
    result = integrate_roads(base.nodes, base.edges, base.streets, None, [feature], node_ids={})
    incident = [i for i in result.edges.index if i[0] < i[1] and node in i[:2]]
    assert len(incident) == 3  # two retained base-road sides plus the new road
    assert sum(str(result.edges.loc[i].osmid).startswith('road1:') for i in incident) == 1
    # The base road is split for topology, but its two retained sides meet at
    # the reviewed junction.  Replaying a later connection must not pull that
    # junction (and the surrounding corrected roads) back onto the old line.
    assert result.nodes.geometry.loc[node].distance(saved) < .01
    for edge_idx in incident:
        geometry = result.edges.loc[edge_idx].geometry
        endpoint = Point(geometry.coords[0 if edge_idx[0] == node else -1])
        assert endpoint.distance(saved) < .01


def test_a_deleted_portion_stays_deleted_when_the_new_road_is_drawn_between_the_cut_ends(client, root):  # noqa: F811
    base, _ = client.app.state.ctx.get_effective()
    idx = _section_at(base, H.X0 + 180, H.Y0)
    line = base.edges.loc[idx].geometry
    a, b = line.interpolate(line.length / 3), line.interpolate(line.length * 2 / 3)
    body = {"ref": edge_ref(*idx), "points": _wgs([a, b], base.crs), "revision": client.app.state.ctx.store.revision()}
    assert client.post("/api/roads/cut", json=body).status_code == 200
    cut, _ = client.app.state.ctx.get_effective()
    p, q = _node_at(cut, a.x, a.y), _node_at(cut, b.x, b.y)
    assert p < 0 and q < 0                                                      # the cut ends
    detour = Point((a.x + b.x) / 2, (a.y + b.y) / 2 + 15)
    r = client.post("/api/roads/draw", json={"coords": _wgs([a, detour, b], base.crs),
                                             "start": {"type": "node", "node": int(p)}, "end": {"type": "node", "node": int(q)}})
    assert r.status_code == 200, r.text
    for c in (client, TestClient(create_app(root, auth_enabled=False, auto_compute=False))):
        after, res = c.app.state.ctx.get_effective()
        assert not res.report.get("stale_cuts")                                # the deletion still applies
        middle = LineString([a, b]).buffer(1)
        old = [i for i in after.edges.index if not str(after.edges.loc[i].osmid).startswith("road")]
        assert not [i for i in old if after.edges.loc[i].geometry.intersection(middle).length > 1.5]   # and the old portion is gone (the kept parts touch its ends)
        drawn = [i for i in after.edges.index if i[0] < i[1] and str(after.edges.loc[i].osmid).startswith("road")]
        assert {n for i in drawn for n in i[:2]} >= {p, q}                       # the new road starts and ends at the cut ends


def test_a_reshaped_drawn_road_keeps_its_shape_when_another_road_is_drawn(client):  # noqa: F811
    base, _ = client.app.state.ctx.get_effective()
    one = [Point(H.X0 + 60, H.Y0 + 30), Point(H.X0 + 60, H.Y0 + 90)]           # inside a block: both ends stay free
    assert client.post("/api/roads/draw", json={"coords": _wgs(one, base.crs)}).status_code == 200
    drawn, _ = client.app.state.ctx.get_effective()
    idx = next(i for i in drawn.edges.index if i[0] < i[1] and str(drawn.edges.loc[i].osmid).startswith("road"))
    old = drawn.edges.loc[idx].geometry
    bend = Point(H.X0 + 70, H.Y0 + 60)
    shape = [Point(old.coords[0]), bend, Point(old.coords[-1])]
    r = client.post("/api/roads/geometry", json={"ref": edge_ref(*idx), "coords": _wgs(shape, base.crs),
                                                 "revision": client.app.state.ctx.store.revision()})
    assert r.status_code == 200, r.text
    two = [Point(H.X0 + 300, H.Y0 + 60), Point(H.X0 + 300, H.Y0 + 2)]          # ends on a road between two junctions: splits it
    assert client.post("/api/roads/draw", json={"coords": _wgs(two, base.crs)}).status_code == 200
    after, res = client.app.state.ctx.get_effective()
    assert res.report["split_edges"] >= 1
    assert idx in after.edges.index                                             # same section, same reference
    assert after.edges.loc[idx].geometry.distance(bend) < .01                  # still reshaped


def test_redrawing_a_deleted_drawn_road_is_not_deleted_by_its_old_cut(client, root):  # noqa: F811
    base, _ = client.app.state.ctx.get_effective()
    points = [Point(H.X0 + 60, H.Y0 + 30), Point(H.X0 + 60, H.Y0 + 90)]
    coords = _wgs(points, base.crs)
    assert client.post('/api/roads/draw', json={'coords': coords}).status_code == 200

    drawn, _ = client.app.state.ctx.get_effective()
    idx = next(i for i in drawn.edges.index if i[0] < i[1] and str(drawn.edges.loc[i].osmid) == 'road1:0')
    line = drawn.edges.loc[idx].geometry
    cut = {'ref': edge_ref(*idx), 'points': _wgs([Point(line.coords[0]), Point(line.coords[-1])], drawn.crs),
           'revision': client.app.state.ctx.store.revision()}
    response = client.post('/api/roads/cut', json=cut)
    assert response.status_code == 200, response.text
    deleted, _ = client.app.state.ctx.get_effective()
    assert not any(str(value) == 'road1:0' for value in deleted.edges.osmid)

    assert client.post('/api/roads/draw', json={'coords': coords}).status_code == 200
    for current in (client, TestClient(create_app(root, auth_enabled=False, auto_compute=False))):
        restored, report = current.app.state.ctx.get_effective()
        assert not report.report.get('stale_cuts')
        recreated = restored.edges[restored.edges.osmid.astype(str) == 'road2:0']
        assert len(recreated) == 2
        assert recreated.geometry.iloc[0].hausdorff_distance(LineString(points)) < .01


def test_redrawing_a_deleted_drawn_road_from_a_reshaped_road_changes_no_other_road(client, root):  # noqa: F811
    """Loryan's case of 9 November: a drawn road starting on a reshaped road is deleted, then drawn again along the same
    path from that reshaped road. The deleted road must not come back and the reshape must stay; nothing else changes."""
    ctx = client.app.state.ctx

    def snap(point, crs):
        lon, lat = _wgs([point], crs)[0]
        return client.post("/api/roads/snap", json={"lat": lat, "lon": lon, "node_m": 1.0}).json()["target"]

    def sections(c):
        b, res = c.app.state.ctx.get_effective()
        return {edge_ref(*i): b.edges.loc[i].geometry for i in b.edges.index if i[0] < i[1]}, b, res

    base, _ = ctx.get_effective()
    start, top = Point(H.X0 + 170, H.Y0), Point(H.X0 + 170, H.Y0 + 60)
    assert client.post("/api/roads/draw", json={"coords": _wgs([start, top], base.crs), "start": snap(start, base.crs),
                                                "end": {"type": "none"}}).status_code == 200
    drawn = ctx.get_effective()[0]
    node = _node_at(drawn, start.x, start.y)
    east = next(i for i in drawn.edges.index if i[0] < i[1] and node in i[:2] and not str(drawn.edges.loc[i].osmid).startswith("road")
                and drawn.edges.loc[i].geometry.distance(Point(H.X0 + 200, H.Y0)) < 1)
    line = drawn.edges.loc[east].geometry
    bend = Point(H.X0 + 205, H.Y0 - 8)
    shape = [Point(line.coords[0]), bend, Point(line.coords[-1])]
    assert client.post("/api/roads/geometry", json={"ref": edge_ref(*east), "coords": _wgs(shape, base.crs),
                                                    "revision": ctx.store.revision()}).status_code == 200
    reshaped = ctx.get_effective()[0]
    road = next(i for i in reshaped.edges.index if i[0] < i[1] and str(reshaped.edges.loc[i].osmid) == "road1:0")
    r = client.post("/api/roads/cut", json={"ref": edge_ref(*road), "points": _wgs([start, top], base.crs), "whole": True,
                                            "revision": ctx.store.revision()})
    assert r.status_code == 200, r.text
    before, _, _ = sections(client)
    assert not any(str(v) == "road1:0" for v in ctx.get_effective()[0].edges.osmid)

    again = Point(H.X0 + 172, H.Y0 + 0.1)                                     # 2 m along the reshaped road, as clicked
    target = snap(again, base.crs)
    assert target["type"] == "edge"
    r = client.post("/api/roads/draw", json={"coords": _wgs([again, Point(H.X0 + 168, H.Y0 + 30), Point(H.X0 + 169, H.Y0 + 60)], base.crs),
                                             "start": target, "end": {"type": "none"}})
    assert r.status_code == 200, r.text
    for current in (client, TestClient(create_app(root, auth_enabled=False, auto_compute=False))):
        after, b, res = sections(current)
        assert not res.report.get("stale_cuts") and not res.report.get("lost_edits")
        assert not any(str(v) == "road1:0" for v in b.edges.osmid)                    # the deleted road stays deleted
        split = {ref for ref in before if ref not in after}
        assert len(split) <= 1                                                       # only the section the new road starts on
        for ref in set(before) - split:
            assert after[ref].equals(before[ref]), ref                              # every other road is exactly as before
        pieces = [g for ref, g in after.items() if ref not in before and not any(
            str(b.edges.loc[i].osmid).startswith("road2") for i in b.edges.index if i[0] < i[1] and edge_ref(*i) == ref)]
        assert min(g.distance(bend) for g in pieces) < .01                           # the reshape is still there


def test_a_prolongation_uses_the_saved_position_of_a_moved_drawn_node(client, root):  # noqa: F811
    base, _ = client.app.state.ctx.get_effective()
    original = [Point(H.X0 + 60, H.Y0 + 30), Point(H.X0 + 60, H.Y0 + 90)]
    assert client.post('/api/roads/draw', json={'coords': _wgs(original, base.crs),
                                                'start': {'type': 'none'}, 'end': {'type': 'none'}}).status_code == 200
    drawn, _ = client.app.state.ctx.get_effective()
    idx = next(i for i in drawn.edges.index if i[0] < i[1] and str(drawn.edges.loc[i].osmid) == 'road1:0')
    line = drawn.edges.loc[idx].geometry
    start_node = idx[0]
    if Point(line.coords[0]).distance(original[0]) > Point(line.coords[-1]).distance(original[0]):
        start_node = idx[1]
        shape = [original[1], Point(H.X0 + 70, H.Y0 + 30)]
    else:
        shape = [Point(H.X0 + 70, H.Y0 + 30), original[1]]
    moved = Point(H.X0 + 70, H.Y0 + 30)
    ref = edge_ref(*idx)
    client.app.state.ctx.store.set_road_stretch(
        {ref: _wgs(shape, base.crs)}, {str(start_node): _wgs([moved], base.crs)[0]},
        client.app.state.ctx.store.revision(), 'mapper')

    end = Point(H.X0 + 100, H.Y0 + 20)
    response = client.post('/api/roads/draw', json={'coords': _wgs([moved, end], base.crs),
                                                    'start': {'type': 'node', 'node': int(start_node)},
                                                    'end': {'type': 'none'},
                                                    'join': int(drawn.edges.loc[idx].street_id)})
    assert response.status_code == 200, response.text
    for current in (client, TestClient(create_app(root, auth_enabled=False, auto_compute=False))):
        after, _ = current.app.state.ctx.get_effective()
        extension = after.edges[after.edges.osmid.astype(str) == 'road2:0']
        assert len(extension) == 2
        assert min(Point(g.coords[0]).distance(moved) for g in extension.geometry) < .01
        assert after.nodes.geometry.loc[start_node].distance(moved) < .01
