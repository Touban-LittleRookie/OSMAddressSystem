"""Persistent review areas: regular grids or provisional quartiers from survey points."""

import csv
import io
import math
import re
import unicodedata
from collections import Counter

import geopandas as gpd
import shapely
from shapely.geometry import LineString, MultiPoint, Point, box
from shapely.ops import split

from rapidfuzz.fuzz import ratio

STATUSES = {'unreviewed', 'in_progress', 'reviewed', 'needs_review'}
STAGE_STATUSES = {
    'geometry': {'not_started', 'in_progress', 'reviewed', 'needs_review'},
    'attributes': {'not_started', 'in_progress', 'reviewed', 'needs_review'},
    'names': {'not_started', 'in_progress', 'waiting_for_community', 'complete', 'needs_review'},
    'buildings': {'not_started', 'in_progress', 'reviewed', 'needs_review'},
    'addresses': {'not_started', 'in_progress', 'needs_correction', 'verified'},
}

# Approved Fotouni catalogue supplied in ``Overview Abbreviations.xlsx`` on 2 November 2026.
# The user subsequently confirmed that Balassie is Lassié, so it is deliberately an alias, not a second quartier.
# Baving (survey spelling) is Mving: confirmed by Boris on 16 November 2026.
FOTOUNI_QUARTIERS = [
    ('Babong', 'BAB', ['Badong']), ('Badenla', 'BDL', []), ('Balafi', 'BLF', []),
    ('Balatchie', 'BLT', ['Balatchi']), ('Bamendjo', 'BMJ', ['Bamedjo']),
    ('Bandja', 'BDJ', ['Bandjaing']), ('Bankwop', 'BKW', ['Bakwop']), ('Bano', 'BAN', ['Bani']),
    ('Djeugne', 'DJG', []), ('Fangam', 'FGM', ['Famgam', 'Famgang']), ('Fotouni', 'FOT', []),
    ('Hiela', 'HIE', ['HIELA', 'Heila', 'Hiela-Tonga', 'Hiela-Marché Fotouni']), ('Kouotchack', 'KTC', []),
    ('Lassié', 'LAS', ['Balassie', 'Lassie', 'Lasssie']), ('Mbeum', 'MBM', []),
    ('Mving', 'MVI', ['mving', 'Bavong', 'Bving', 'Bvong', 'Baving']), ('Ngonfet', 'NGF', ['Gonfet']),
    ("Nguaka'am", 'NGK', ["NGUAKA'AM", "Ngaka'am", "Nganka'am", 'Nguaka’am']),
    ('Song', 'SON', ['SONG', 'Sang']), ('Tcham', 'TCM', []), ('Tchikong', 'TCK', ['Tchikwong']),
    ('Tchisso', 'TCS', ['Tchisson']), ('Tchouno', 'TCO', ['Tchono', 'Tchounou']), ('Toukong', 'TKG', [])]


def fotouni_catalog() -> dict:
    """Return canonical-name, trigram and alias lookup for the approved pilot catalogue."""
    lookup, entries = {}, []
    for name, code, aliases in FOTOUNI_QUARTIERS:
        entry = {'name': name, 'code': code, 'aliases': aliases}
        entries.append(entry)
        for value in [name, *aliases]:
            lookup[_name_key(value)] = entry
    return {'entries': entries, 'lookup': lookup}


def default_stages() -> dict:
    """Fresh progress values for the five independent review stages."""
    return {name: 'not_started' for name in STAGE_STATUSES}


def ensure_stages(properties: dict) -> dict:
    """Return validated stage values, migrating a legacy general status as geometry only."""
    stages = default_stages()
    supplied = properties.get('stages') if isinstance(properties.get('stages'), dict) else {}
    for name, allowed in STAGE_STATUSES.items():
        if supplied.get(name) in allowed:
            stages[name] = supplied[name]
    if not supplied:
        legacy = properties.get('status', 'unreviewed')
        stages['geometry'] = {'in_progress': 'in_progress', 'reviewed': 'reviewed', 'needs_review': 'needs_review'}.get(legacy, 'not_started')
    return stages


