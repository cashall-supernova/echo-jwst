#!/usr/bin/env python3
"""Public SN/JWST index and WCS cutouts. No private repository dependency.

Run with --refresh to query the catalogues and the complete MAST public image
index. Without --refresh, resume a cached run. --publish reads service access
JSON from stdin (never from a command argument or a file).
"""
import argparse,base64,collections,concurrent.futures,hashlib,io,json,math,os,re,shutil,sys,time,warnings
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
import numpy as np
import requests
from astropy.io import fits
from astropy.wcs import WCS
from astropy.nddata import Cutout2D
from astropy.coordinates import SkyCoord
import astropy.units as u
from PIL import Image
from site_access import site_headers
from geometry import contains,unit,classify,ALL_IMAGING
from settings import CUTOUT_ARCSEC

PROJECT=Path(__file__).resolve().parent.parent
ROOT=Path(os.environ.get('ECHO_WORK_DIR',str(PROJECT/'work')))
MAST='https://mast.stsci.edu/api/v0/invoke'
DOWNLOAD='https://mast.stsci.edu/api/v0.1/Download/file/?uri='
OSC='https://raw.githubusercontent.com/astrocatalogs/supernovae/master/output/catalog.json'
NOTE='Daily official TNS bulk catalogue of classified SNe with reported z < 0.02, merged by designation and aliases with the historical Open Supernova Catalog and SIMBAD. Unknown redshifts and unreported events prevent a complete nearby census. Public JWST NIRCam/MIRI/NIRISS level-3 imaging is supplemented by calibrated level-2 images where date/filter coverage is missing. Coverage is not a confirmed SN detection.'

def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def atomic(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,separators=(',',':'),allow_nan=False));tmp.replace(path)
def http(method,url,**kwargs):
 for attempt in range(4):
  try:
   r=requests.request(method,url,timeout=kwargs.pop('timeout',120),**kwargs)
   if r.status_code in (429,500,502,503,504):
    if attempt<3:time.sleep(min(15,2**attempt));continue
   r.raise_for_status();return r
  except requests.RequestException:
   if attempt==3:raise
   time.sleep(2**attempt)

def refresh(credentials=None,tns_catalog=None):
 ROOT.mkdir(parents=True,exist_ok=True)
 if tns_catalog is None:
  if not credentials:raise RuntimeError('Refresh requires private Site service access or --tns-catalog; no stale fallback')
  response=http('GET',credentials['site'].rstrip('/')+'/api/sources/tns',headers=site_headers(credentials['token'],credentials.get('updater_token')))
  tns_catalog=ROOT/'tns-public.zip';tns_catalog.write_bytes(response.content)
 from merge_tns import read_snapshot
 read_snapshot(tns_catalog) # Validate freshness before doing any archive work.
 atomic(ROOT/'catalog.json',http('GET',OSC).json())
 os.environ['ECHO_WORK_DIR']=str(ROOT)
 import normalize
 rows=json.loads((ROOT/'nearby.json').read_text())
 for sn in rows:sn['catalogue_status']=classify(sn)
 rows=[s for s in rows if s['catalogue_status']!='excluded']
 atomic(ROOT/'nearby-supernovae.json',rows)
 from mast_index import fetch as fetch_mast_index
 archive=fetch_mast_index(http,3);observations=archive['data']
 atomic(ROOT/'all-jwst-mast.json',archive)
 positions=unit([s['ra'] for s in rows],[s['dec'] for s in rows]);matches=collections.defaultdict(list)
 for o in observations:
  if o['instrument_name'] not in ALL_IMAGING:continue
  for i in contains(o['s_region'],positions):matches[rows[i]['name']].append(o)
 atomic(ROOT/'matches.json',dict(matches))
 query=(PROJECT/'pipeline/simbad-query.adql').read_text();(ROOT/'simbad-query.adql').write_text(query)
 payload=http('POST','https://simbad.cfa.harvard.edu/simbad/sim-tap/sync',data={'request':'doQuery','lang':'adql','format':'json','query':query}).json()
 atomic(ROOT/'simbad-nearby.json',payload)
 import merge_simbad
 merge_simbad.main()
 import merge_tns
 merge_tns.main(tns_catalog)
 # Audit standalone calibrated level-2 images for missing date/filter coverage.
 atomic(ROOT/'all-cal2-mast.json',fetch_mast_index(http,2))
 import supplement_cal2
 supplement_cal2.main()
 for level in [2,3]:
  atomic(ROOT/f'exclusive-level{level}-mast.json',fetch_mast_index(http,level,'EXCLUSIVE_ACCESS'))

