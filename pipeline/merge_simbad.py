import json, math, re, collections, sys
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from geometry import unit,contains,ALL_IMAGING
import os
ROOT=Path(os.environ.get('ECHO_WORK_DIR', str(Path(__file__).resolve().parent.parent/'work')))
QUERY=(ROOT/'simbad-query.adql').read_text().strip()
SOURCE='https://simbad.cfa.harvard.edu/simbad/sim-tap/sync'
def canon(name):
 s=re.sub(r'\s+','',str(name)).lower()
 # Only recognized transient identifiers are used for identity matching.
 if re.match(r'^(?:sn\d{3,4}|at\d{4}|asassn-|ptf\d|iptf\d|ztf\d|gaia\d|psnj|ps1-|masterotj|spirits\d)',s):return s
 return None
def main():
 old=json.loads((ROOT/'nearby-supernovae.json').read_text())
 payload=json.loads((ROOT/'simbad-nearby.json').read_text())
 keys=[x['name'] for x in payload['metadata']]
 remote=[dict(zip(keys,x)) for x in payload['data']]
 current=list(old);names=collections.defaultdict(set)
 for i,sn in enumerate(current):
  for n in [sn['name']]+sn['aliases']:
   n=canon(n)
   if n:names[n].add(i)
 xyz=unit([sn['ra'] for sn in current],[sn['dec'] for sn in current])
 added=[];dedup=[];conflicts=[];invalid=[]
 for row in remote:
  try:
   ra=float(row['ra']);dec=float(row['dec']);z=float(row['rvz_redshift'])
   if not all(map(math.isfinite,[ra,dec,z])) or not 0<=ra<360 or not -90<=dec<=90 or not -1<z<0.02:raise ValueError('Invalid coordinate or redshift')
  except (ValueError,TypeError):invalid.append(row);continue
  aliases=list(dict.fromkeys([row['main_id']]+str(row.get('ids') or '').split('|')))
  matches=set()
  for a in aliases:
   key=canon(a)
   if key:matches.update(names.get(key,set()))
  vec=unit([ra],[dec])[0]
  dots=np.clip(xyz@vec,-1,1)
  nearest=int(dots.argmax());dist=math.degrees(math.acos(dots[nearest]))*3600
  if matches:
   seps={current[i]['name']:math.degrees(math.acos(dots[i]))*3600 for i in matches}
   item={'simbad_name':row['main_id'],'matched_names':[current[i]['name'] for i in matches],'separations_arcsec':seps}
   if min(seps.values())>1:conflicts.append({**item,'reason':'same identifier but coordinate discrepancy over 1 arcsec; existing record retained'})
   else:dedup.append(item)
   continue
  if dist<1:
   conflicts.append({'simbad_name':row['main_id'],'nearest':current[nearest]['name'],'separation_arcsec':dist,'reason':'new identifier within 1 arcsec of existing event; not added automatically'})
   continue
  preferred=next((re.sub(r'\s+','',a) for a in aliases if re.match(r'^SN\s*\d{3,4}[A-Za-z]*$',a)),row['main_id'].strip())
  rawrefs=list(dict.fromkeys(str(x).strip() for x in [row.get('rvz_bibcode'),row.get('coo_bibcode')] if x))
  refs=[x for x in rawrefs if re.match(r'^\d{4}',x)]
  sn={'name':preferred,'ra':ra,'dec':dec,'redshift':z,'redshifts':[{'value':z,'kind':'SIMBAD '+str(row.get('rvz_type') or 'unspecified')}],'redshift_kind':row.get('rvz_type'),'redshift_boundary_conflict':False,'aliases':aliases,'types':['SN'],'hosts':[],'discovery_dates':[],'coordinate_candidates':{'ra':[str(ra)],'dec':[str(dec)]},'references':refs,'reference_labels':rawrefs,'reference_urls':(['https://www.wis-tns.org/object/'+preferred.removeprefix('SN')] if 'url:TNS' in rawrefs and preferred.startswith('SN') else []),'catalogue_status':'classified','simbad_object_type':row['otype'],'classification_note':'SIMBAD classifies the object as a supernova (SN*); no spectroscopic subtype inferred.','provenance':{'catalogue':'SIMBAD','source_url':SOURCE,'record_name':row['main_id'],'query':QUERY,'retrieved_at':datetime.now(timezone.utc).isoformat(),'source_modified_at':None,'coordinate_bibcode':row.get('coo_bibcode'),'redshift_bibcode':row.get('rvz_bibcode'),'redshift_quality':row.get('rvz_qual'),'note':'Public SIMBAD TAP snapshot. Source modification timestamp unavailable; subtype, host and discovery date not inferred.'}}
  i=len(current);current.append(sn);added.append(sn)
  xyz=np.vstack([xyz,vec])
  for a in aliases:
   key=canon(a)
   if key:names[key].add(i)
 observations=json.loads((ROOT/'all-jwst-mast.json').read_text())['data']
 matches=json.loads((ROOT/'matches.json').read_text());addedmatches=collections.defaultdict(list)
 if added:
  newxyz=unit([s['ra'] for s in added],[s['dec'] for s in added])
  for row in observations:
   if row['instrument_name'] not in ALL_IMAGING:continue
   for idx in contains(row['s_region'],newxyz):addedmatches[added[idx]['name']].append(row)
 matches.update(addedmatches)
 (ROOT/'nearby-current.json').write_text(json.dumps(current,indent=2))
 (ROOT/'matches-current.json').write_text(json.dumps(matches,indent=2))
 (ROOT/'simbad-new.json').write_text(json.dumps(added,indent=2))
 (ROOT/'simbad-merge-conflicts.json').write_text(json.dumps(conflicts,indent=2))
 (ROOT/'simbad-deduplicated.json').write_text(json.dumps(dedup,indent=2))
 summary={'simbad_rows':len(remote),'old_catalogue_rows':len(old),'added':len(added),'deduplicated':len(dedup),'coordinate_conflicts':len(conflicts),'invalid':len(invalid),'current_catalogue_rows':len(current),'current_matched_sne':len(matches),'current_matched_rows':sum(map(len,matches.values())),'new_matches':{k:len(v) for k,v in addedmatches.items()},'newer_2020_named_sne':sum(bool(re.match(r'^SN202[1-9]',s['name'])) for s in added)}
 (ROOT/'current-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
