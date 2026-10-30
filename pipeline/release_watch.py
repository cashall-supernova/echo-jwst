"""Keep a metadata-only watch list for JWST images under exclusive access.

Release dates are estimates. Only an explicit PUBLIC archive record proves
release; missing rows are retained as unconfirmed, never silently released.
"""
import collections
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from geometry import ALL_IMAGING, contains, unit
from mast_index import validate


def finite(value):
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (ValueError,TypeError):return None


def record(row, checked_at, previous=None):
    old=previous or {}
    return {'id':str(row['obsid']), 'obsId':row['obs_id'],
            'instrument':row['instrument_name'], 'filter':row.get('filters') or 'Unknown',
            'proposal':str(row.get('proposal_id') or ''), 'start':finite(row.get('t_min')),
            'end':finite(row.get('t_max')), 'release':finite(row.get('t_obs_release')),
            'calibLevel':int(row.get('calib_level',3)), 'status':'exclusive',
            'firstSeen':old.get('firstSeen',checked_at), 'lastSeen':checked_at,
            'lastChecked':checked_at}


def reconcile(objects, exclusive_rows, public_rows, previous_objects, checked_at):
    positions=unit([s['ra'] for s in objects],[s['dec'] for s in objects])
    previous={s['name']:s for s in previous_objects}
    public={str(row['obsid']):row for row in public_rows}
    exclusive={str(row['obsid']):row for row in exclusive_rows}
    current=collections.defaultdict(dict);regions={};missing_regions=0
    for row in exclusive_rows:
        if row['instrument_name'] not in ALL_IMAGING:continue
        region=row.get('s_region')
        if not region or not str(region).strip():missing_regions+=1;continue
        if region not in regions:regions[region]=contains(region,positions)
        for index in regions[region]:
            sn=objects[index];key=str(row['obsid'])
            old=next((w for w in previous.get(sn['name'],{}).get('releaseWatch',[]) if w['id']==key),None)
            current[sn['name']][key]=record(row,checked_at,old)
    for sn in objects:
        watched=current[sn['name']]
        for old in previous.get(sn['name'],{}).get('releaseWatch',[]):
            key=old['id']
            if key in watched:continue
            if key in public:
                # Explicit rights outrank the expected date and previous state.
                row=public[key]
                watched[key]={**old,'status':'public','lastSeen':checked_at,'lastChecked':checked_at,
                              'releasedAt':old.get('releasedAt',checked_at),
                              'release':finite(row.get('t_obs_release'))}
            elif key in exclusive:
                # The footprint/coordinate no longer matches. Preserve the
                # earlier discovery, but do not count it as current SN coverage.
                watched[key]={**record(exclusive[key],checked_at,old),'status':'unconfirmed'}
            else:
                watched[key]={**old,'status':'unconfirmed','lastChecked':checked_at}
        sn['releaseWatch']=sorted(watched.values(),key=lambda w:(w['start'] or 0,w['id']),reverse=True)
    return {'checkedAt':checked_at,'exclusiveArchiveRows':len(exclusive_rows),
            'matchedObservations':sum(w['status']=='exclusive' for s in objects for w in s['releaseWatch']),
            'matchedObjects':sum(any(w['status']=='exclusive' for w in s['releaseWatch']) for s in objects),
            'missingFootprints':missing_regions,'calibrationLevels':[2,3]}


def apply_release_watch(snapshot, previous, root):
    root=Path(root);exclusive=[];checked=[];public=[]
    for level in [2,3]:
        path=root/f'exclusive-level{level}-mast.json'
        if not path.exists():raise RuntimeError('Missing exclusive-access metadata index; run --refresh first')
        payload=json.loads(path.read_text());rows=validate(payload,allow_empty=True)
        if any(row.get('dataRights')!='EXCLUSIVE_ACCESS' for row in rows):
            raise RuntimeError('Unexpected archive rights in exclusive-access index')
        exclusive.extend(rows)
        checked.append(payload.get('fetchedAt') or datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat().replace('+00:00','Z'))
        source=root/('all-cal2-mast.json' if level==2 else 'all-jwst-mast.json')
        payload=json.loads(source.read_text());rows=validate(payload)
        if any(row.get('dataRights','PUBLIC')!='PUBLIC' for row in rows):
            raise RuntimeError('Unexpected archive rights in public index')
        public.extend(rows)
    snapshot['releaseWatchAudit']=reconcile(snapshot['objects'],exclusive,public,(previous or {}).get('objects',[]),min(checked))
    print('Release watch:',json.dumps(snapshot['releaseWatchAudit']),flush=True)
