"""Merge the daily official TNS bulk snapshot, then rematch every coordinate.

TNS includes modern classified SNe, not a complete historical census. Unknown
redshifts cannot establish eligibility; earlier documented redshifts are retained.
"""
import collections
import csv
import io
import json
import math
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from geometry import unit, contains, ALL_IMAGING

ROOT = Path(os.environ.get('ECHO_WORK_DIR', str(Path(__file__).resolve().parent.parent / 'work')))


def identity(value):
    value = re.sub(r'\s+', '', str(value)).lower()
    # The same IAU designation changes prefix from AT to SN upon classification.
    return re.sub(r'^(?:sn|at)(?=\d{4})', 'iau:', value)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def read_snapshot(path, current_time=None):
    raw = Path(path).read_bytes()
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = [n for n in archive.namelist() if n.endswith('.csv')]
            if len(names) != 1:
                raise ValueError('Expected one TNS catalogue CSV')
            raw = archive.read(names[0])
    stream = io.StringIO(raw.decode('utf-8-sig'))
    timestamp = stream.readline().strip().strip('"')
    date = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
    age = ((current_time or datetime.now(timezone.utc)) - date).total_seconds()
    if age < -3600 or age > 48 * 3600:
        raise ValueError('TNS snapshot is stale or future-dated; previous publication retained')
    rows = list(csv.DictReader(stream))
    if not rows or not {'name', 'name_prefix', 'ra', 'declination', 'redshift', 'type'} <= rows[0].keys():
        raise ValueError('Incomplete TNS catalogue schema')
    return date.isoformat().replace('+00:00', 'Z'), rows


