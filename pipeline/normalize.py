import json, math, re, html, collections
from datetime import datetime, timezone
from pathlib import Path
import os
ROOT=Path(os.environ.get('ECHO_WORK_DIR', str(Path(__file__).resolve().parent.parent/'work')))
catalog=json.loads((ROOT/'catalog.json').read_text())
SOURCE='https://raw.githubusercontent.com/astrocatalogs/supernovae/master/output/catalog.json'
def vals(row,key):
 return list(dict.fromkeys(html.unescape(re.sub('<[^>]+>','',str(v.get('value','')))).strip() for v in row.get(key,[]) if v.get('value') is not None))
def coord(value,ra=False):
 value=str(value).strip()
 if ':' in value or len(value.split())==3:
  parts=re.split('[: ]+',value.lstrip('+-'))
  if len(parts)!=3: raise ValueError(value)
  a,b,c=map(float,parts)
  if b>=60 or c>=60: raise ValueError(value)
  result=(a+b/60+c/3600)*(-1 if value.startswith('-') else 1)
  if ra: result*=15
 else: result=float(value)
 if not math.isfinite(result) or not ((0<=result<360) if ra else (-90<=result<=90)): raise ValueError(value)
 return result
out=[]
errors=collections.Counter()
for row in catalog:
 zs=[]
 for item in row.get('redshift',[]):
  try:
   z=float(item['value'])
   if math.isfinite(z): zs.append({'value':z,**({'kind':item['kind']} if 'kind' in item else {})})
  except (ValueError,KeyError,TypeError): pass
 eligible=[z for z in zs if z['value']<0.02 and 'photo' not in str(z.get('kind','')).lower()]
 if not eligible: continue
 try:
  ra=next(coord(v,True) for v in vals(row,'ra'))
  dec=next(coord(v) for v in vals(row,'dec'))
 except (ValueError,StopIteration):
  errors['invalid_or_missing_coordinates']+=1;continue
 selected=eligible[0]
 names=vals(row,'alias')
 out.append({'name':row['name'],'ra':ra,'dec':dec,'redshift':selected['value'],'redshifts':zs,'redshift_kind':selected.get('kind'),'redshift_boundary_conflict':any(z['value']>=0.02 for z in zs),'aliases':names,'types':vals(row,'claimedtype'),'hosts':vals(row,'host'),'discovery_dates':vals(row,'discoverdate'),'coordinate_candidates':{'ra':vals(row,'ra'),'dec':vals(row,'dec')},'references':row.get('references','').split(',') if row.get('references') else [],'provenance':{'catalogue':'Open Supernova Catalog','source_url':SOURCE,'record_name':row['name'],'note':'Catalogue snapshot. First listed valid coordinate pair and first listed eligible redshift used; complete candidates retained. Summary catalogue does not establish spectroscopic measurement for every redshift.'}})
(ROOT/'nearby.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
summary={'source_url':SOURCE,'retrieved_at':datetime.now(timezone.utc).isoformat(),'input_count':len(catalog),'nearby_count':len(out),'negative_redshift_count':sum(x['redshift']<0 for x in out),'boundary_conflicts':sum(x['redshift_boundary_conflict'] for x in out),'excluded':dict(errors),'redshift_kinds':dict(collections.Counter(str(v.get('kind')) for a in catalog for v in a.get('redshift',[]))),'types':dict(collections.Counter(t for x in out for t in x['types']))}
(ROOT/'nearby-summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k not in ['types','redshift_kinds']},indent=2))
