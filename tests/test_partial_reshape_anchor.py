"""Reshape between two points: anchor B stays where it was clicked, and a dead end may move with it."""

import geopandas as gpd
import shapely
import shapely.ops
from shapely.geometry import Point

from osmaddresssystem.app.roads import edge_ref
from test_app_backend import client, root  # noqa: F401  (pytest fixtures)


def _wgs(points, crs):
    return [[p.x, p.y] for p in gpd.GeoSeries(points, crs=crs).to_crs(4326)]


def _save(client, ref, clicks, trace, crs):  # noqa: F811
    body = {"ref": ref, "points": _wgs(clicks, crs), "revision": client.app.state.ctx.store.revision()}
    preview = client.post("/api/roads/geometry/partial/preview", json=body)
    assert preview.status_code == 200, preview.text
    anchors = gpd.GeoSeries([Point(p) for p in preview.json()["properties"]["anchors"]], crs=4326).to_crs(crs)
    r = client.post("/api/roads/geometry/partial", json={**body, "coords": _wgs(trace, crs)})
    return anchors, r


def test_an_anchor_clicked_off_the_old_line_stays_where_it_was_clicked(client):  # noqa: F811
    base, _ = client.app.state.ctx.get_effective()
    idx = next(i for i in base.edges.index if i[0] < i[1])
    line = base.edges.loc[idx].geometry
    a = line.interpolate(line.length * .25)
    on_line = line.interpolate(line.length * .75)
    dx, dy = line.coords[-1][0] - line.coords[0][0], line.coords[-1][1] - line.coords[0][1]
    norm = (dx * dx + dy * dy) ** .5
    b = Point(on_line.x - dy / norm * 10, on_line.y + dx / norm * 10)              # 10 m beside the old line
    anchors, r = _save(client, edge_ref(*idx), [a, b], [a, Point((a.x + b.x) / 2 - dy / norm * 8, (a.y + b.y) / 2 + dx / norm * 8), b], base.crs)
    assert anchors.iloc[1].distance(b) < .01                                       # B was not pulled onto the crooked line
    assert anchors.iloc[0].distance(a) < .01                                       # A was on the line and stays there
    assert r.status_code == 200, r.text
    after, _ = client.app.state.ctx.get_effective()
    new = after.edges.loc[idx].geometry
    assert new.distance(b) < .01                                                   # the road passes through B
    assert Point(new.coords[0]).distance(Point(line.coords[0])) < .01               # both junctions unchanged
    assert Point(new.coords[-1]).distance(Point(line.coords[-1])) < .01
    assert new.distance(on_line) < .01                                              # and rejoins the old line after B


def test_a_nearby_disconnected_road_does_not_hijack_an_off_line_anchor(client):  # noqa: F811
    """An off-line B is part of the reshape, even when an unrelated road happens to be nearer to it."""
    import app_helpers as H

    base, _ = client.app.state.ctx.get_effective()
    idx = _section_at(base, H.X0 + 60, H.Y0)
    a = Point(H.X0 + 20, H.Y0)
    b = Point(H.X0 + 70, H.Y0 + 8)
    island = [Point(H.X0 + 30, H.Y0 + 10), Point(H.X0 + 90, H.Y0 + 10)]
    response = client.post("/api/roads/draw", json={
        "coords": _wgs(island, base.crs),
        "start": {"type": "none"},
        "end": {"type": "none"},
    })
    assert response.status_code == 200, response.text

    body = {
        "ref": edge_ref(*idx),
        "points": _wgs([a, b], base.crs),
        "revision": client.app.state.ctx.store.revision(),
    }
    preview = client.post("/api/roads/geometry/partial/preview", json=body)
    assert preview.status_code == 200, preview.text
    anchors = gpd.GeoSeries(
        [Point(p) for p in preview.json()["properties"]["anchors"]], crs=4326
    ).to_crs(base.crs)
    assert anchors.iloc[1].distance(b) < .01
    assert 45 < preview.json()["properties"]["selected_m"] < 55


