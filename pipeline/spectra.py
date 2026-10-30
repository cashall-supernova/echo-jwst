"""All-redshift SN spectroscopy index. Archive extraction, never a new extraction.

Only PUBLIC products are downloaded. A field footprint is never sufficient to
label a spectrum as the SN: extracted-source coordinates must agree within 1″.
Named single-target spectra without source coordinates are labelled separately.
"""
import argparse, collections, concurrent.futures, hashlib, html, io, json, math, os, re, sys, time
from pathlib import Path
from urllib.parse import quote
import numpy as np
from astropy.io import fits
from astropy import units as u
from astropy.coordinates import Angle
from scipy.spatial import cKDTree
from site_access import site_headers
from geometry import unit, contains, parse_region, classify
from merge_tns import read_snapshot, identity, number
from update import http, atomic, now, ingest, PROJECT, DOWNLOAD, MAST

PARSER_VERSION = 'spectra-v1'
MATCH_ARCSEC = 1.0
COLUMNS = 'obsid,obs_id,s_ra,s_dec,s_region,t_min,t_max,t_exptime,instrument_name,filters,proposal_id,dataURL,t_obs_release,dataRights,calib_level,dataproduct_type,target_name,obs_title,em_min,em_max'

def values(row, key):
    return list(dict.fromkeys(html.unescape(re.sub('<[^>]+>', '', str(v.get('value', '')))).strip() for v in row.get(key, []) if v.get('value') is not None))

def coordinate(value, ra=False):
    if ':' in value or len(value.split()) == 3:
        return float(Angle(value, unit=u.hourangle if ra else u.deg).degree)
    return float(value)

def catalogue(tns_path, historical_path):
    timestamp, tns = read_snapshot(tns_path)
    objects = {}; by_alias = collections.defaultdict(set)
    valid_tns = 0; missing_coordinates = 0
    for t in tns:
        if t['name_prefix'] != 'SN': continue
        ra, dec = number(t['ra']), number(t['declination'])
        if ra is None or dec is None or not 0 <= ra < 360 or not -90 <= dec <= 90:
            missing_coordinates += 1; continue
        name = 'SN' + t['name']; key = identity(name)
        aliases = [name, 'AT' + t['name']] + [v.strip() for v in t.get('internal_names', '').split(',') if v.strip()]
        objects[key] = dict(name=name, aliases=aliases, ra=ra, dec=dec, z=number(t['redshift']), type=t['type'].removeprefix('SN ').strip() or 'SN', host='', source='TNS', tnsUrl='https://www.wis-tns.org/object/' + t['name'], discovery=t.get('discoverydate',''))
        for alias in aliases: by_alias[identity(alias)].add(key)
        valid_tns += 1
    historical_added = 0
    for row in json.loads(Path(historical_path).read_text()):
        names = [row['name'], *values(row, 'alias')]
        types = values(row, 'claimedtype')
        if classify({'name':row['name'], 'aliases':names, 'types':types}) == 'excluded': continue
        if not any(re.match(r'^SN\s?\d{3,4}[A-Za-z]+$', n) for n in names) and not any(re.match(r'^(?:Ia|Ib|Ic|II|I$|SLSN|SN$)',t) for t in types): continue
        keys = set().union(*(by_alias.get(identity(n), set()) for n in names))
        if len(keys) == 1:
            old = objects[next(iter(keys))]
            old['aliases'] = list(dict.fromkeys(old['aliases'] + names))
            old['host'] = '; '.join(values(row,'host'))
            continue
        try:
            ra = coordinate(values(row,'ra')[0],True); dec = coordinate(values(row,'dec')[0])
            if not 0 <= ra < 360 or not -90 <= dec <= 90: continue
        except (ValueError, IndexError): continue
        key = identity(row['name'])
        if key in objects: continue
        z = next((v for x in values(row,'redshift') if (v:=number(x)) is not None), None)
        objects[key] = dict(name=row['name'], aliases=names, ra=ra, dec=dec, z=z, type=types[0] if types else 'Candidate', host='; '.join(values(row,'host')), source='Open Supernova Catalog', tnsUrl=None, discovery=next(iter(values(row,'discoverdate')),''))
        historical_added += 1
    rows = list(objects.values())
    audit = dict(tnsSnapshotAt=timestamp, classifiedTns=valid_tns, missingTnsCoordinates=missing_coordinates, historicalAdded=historical_added, indexedObjects=len(rows), unknownRedshift=sum(s['z'] is None for s in rows), redshiftLimit=None)
    return rows, audit