def overall_status(stages: dict) -> str:
    """Compact colour/status derived from all five stage values."""
    values = set(stages.values())
    if values & {'needs_review', 'needs_correction'}:
        return 'needs_review'
    done = {'geometry': 'reviewed', 'attributes': 'reviewed', 'names': 'complete', 'buildings': 'reviewed', 'addresses': 'verified'}
    if all(stages.get(k) == v for k, v in done.items()):
        return 'reviewed'
    if values != {'not_started'}:
        return 'in_progress'
    return 'unreviewed'


def _properties(area_id: str, **extra) -> dict:
    stages = default_stages()
    return {'id': area_id, 'status': overall_status(stages), 'stages': stages, 'note': '', **extra}


def make_grid(aoi_wgs84, crs, cell_m: float | str) -> dict:
    """Square work areas of ``cell_m`` metres covering the boundary; every cell that touches it is kept whole (never clipped)."""
    aoi = gpd.GeoSeries([aoi_wgs84], crs=4326).to_crs(crs).iloc[0]
    x0, y0, x1, y1 = aoi.bounds
    if cell_m == 'auto':
        cell_m = max(50, math.ceil(max(x1-x0, y1-y0)/12/50)*50)
    elif not math.isfinite(cell_m) or not 50 <= cell_m <= 2000:
        raise ValueError('choose Auto or an area size from 50 to 2000 metres')
    cols, rows = math.ceil((x1-x0)/cell_m), math.ceil((y1-y0)/cell_m)
    if rows * cols > 10000:
        raise ValueError('more than 400 areas; choose Auto or a larger area size')
    cells = []
    for row in range(rows):
        for col in range(cols):
            shape = box(x0+col*cell_m, y1-(row+1)*cell_m, x0+(col+1)*cell_m, y1-row*cell_m)
            if shape.intersection(aoi).area < 1:            # keep whole squares: a cell is not cut to the boundary
                continue
            geom = gpd.GeoSeries([shape], crs=crs).to_crs(4326).iloc[0]
            cells.append({'type': 'Feature', 'properties': _properties(f'R{row+1:02}C{col+1:02}', kind='grid'),
                          'geometry': shapely.geometry.mapping(geom)})
            if len(cells) > 400:
                raise ValueError('more than 400 areas; choose Auto or a larger area size')
    return {'kind': 'grid', 'cell_m': cell_m, 'type': 'FeatureCollection', 'features': cells}


def grid_collection(areas: dict) -> dict:
    """Return the child work-cell collection from legacy or hierarchical storage."""
    if areas.get('kind') == 'hierarchy':
        return {'kind': 'grid', 'cell_m': areas.get('cell_m'), 'type': 'FeatureCollection',
                'features': areas.get('features', [])}
    return areas if areas.get('kind') == 'grid' else {}


def quartier_collection(areas: dict) -> dict:
    """Return the parent quartier collection from legacy or hierarchical storage."""
    if areas.get('kind') == 'hierarchy':
        return areas.get('quartiers') or {}
    return areas if areas.get('kind') == 'quartiers' else {}


def make_hierarchy(grid: dict, quartiers: dict, crs) -> dict:
    """Keep the original work cells beneath quartier parents and assign each cell by greatest overlap."""
    import copy
    grid, quartiers = copy.deepcopy(grid), copy.deepcopy(quartiers)
    q_features = quartiers.get('features', [])
    if grid.get('features') and q_features:
        q_shapes = [(feature['properties']['id'], feature['properties'].get('name'),
                     gpd.GeoSeries([shapely.geometry.shape(feature['geometry'])], crs=4326).to_crs(crs).iloc[0])
                    for feature in q_features]
        for cell in grid['features']:
            shape = gpd.GeoSeries([shapely.geometry.shape(cell['geometry'])], crs=4326).to_crs(crs).iloc[0]
            overlaps = [(shape.intersection(q_shape).area, qid, name) for qid, name, q_shape in q_shapes]
            area, qid, name = max(overlaps, default=(0, None, None))
            cell['properties'].update(quartier_id=qid if area > 0 else None,
                                      quartier_name=name if area > 0 else None)
    return {'kind': 'hierarchy', 'type': 'FeatureCollection', 'cell_m': grid.get('cell_m'),
            'features': grid.get('features', []), 'quartiers': quartiers}