def test_a_connected_cross_street_does_not_hijack_an_off_line_anchor(client):  # noqa: F811
    """The shortest graph route must not reshape a different street through a nearby junction."""
    import app_helpers as H

    base, _ = client.app.state.ctx.get_effective()
    idx = _section_at(base, H.X0 + 60, H.Y0)
    a = Point(H.X0 + 80, H.Y0)
    b = Point(H.X0 + 5, H.Y0 + 15)  # nearer to the connected cross street, but still a valid off-line anchor
    body = {
        "ref": edge_ref(*idx),
        "points": _wgs([a, b], base.crs),
        "revision": client.app.state.ctx.store.revision(),
    }
    preview = client.post("/api/roads/geometry/partial/preview", json=body)
    assert preview.status_code == 200, preview.text
    anchors = gpd.GeoSeries(
        [Point(p) for p in preview.json()["properties"]["anchors"]], crs=4326
    ).to_crs(base.crs)
    assert anchors.iloc[0].distance(b) < .01 or anchors.iloc[1].distance(b) < .01
    assert 70 < preview.json()["properties"]["selected_m"] < 80


def test_at_a_dead_end_the_road_end_moves_to_the_clicked_point(client):  # noqa: F811
    base, _ = client.app.state.ctx.get_effective()
    corner = min(base.nodes.index, key=lambda n: base.nodes.geometry.loc[n].x + base.nodes.geometry.loc[n].y)
    touching = sorted({tuple(sorted(i[:2])) + (i[2],) for i in base.edges.index if corner in i[:2]})
    assert len(touching) == 2
    gone, kept = touching
    assert client.post("/api/edges/remove", json={"edges": [edge_ref(*gone)]}).status_code == 200
    base, _ = client.app.state.ctx.get_effective()
    line = base.edges.loc[kept].geometry
    corner_xy = Point(base.nodes.geometry.loc[corner].coords[0])
    inner = line.interpolate(1 if kept[0] == corner else line.length - 1)          # geometry runs from u to v
    beyond = Point(corner_xy.x + (corner_xy.x - inner.x) * 15, corner_xy.y + (corner_xy.y - inner.y) * 15)   # 15 m past the old end
    a = line.interpolate(line.length * .5)
    anchors, r = _save(client, edge_ref(*kept), [a, beyond], [a, beyond], base.crs)
    assert min(anchors.distance(beyond)) < .01
    assert r.status_code == 200, r.text
    after, _ = client.app.state.ctx.get_effective()
    new = after.edges.loc[kept].geometry
    end = Point(new.coords[0]) if kept[0] == corner else Point(new.coords[-1])
    assert end.distance(beyond) < .01                                               # the road now ends at the clicked point
    assert after.nodes.geometry.loc[corner].distance(beyond) < .01                  # and its node moved with it
    assert abs(new.length - (line.length + 15)) < .05                               # straight on, no spike back to the old end
    other = Point(new.coords[-1]) if kept[0] == corner else Point(new.coords[0])
    assert other.distance(Point(line.coords[-1] if kept[0] == corner else line.coords[0])) < .01   # the junction stays
    assert client.post("/api/undo").status_code == 200
    restored, _ = client.app.state.ctx.get_effective()
    assert restored.nodes.geometry.loc[corner].distance(corner_xy) < .01


def test_b_clicked_past_a_junction_lands_on_the_next_section_of_the_road(client):  # noqa: F811
    base, _ = client.app.state.ctx.get_effective()
    idx = next(i for i in base.edges.index if i[0] < i[1])
    line = base.edges.loc[idx].geometry
    end = Point(line.coords[-1])
    dx, dy = end.x - line.coords[-2][0], end.y - line.coords[-2][1]
    norm = (dx * dx + dy * dy) ** .5
    beyond = Point(end.x + dx / norm * 8, end.y + dy / norm * 8)
    a = line.interpolate(line.length * .4)
    body = {"ref": edge_ref(*idx), "points": _wgs([a, beyond], base.crs), "revision": client.app.state.ctx.store.revision()}
    preview = client.post("/api/roads/geometry/partial/preview", json=body).json()
    anchors = gpd.GeoSeries([Point(p) for p in preview["properties"]["anchors"]], crs=4326).to_crs(base.crs)
    assert anchors.iloc[1].distance(beyond) < .01                                  # not pulled back to the end of the first section
    assert preview["properties"]["selected_m"] > line.length * .6                     # the orange stretch crosses the junction


def _section_at(base, x, y):
    p = Point(x, y)
    return min((i for i in base.edges.index if i[0] < i[1]), key=lambda i: base.edges.loc[i].geometry.distance(p))