def validate_observations(result, rights):
    rows = result.get('data', []); paging = result.get('paging', {})
    if result.get('status') != 'COMPLETE' or paging.get('rowsFiltered') != len(rows) or int(paging.get('pagesFiltered',1)) != 1:
        raise RuntimeError('Incomplete MAST spectra query; retain previous publication')
    if rights=='PUBLIC' and not rows: raise RuntimeError('Empty public spectral index; retain previous publication')
    if any(r.get('dataRights') != rights for r in rows): raise RuntimeError('MAST rights mismatch')
    # CAOM spectroscopy can repeat an observation for different data-product
    # types. Deduplication is checked after the full advertised row count.
    unique = {}
    for row in rows:
        key = (str(row['obsid']), row.get('dataproduct_type'), row.get('dataURL'))
        if key in unique and unique[key] != row: raise RuntimeError('Conflicting duplicate spectral observation')
        unique[key] = row
    return list(unique.values())

def fetch_observations(rights):
    filters = [{'paramName':'obs_collection','values':['JWST']},{'paramName':'dataproduct_type','values':['spectrum','cube']},{'paramName':'calib_level','values':[{'min':2,'max':3}]},{'paramName':'dataRights','values':[rights]}]
    q = {'service':'Mast.Caom.Filtered','params':{'columns':COLUMNS,'filters':filters},'format':'json','pagesize':500000,'page':1,'timeout':60}
    deadline = time.monotonic() + 360
    while True:
        r = http('POST',MAST,data={'request':json.dumps(q)}).json()
        if r.get('status') != 'EXECUTING' or time.monotonic() > deadline: break
        time.sleep(1)
    validate_observations(r,rights); r['fetchedAt'] = now()
    return r

def normalized_name(name): return re.sub(r'[^a-z0-9]','',str(name).lower())

def region_candidates(region, tree, positions):
    candidates = set()
    parts = re.findall(r'(?:POLYGON|CIRCLE)\b.*?(?=\b(?:POLYGON|CIRCLE)\b|$)',region or '',flags=re.I)
    if not parts: raise ValueError('Missing footprint')
    for part in parts:
        shape, xy = parse_region(part)
        if shape == 'CIRCLE': center=unit([xy[0]],[xy[1]])[0]; radius=2*math.sin(math.radians(xy[2])/2)
        else:
            vertices=unit(xy[:,0],xy[:,1]); center=vertices.mean(axis=0); center/=np.linalg.norm(center)
            radius=float(np.max(np.linalg.norm(vertices-center,axis=1)))+1e-8
        candidates.update(tree.query_ball_point(center,radius+1e-8))
    ids = np.array(sorted(candidates), dtype=int)
    return ids[contains(region, positions[ids])] if len(ids) else ids

def crossmatch(objects, archives):
    positions=unit([s['ra'] for s in objects],[s['dec'] for s in objects]); tree=cKDTree(positions)
    named=collections.defaultdict(set)
    for i,s in enumerate(objects):
        for n in [s['name'],*s['aliases']]: named[normalized_name(n)].add(i)
    matches=collections.defaultdict(dict); missing=[]
    for row in archives:
        try: ids=set(region_candidates(row.get('s_region'),tree,positions))
        except ValueError: ids=set(); missing.append(str(row['obsid']))
        footprint_ids=set(ids)
        exact=named.get(normalized_name(row.get('target_name')),set())
        if len(exact)==1: ids.update(exact)
        for i in ids:
            key=str(row['obsid'])
            prior=matches[i].get(key)
            if prior is None or row['dataproduct_type']=='spectrum': matches[i][key]={**row,'nameMatched':i in exact and len(exact)==1,'footprintMatched':i in footprint_ids}
    return matches, missing

