"""Apply explicitly reviewed optical positions, preserving catalogue provenance.

This never identifies a transient by choosing a peak in a JWST image. Reviewed
measurements live in the private updater configuration, outside public source.
"""
import copy
import json
import math
import os
from pathlib import Path
from astropy.coordinates import SkyCoord

DEFAULT = Path(__file__).resolve().parents[1] / 'local/position-refinements.json'


def separation(a, b):
    return float(SkyCoord(a['ra'], a['dec'], unit='deg').separation(
        SkyCoord(b['ra'], b['dec'], unit='deg')).arcsec)


def apply_refinements(rows, path=None):
    path = Path(path or os.environ.get('ECHO_POSITION_REFINEMENTS', DEFAULT))
    records = json.loads(path.read_text()) if path.exists() else {'version': 1, 'objects': {}}
    if records.get('version') != 1 or not isinstance(records.get('objects'), dict):
        raise ValueError('Invalid reviewed-position configuration')
    for row in rows:
        prior = row.pop('astrometry', None)
        # Idempotent for cached catalogues. Fresh TNS merges remove this field.
        if prior and prior.get('status') == 'refined':
            row.update({k: prior['catalogue'][k] for k in ('ra', 'dec')})
        record = records['objects'].get(row['name'])
        if not record:
            continue
        if record.get('status') != 'reviewed' or not record.get('reviewedAt') or not record.get('references'):
            raise ValueError('Position refinement lacks reviewed provenance: ' + row['name'])
        if not all(isinstance(record.get(k), (int, float)) and math.isfinite(record[k]) for k in ('ra', 'dec')) or not 0 <= record['ra'] < 360 or not -90 <= record['dec'] <= 90:
            raise ValueError('Invalid refined coordinates: ' + row['name'])
        anchor = record['catalogue']
        source = row.get('provenance', {}).get('catalogue')
        if source != anchor['source'] or separation(row, anchor) > .001:
            row['astrometry'] = {'status': 'needs-review', 'note': 'Catalogue position changed; the earlier refinement is suspended.'}
            continue
        shift = separation(row, record)
        if shift > 2:
            raise ValueError('Reviewed refinement exceeds the 2 arcsecond guard: ' + row['name'])
        row['astrometry'] = {**copy.deepcopy(record), 'status': 'refined', 'offsetArcsec': shift}
        row['ra'], row['dec'] = record['ra'], record['dec']
    return rows


def fits_provenance(header, sn):
    position = sn.get('astrometry') or {}
    if position.get('status') == 'refined':
        header['SNPSRC'] = 'ZTF/Gaia optical refinement'
        header['CATRA'] = position['catalogue']['ra']
        header['CATDEC'] = position['catalogue']['dec']
        header['CATPSRC'] = position['catalogue']['source']
        header['POSSHIFT'] = (position['offsetArcsec'], 'Adopted minus catalogue separation [arcsec]')
        header['HISTORY'] = 'SN position from reviewed optical difference images tied to Gaia; archive WCS unchanged.'
    else:
        header['SNPSRC'] = 'Catalogue position'
