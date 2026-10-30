"""Display-only RGB composites of coeval calibrated cutouts.

Never coadd archive mosaics: they can contain overlapping input exposures.
Each channel uses one product. Reprojection preserves surface brightness,
not point-source photometry; PSFs and residual astrometric errors are unmatched.
"""
import collections
import hashlib
import json
import math
import re
import warnings
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning
from astropy.wcs.utils import proj_plane_pixel_scales
from PIL import Image

VERSION = 'rgb-wcs-v1'


def wavelength(label):
    # In a filter+pupil pair the last filter is the narrower effective band.
    bands = re.findall(r'F(\d+)(?:W2|W|M|N)(?=;|$)', label)
    return int(bands[-1]) / 100 if bands else None


def groups(observations):
    """Require the same UTC day, program and instrument, with >=3 bands."""
    grouped = collections.defaultdict(list)
    for o in observations:
        if o['status'] != 'ready' or wavelength(o['filter']) is None:
            continue
        if not (math.isfinite(o['start']) and math.isfinite(o['end']) and
                o['start'] <= o['end'] and math.floor(o['start']) == math.floor(o['end'])):
            continue  # Multi-day mosaics cannot represent an individual date.
        key = (math.floor(o['start']), o['instrument'].split('/')[0], o['proposal'])
        grouped[key].append(o)
    result = []
    for key, products in sorted(grouped.items()):
        by_band = {}
        # Prefer mosaics, then greater usable coverage, then the shorter span.
        # A deterministic tie-break avoids duplicating overlapping products.
        products.sort(key=lambda o: (not o['uri'].endswith('_i2d.fits'),
                                     -o.get('coverage', 0), o['end']-o['start'], o['id']))
        for o in products:
            by_band.setdefault(wavelength(o['filter']), o)
        bands = sorted(by_band)
        if len(bands) < 3:
            continue
        blue, red = bands[0], bands[-1]
        middle = min(bands[1:-1], key=lambda b: abs(math.log(b) - math.log(blue*red)/2))
        result.append((key, [by_band[red], by_band[middle], by_band[blue]]))
    return result


def reproject_bilinear(data, source_wcs, target_wcs, shape):
    """Sample surface brightness on a common WCS grid, masking invalid support."""
    y, x = np.indices(shape, dtype=float)
    sx, sy = source_wcs.world_to_pixel_values(*target_wcs.pixel_to_world_values(x, y))
    finite = np.isfinite(sx) & np.isfinite(sy)
    sx = np.where(finite, sx, -2); sy = np.where(finite, sy, -2)
    x0 = np.floor(sx).astype(int); y0 = np.floor(sy).astype(int)
    valid = finite & (x0 >= 0) & (y0 >= 0) & (x0+1 < data.shape[1]) & (y0+1 < data.shape[0])
    xx = np.clip(x0, 0, data.shape[1]-2); yy = np.clip(y0, 0, data.shape[0]-2)
    dx, dy = sx-x0, sy-y0
    corners = [data[yy,xx], data[yy,xx+1], data[yy+1,xx], data[yy+1,xx+1]]
    valid &= np.all(np.isfinite(corners), axis=0)
    values = (corners[0]*(1-dx)*(1-dy) + corners[1]*dx*(1-dy) +
              corners[2]*(1-dx)*dy + corners[3]*dx*dy)
    return np.where(valid, values, np.nan).astype(np.float32)


def render_rgb(cube):
    channels = []
    valid = np.all(np.isfinite(cube), axis=0)
    for plane in cube:
        values = plane[valid]
        lo, hi = np.percentile(values, [1, 99.5])
        span = max(float(hi-lo), 1e-12)
        scaled = np.arcsinh(np.clip((np.nan_to_num(plane, nan=lo)-lo)/span, 0, 1)*10)/np.arcsinh(10)
        channels.append(scaled)
    rgb = np.uint8(np.clip(np.stack(channels, axis=-1)*255, 0, 255))
    rgb[~valid] = 0
    return Image.fromarray(np.flipud(rgb)).resize((400, 400), Image.Resampling.BICUBIC)