def fetch_products(obsid):
    q={'service':'Mast.Caom.Products','params':{'obsid':str(obsid)},'format':'json','pagesize':500000,'page':1}
    r=http('POST',MAST,data={'request':json.dumps(q)}).json()
    if r.get('status')!='COMPLETE': raise RuntimeError('Spectral product listing failed')
    rows=r.get('data',[]); p=r.get('paging',{})
    if p.get('rowsFiltered',len(rows))!=len(rows) or int(p.get('pagesFiltered',1))!=1: raise RuntimeError('Truncated product list')
    return [x for x in rows if x.get('dataRights')=='PUBLIC' and re.search(r'_(?:x1d|c1d)\.fits$',x.get('dataURI','')) and x.get('productType')=='SCIENCE']

def separation(ra,dec,sn):
    a=unit([ra],[dec])[0];b=unit([sn['ra']],[sn['dec']])[0]
    return float(math.degrees(2*math.asin(min(1,float(np.linalg.norm(a-b))/2)))*3600)

def scalar(value):
    try: return number(np.asarray(value).item())
    except (ValueError, TypeError): return None

def source_association(meta, primary, sn, named, mode):
    for rak,deck in [('SRCRA','SRCDEC'),('SOURCE_RA','SOURCE_DEC'),('SLIT_RA','SLIT_DEC'),('RA','DEC')]:
        ra,dec=scalar(meta.get(rak)),scalar(meta.get(deck))
        if ra is not None and dec is not None and not (ra==0 and dec==0):
            sep=separation(ra,dec,sn)
            return ('source-position',sep) if sep<=MATCH_ARCSEC else (None,sep)
    # Never use the pointing of a MOS/slitless field as an extracted source.
    if any(x in mode for x in ['MSA','WFSS','SOSS','TSO']): return None,None
    if named:
        ra,dec=scalar(primary.get('TARG_RA')),scalar(primary.get('TARG_DEC'))
        if ra is not None and dec is not None:
            sep=separation(ra,dec,sn)
            if sep<=MATCH_ARCSEC:return 'named-target',sep
    return None,None

