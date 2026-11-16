"""Browser checks: set drivable along a stretch from A to B, and remove the last point of a partial reshape."""

from test_app_frontend import live_app, playwright_sync_api  # noqa: F401  (pytest fixture)
import app_helpers as H
from osmaddresssystem.app.store import Store


def _open(page, url):
    lon, lat = H.lonlat(H.X0 + 120, H.Y0 + 120)
    assert page.request.post(url + '/api/reference', data={'lat': lat, 'lon': lon}).ok
    page.goto(url, wait_until='domcontentloaded')
    page.locator('#ref-confirm').click()
    page.wait_for_function('S.network && !S.polling')
    page.locator('#tabs button[data-tab=roads]').click()


def _screen(page, dx, dy):
    lon, lat = H.lonlat(H.X0 + dx, H.Y0 + dy)
    return page.evaluate('''([lat, lon]) => { const r = map.getContainer().getBoundingClientRect(), p = map.latLngToContainerPoint([lat, lon]);
                            return {x: r.left + p.x, y: r.top + p.y}; }''', [lat, lon])


def test_classify_a_stretch_from_a_to_b(live_app):  # noqa: F811
    url, root = live_app
    with playwright_sync_api.sync_playwright() as pw:
        browser = H.launch_browser(pw)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        _open(page, url)
        page.locator('details[data-sec=access] > summary').click()
        page.locator('[data-act=edge-access-start]').click()
        a, b = _screen(page, 0, 0), _screen(page, 240, 0)
        page.mouse.click(a['x'], a['y'])
        page.wait_for_function('S.edgeAccess && S.edgeAccess.a')
        page.mouse.click(b['x'], b['y'])
        page.wait_for_function('S.edgeAccess && S.edgeAccess.result')
        assert page.evaluate('S.edgeAccess.result.routes[0].refs.length') == 2
        page.locator('[data-act=edge-access-other]').click()                     # the other route, then back
        assert page.evaluate('S.edgeAccess.route') == 1
        page.locator('[data-act=edge-access-other]').click()
        assert page.locator('#edge-access-value option').all_inner_texts() == ['Yes', 'No (foot or motorbike)', 'Unknown']
        page.locator('#edge-access-value').select_option('foot')
        with page.expect_response(lambda r: r.url.endswith('/api/edges/access')) as saved:
            page.locator('[data-act=edge-access-save]').click()
        assert saved.value.status == 200
        page.wait_for_function('!S.edgeAccess')
        store = Store(root)
        assert list(store.project().roads['edge_access'].values()) == ['foot', 'foot']
        store.engine.dispose()
        assert not errors
        browser.close()


def test_right_click_a_road_starts_the_classification_from_there(live_app):  # noqa: F811
    url, _root = live_app
    with playwright_sync_api.sync_playwright() as pw:
        browser = H.launch_browser(pw)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        _open(page, url)
        a = _screen(page, 100, 0)
        page.mouse.click(a['x'], a['y'], button='right')
        page.locator('[data-road-action=access]').click()
        page.wait_for_function('S.edgeAccess && S.edgeAccess.a && !S.edgeAccess.result')
        b = _screen(page, 360, 0)
        page.mouse.click(b['x'], b['y'])
        page.wait_for_function('S.edgeAccess && S.edgeAccess.result')
        assert page.evaluate('S.edgeAccess.result.routes[0].refs.length') == 2   # A snapped to the junction at 120 m
        assert page.locator('[data-act=edge-access-save]').is_visible()
        assert not errors
        browser.close()


def test_a_refresh_comes_back_to_the_same_tab_place_and_colours(live_app):  # noqa: F811
    url, _root = live_app
    with playwright_sync_api.sync_playwright() as pw:
        browser = H.launch_browser(pw)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        lon, lat = H.lonlat(H.X0 + 120, H.Y0 + 120)
        assert page.request.post(url + '/api/reference', data={'lat': lat, 'lon': lon}).ok
        page.goto(url, wait_until='domcontentloaded')
        page.locator('#ref-confirm').click()
        page.wait_for_function('S.network && !S.polling && S.ready')
        page.select_option('#color-mode', 'drivable')
        page.locator('#tabs button[data-tab=roads]').click()
        page.wait_for_function('S.tab === "roads" && S.roads')
        flon, flat = H.lonlat(H.X0 + 360, H.Y0 + 240)
        page.evaluate('([lat, lon]) => map.setView([lat, lon], 19, {animate: false})', [flat, flon])
        page.reload(wait_until='domcontentloaded')
        page.wait_for_function('S.ready && S.tab === "roads"')
        view = page.evaluate('({lat: map.getCenter().lat, lon: map.getCenter().lng, zoom: map.getZoom(), colour: S.idColor})')
        assert view['zoom'] == 19 and view['colour'] == 'drivable'
        assert abs(view['lat'] - flat) < 1e-5 and abs(view['lon'] - flon) < 1e-5
        assert page.locator('#tabs button[data-tab=roads].active').count() == 1
        assert not errors
        browser.close()


def test_partial_reshape_can_remove_its_last_point(live_app):  # noqa: F811
    url, _root = live_app
    with playwright_sync_api.sync_playwright() as pw:
        browser = H.launch_browser(pw)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        _open(page, url)
        page.locator('details[data-sec=draw] > summary').click()
        page.locator('[data-act=partial-pick]').click()
        page.wait_for_function('!!S.reshapePick')
        points = page.evaluate('''() => {
            const f=S.reshapePick.edges.features.find(f=>f.geometry.coordinates.length===2 && !f.properties.ref.startsWith('-'));
            map.fitBounds(L.geoJSON(f).getBounds().pad(.8),{animate:false});
            const [a,b]=f.geometry.coordinates, r=map.getContainer().getBoundingClientRect();
            return [.5,.2,.8].map(t=>{const p=map.latLngToContainerPoint([a[1]+(b[1]-a[1])*t,a[0]+(b[0]-a[0])*t]);return {x:r.left+p.x,y:r.top+p.y};});
        }''')
        page.mouse.click(points[0]['x'], points[0]['y'])
        page.wait_for_function('S.cut && S.cut.reshape')
        for point in points[1:]:
            page.mouse.click(point['x'], point['y'])
        page.wait_for_function('S.cut && S.cut.preview')
        page.locator('#banner-next').click()
        page.wait_for_function('S.draw && S.draw.mode === "reshape-partial"')
        undo = page.locator('[data-act=draw-undo]')
        assert undo.is_visible() and undo.is_disabled()                          # anchor A alone: nothing to remove
        assert page.locator('[data-act=reshape-reset]').is_visible()
        for dy in (-40, -60):
            page.mouse.click(points[0]['x'] + 20, points[0]['y'] + dy)
        page.wait_for_function('S.draw.pts.length === 3')
        anchor = page.evaluate('JSON.stringify(S.draw.pts[0])')
        undo.click()
        assert page.evaluate('S.draw.pts.length') == 2
        undo.click()
        assert page.evaluate('S.draw.pts.length') == 1 and page.evaluate('JSON.stringify(S.draw.pts[0])') == anchor
        assert undo.is_disabled()
        page.evaluate("ACT['draw-undo']()")                                     # even when called directly, anchor A stays
        assert page.evaluate('S.draw.pts.length') == 1
        assert not errors
        browser.close()
