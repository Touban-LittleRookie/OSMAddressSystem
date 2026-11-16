"""Work tracking is persistent but does not change address calculations."""

import base64

from fastapi.testclient import TestClient
from test_app_backend import client, root, set_reference, compute
import app_helpers as H
from osmaddresssystem.app.server import create_app


def test_grid_status_roundtrip_and_no_recomputation(client, root):
    set_reference(client)
    compute(client)
    store = client.app.state.ctx.store
    before = store.project()
    r = client.post('/api/work-areas/grid', json={'cell_m':250, 'revision':store.revision()})
    assert r.status_code == 200, r.text
    areas = r.json()['areas']
    assert len(areas['features']) > 1
    assert all(f['properties']['status'] == 'unreviewed' for f in areas['features'])
    assert all(set(f['properties']['stages']) == {'geometry', 'attributes', 'names', 'buildings', 'addresses'} for f in areas['features'])
    assert store.project().state_hash() == before.state_hash()
    assert store.project().address_hash() == before.address_hash()
    assert not client.get('/api/project').json()['stale']
    body = {'id':areas['features'][0]['properties']['id'], 'status':'needs_review', 'note':'Path hidden by trees', 'revision':store.revision()}
    assert client.post('/api/work-areas/status', json=body).status_code == 200
    assert client.post('/api/work-areas/status', json=body).status_code == 409
    checkpoint = client.post('/api/save', json={'label':'area review'}).json()['checkpoint']
    client.post('/api/undo')
    assert store.project().work_areas['features'][0]['properties']['status'] == 'unreviewed'
    client.post('/api/restore', json={'id':checkpoint})
    reopened = TestClient(create_app(root, auth_enabled=False, auto_compute=False))
    saved = reopened.get('/api/project').json()['work_areas']['features'][0]['properties']
    assert saved['status'] == 'needs_review'
    assert saved['note'] == 'Path hidden by trees'
    assert reopened.post('/api/work-areas/grid', json={'cell_m':100,'revision':store.revision()}).status_code == 409


def test_five_independent_area_stages_are_saved(client):
    store = client.app.state.ctx.store
    areas = client.post('/api/work-areas/grid', json={'cell_m': 250, 'revision': store.revision()}).json()['areas']
    area_id = areas['features'][0]['properties']['id']
    stages = {'geometry': 'reviewed', 'attributes': 'in_progress', 'names': 'waiting_for_community',
              'buildings': 'needs_review', 'addresses': 'needs_correction'}
    response = client.post('/api/work-areas/status', json={'id': area_id, 'stages': stages, 'note': 'five checks', 'revision': store.revision()})
    assert response.status_code == 200, response.text
    saved = store.project().work_areas['features'][0]['properties']
    assert saved['stages'] == stages
    assert saved['status'] == 'needs_review'


def test_quartier_preview_and_provisional_partition_keep_only_safe_summary():
    import geopandas as gpd
    import shapely
    from shapely.geometry import box, shape
    from osmaddresssystem.app.work_areas import make_quartiers, preview_quartiers

    aoi = box(10.0, 5.0, 10.03, 5.03)
    content = ("district,latitude,longitude,phone,household_income\n"
               "NDE-NDE,5.005,10.005,+237SECRET,private\n"
               "Nde Nde,5.010,10.008,+237SECRET,private\n"
               "FONGO,5.020,10.023,+237SECRET,private\n"
               "FONGO,5.025,10.025,+237SECRET,private\n"
               "OUTSIDE,6,11,+237SECRET,private\n").encode()
    preview = preview_quartiers(content, aoi)
    assert preview['inside_rows'] == 4
    assert preview['outside_rows'] == 1
    assert {group['canonical'] for group in preview['groups']} == {'Nde Nde', 'FONGO'}
    nde_group = next(group for group in preview['groups'] if group['canonical'].startswith('N'))
    assert {variant['name'] for variant in nde_group['variants']} == {'NDE-NDE', 'Nde Nde'}
    nde_keys = [nde_group['key']]
    mapping = {key: 'NDE-NDE' for key in nde_keys}
    result = make_quartiers(content, aoi, 32632, mapping)
    assert result['kind'] == 'quartiers'
    assert result['provisional'] is True
    assert {feature['properties']['name'] for feature in result['features']} == {'NDE-NDE', 'FONGO'}
    saved_text = str(result)
    assert '+237SECRET' not in saved_text and 'household_income' not in saved_text
    covered = shapely.union_all([shape(feature['geometry']) for feature in result['features']])
    projected = gpd.GeoSeries([aoi, covered], crs=4326).to_crs(32632)
    assert projected.iloc[0].symmetric_difference(projected.iloc[1]).area < 1