def test_a_and_b_on_two_sections_reshape_both_and_move_the_junction_between(client):  # noqa: F811
    import app_helpers as H
    base, _ = client.app.state.ctx.get_effective()
    first, second = _section_at(base, H.X0 + 60, H.Y0), _section_at(base, H.X0 + 180, H.Y0)
    junction = (set(first[:2]) & set(second[:2])).pop()
    side = next(i for i in base.edges.index if i[0] < i[1] and junction in i[:2] and i not in (first, second))
    ids = base.edges["street_id"].copy()
    n_edges = len(base.edges)
    a, b = Point(H.X0 + 60, H.Y0), Point(H.X0 + 200, H.Y0)
    trace = [a, Point(H.X0 + 100, H.Y0 + 8), Point(H.X0 + 140, H.Y0 + 8), b]
    anchors, r = _save(client, edge_ref(*first), [a, b], trace, base.crs)
    assert anchors.iloc[1].distance(b) < .01                                       # B stays on the second section, not at the junction
    assert r.status_code == 200, r.text
    assert r.json()["sections"] == 2
    after, _ = client.app.state.ctx.get_effective()
    moved = after.nodes.geometry.loc[junction]
    assert abs(moved.y - (H.Y0 + 8)) < .5 and abs(moved.x - (H.X0 + 120)) < 1      # the junction is on the new line
    path = shapely.ops.linemerge([after.edges.loc[first].geometry, after.edges.loc[second].geometry])
    assert path.distance(Point(H.X0 + 120, H.Y0 + 8)) < .5 and path.distance(Point(H.X0 + 120, H.Y0)) > 5
    side_geom = after.edges.loc[side].geometry
    assert min(Point(side_geom.coords[0]).distance(moved), Point(side_geom.coords[-1]).distance(moved)) < .01   # side road follows
    assert len(after.edges) == n_edges and (after.edges["street_id"] == ids).all()                             # no new road, same IDs
    assert client.app.state.ctx.store.history()[0]["action"] == "road_stretch"
    assert client.post("/api/undo").status_code == 200
    restored, _ = client.app.state.ctx.get_effective()
    assert restored.nodes.geometry.loc[junction].distance(Point(H.X0 + 120, H.Y0)) < .01
    assert restored.edges.loc[first].geometry.equals_exact(base.edges.loc[first].geometry, .01)


def test_a_two_section_reshape_survives_compute_and_reopen(client, root):  # noqa: F811
    import app_helpers as H
    from fastapi.testclient import TestClient
    from osmaddresssystem.app.server import create_app
    from test_app_backend import compute, set_reference
    set_reference(client)
    base, _ = client.app.state.ctx.get_effective()
    first = _section_at(base, H.X0 + 60, H.Y0)
    a, b = Point(H.X0 + 60, H.Y0), Point(H.X0 + 200, H.Y0)
    _anchors, r = _save(client, edge_ref(*first), [a, b], [a, Point(H.X0 + 120, H.Y0 + 6), b], base.crs)
    assert r.status_code == 200, r.text
    assert compute(client)["streets"]["features"]
    reopened = TestClient(create_app(root, auth_enabled=False, auto_compute=False))
    again, _ = reopened.app.state.ctx.get_effective()
    assert again.edges.loc[first].geometry.distance(Point(H.X0 + 120, H.Y0 + 6)) < 1


def test_b_clicked_beside_a_junction_stays_there_and_the_junction_follows(client):  # noqa: F811
    import app_helpers as H
    base, _ = client.app.state.ctx.get_effective()
    first = _section_at(base, H.X0 + 60, H.Y0)
    junction = first[1] if base.nodes.geometry.loc[first[1]].x > base.nodes.geometry.loc[first[0]].x else first[0]
    others = [i for i in base.edges.index if i[0] < i[1] and junction in i[:2] and i != first]
    a, b = Point(H.X0 + 60, H.Y0), Point(H.X0 + 121, H.Y0 - 6)                        # B 6 m beside the junction
    anchors, r = _save(client, edge_ref(*first), [a, b], [a, Point(H.X0 + 90, H.Y0 - 4), b], base.crs)
    assert anchors.iloc[1].distance(b) < .01                                        # not moved onto the junction
    assert r.status_code == 200, r.text
    after, _ = client.app.state.ctx.get_effective()
    assert after.nodes.geometry.loc[junction].distance(b) < .01                       # the junction moved to B
    assert Point(after.edges.loc[first].geometry.coords[-1]).distance(b) < .01
    for i in others:                                                                  # the roads joined there follow it
        g = after.edges.loc[i].geometry
        assert min(Point(g.coords[0]).distance(b), Point(g.coords[-1]).distance(b)) < .01
    assert len(after.edges) == len(base.edges)