def _name_key(value: str) -> str:
    """Conservative matching key: case, accents, apostrophe style and whitespace only."""
    value = value.strip().replace('’', "'").replace('`', "'")
    value = ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9']+", ' ', value).strip()


def _read_quartier_csv(content: bytes, aoi_wgs84, district_column='district', lat_column='latitude', lon_column='longitude') -> dict:
    """Extract only quartier spelling and coordinates; no private survey columns are retained."""
    if not content or len(content) > 10 * 1024 * 1024:
        raise ValueError('choose a non-empty CSV smaller than 10 MB')
    text = None
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252'):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError('the CSV encoding is not supported')
    reader = csv.DictReader(io.StringIO(text))
    fields = {str(f).strip().casefold(): f for f in (reader.fieldnames or [])}
    def col(requested):
        found = fields.get(str(requested).strip().casefold())
        if not found:
            raise ValueError(f'missing CSV column: {requested}')
        return found
    dc, lac, loc = col(district_column), col(lat_column), col(lon_column)
    records, invalid, outside = [], 0, 0
    for i, row in enumerate(reader):
        if i >= 100000:
            raise ValueError('the CSV has more than 100,000 rows')
        raw = str(row.get(dc) or '').strip()
        try:
            lat, lon = float(row.get(lac)), float(row.get(loc))
        except (TypeError, ValueError):
            invalid += 1
            continue
        if not raw or not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            invalid += 1
            continue
        point = Point(lon, lat)
        if not aoi_wgs84.covers(point):
            outside += 1
            continue
        key = _name_key(raw)
        if not key:
            invalid += 1
            continue
        records.append({'key': key, 'raw': raw, 'lat': lat, 'lon': lon})
    if not records:
        raise ValueError('no labelled CSV point falls inside the project boundary')
    return {'records': records, 'invalid_rows': invalid, 'outside_rows': outside, 'total_rows': len(records) + invalid + outside}


def preview_quartiers(content: bytes, aoi_wgs84, district_column='district', lat_column='latitude', lon_column='longitude',
                      use_fotouni_catalog=False) -> dict:
    """Summarise conservative spelling groups and possible similar-name aliases."""
    parsed = _read_quartier_csv(content, aoi_wgs84, district_column, lat_column, lon_column)
    variants: dict[str, Counter] = {}
    for row in parsed['records']:
        variants.setdefault(row['key'], Counter())[row['raw']] += 1
    groups = []
    for key, counts in variants.items():
        ordered = sorted(counts.items(), key=lambda x: (-x[1], x[0].casefold(), x[0]))
        groups.append({'key': key, 'canonical': ordered[0][0], 'points': sum(counts.values()),
                       'variants': [{'name': name, 'count': count} for name, count in ordered]})
    groups.sort(key=lambda g: (_name_key(g['canonical']), g['canonical']))
    catalog_summary = None
    if use_fotouni_catalog:
        catalog = fotouni_catalog()
        present = set()
        for group in groups:
            entry = catalog['lookup'].get(group['key'])
            group.update(catalog_status='approved' if entry else 'not_in_catalog',
                         approved_name=entry['name'] if entry else None, code=entry['code'] if entry else None)
            if entry:
                present.add(entry['name'])
        catalog_summary = {'approved': len(catalog['entries']),
                           'with_points': len(present),
                           'without_points': [entry for entry in catalog['entries'] if entry['name'] not in present]}
    suggestions = []
    for i, left in enumerate(groups):
        for right in groups[i+1:]:
            score = ratio(left['key'], right['key'])
            if score >= 84:
                suggestions.append({'left': left['key'], 'right': right['key'], 'score': round(score),
                                    'message': f"{left['canonical']} / {right['canonical']}"})
    suggestions.sort(key=lambda x: (-x['score'], x['message']))
    return {'groups': groups, 'suggestions': suggestions[:100], 'catalog': catalog_summary,
            'inside_rows': len(parsed['records']), 'outside_rows': parsed['outside_rows'],
            'invalid_rows': parsed['invalid_rows'], 'total_rows': parsed['total_rows']}