def build(previous=None):
 rows=json.loads((ROOT/'nearby-current.json').read_text());matches=json.loads((ROOT/('matches-complete.json' if (ROOT/'matches-complete.json').exists() else 'matches-current.json')).read_text())
 old={o['id']:o for s in (previous or {}).get('objects',[]) for o in s['observations']}
 audit=json.loads((ROOT/'tns-audit.json').read_text())
 if audit['eligibleSn']!=audit['representedSn']:raise RuntimeError('Incomplete TNS representation')
 result={'version':1,'updatedAt':now(),'catalogueSource':'TNS + Open Supernova Catalog + SIMBAD; MAST JWST','catalogueNote':NOTE,'catalogueAudit':audit,'scanComplete':True,'scanned':len(rows),'total':len(rows),'schedule':(previous or {}).get('schedule',{'enabled':False,'time':''}),'errors':[],'objects':[]}
 for s in rows:
  types=s['types'];typ=types[0] if types else 'Candidate'
  # Keep the recorded subtype; an uncertain alternative does not unclassify a named SN.
  if not types:typ='Candidate'
  sn={'name':s['name'],'aliases':s['aliases'],'ra':s['ra'],'dec':s['dec'],'z':s['redshift'],'zKind':str(s.get('redshift_kind') or s.get('provenance',{}).get('catalogue','Catalogue value')),'type':typ,'host':'; '.join(s['hosts'][:2]),'discovery':s['discovery_dates'][0].replace('/','-') if s['discovery_dates'] else '', 'references':s['references'],'conflict':bool(s.get('redshift_boundary_conflict')),'checked':True,'observations':[],'source':s.get('provenance',{}).get('catalogue')}
  sn['referenceUrls']=s.get('reference_urls',[])
  seen=set()
  for o in matches.get(s['name'],[]):
   if o.get('dataRights','PUBLIC')!='PUBLIC':raise RuntimeError('Nonpublic data entered the public stamp pipeline')
   uri=o.get('dataURL')
   if not uri or not uri.startswith('mast:JWST/') or not re.search(r'_(i2d|cal)\.fits$',uri) or uri in seen:continue
   seen.add(uri)
   identity=f"{uri}|{sn['ra']:.8f}|{sn['dec']:.8f}|{CUTOUT_ARCSEC:g}|{o.get('t_obs_release')}|{o.get('t_exptime')}"
   sid=hashlib.sha256(identity.encode()).hexdigest()[:24]
   item={'id':sid,'uri':uri,'filter':o['filters'],'instrument':o['instrument_name'],'start':float(o['t_min']),'end':float(o['t_max']),'proposal':str(o['proposal_id']),'obsId':o['obs_id'],'status':'pending','widthArcsec':CUTOUT_ARCSEC}
   if sid in old and old[sid]['status'] in ('ready','outside'):
    # Recheck cutouts at least weekly to catch recalibration under the same URI.
    age=time.time()-float(old[sid].get('validatedUnix',0))
    if age<7*86400:item.update(old[sid])
   sn['observations'].append(item)
  result['objects'].append(sn)
 return result

def read_window(hdu,slices):
 """Read adjacent FITS rows together, with bounded temporary allocation."""
 sy,sx=slices
 # Full rows are contiguous on disk, avoiding hundreds of tiny HTTP requests.
 # Very wide mosaics keep the rectangular reader to bound transfer/memory.
 stripe_bytes=(sy.stop-sy.start)*hdu.shape[1]*abs(hdu.header['BITPIX'])//8
 if stripe_bytes<=32*1024*1024:return np.asarray(hdu.section[sy,:])[:,sx]
 return np.asarray(hdu.section[slices])

def science_cutout(sci,wcs,pos,width_arcsec=CUTOUT_ARCSEC):
 # A read-only shape proxy computes Astropy's native pixel slices and WCS
 # without allocating or fetching the full mosaic.
 proxy=np.broadcast_to(np.float32(0),sci.shape)
 cut=Cutout2D(proxy,pos,(width_arcsec*u.arcsec,width_arcsec*u.arcsec),wcs=wcs,mode='partial',fill_value=np.nan)
 arr=np.full(cut.data.shape,np.nan,dtype=np.float32)
 arr[cut.slices_cutout]=read_window(sci,cut.slices_original)
 return cut,arr