def test_fotouni_catalog_applies_confirmed_aliases_codes_and_exclusions():
    from shapely.geometry import box
    from osmaddresssystem.app.work_areas import make_quartiers, preview_quartiers
    aoi = box(10, 5, 10.03, 5.03)
    content = ("district,latitude,longitude\n"
               "Balassie,5.005,10.005\nLassie,5.008,10.008\n"
               "Tchono,5.020,10.022\nTchounou,5.025,10.025\n"
               "Unknown,5.015,10.015\n").encode()
    preview = preview_quartiers(content, aoi, use_fotouni_catalog=True)
    approved = {group['canonical']: group.get('approved_name') for group in preview['groups']}
    assert approved['Balassie'] == 'Lassié'
    assert approved['Tchono'] == 'Tchouno'
    assert next(group for group in preview['groups'] if group['canonical'] == 'Unknown')['catalog_status'] == 'not_in_catalog'
    result = make_quartiers(content, aoi, 32632, use_fotouni_catalog=True)
    assert {(f['properties']['name'], f['properties']['code']) for f in result['features']} == {('Lassié', 'LAS'), ('Tchouno', 'TCO')}
    assert result['source']['excluded_by_catalog'] == 1


def test_quartier_api_preview_save_and_explicit_replace(client):
    store = client.app.state.ctx.store
    coordinates = [H.lonlat(H.X0, H.Y0), H.lonlat(H.X0 + 40, H.Y0 + 40),
                   H.lonlat(H.X0 + 450, H.Y0 + 350), H.lonlat(H.X0 + 500, H.Y0 + 400)]
    lines = ['district,latitude,longitude,private_note']
    for name, (lon, lat) in zip(['West', 'WEST', 'East', 'East'], coordinates):
        lines.append(f'{name},{lat},{lon},do-not-save')
    content_b64 = base64.b64encode(('\n'.join(lines) + '\n').encode()).decode()
    preview = client.post('/api/work-areas/quartiers/preview', json={'content_b64': content_b64, 'use_fotouni_catalog': False})
    assert preview.status_code == 200, preview.text
    assert preview.json()['inside_rows'] == 4
    response = client.post('/api/work-areas/quartiers', json={'content_b64': content_b64, 'filename': '../survey.csv',
                           'mapping': {'west': 'West', 'east': 'East'}, 'use_fotouni_catalog': False, 'revision': store.revision()})
    assert response.status_code == 200, response.text
    saved = store.project().work_areas
    assert saved['kind'] == 'hierarchy'
    assert saved['features']
    assert saved['quartiers']['source']['filename'] == 'survey.csv'
    assert all('quartier_id' in feature['properties'] for feature in saved['features'])
    assert 'do-not-save' not in str(saved)
    rejected = client.post('/api/work-areas/quartiers', json={'content_b64': content_b64, 'use_fotouni_catalog': False, 'revision': store.revision()})
    assert rejected.status_code == 409


