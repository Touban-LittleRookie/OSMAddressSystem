"""Actual browser interactions for connected tracing, local cuts and work areas."""

from test_app_frontend import live_app, playwright_sync_api
import app_helpers as H
from osmaddresssystem.app.store import Store
import pytest


def test_coordinate_search_offers_work_area_switch(live_app):
    url, root = live_app
    with playwright_sync_api.sync_playwright() as pw:
        browser = H.launch_browser(pw)
        page = browser.new_page(viewport={'width': 1400, 'height': 900})
        lon, lat = H.lonlat(H.X0 + 120, H.Y0 + 120)
        assert page.request.post(url + '/api/reference', data={'lat': lat, 'lon': lon}).ok
        revision = page.request.get(url + '/api/project').json()['status']['revision']
        assert page.request.post(url + '/api/work-areas/grid', data={'cell_m': 250, 'revision': revision}).ok
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_function('S.ready && S.project.work_areas.features.length > 1')
        target = page.evaluate('''() => {
          const f=S.project.work_areas.features[0], ring=f.geometry.coordinates[0];
          const lon=(Math.min(...ring.map(p=>p[0]))+Math.max(...ring.map(p=>p[0])))/2;
          const lat=(Math.min(...ring.map(p=>p[1]))+Math.max(...ring.map(p=>p[1])))/2;
          return {id:f.properties.id,lat,lon};
        }''')
        page.locator('.goto-box input').fill(f"{target['lat']}, {target['lon']}")
        page.locator('.goto-box input').press('Enter')
        page.locator('.goto-area-result button').wait_for()
        assert target['id'] in page.locator('.goto-area-result').inner_text()
        page.locator('.goto-area-result button').click()
        page.wait_for_function('(id) => S.activeArea === id && S.areaView === "work"', arg=target['id'])
        centre = page.evaluate('({lat:map.getCenter().lat,lon:map.getCenter().lng})')
        assert abs(centre['lat'] - target['lat']) < 1e-6 and abs(centre['lon'] - target['lon']) < 1e-6
        browser.close()