def make_composite(sn, key, products, cache, width_arcsec=None):
    cache = Path(cache)
    arrays, headers, wcses = [], [], []
    digest = hashlib.sha256(VERSION.encode())
    for o in products:
        path = cache/(o['id']+'.fits')
        digest.update(path.read_bytes())
        with fits.open(path, checksum=True) as hdul:
            if hdul[0].verify_checksum() != 1 or hdul[0].verify_datasum() != 1:
                raise ValueError('Input FITS checksum failed')
            if hdul[0].header.get('BUNIT', '').lower() != 'mjy/sr':
                raise ValueError('RGB inputs must have surface-brightness units MJy/sr')
            arrays.append(hdul[0].data.copy()); headers.append(hdul[0].header.copy())
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', FITSFixedWarning)
                wcses.append(WCS(hdul[0].header).celestial)
    # Use the common input field, north up / east left, at no finer than the
    # coarsest native pixel scale. Never pad a small cutout to imply more sky.
    width = min(float(o.get('widthArcsec',10)) for o in products)
    if width_arcsec is not None: width = min(width, float(width_arcsec))
    scale = max(float(np.max(proj_plane_pixel_scales(w)))*3600 for w in wcses)
    n = max(3, math.floor(width/scale)); scale = width/n
    target = WCS(naxis=2)
    target.wcs.crpix = [(n+1)/2, (n+1)/2]
    target.wcs.crval = [sn['ra'], sn['dec']]
    target.wcs.cdelt = [-scale/3600, scale/3600]
    target.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    cube = np.stack([reproject_bilinear(a,w,target,(n,n)) for a,w in zip(arrays,wcses)])
    valid = np.all(np.isfinite(cube), axis=0)
    if not valid[n//2,n//2] or valid.mean() < .5:
        raise ValueError('Insufficient shared valid pixels for an RGB preview')
    cube[:,~valid] = np.nan
    digest.update(json.dumps(target.to_header_string()).encode())
    cid = digest.hexdigest()[:24]
    header = target.to_header(); header['BUNIT'] = 'MJy/sr'
    header['SNNAME'] = sn['name']; header['SNRA'] = sn['ra']; header['SNDEC'] = sn['dec']
    header['RGBORDER'] = 'RED,GREEN,BLUE'; header['RGBVER'] = VERSION
    header['HISTORY'] = 'Display cube: bilinear WCS reprojection; no coadd or PSF matching.'
    for i,o in enumerate(products,1):
        header[f'FILTER{i}'] = o['filter']; header[f'SOURCE{i}'] = o['uri']
        header[f'START{i}'] = o['start']; header[f'END{i}'] = o['end']
    fits.PrimaryHDU(cube.astype(np.float32), header).writeto(cache/(cid+'.fits'), overwrite=True, checksum=True)
    render_rgb(cube).save(cache/(cid+'.png'))
    result = {'id':cid, 'kind':'rgb', 'version':VERSION, 'status':'ready',
              'filter':'RGB colour', 'instrument':key[1], 'proposal':key[2],
              'start':min(o['start'] for o in products), 'end':max(o['end'] for o in products),
              'center':[.5,.5], 'widthArcsec':width, 'pixelScaleArcsec':scale,
              'coverage':float(valid.mean()), 'png':f'/api/stamps/{cid}.png',
              'fits':f'/api/stamps/{cid}.fits', 'channels':[
                  {'colour':colour,'filter':o['filter'],'id':o['id'],'uri':o['uri'],
                   'start':o['start'],'end':o['end']} for colour,o in zip(['Red','Green','Blue'],products)],
              'inputVersions':[[o['id'],o.get('validatedUnix',0)] for o in products]}
    (cache/(cid+'.json')).write_text(json.dumps(result))
    return result


def add_composites(snapshot, previous, root, ensure_fits=None):
    cache = Path(root)/'stamps'; cache.mkdir(parents=True, exist_ok=True)
    old = {s['name']:s for s in (previous or {}).get('objects',[])}
    ready = reused = errors = 0
    for sn in snapshot['objects']:
        sn['colorComposites'] = []; sn['colorIssues'] = []
        older = old.get(sn['name'],{}).get('colorComposites',[])
        for key, products in groups(sn['observations']):
            versions = [[o['id'],o.get('validatedUnix',0)] for o in products]
            cached = next((c for c in older if c.get('version')==VERSION and c.get('inputVersions')==versions), None)
            if cached:
                sn['colorComposites'].append(cached); reused += 1; continue
            try:
                for o in products:
                    if ensure_fits: ensure_fits(o)
                try:
                    composite = make_composite(sn,key,products,cache)
                except ValueError as exc:
                    # Retain a useful smaller field when wider detector edges
                    # leave too little overlap. Never pad or invent pixels.
                    if str(exc) != 'Insufficient shared valid pixels for an RGB preview' or min(o.get('widthArcsec',10) for o in products) <= 10: raise
                    composite = make_composite(sn,key,products,cache,width_arcsec=10)
                    composite['fieldNote'] = '10″ colour field: limited shared coverage at 15″.'
                    (cache/(composite['id']+'.json')).write_text(json.dumps(composite))
                sn['colorComposites'].append(composite); ready += 1
            except Exception as exc:
                sn['colorIssues'].append(f'{key[0]} / {key[1]} / {key[2]}: {str(exc)[:160]}')
                errors += 1
    print('RGB previews:',ready,'new;',reused,'reused;',errors,'unavailable',flush=True)
