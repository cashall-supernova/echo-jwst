"""Fetch a complete CAOM result in one response and reject silent truncation.

Independent offset-page requests can receive different row orderings. Counting
rows alone then hides duplicates and missing observations. A single result avoids
that failure; the archive's advertised count and unique IDs are both checked.
"""
import json
import time
from datetime import datetime, timezone

COLUMNS = 'obsid,obs_id,s_ra,s_dec,s_region,t_min,t_max,t_exptime,instrument_name,filters,proposal_id,dataURL,t_obs_release,dataRights,calib_level'


def validate(result, allow_empty=False):
    if result.get('status') != 'COMPLETE':
        raise RuntimeError('MAST query did not complete; previous publication retained')
    rows = result.get('data', [])
    paging = result.get('paging', {})
    expected = paging.get('rowsFiltered')
    if expected is None or int(expected) != len(rows) or int(paging.get('pagesFiltered', 1)) != 1:
        raise RuntimeError('MAST result is truncated; previous publication retained')
    ids = [str(row['obsid']) for row in rows]
    if len(set(ids)) != len(ids):
        raise RuntimeError('MAST returned duplicate observation IDs; previous publication retained')
    if not rows and not allow_empty:
        raise RuntimeError('MAST index is empty; previous publication retained')
    return rows


def fetch(http, level, rights='PUBLIC'):
    if rights not in ('PUBLIC','EXCLUSIVE_ACCESS'):
        raise ValueError('Unknown MAST access classification')
    filters = [{'paramName': 'obs_collection', 'values': ['JWST']},
               {'paramName': 'dataproduct_type', 'values': ['image']},
               {'paramName': 'calib_level', 'values': [{'min': level, 'max': level}]},
               {'paramName': 'dataRights', 'values': [rights]}]
    request = {'service': 'Mast.Caom.Filtered', 'params': {'columns': COLUMNS, 'filters': filters},
               'format': 'json', 'pagesize': 500000, 'page': 1, 'timeout': 60}
    deadline = time.monotonic() + 300
    while True:
        result = http('POST', 'https://mast.stsci.edu/api/v0/invoke', data={'request': json.dumps(request)}).json()
        if result.get('status') != 'EXECUTING' or time.monotonic() >= deadline:
            break
        print('Waiting for MAST level', level, 'query', flush=True)
        time.sleep(1)
    rows = validate(result, allow_empty=rights=='EXCLUSIVE_ACCESS')
    if any(row.get('dataRights') != rights for row in rows):
        raise RuntimeError('MAST access filter mismatch; publication aborted')
    print('MAST', rights, 'level', level, ':', len(rows), 'unique observations; full result verified', flush=True)
    return {'status': 'COMPLETE', 'paging': result['paging'], 'data': rows, 'dataRights':rights,
            'fetchedAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}