def parse_spectrum(path, sn, observation):
    segments=[]; skipped=0
    with fits.open(path,memmap=False) as hdus:
        primary=hdus[0].header; mode=str(primary.get('EXP_TYPE',observation['instrument_name']))
        if primary.get('BKGDTARG') is True: return dict(segments=[],skippedExtractions=1,exposureType=mode,reason='Archive marks this as a background target')
        for hdu in hdus:
            if hdu.name not in ('EXTRACT1D','COMBINE1D') or hdu.data is None:continue
            cols=set(hdu.columns.names or [])
            if not {'WAVELENGTH','FLUX'}<=cols:continue
            waves=np.asarray(hdu.data['WAVELENGTH']); vector=waves.ndim>1 or waves.dtype.kind=='O'
            entries=list(hdu.data) if vector else [hdu.data]
            for index,entry in enumerate(entries):
                meta=dict(hdu.header)
                if vector:
                    for k in ['SOURCE_RA','SOURCE_DEC','SOURCE_ID','SPECTRAL_ORDER','SOURCE_TYPE']:
                        if k in cols:meta[k]=entry[k]
                assoc,sep=source_association(meta,primary,sn,observation['nameMatched'] and observation.get('footprintMatched',False),mode)
                if not assoc:skipped+=1;continue
                wave=np.asarray(entry['WAVELENGTH'],dtype=float).ravel(); flux=np.asarray(entry['FLUX'],dtype=float).ravel()
                wu=hdu.columns['WAVELENGTH'].unit; fu=hdu.columns['FLUX'].unit
                if not wu or not fu:raise ValueError('Missing spectral units')
                wave=(wave*u.Unit(wu)).to_value(u.um);flux=(flux*u.Unit(fu)).to_value(u.Jy)
                ek='FLUX_ERROR' if 'FLUX_ERROR' in cols else 'ERROR' if 'ERROR' in cols else None
                err=(np.asarray(entry[ek],dtype=float).ravel()*u.Unit(hdu.columns[ek].unit or fu)).to_value(u.Jy) if ek else np.full(len(wave),np.nan)
                dq=np.asarray(entry['DQ'],dtype=np.uint32).ravel() if 'DQ' in cols else np.zeros(len(wave),dtype=np.uint32)
                if not (len(wave)==len(flux)==len(err)==len(dq)):raise ValueError('Spectral array length mismatch')
                valid=np.isfinite(wave)&(wave>0);order=np.argsort(wave[valid],kind='stable')
                arrays=[a[valid][order] for a in [wave,flux,err,dq]]
                if np.count_nonzero(np.isfinite(arrays[1])&((arrays[3]&1)==0))<2:skipped+=1;continue
                data=[[float(w),float(f) if math.isfinite(f) else None,float(e) if math.isfinite(e) and e>=0 else None,int(d)] for w,f,e,d in zip(*arrays)]
                segments.append(dict(label=f"{hdu.name} {hdu.header.get('EXTVER',1)}"+(f" · source {index+1}" if vector else ''),sourceId=str(meta.get('SOURCEID',meta.get('SOURCE_ID',''))),order=str(meta.get('SPORDER',meta.get('SPECTRAL_ORDER',''))),association=assoc,separationArcsec=sep,sourceType=str(meta.get('SRCTYPE',meta.get('SOURCE_TYPE',primary.get('SRCTYPE','UNKNOWN')))),points=data))
        return dict(segments=segments,skippedExtractions=skipped,exposureType=mode,pipelineVersion=str(primary.get('CAL_VER','')),target=str(primary.get('TARGNAME',observation.get('target_name',''))),wavelengthUnit='um',fluxUnit='Jy',columns=['wavelength_um','flux_jy','error_jy','dq'])

def observation_record(o, checked, previous=None):
    old=previous or {}
    return dict(id=str(o['obsid']),obsId=o['obs_id'],instrument=o['instrument_name'],configuration=o.get('filters') or '',proposal=str(o['proposal_id']),start=number(o.get('t_min')),end=number(o.get('t_max')),release=number(o.get('t_obs_release')),level=int(o['calib_level']),status='public' if o['dataRights']=='PUBLIC' else 'exclusive',target=o.get('target_name') or '',nameMatched=bool(o.get('nameMatched')),firstSeen=old.get('firstSeen',checked),lastSeen=checked,lastChecked=checked)

def materialize(sn,o,p,root):
    uri=p['dataURI']; identifier=hashlib.sha256(f"{PARSER_VERSION}|{sn['name']}|{sn['ra']}|{sn['dec']}|{uri}".encode()).hexdigest()[:24]
    record=dict(id=identifier,uri=uri,filename=uri.rsplit('/',1)[-1],obsid=str(o['obsid']),instrument=o['instrument_name'],configuration=p.get('filters') or o.get('filters') or '',proposal=str(o['proposal_id']),start=number(o.get('t_min')),end=number(o.get('t_max')),level=int(p.get('calib_level',o['calib_level'])),status='error',reason='')
    if p.get('dataRights')!='PUBLIC' or o.get('dataRights')!='PUBLIC':raise ValueError('Protected spectral pixels must not be requested')
    if not re.fullmatch(r'mast:JWST/product/[a-zA-Z0-9_.-]+_(?:x1d|c1d)\.fits',uri):raise ValueError('Unexpected product URI')
    try:
        if int(p.get('size') or 0)>100_000_000:
            return {**record,'status':'unsupported','reason':'Extracted product exceeds the 100 MB processing limit; use the original FITS.'}
        raw=root/'fits'/(hashlib.sha256(uri.encode()).hexdigest()[:24]+'.fits')
        if not raw.exists() or time.time()-raw.stat().st_mtime>7*86400:
            response=http('GET',DOWNLOAD+quote(uri,safe=''))
            if len(response.content)>100_000_000:raise ValueError('Extracted product exceeds processing size limit')
            raw.write_bytes(response.content)
        payload=parse_spectrum(raw,sn,o)
        if not payload['segments']:
            return {**record,'status':'unmatched','reason':payload.get('reason','No usable extracted source within 1″ of the catalogue position; field coverage alone is insufficient.')}
        points=[p for seg in payload['segments'] for p in seg['points']]
        payload.update(id=identifier,snName=sn['name'],uri=uri)
        atomic(root/'assets'/(identifier+'.json'),payload)
        record.update(status='ready',samples=len(points),segments=len(payload['segments']),waveMin=min(p[0] for p in points),waveMax=max(p[0] for p in points),association='named-target' if any(s['association']=='named-target' for s in payload['segments']) else 'source-position',separationArcsec=max(s['separationArcsec'] or 0 for s in payload['segments']),exposureType=payload['exposureType'],pipelineVersion=payload['pipelineVersion'])
    except Exception as e:record['reason']=f'{type(e).__name__}: {str(e)[:220]}'
    return record