def make_quartiers(content: bytes, aoi_wgs84, crs, mapping: dict | None = None,
                    district_column='district', lat_column='latitude', lon_column='longitude', use_fotouni_catalog=False) -> dict:
    """Create a provisional, complete AOI partition using point Voronoi cells united by reviewed quartier name."""
    parsed = _read_quartier_csv(content, aoi_wgs84, district_column, lat_column, lon_column)
    preview = preview_quartiers(content, aoi_wgs84, district_column, lat_column, lon_column, use_fotouni_catalog)
    defaults = {g['key']: g['canonical'] for g in preview['groups']}
    mapping = mapping or {}
    chosen = {}
    for key, default in defaults.items():
        group = next(group for group in preview['groups'] if group['key'] == key)
        if use_fotouni_catalog and group.get('catalog_status') != 'approved':
            continue
        name = str(group.get('approved_name') or mapping.get(key, default)).strip()
        if not name or len(name) > 120:
            raise ValueError(f'enter a quartier name of 1-120 characters for {default}')
        chosen[key] = name
    if len({_name_key(v) for v in chosen.values()}) < 2:
        raise ValueError('at least two different quartiers are required')

    aoi = gpd.GeoSeries([aoi_wgs84], crs=4326).to_crs(crs).iloc[0]
    accepted_records = [row for row in parsed['records'] if row['key'] in chosen]
    excluded_catalog = len(parsed['records']) - len(accepted_records)
    if len(accepted_records) < 2:
        raise ValueError('not enough approved quartier points to create areas')
    parsed['records'] = accepted_records
    source = gpd.GeoDataFrame(parsed['records'], geometry=[Point(r['lon'], r['lat']) for r in parsed['records']], crs=4326).to_crs(crs)
    # Repeated survey coordinates are harmless. Conflicting labels at exactly the same location are excluded and reported.
    positions: dict[tuple[float, float], list] = {}
    for row, geom in zip(parsed['records'], source.geometry):
        positions.setdefault((round(geom.x, 3), round(geom.y, 3)), []).append((row, geom))
    samples, conflicts = [], 0
    for rows in positions.values():
        names = {_name_key(chosen[r['key']]) for r, _g in rows}
        if len(names) != 1:
            conflicts += len(rows)
            continue
        samples.append((rows[0][1], chosen[rows[0][0]['key']]))
    if len(samples) < 2:
        raise ValueError('not enough distinct, non-conflicting coordinates to create quartier areas')
    points = [p for p, _name in samples]
    cells = shapely.voronoi_polygons(MultiPoint(points), extend_to=aoi.envelope, ordered=True)
    by_name: dict[str, list] = {}
    for cell, (_point, name) in zip(cells.geoms, samples):
        clipped = shapely.make_valid(cell.intersection(aoi))
        if not clipped.is_empty:
            by_name.setdefault(name, []).append(clipped)

    variant_counts: dict[str, Counter] = {}
    point_counts: Counter = Counter()
    for row in parsed['records']:
        name = chosen[row['key']]
        variant_counts.setdefault(name, Counter())[row['raw']] += 1
        point_counts[name] += 1
    features = []
    for index, name in enumerate(sorted(by_name, key=lambda x: (_name_key(x), x)), 1):
        shape = shapely.make_valid(shapely.union_all(by_name[name]).intersection(aoi))
        geom = gpd.GeoSeries([shape], crs=crs).to_crs(4326).iloc[0]
        aliases = [{'name': alias, 'count': count} for alias, count in sorted(variant_counts[name].items(), key=lambda x: (-x[1], x[0].casefold()))]
        catalog_entry = fotouni_catalog()['lookup'].get(_name_key(name)) if use_fotouni_catalog else None
        features.append({'type': 'Feature',
                         'properties': _properties(f'Q{index:02}', kind='quartier', name=name,
                                                   code=catalog_entry['code'] if catalog_entry else None, aliases=aliases,
                                                   point_count=int(point_counts[name]), provisional=True),
                         'geometry': shapely.geometry.mapping(geom)})
    return {'kind': 'quartiers', 'method': 'survey_point_voronoi', 'provisional': True,
            'type': 'FeatureCollection', 'features': features,
            'source': {'inside_rows': len(parsed['records']), 'outside_rows': parsed['outside_rows'],
                       'invalid_rows': parsed['invalid_rows'], 'excluded_by_catalog': excluded_catalog,
                       'catalog_quartiers_without_points': preview.get('catalog', {}).get('without_points', []) if preview.get('catalog') else [],
                       'conflicting_coordinate_rows': conflicts}}