def test_connected_trace_uncertainty_areas_and_local_cut(live_app):
    url, root = live_app
    with playwright_sync_api.sync_playwright() as pw:
        browser = H.launch_browser(pw)
        page = browser.new_page(viewport={'width':1600, 'height':1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('dialog', lambda d: d.accept())
        lon, lat = H.lonlat(H.X0+120, H.Y0+120)
        assert page.request.post(url+'/api/reference', data={'lat':lat,'lon':lon}).ok
        page.goto(url, wait_until='domcontentloaded')
        page.locator('#ref-confirm').click()
        page.wait_for_function('S.network && !S.polling')
        layout = page.evaluate('''() => {
          const box = id => document.querySelector(id).getBoundingClientRect();
          return {map:box('#map'), main:box('main'), bodyScroll:document.body.scrollHeight, viewport:innerHeight,
            sideOverflow:getComputedStyle(document.querySelector('#side')).overflowY,
            panelOverflow:getComputedStyle(document.querySelector('#panel')).overflowY};
        }''')
        assert abs(layout['map']['bottom'] - layout['main']['bottom']) < 2
        assert layout['bodyScroll'] <= layout['viewport'] + 1
        assert layout['sideOverflow'] == 'auto'
        assert layout['panelOverflow'] == 'visible'
        page.locator('#tabs button[data-tab=roads]').click()
        page.locator('#workarea-box > details > summary').click()
        page.locator('input[name=area-view][value=work]').check()
        page.locator('#areas-create').click()
        page.wait_for_selector('#area-select')
        assert page.locator('#area-select option').nth(1).inner_text().startswith('1. R')
        assert page.locator('#area-select option').nth(2).inner_text().startswith('2. R')
        area_id = page.locator('#area-select option').nth(1).get_attribute('value')
        page.locator('#area-select').select_option(area_id)
        page.locator('.work-area-focus-label').wait_for()
        assert page.locator('.work-area-focus-label').inner_text().startswith('1. R')
        page.locator('.area-progress > summary').click()
        assert page.locator('[data-area-stage]').count() == 5
        page.locator('[data-area-stage=geometry]').select_option('in_progress')
        page.locator('#area-note').fill('Roads checked; trees obscure the end')
        page.locator('#area-save').click()
        page.wait_for_function('!S.project.stale')
        page.locator('#area-select').select_option('')

        page.locator('details[data-sec=draw] summary').click()
        page.locator('[data-act=draw-route]').click()
        page.locator('#draw-snap').uncheck()
        page.mouse.click(300,300)
        page.wait_for_function('S.draw.phase === "end"')
        page.mouse.click(700,400)
        page.wait_for_function('S.draw.phase === "trace"')
        assert page.evaluate('S.draw.pts.length') == 1  # planned end has no invented connection
        target = page.evaluate('JSON.parse(JSON.stringify(S.draw.target))')
        page.locator('#draw-tool').select_option('freehand')
        page.mouse.move(500,200); page.mouse.down(); page.mouse.move(550,220,steps=6); page.mouse.up()
        assert page.evaluate('S.draw.pts.length') == 1
        page.mouse.move(300,300); page.mouse.down()
        page.mouse.move(350,320,steps=8); page.mouse.move(400,350,steps=8); page.mouse.up()
        page.wait_for_function('S.draw.pts.length >= 3')
        count = page.evaluate('S.draw.pts.length')
        last = page.locator('.road-vertex').last.bounding_box()
        page.mouse.move(last['x']+6,last['y']+6); page.mouse.down()
        page.mouse.move(450,360,steps=8); page.mouse.move(500,350,steps=8); page.mouse.up()
        assert page.evaluate('S.draw.pts.length') > count
        page.locator('[data-act=draw-undo-stroke]').click()
        assert page.evaluate('S.draw.pts.length') == count
        last = page.locator('.road-vertex').last.bounding_box()
        page.mouse.move(last['x']+6,last['y']+6); page.mouse.down()
        page.mouse.move(450,360,steps=8); page.mouse.move(500,350,steps=8); page.mouse.up()
        page.locator('[data-act=draw-finish]').click()
        assert page.evaluate('!!S.draw')  # no automatic bridge to planned end
        page.locator('#draw-uncertain').check()
        with page.expect_response(lambda r:r.url.endswith('/api/roads/draw')) as saved:
            page.locator('[data-act=draw-finish]').click()
        assert saved.value.status == 200
        page.wait_for_function('!S.draw')
        store = Store(root)
        feature = store.project().roads['imports'][-1]['features'][0]
        assert feature['end_review'] == 'uncertain'
        assert feature['end'] == {'type':'none'}
        assert feature['coords'][-1] != [target[1],target[0]]
        assert store.project().work_areas['features'][0]['properties']['note'] == 'Roads checked; trees obscure the end'
        store.engine.dispose()
        page.locator('.uncertain-end').wait_for(state='visible')
        assert page.locator('.uncertain-end').count() == 1

        page.locator('details[data-sec=del] summary').click()
        page.locator('[data-act=cut-pick]').click()
        page.wait_for_function('!!S.reshapePick')
        clicks = page.evaluate('''() => {
            const f=S.reshapePick.edges.features.find(f=>f.geometry.coordinates.length===2 && !f.properties.ref.startsWith('-'));
            map.fitBounds(L.geoJSON(f).getBounds().pad(.5),{animate:false});
            const [a,b]=f.geometry.coordinates, r=map.getContainer().getBoundingClientRect();
            return [.5,.25,.75].map(t=>{const p=map.latLngToContainerPoint([a[1]+(b[1]-a[1])*t,a[0]+(b[0]-a[0])*t]);return {x:r.left+p.x,y:r.top+p.y};});
        }''')
        page.mouse.click(clicks[0]['x'],clicks[0]['y'])
        page.wait_for_function('!!S.cut')
        page.wait_for_function('G.base.getLayers().some(g => g.getLayers && g.getLayers().length > 1)')
        for p in clicks[1:]:
            page.mouse.click(p['x'],p['y'])
        page.wait_for_function('!!S.cut.preview')
        with page.expect_response(lambda r:r.url.endswith('/api/roads/cut')) as saved:
            page.locator('[data-act=cut-save]').click()
        assert saved.value.status == 200
        page.wait_for_function('!S.cut')
        store = Store(root)
        assert len(store.project().roads['cuts']) == 1
        assert store.history()[0]['action'] == 'road_cut'
        store.engine.dispose()
        page.locator('#btn-undo').click()
        page.wait_for_function('S.project.status.can_redo')
        store = Store(root)
        assert not store.project().roads['cuts']
        store.engine.dispose()

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
        assert page.locator('[data-act=partial-start]').is_enabled()
        assert page.locator('#banner-next').is_visible()
        page.locator('#banner-next').click()
        page.wait_for_function('S.draw && S.draw.mode === "reshape-partial"')
        assert page.evaluate('S.draw.pts.length') == 1
        assert page.evaluate('Array.isArray(S.draw.target) && S.draw.target.length === 2')
        assert page.locator('[data-act=partial-change-anchors]').is_visible()
        page.locator('#draw-tool').select_option('freehand')
        trace = page.evaluate('''() => {
          const a=S.draw.original[0], b=S.draw.original[S.draw.original.length-1], r=map.getContainer().getBoundingClientRect();
          return [.05,.5,.95].map(t=>{const p=map.latLngToContainerPoint([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]);return {x:r.left+p.x,y:r.top+p.y};});
        }''')
        page.mouse.move(trace[0]['x'], trace[0]['y'])
        page.mouse.down()
        page.mouse.move(trace[1]['x'], trace[1]['y']-25, steps=12)
        page.mouse.move(trace[2]['x'], trace[2]['y'], steps=12)
        page.mouse.up()
        page.wait_for_function('S.draw.pts.length >= 3')
        page.locator('#draw-uncertain').check()
        with page.expect_response(lambda r:r.url.endswith('/api/roads/geometry/partial')) as reshaped:
            page.locator('[data-act=draw-finish]').click()
        assert reshaped.value.status == 200
        page.wait_for_function('!S.draw')
        store = Store(root)
        assert store.history()[0]['action'] == 'road_geometry'
        assert store.project().roads.get('geometry_reviews')
        store.engine.dispose()
        page.wait_for_function('(S.roads.report.uncertain_ends || []).length >= 2')
        assert page.locator('.uncertain-end').count() >= 2

        page.locator('details[data-sec=review] > summary').click()
        page.locator('[data-act=review-pick]').click()
        page.wait_for_function('S.reshapePick && S.reshapePick.action === "review"')
        review_points = page.evaluate('''() => {
          const f=S.reshapePick.edges.features.find(f=>f.geometry.coordinates.length>=2 && !f.properties.ref.startsWith('-'));
          map.fitBounds(L.geoJSON(f).getBounds().pad(.8),{animate:false});
          const [a,b]=f.geometry.coordinates, r=map.getContainer().getBoundingClientRect();
          return [.5,.2,.8].map(t=>{const p=map.latLngToContainerPoint([a[1]+(b[1]-a[1])*t,a[0]+(b[0]-a[0])*t]);return {x:r.left+p.x,y:r.top+p.y};});
        }''')
        page.mouse.click(review_points[0]['x'], review_points[0]['y'])
        page.wait_for_function('S.cut && S.cut.review')
        for point in review_points[1:]:
            page.mouse.click(point['x'], point['y'])
        page.wait_for_function('S.cut && S.cut.preview')
        page.locator('#review-note').fill('Canopy hides this road portion')
        page.locator('[data-act=review-save]').click()
        page.wait_for_function('S.roads.reviews && S.roads.reviews.features.length === 1')
        store = Store(root)
        assert len(store.project().roads['reviews']) == 1
        store.engine.dispose()
        assert page.locator('[data-act=review-remove]').is_visible()
        page.locator('[data-act=review-remove]').click()
        page.wait_for_function('S.roads.reviews.features.length === 0')
        store = Store(root)
        assert store.project().roads['reviews'] == []
        store.engine.dispose()
        assert not errors
        browser.close()


def test_quartier_shared_boundary_editor_saves_reason(live_app):
    import geopandas as gpd
    import shapely
    from shapely.geometry import box
    from osmaddresssystem.app.work_areas import default_stages

    url, root = live_app
    shapes = gpd.GeoSeries([box(H.X0-40, H.Y0-40, H.X0+240, H.Y0+400),
                            box(H.X0+240, H.Y0-40, H.X0+520, H.Y0+400)], crs=H.CRS).to_crs(4326)
    features = []
    for area_id, name, geometry in zip(('Q01', 'Q02'), ('West', 'East'), shapes):
        features.append({'type': 'Feature', 'properties': {'id': area_id, 'kind': 'quartier', 'name': name,
                        'status': 'unreviewed', 'stages': default_stages(), 'note': '', 'provisional': True},
                        'geometry': shapely.geometry.mapping(geometry)})
    cell_shape = gpd.GeoSeries([box(H.X0, H.Y0, H.X0+180, H.Y0+180)], crs=H.CRS).to_crs(4326).iloc[0]
    cell = {'type': 'Feature', 'properties': {'id': 'R01C01', 'kind': 'grid', 'status': 'unreviewed',
            'stages': default_stages(), 'note': '', 'quartier_id': 'Q01', 'quartier_name': 'West'},
            'geometry': shapely.geometry.mapping(cell_shape)}
    store = Store(root)
    store.set_work_areas({'kind': 'hierarchy', 'type': 'FeatureCollection', 'cell_m': 200, 'features': [cell],
                          'quartiers': {'kind': 'quartiers', 'type': 'FeatureCollection', 'features': features}}, store.revision(), 'test')

    with playwright_sync_api.sync_playwright() as pw:
        browser = H.launch_browser(pw)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        lon, lat = H.lonlat(H.X0+120, H.Y0+120)
        assert page.request.post(url+'/api/reference', data={'lat': lat, 'lon': lon}).ok
        page.goto(url, wait_until='domcontentloaded')
        page.locator('#ref-confirm').click()
        page.wait_for_function('S.project && !S.polling')
        page.locator('#tabs button[data-tab=roads]').click()
        page.locator('#workarea-box > details > summary').click()
        def area_layers(kind, selected=None):
            return page.evaluate('''([kind,selected]) => areaLayer.getLayers().flatMap(x => x.getLayers ? x.getLayers() : [x])
              .filter(x => x._areaKind === kind && (selected === null || x._areaSelected === selected)).length''', [kind, selected])
        assert area_layers('quartier') == 0
        assert area_layers('work') == 0
        page.locator('input[name=area-view][value=work]').check()
        assert area_layers('work') == 1
        assert area_layers('quartier') == 0
        page.locator('#area-select').select_option('R01C01')
        assert area_layers('work', True) == 1
        assert area_layers('quartier', True) == 0
        page.locator('#show-quartier-boundaries').check()
        assert area_layers('quartier') == 2
        assert area_layers('quartier', True) == 0
        page.locator('input[name=area-view][value=quartiers]').check()
        assert area_layers('work') == 0
        assert page.evaluate("sharedBoundaryLayer.getLayers().flatMap(x => x.getLayers ? x.getLayers() : [x]).filter(x => x._sharedQuartierBoundary).length") == 1
        border_label = page.evaluate('''() => {
          const line = sharedBoundaryLayer.getLayers().flatMap(x => x.getLayers ? x.getLayers() : [x]).find(x => x._sharedQuartierBoundary);
          line.fire('mouseover');
          return line.getTooltip().getContent();
        }''')
        assert 'West' in border_label and 'East' in border_label
        assert page.evaluate("quartierHoverLayer.getLayers().flatMap(x => x.getLayers ? x.getLayers() : [x]).length") == 2
        page.evaluate('''() => sharedBoundaryLayer.getLayers().flatMap(x => x.getLayers ? x.getLayers() : [x])
          .find(x => x._sharedQuartierBoundary).fire('mouseout')''')
        assert page.evaluate("quartierHoverLayer.getLayers().length") == 0
        page.locator('#quartier-select').select_option('Q01')
        assert area_layers('quartier', True) == 1
        assert area_layers('work', True) == 0
        page.locator('#boundary-load').click()
        page.wait_for_selector('#boundary-neighbour')
        assert page.locator('#boundary-neighbour').input_value() == 'Q02'
        page.locator('#boundary-start').click()
        page.wait_for_selector('.road-midpoint')
        page.locator('.road-midpoint').click()
        assert page.locator('.road-vertex').count() == 3
        page.locator('#boundary-reason').fill('Limite confirmée avec le relais de terrain')
        page.locator('#boundary-save').click()
        page.wait_for_function('!S.boundaryEdit')
        assert Store(root).project().work_areas['quartiers']['features'][0]['properties']['boundary_note'] == 'Limite confirmée avec le relais de terrain'
        assert errors == []
        browser.close()


def test_connected_click_route_finishes_at_the_planned_end(live_app):
    url, root = live_app
    with playwright_sync_api.sync_playwright() as pw:
        browser = H.launch_browser(pw)
        page = browser.new_page(viewport={'width':1400,'height':900})
        lon, lat = H.lonlat(H.X0+120,H.Y0+120)
        page.request.post(url+'/api/reference',data={'lat':lat,'lon':lon})
        page.goto(url,wait_until='domcontentloaded')
        page.locator('#ref-confirm').click()
        page.wait_for_function('S.network && !S.polling')
        page.locator('#tabs button[data-tab=roads]').click()
        page.locator('details[data-sec=draw] summary').click()
        page.locator('[data-act=draw-route]').click()
        page.locator('#draw-snap').uncheck()
        page.mouse.click(300,300)
        page.wait_for_function('S.draw.phase === "end"')
        page.mouse.click(600,400)
        page.wait_for_function('S.draw.phase === "trace"')
        expected = page.evaluate('S.draw.target.map((v,i)=>S.draw.target[1-i])')
        assert page.evaluate('S.draw.pts.length') == 1
        page.mouse.click(450,350)
        page.mouse.click(600,400)
        page.wait_for_function('S.draw.reached')
        assert page.evaluate('S.draw.pts.length') == 3
        page.locator('[data-act=draw-finish]').click()
        page.wait_for_function('!S.draw')
        store = Store(root)
        feature = store.project().roads['imports'][-1]['features'][0]
        assert len(feature['coords']) == 3
        assert feature['coords'][-1] == pytest.approx(expected,abs=1e-7)
        assert not feature.get('end_review')
        store.engine.dispose()
        browser.close()
