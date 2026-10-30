"""Add one longest calibrated exposure per missing SN/date/instrument/filter.
Existing level-3 products cover dates inclusively between t_min and t_max.
Matching remains metadata footprint coverage; downstream SCI pixels need checking.
"""
import json,math,collections,re,time
from pathlib import Path
from datetime import datetime,timedelta,timezone
from geometry import unit,contains,ALL_IMAGING
import os
ROOT=Path(os.environ.get('ECHO_WORK_DIR', str(Path(__file__).resolve().parent.parent/'work')))
MJD_EPOCH=datetime(1858,11,17,tzinfo=timezone.utc)
def date_from_mjd(value):
 v=float(value)
 if not math.isfinite(v):raise ValueError('nonfinite MJD')
 return (MJD_EPOCH+timedelta(days=v)).date().isoformat()
def filter_key(value):
 # CLEAR does not change the selected passband; preserve nonclear pupils/masks.
 parts=[x.strip().upper() for x in str(value or '').split(';')]
 return ';'.join(sorted(set(x for x in parts if x and x not in ('CLEAR','CLEARP'))))
def main():
 start=time.time();catalog=json.loads((ROOT/'nearby-current.json').read_text());old=json.loads((ROOT/'matches-current.json').read_text())
 source=json.loads((ROOT/'all-cal2-mast.json').read_text())
 if source.get('status')!='COMPLETE':raise ValueError('MAST response incomplete')
 if source.get('paging',{}).get('rowsFiltered')!=len(source['data']):raise ValueError('MAST response truncated')
 positions=unit([s['ra'] for s in catalog],[s['dec'] for s in catalog])
 allmatches=collections.defaultdict(list);errors=[];unsupported=[];supported=0
 for row in source['data']:
  if row.get('instrument_name') not in ALL_IMAGING:continue
  if not re.search(r'_(cal|i2d)\.fits$',row.get('dataURL') or '',re.I):
   unsupported.append({'obsid':row['obsid'],'dataURL':row.get('dataURL'),'reason':'not 2-D calibrated FITS suffix'});continue
  supported+=1
  try:
   day=date_from_mjd(row['t_min']);ids=contains(row['s_region'],positions)
  except Exception as e:errors.append({'obsid':row['obsid'],'error':str(e)});continue
  for idx in ids:
   allmatches[catalog[idx]['name']].append({**row,'calib_level':2,'epoch_start_utc':day,'canonical_filter':filter_key(row['filters'])})
 selected=collections.defaultdict(list);gaps=collections.defaultdict(list);covered_rows=0;missing_groups=0;candidate_rows=0
 for name,rows in allmatches.items():
  intervals=collections.defaultdict(list)
  for row in old.get(name,[]):
   try:
    lo=date_from_mjd(row['t_min']);hi=date_from_mjd(row['t_max'] if row.get('t_max') is not None else row['t_min'])
   except Exception as e:errors.append({'obsid':row['obsid'],'error':'cal3 time: '+str(e)});continue
   intervals[(row['instrument_name'],filter_key(row['filters']))].append((min(lo,hi),max(lo,hi)))
  groups=collections.defaultdict(list)
  for row in rows:
   key=(row['instrument_name'],row['canonical_filter']);day=row['epoch_start_utc']
   if any(lo<=day<=hi for lo,hi in intervals[key]):covered_rows+=1;continue
   groups[(day,*key)].append(row)
  for group,candidates in groups.items():
   # Deterministic ties: earliest exposure start, then archive identifier.
   def rank(row):
    exp=float(row.get('t_exptime') or 0)
    if not math.isfinite(exp):exp=0
    return (-exp,float(row['t_min']),str(row['obs_id']))
   candidates=sorted(candidates,key=rank)
   best=dict(candidates[0]);best['supplemental_selection']={'reason':'No matched level-3 image interval covers this UTC date/instrument/filter','method':'Longest t_exptime; earliest t_min and obs_id break ties','candidate_count':len(candidates),'candidate_uris':[r['dataURL'] for r in candidates]}
   selected[name].append(best);missing_groups+=1;candidate_rows+=len(candidates)
   gaps[name].append({'utc_date':group[0],'instrument':group[1],'filter':group[2],'selected_uri':best['dataURL'],'candidates':candidates})
 complete={name:list(rows) for name,rows in old.items()}
 for name,rows in selected.items():complete.setdefault(name,[]).extend(rows)
 for rows in complete.values():rows.sort(key=lambda r:(float(r['t_min']),r['instrument_name'],str(r['filters']),str(r['dataURL'])))
 (ROOT/'cal2-matches-all.json').write_text(json.dumps(dict(allmatches),indent=2))
 (ROOT/'cal2-gap-candidates.json').write_text(json.dumps(dict(gaps),indent=2))
 (ROOT/'cal2-supplemental-selected.json').write_text(json.dumps(dict(selected),indent=2))
 (ROOT/'matches-complete.json').write_text(json.dumps(complete,indent=2))
 summary={'cal2_archive_rows':len(source['data']),'supported_cal2_imaging_rows':supported,'unsupported_suffixes':len(unsupported),'cal2_matched_sne':len(allmatches),'cal2_matched_rows':sum(map(len,allmatches.values())),'cal2_rows_already_covered_by_cal3_date_intervals':covered_rows,'gap_candidate_rows':candidate_rows,'selected_supplemental_rows':missing_groups,'sne_with_supplement':len(selected),'newly_covered_sne':sorted(set(selected)-set(old)),'old_sne':len(old),'complete_sne':len(complete),'complete_rows':sum(map(len,complete.values())),'unique_products':len({r['dataURL'] for rows in complete.values() for r in rows}),'errors':errors,'supplement_counts':{k:len(v) for k,v in selected.items()},'seconds':round(time.time()-start,2),'representation_rule':'Same instrument and canonical filter, with level-2 UTC start date falling inclusively within a matched level-3 UTC start/end date interval. CLEAR/CLEARP omitted from canonical passband; other optics retained.','limitation':'Selected exposure supplements calendar-date/filter gaps; it does not represent every individual integration, nor validate finite-pixel coverage or detected SN flux.'}
 (ROOT/'cal2-supplemental-summary.json').write_text(json.dumps(summary,indent=2))
 (ROOT/'cal2-unsupported-products.json').write_text(json.dumps(unsupported,indent=2))
 if errors:raise RuntimeError(f'{len(errors)} supported calibrated footprints could not be parsed; publication aborted')
 print(json.dumps({k:v for k,v in summary.items() if k not in ('supplement_counts','errors')},indent=2));print('Errors',len(errors),errors[:3])
if __name__=='__main__':main()