def _line_parts(geometry):
    """Yield non-empty lines from any boundary intersection."""
    if geometry.geom_type == 'LineString':
        if geometry.length:
            yield geometry
    elif geometry.geom_type in {'MultiLineString', 'GeometryCollection'}:
        for part in geometry.geoms:
            yield from _line_parts(part)


def boundary_options(areas: dict, area_id: str, crs) -> list[dict]:
    """Return editable shared borders between one quartier and its neighbours."""
    features = areas.get('features', [])
    selected = next((f for f in features if f.get('properties', {}).get('id') == area_id), None)
    if selected is None or selected.get('properties', {}).get('kind') != 'quartier':
        raise ValueError('select a quartier area')
    selected_shape = gpd.GeoSeries([shapely.geometry.shape(selected['geometry'])], crs=4326).to_crs(crs).iloc[0]
    options = []
    for feature in features:
        props = feature.get('properties', {})
        if props.get('id') == area_id or props.get('kind') != 'quartier':
            continue
        other = gpd.GeoSeries([shapely.geometry.shape(feature['geometry'])], crs=4326).to_crs(crs).iloc[0]
        parts = sorted(_line_parts(selected_shape.boundary.intersection(other.boundary)), key=lambda line: line.length, reverse=True)
        if not parts or parts[0].length < 1:
            continue
        line = gpd.GeoSeries([parts[0]], crs=crs).to_crs(4326).iloc[0]
        options.append({'id': props['id'], 'name': props.get('name') or props['id'],
                        'length_m': round(parts[0].length, 1), 'geometry': shapely.geometry.mapping(line)})
    return sorted(options, key=lambda option: (_name_key(option['name']), option['id']))


def shared_boundaries(areas: dict, crs) -> dict:
    """Return every unique shared quartier boundary with both adjacent quartier identities."""
    features = areas.get('features', [])
    projected = []
    for feature in features:
        if feature.get('properties', {}).get('kind') != 'quartier':
            continue
        shape = gpd.GeoSeries([shapely.geometry.shape(feature['geometry'])], crs=4326).to_crs(crs).iloc[0]
        projected.append((feature, shape))
    boundaries = []
    for index, (left, left_shape) in enumerate(projected):
        for right, right_shape in projected[index+1:]:
            parts = [line for line in _line_parts(left_shape.boundary.intersection(right_shape.boundary)) if line.length >= 1]
            if not parts:
                continue
            shared = shapely.union_all(parts)
            wgs = gpd.GeoSeries([shared], crs=crs).to_crs(4326).iloc[0]
            lp, rp = left['properties'], right['properties']
            boundaries.append({'type': 'Feature', 'properties': {
                'id': f"{lp['id']}--{rp['id']}", 'left_id': lp['id'], 'left_name': lp.get('name') or lp['id'],
                'right_id': rp['id'], 'right_name': rp.get('name') or rp['id'], 'length_m': round(shared.length, 1)},
                'geometry': shapely.geometry.mapping(wgs)})
    return {'type': 'FeatureCollection', 'features': boundaries}