def stamp(sn,o):
 if o.get('dataRights','PUBLIC')!='PUBLIC':raise ValueError('Protected data are metadata-only; no pixel download attempted')
 cache=ROOT/'stamps';cache.mkdir(parents=True,exist_ok=True);meta=cache/(o['id']+'.json')
 if meta.exists():
  cached=json.loads(meta.read_text())
  if cached.get('status') in ('ready','outside') and time.time()-cached.get('validatedUnix',0)<7*86400:
   if cached.get('status')=='ready':cached.pop('error',None)
   return cached
 url=DOWNLOAD+quote(o['uri'],safe='')
 try:
  with warnings.catch_warnings():
   warnings.simplefilter('ignore')
   with fits.open(url,use_fsspec=True,fsspec_kwargs={'block_size':65536,'client_kwargs':{'trust_env':True}},lazy_load_hdus=True) as hdul:
    sci=hdul['SCI'];wcs=WCS(sci.header,hdul).celestial;pos=SkyCoord(sn['ra'],sn['dec'],unit='deg')
    cut,arr=science_cutout(sci,wcs,pos);valid=np.isfinite(arr)
    weight=None
    if 'WHT' in hdul:
     weight=read_window(hdul['WHT'],cut.slices_original);full=np.zeros(arr.shape);full[cut.slices_cutout]=weight;valid &= full>0
    if 'DQ' in hdul:
     dq=read_window(hdul['DQ'],cut.slices_original);full=np.ones(arr.shape,dtype=np.uint32);full[cut.slices_cutout]=dq;valid &= (full&1)==0
    cx,cy=cut.wcs.world_to_pixel(pos);ix,iy=int(round(float(cx))),int(round(float(cy)))
    if not (0<=iy<arr.shape[0] and 0<=ix<arr.shape[1] and valid[iy,ix]):
     result={**o,'status':'outside','error':'No finite, usable science pixel at catalogue coordinate','validatedUnix':time.time()};atomic(meta,result);return result
    header=cut.wcs.to_header(relax=True)
    for key in ['BUNIT','FILTER','PUPIL','INSTRUME','TELESCOP','PIXAR_SR','PIXAR_A2','PHOTMJSR','DATE-OBS']:
     if key in sci.header:header[key]=sci.header[key]
     elif key in hdul[0].header:header[key]=hdul[0].header[key]
    header['SNNAME']=sn['name'];header['SNRA']=sn['ra'];header['SNDEC']=sn['dec'];header['SRCURI']=o['uri'];header['HISTORY']=f'ECHO {CUTOUT_ARCSEC:g} arcsec WCS cutout; no flux measurement or background subtraction.'
    arr[~valid]=np.nan
    fits.PrimaryHDU(arr,header).writeto(cache/(o['id']+'.fits'),overwrite=True,checksum=True)
    values=arr[valid];lo,hi=np.percentile(values,[1,99.5]);span=max(float(hi-lo),float(np.std(values)),1e-12)
    scaled=np.arcsinh(np.clip((np.nan_to_num(arr,nan=lo)-lo)/span,0,1)*10)/np.arcsinh(10)
    pixels=np.uint8(np.clip(scaled*255,0,255));pixels[~valid]=0
    # FITS pixel coordinates start at lower left; display PNG origin is top left.
    Image.fromarray(np.flipud(pixels)).resize((400,400),Image.Resampling.BICUBIC).save(cache/(o['id']+'.png'))
    result={**o,'status':'ready','center':[(float(cx)+.5)/arr.shape[1],1-(float(cy)+.5)/arr.shape[0]],'coverage':float(valid.mean()),'validatedUnix':time.time(),'png':f"/api/stamps/{o['id']}.png",'fits':f"/api/stamps/{o['id']}.fits"};result.pop('error',None)
    atomic(meta,result);return result
 except Exception as exc:
  # Public URLs only; no tokens are ever in these exceptions.
  return {**o,'status':'error','error':str(exc)[:240]}

def ingest(site,token,payload):
 return http('POST',site.rstrip('/')+'/api/ingest',headers=site_headers(token),json=payload).json()
def upload_asset(site,token,file):
 return ingest(site,token,{'action':'asset','file':file.name,'base64':base64.b64encode(file.read_bytes()).decode()})