def merge(historical, tns_rows, timestamp):
    current = [dict(row) for row in historical]
    names = collections.defaultdict(set)
    for i, row in enumerate(current):
        for alias in [row['name'], *row['aliases']]:
            if alias.strip():
                names[identity(alias)].add(i)
    audit = {'snapshotAt': timestamp, 'sourceUrl': 'https://www.wis-tns.org/tns-bulk-data',
             'totalTnsRows': len(tns_rows), 'classifiedSn': 0, 'unknownRedshift': 0,
             'eligibleSn': 0, 'representedSn': 0, 'added': 0, 'updated': 0,
             'mergedHistoricalDuplicates': 0, 'removedByTnsRedshift': 0,
             'coordinateChangesOver1Arcsec': 0}
    changes = []
    eligible = []
    owners = collections.defaultdict(set)
    for tns in tns_rows:
        if tns['name_prefix'] == 'SN':
            for alias in [a.strip() for a in tns.get('internal_names', '').split(',') if a.strip()]:
                owners[identity(alias)].add(tns['name'])
    audit['ambiguousSurveyAliases'] = sum(len(values) > 1 for values in owners.values())
    for tns in tns_rows:
        if tns['name_prefix'] != 'SN':
            continue
        audit['classifiedSn'] += 1
        designation = 'SN' + tns['name']
        aliases = [designation, 'AT' + tns['name']] + [s.strip() for s in tns.get('internal_names', '').split(',') if s.strip()]
        # Survey identifiers can be reused across two IAU designations. Keep both
        # official records; a shared ambiguous alias is not proof of identity.
        matches = set().union(*(names.get(identity(a), set()) for a in aliases if len(owners.get(identity(a), set())) <= 1))
        matches = sorted(i for i in matches if current[i] is not None)
        z = number(tns['redshift'])
        if z is None:
            audit['unknownRedshift'] += 1
            continue
        if not -1 < z < 0.02:
            for i in matches:
                changes.append({'name': current[i]['name'], 'tnsName': designation, 'reason': 'TNS redshift outside selection', 'redshift': z})
                current[i] = None
                audit['removedByTnsRedshift'] += 1
            continue
        ra, dec = number(tns['ra']), number(tns['declination'])
        if ra is None or dec is None or not 0 <= ra < 360 or not -90 <= dec <= 90:
            raise ValueError('Eligible TNS SN has invalid coordinates: ' + designation)
        audit['eligibleSn'] += 1
        eligible.append(designation)
        prior = [current[i] for i in matches]
        # Shared survey aliases must never merge two distinct IAU SN designations.
        for row in prior:
            if row.get('provenance', {}).get('catalogue') == 'TNS' and identity(row['name']) != identity(designation):
                raise ValueError('Ambiguous TNS identity: ' + designation + ' / ' + row['name'])
        previous = prior[0] if prior else {}
        for row in prior:
            aliases.extend([row['name'], *row['aliases']])
            dot = float(unit([ra], [dec])[0] @ unit([row['ra']], [row['dec']])[0])
            delta = math.degrees(math.acos(max(-1, min(1, dot)))) * 3600
            if delta > 1:
                audit['coordinateChangesOver1Arcsec'] += 1
                changes.append({'name': row['name'], 'tnsName': designation, 'reason': 'Using current TNS coordinate', 'separationArcsec': delta})
        refs = list(previous.get('references', []))
        for key in ('Discovery_ADS_bibcode', 'Class_ADS_bibcodes'):
            refs.extend(x.strip() for x in tns.get(key, '').split(',') if re.match(r'^\d{4}', x.strip()))
        source_url = 'https://www.wis-tns.org/object/' + tns['name']
        row = {**previous, 'name': designation, 'aliases': list(dict.fromkeys(aliases)), 'ra': ra, 'dec': dec,
               'redshift': z, 'redshift_kind': 'TNS reported redshift',
               'redshifts': [{'value': z, 'kind': 'TNS reported redshift'}, *previous.get('redshifts', [])],
               'redshift_boundary_conflict': previous.get('redshift_boundary_conflict', False),
               'types': [tns['type'].removeprefix('SN ').strip() or 'SN'],
               'hosts': previous.get('hosts', []), 'discovery_dates': [tns['discoverydate']] if tns.get('discoverydate') else previous.get('discovery_dates', []),
               'references': list(dict.fromkeys(refs)), 'reference_urls': [source_url], 'catalogue_status': 'classified',
               'provenance': {'catalogue': 'TNS', 'source_url': source_url, 'snapshot_at': timestamp,
                              'source_modified_at': tns.get('lastmodified'), 'objid': tns.get('objid')}}
        if prior:
            i = matches[0]
            current[i] = row
            for duplicate in matches[1:]:
                current[duplicate] = None
            audit['updated'] += 1
            audit['mergedHistoricalDuplicates'] += max(0, len(matches) - 1)
        else:
            i = len(current)
            current.append(row)
            audit['added'] += 1
        for alias in row['aliases']:
            names[identity(alias)].add(i)
    current = [row for row in current if row is not None]
    final = {row['name'] for row in current}
    missing = sorted(set(eligible) - final)
    if missing:
        raise ValueError('Eligible TNS SNe lost during merge: ' + ', '.join(missing[:10]))
    audit['representedSn'] = len(eligible)
    audit['indexedObjects'] = len(current)
    audit['unknownRedshiftNote'] = 'TNS classified SNe without a finite bulk-catalogue redshift; some may be retained through historical redshifts. No distances inferred.'
    return current, audit, changes


def main(path):
    timestamp, tns = read_snapshot(path)
    rows, audit, changes = merge(json.loads((ROOT / 'nearby-current.json').read_text()), tns, timestamp)
    positions = unit([s['ra'] for s in rows], [s['dec'] for s in rows])
    matches = collections.defaultdict(list)
    for obs in json.loads((ROOT / 'all-jwst-mast.json').read_text())['data']:
        if obs['instrument_name'] not in ALL_IMAGING or not re.search(r'_(i2d|cal)\.fits$', obs.get('dataURL') or ''):
            continue
        for i in contains(obs['s_region'], positions):
            matches[rows[i]['name']].append(obs)
    for name, value in [('nearby-current.json', rows), ('matches-current.json', dict(matches)), ('tns-audit.json', audit), ('tns-changes.json', changes)]:
        path_out = ROOT / name
        tmp = path_out.with_suffix('.tmp')
        tmp.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False))
        tmp.replace(path_out)
    print('TNS catalogue audit:', json.dumps(audit), flush=True)


if __name__ == '__main__':
    import sys
    main(sys.argv[1])