def test_shared_quartier_boundary_can_be_reshaped_without_gap_or_overlap():
    import shapely
    from shapely.geometry import box, shape
    from osmaddresssystem.app.work_areas import boundary_options, default_stages, reshape_boundary, shared_boundaries

    def feature(area_id, name, geometry):
        return {'type': 'Feature', 'properties': {'id': area_id, 'kind': 'quartier', 'name': name,
                'status': 'unreviewed', 'stages': default_stages(), 'note': ''},
                'geometry': shapely.geometry.mapping(geometry)}
    original_union = box(10, 5, 10.02, 5.02)
    areas = {'kind': 'quartiers', 'type': 'FeatureCollection', 'features': [
        feature('Q01', 'West', box(10, 5, 10.01, 5.02)), feature('Q02', 'East', box(10.01, 5, 10.02, 5.02))]}
    options = boundary_options(areas, 'Q01', 32632)
    assert len(options) == 1 and options[0]['id'] == 'Q02'
    hover_boundaries = shared_boundaries(areas, 32632)
    assert len(hover_boundaries['features']) == 1
    hover = hover_boundaries['features'][0]
    assert {hover['properties']['left_name'], hover['properties']['right_name']} == {'West', 'East'}
    assert hover['properties']['length_m'] > 1000
    line = options[0]['geometry']['coordinates']
    midpoint = [(line[0][0] + line[-1][0]) / 2 + .001, (line[0][1] + line[-1][1]) / 2]
    changed = reshape_boundary(areas, 'Q01', 'Q02', [line[0], midpoint, line[-1]], 'Confirmed with field agent', 32632)
    west, east = [shape(f['geometry']) for f in changed['features']]
    assert west.intersection(east).area < 1e-12
    assert west.union(east).symmetric_difference(original_union).area < 1e-12
    assert changed['features'][0]['properties']['boundary_note'] == 'Confirmed with field agent'
    assert changed['features'][0]['properties']['stages']['geometry'] == 'in_progress'


def test_quartier_boundary_rejects_moved_endpoints_and_short_reason():
    import shapely
    from shapely.geometry import box
    from osmaddresssystem.app.work_areas import default_stages, reshape_boundary
    features = []
    for area_id, name, geometry in [('Q01', 'West', box(10, 5, 10.01, 5.02)), ('Q02', 'East', box(10.01, 5, 10.02, 5.02))]:
        features.append({'type': 'Feature', 'properties': {'id': area_id, 'kind': 'quartier', 'name': name,
                        'status': 'unreviewed', 'stages': default_stages()}, 'geometry': shapely.geometry.mapping(geometry)})
    areas = {'kind': 'quartiers', 'type': 'FeatureCollection', 'features': features}
    import pytest
    with pytest.raises(ValueError, match='5 to 500'):
        reshape_boundary(areas, 'Q01', 'Q02', [[10.01, 5], [10.01, 5.02]], 'no', 32632)
    with pytest.raises(ValueError, match='endpoints'):
        reshape_boundary(areas, 'Q01', 'Q02', [[10.011, 5], [10.01, 5.02]], 'Field confirmation', 32632)


def test_grid_rejects_invalid_size_and_stale_create(client):
    store = client.app.state.ctx.store
    assert client.post('/api/work-areas/grid', json={'cell_m':1,'revision':store.revision()}).status_code == 400
    rev = store.revision()
    store.set_name(1,'Test')
    assert client.post('/api/work-areas/grid', json={'cell_m':250,'revision':rev}).status_code == 409
    assert not store.project().work_areas


def test_automatic_grid_handles_a_large_boundary_without_tiny_cells():
    import geopandas as gpd
    from shapely.geometry import box
    from osmaddresssystem.app.work_areas import make_grid
    boundary = gpd.GeoSeries([box(600000,570000,620000,590000)],crs=32632).to_crs(4326).iloc[0]
    grid = make_grid(boundary,32632,'auto')
    assert 1 < len(grid['features']) <= 144
    assert grid['cell_m'] > 250


def test_grid_counts_actual_work_areas_not_empty_space_between_them():
    import geopandas as gpd
    from shapely.geometry import box
    from shapely.ops import unary_union
    from osmaddresssystem.app.work_areas import make_grid
    boundary = gpd.GeoSeries([unary_union([box(600000,570000,600400,570400),box(620000,590000,620400,590400)])],crs=32632).to_crs(4326).iloc[0]
    grid = make_grid(boundary,32632,500)
    assert 1 < len(grid['features']) < 10