def reshape_boundary(areas: dict, area_id: str, neighbour_id: str, coords: list, reason: str, crs) -> dict:
    """Move one shared quartier border while preserving the two-area union exactly."""
    import copy
    if not isinstance(reason, str) or not 5 <= len(reason.strip()) <= 500:
        raise ValueError('explain the boundary change in 5 to 500 characters')
    if not isinstance(coords, list) or not 2 <= len(coords) <= 1000:
        raise ValueError('a boundary needs 2 to 1,000 points')
    try:
        proposed_wgs = LineString([(float(point[0]), float(point[1])) for point in coords])
    except (TypeError, ValueError, IndexError):
        raise ValueError('provide valid longitude/latitude boundary points')
    if proposed_wgs.is_empty or not proposed_wgs.is_simple:
        raise ValueError('the proposed boundary must not cross itself')

    result = copy.deepcopy(areas)
    by_id = {f.get('properties', {}).get('id'): f for f in result.get('features', [])}
    if area_id == neighbour_id or area_id not in by_id or neighbour_id not in by_id:
        raise ValueError('select two different neighbouring quartiers')
    left, right = by_id[area_id], by_id[neighbour_id]
    if left['properties'].get('kind') != 'quartier' or right['properties'].get('kind') != 'quartier':
        raise ValueError('boundary editing is available only for quartier areas')
    left_shape, right_shape, proposed = gpd.GeoSeries(
        [shapely.geometry.shape(left['geometry']), shapely.geometry.shape(right['geometry']), proposed_wgs], crs=4326
    ).to_crs(crs)
    shared = sorted(_line_parts(left_shape.boundary.intersection(right_shape.boundary)), key=lambda line: line.length, reverse=True)
    if not shared or shared[0].length < 1:
        raise ValueError('the selected quartiers do not share an editable border')
    old_line = shared[0]
    a0, a1 = Point(old_line.coords[0]), Point(old_line.coords[-1])
    b0, b1 = Point(proposed.coords[0]), Point(proposed.coords[-1])
    endpoint_error = min(a0.distance(b0) + a1.distance(b1), a0.distance(b1) + a1.distance(b0))
    if endpoint_error > 2:
        raise ValueError('the two fixed boundary endpoints must not move')
    if proposed.length < 1:
        raise ValueError('the proposed boundary is too short')

    pair = shapely.make_valid(left_shape.union(right_shape))
    components = list(pair.geoms) if pair.geom_type == 'MultiPolygon' else [pair]
    local = min(components, key=lambda component: component.distance(old_line.interpolate(.5, normalized=True)))
    if local.distance(old_line.interpolate(.5, normalized=True)) > 1 or not local.buffer(1).covers(proposed):
        raise ValueError('keep the corrected border inside the two selected quartiers')
    # Projection round-off can place a fixed endpoint a fraction inside the outer boundary. Extend only the
    # temporary cutting line; the geometry saved below still uses the user's exact fixed endpoints.
    cut_coords = list(proposed.coords)
    def extend(point, neighbour, metres=2):
        dx, dy = point[0]-neighbour[0], point[1]-neighbour[1]
        length = math.hypot(dx, dy)
        return (point[0]+dx/length*metres, point[1]+dy/length*metres) if length else point
    cutting_line = LineString([extend(cut_coords[0], cut_coords[1]), *cut_coords[1:-1], extend(cut_coords[-1], cut_coords[-2])])
    pieces = [part for part in split(local, cutting_line).geoms if part.geom_type in {'Polygon', 'MultiPolygon'} and part.area > .01]
    if len(pieces) != 2:
        raise ValueError('the corrected line must divide the two quartiers into exactly two parts')
    left_local = left_shape.intersection(local)
    left_index = max(range(2), key=lambda index: pieces[index].intersection(left_local).area)
    left_piece, right_piece = pieces[left_index], pieces[1-left_index]
    new_left = shapely.make_valid(left_shape.difference(local).union(left_piece))
    new_right = shapely.make_valid(right_shape.difference(local).union(right_piece))
    if abs(new_left.union(new_right).area - pair.area) > .1 or new_left.intersection(new_right).area > .1:
        raise ValueError('the correction would create a gap or overlap')

    converted = gpd.GeoSeries([new_left, new_right], crs=crs).to_crs(4326)
    left['geometry'], right['geometry'] = shapely.geometry.mapping(converted.iloc[0]), shapely.geometry.mapping(converted.iloc[1])
    for feature in (left, right):
        stages = ensure_stages(feature['properties'])
        if stages['geometry'] == 'not_started':
            stages['geometry'] = 'in_progress'
        feature['properties'].update(stages=stages, status=overall_status(stages),
                                     boundary_note=reason.strip(), boundary_provisional=True)
    return result