def main():
 p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');p.add_argument('--tns-catalog',type=Path);p.add_argument('--publish',action='store_true');p.add_argument('--limit',type=int,default=0);p.add_argument('--workers',type=int,default=6);p.add_argument('--local-preview',action='store_true');args=p.parse_args()
 ROOT.mkdir(parents=True,exist_ok=True);credentials=None;previous=None
 if args.publish:
  credentials=json.loads(sys.stdin.readline());site=credentials['site'];token=credentials['token']
  if credentials.get('updater_token'):os.environ['ECHO_UPDATER_TOKEN']=credentials['updater_token']
  previous=http('GET',site.rstrip('/')+'/api/catalog',headers=site_headers(token)).json()
 elif (ROOT/'snapshot.json').exists():previous=json.loads((ROOT/'snapshot.json').read_text())
 if args.refresh:refresh(credentials,args.tns_catalog)
 snapshot=build(previous);target=PROJECT/'data/bootstrap.json'
 from image_availability import enrich
 enrich(snapshot,previous,ROOT)
 from release_watch import apply_release_watch
 apply_release_watch(snapshot,previous,ROOT)
 tasks=[(s,o) for s in snapshot['objects'] for o in s['observations'] if o['status'] not in ('ready','outside')]
 # Distribute initial stamps across the sample before filling all bands.
 tasks.sort(key=lambda pair:(0 if pair[0]['name'] in ('SN2023ixf','SN2004et','SN2017eaw','SN1987A') else 1,pair[1]['start']))
 if args.limit:tasks=tasks[:args.limit]
 new_assets=[]
 def persist():
  snapshot['updatedAt']=now();atomic(ROOT/'snapshot.json',snapshot)
  if args.local_preview:
   local=json.loads(json.dumps(snapshot))
   for s in local['objects']:
    for o in s['observations']:
     if o['status']=='ready' and (ROOT/'stamps'/(o['id']+'.png')).exists():
      for ext in ['png','fits']:shutil.copy2(ROOT/'stamps'/(o['id']+'.'+ext),PROJECT/'public/stamps'/(o['id']+'.'+ext));o[ext]='/stamps/'+o['id']+'.'+ext
   atomic(target,local)

 persist()
 print('Catalogue:',len(snapshot['objects']),'objects;',sum(bool(s['observations']) for s in snapshot['objects']),'matched;',len(tasks),'cutouts to process',flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
  futures={pool.submit(stamp,s,o):(s,o) for s,o in tasks}
  for n,future in enumerate(concurrent.futures.as_completed(futures),1):
   s,o=futures[future];result=future.result();o.update(result)
   if o['status']=='ready':new_assets.extend([ROOT/'stamps'/(o['id']+'.png'),ROOT/'stamps'/(o['id']+'.fits')])
   if n%20==0 or n==len(tasks):persist();print('Cutouts',n,'/',len(tasks),'ready',sum(o['status']=='ready' for s in snapshot['objects'] for o in s['observations']),flush=True)
 from color_images import add_composites
 def ensure_fits(o):
  file=ROOT/'stamps'/(o['id']+'.fits');meta=file.with_suffix('.json')
  if file.exists() and meta.exists() and json.loads(meta.read_text()).get('validatedUnix')==o.get('validatedUnix'):return
  if not credentials:
   if file.exists():return
   raise RuntimeError('Input FITS is not cached; publish access is needed to retrieve it')
  # Only retrieve this known product from our own private storage. Never follow
  # a manifest URL to another host with a Site service credential.
  response=http('GET',site.rstrip('/')+'/api/stamps/'+o['id']+'.fits',headers=site_headers(token))
  file.write_bytes(response.content);atomic(meta,o)
 add_composites(snapshot,previous,ROOT,ensure_fits)
 persist()
 if args.publish:
  # Upload all locally materialized stamps; this also resumes interrupted uploads.
  assets=[]
  for s in snapshot['objects']:
   for o in s['observations']+s.get('colorComposites',[]):
    if o['status']=='ready':
     for ext in ['png','fits']:
      file=ROOT/'stamps'/(o['id']+'.'+ext)
      if file.exists():assets.append(file)
  with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(lambda f:upload_asset(site,token,f),assets))
  snapshot['updatedAt']=now();ingest(site,token,snapshot)
  readback=http('GET',site.rstrip('/')+'/api/catalog',headers=site_headers(token)).json()
  if readback.get('updatedAt')!=snapshot['updatedAt']:raise RuntimeError('Publication readback mismatch')
  print('Published and verified',len(readback['objects']),'objects',flush=True)
 # Keep the exact verified publication timestamp in the resumable local copy.
 if args.publish:atomic(ROOT/'snapshot.json',snapshot)
 else:persist()
 print('Done:',collections.Counter(o['status'] for s in snapshot['objects'] for o in s['observations']),flush=True)
 if args.refresh and args.publish:
  from spectra import run as update_spectra
  update_spectra(ROOT/'spectra',args.tns_catalog or ROOT/'tns-public.zip',ROOT/'catalog.json',credentials,refresh=True,workers=args.workers)
if __name__=='__main__':main()