def run(root,tns_path,historical_path,credentials=None,refresh=True,workers=6,previous=None):
    if credentials and credentials.get('updater_token'):os.environ['ECHO_UPDATER_TOKEN']=credentials['updater_token']
    root=Path(root)
    for d in ['fits','assets']: (root/d).mkdir(parents=True,exist_ok=True)
    if credentials and previous is None:
        response=http('GET',credentials['site'].rstrip('/')+'/api/spectra',headers=site_headers(credentials['token'],credentials.get('updater_token')))
        previous=response.json()
    elif previous is None and (root/'snapshot.json').exists():previous=json.loads((root/'snapshot.json').read_text())
    objects,audit=catalogue(tns_path,historical_path); atomic(root/'objects.json',objects)
    archives={}
    for rights in ['PUBLIC','EXCLUSIVE_ACCESS']:
        path=root/(rights+'.json')
        if refresh:atomic(path,fetch_observations(rights))
        data=json.loads(path.read_text()); rows=validate_observations(data,rights)
        archives[rights]=(rows,data['fetchedAt']);audit[rights.lower()+'Rows']=len(rows)
        audit[rights.lower()+'FetchedAt']=data['fetchedAt']
        audit[rights.lower()+'IdenticalDuplicates']=len(data['data'])-len(rows)
    matches,missing=crossmatch(objects,archives['PUBLIC'][0]+archives['EXCLUSIVE_ACCESS'][0])
    audit['missingFootprints']=len(missing)
    obs={str(o['obsid']):o for group in matches.values() for o in group.values() if o['dataRights']=='PUBLIC'}
    product_map_path=root/'product-map.json'
    if refresh or not product_map_path.exists():
        ids=sorted(obs); batches=[','.join(ids[i:i+40]) for i in range(0,len(ids),40)]; product_map=collections.defaultdict(dict)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers,6)) as pool:
            for i,products in enumerate(pool.map(fetch_products,batches),1):
                for p in products:
                    # Related exposures and other slits are not automatically
                    # promoted to the matched observation's source or epoch.
                    key=str(p['obsID'])
                    if key in obs:product_map[key][p['dataURI']]=p
                print('Spectral product batches',i,'/',len(batches),flush=True)
        product_map={k:list(v.values()) for k,v in product_map.items()};atomic(product_map_path,product_map)
    else:product_map=json.loads(product_map_path.read_text())
    checked=now();old_sn={s['name']:s for s in (previous or {}).get('objects',[])};output=[];tasks=[]
    for i,group in matches.items():
        s={**objects[i],'observations':[],'spectra':[]};old=old_sn.get(s['name'],{});old_obs={o['id']:o for o in old.get('observations',[])}
        for o in group.values():
            s['observations'].append(observation_record(o,checked,old_obs.get(str(o['obsid']))))
            if o['dataRights']=='PUBLIC':
                for p in product_map.get(str(o['obsid']),[]):tasks.append((s,o,p))
        current={o['id'] for o in s['observations']}
        for key,o in old_obs.items():
            if key not in current:s['observations'].append({**o,'status':'unconfirmed','lastChecked':checked})
        output.append(s)
    present={s['name'] for s in output}
    for s in old_sn.values():
        if s['name'] not in present and s.get('observations'):
            output.append({**s,'spectra':[],'observations':[{**o,'status':'unconfirmed','lastChecked':checked} for o in s['observations']]})
    print('Spectral catalogue:',len(objects),'positions;',len(output),'matched fields;',len(tasks),'extracted products to check',flush=True)
    # One URI may cover more than one SN; materialize each unique file first so
    # concurrent source parsing never races a partially written FITS download.
    def download(item):
        uri,p=item;raw=root/'fits'/(hashlib.sha256(uri.encode()).hexdigest()[:24]+'.fits')
        if int(p.get('size') or 0)>100_000_000:return
        if not raw.exists() or time.time()-raw.stat().st_mtime>7*86400:
            try:
                response=http('GET',DOWNLOAD+quote(uri,safe=''))
                if len(response.content)<=100_000_000:raw.write_bytes(response.content)
            except Exception:pass # Per-product retry and explicit status below.
    unique={p['dataURI']:p for _,_,p in tasks}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for n,_ in enumerate(pool.map(download,unique.items()),1):
            if n%100==0 or n==len(unique):print('Spectral FITS fetched',n,'/',len(unique),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(materialize,s,o,p,root):s for s,o,p in tasks}
        for n,future in enumerate(concurrent.futures.as_completed(futures),1):
            futures[future]['spectra'].append(future.result())
            if n%100==0 or n==len(tasks):print('Spectral products parsed',n,'/',len(tasks),flush=True)
    for s in output:s['spectra'].sort(key=lambda x:(-(x['start'] or 0),-x['level'],x['filename']))
    output.sort(key=lambda s:-max((o['start'] or 0 for o in s['observations']),default=0))
    audit.update(matchedObjects=len(output),matchedPublicObservations=len(obs),readySpectra=sum(p['status']=='ready' for s in output for p in s['spectra']),objectsWithSpectra=sum(any(p['status']=='ready' for p in s['spectra']) for s in output),exclusiveObjects=sum(any(o['status']=='exclusive' for o in s['observations']) for s in output))
    snapshot=dict(version=1,updatedAt=checked,scope='all-redshifts',audit=audit,objects=output)
    atomic(root/'snapshot.json',snapshot)
    if credentials:
        site=credentials['site'];token=credentials['token']
        def upload(p):
            asset=json.loads((root/'assets'/(p['id']+'.json')).read_text());return ingest(site,token,{'action':'spectrum_asset','asset':asset})
        ready=[p for s in output for p in s['spectra'] if p['status']=='ready']
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:list(pool.map(upload,ready))
        ingest(site,token,{'action':'spectra_catalog','catalog':snapshot})
        back=http('GET',site.rstrip('/')+'/api/spectra',headers=site_headers(token)).json()
        if back.get('updatedAt')!=checked or back.get('audit')!=audit:raise RuntimeError('Spectra publication readback mismatch')
    print('Spectra index complete:',json.dumps(audit),flush=True)
    return snapshot

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work-dir',type=Path,default=PROJECT/'work'/'spectra');parser.add_argument('--tns-catalog',type=Path,required=True);parser.add_argument('--historical-catalog',type=Path,required=True);parser.add_argument('--cached',action='store_true');parser.add_argument('--publish',action='store_true');parser.add_argument('--workers',type=int,default=6);args=parser.parse_args()
    credentials=json.loads(sys.stdin.readline()) if args.publish else None
    run(args.work_dir,args.tns_catalog,args.historical_catalog,credentials,not args.cached,args.workers)

if __name__=='__main__':main()
