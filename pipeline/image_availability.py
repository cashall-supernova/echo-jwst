"""Attach public-availability dates without confusing release and observation."""
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from mast_index import validate


def enrich(snapshot, previous, root):
    public = {}
    for filename in ('all-jwst-mast.json', 'all-cal2-mast.json'):
        for row in validate(json.loads((Path(root) / filename).read_text())):
            if row.get('dataRights', 'PUBLIC') == 'PUBLIC':
                public[(row.get('obs_id'), row.get('dataURL'))] = row
    def identity(name):
        return re.sub(r'^(sn|at)(?=\d{4})', 'iau:', re.sub(r'\s+', '', name).lower())
    previous_objects = (previous or {}).get('objects', [])
    old_sn = {identity(s['name']): s for s in previous_objects}
    old = {(identity(s['name']), o['id']): o for s in previous_objects for o in s['observations']}
    old_uri = {(identity(s['name']), o['uri']): o for s in previous_objects for o in s['observations']}
    checked = snapshot['updatedAt']
    current_mjd = datetime.fromisoformat(checked.replace('Z', '+00:00')).timestamp() / 86400 + 40587
    for sn in snapshot['objects']:
        name = identity(sn['name'])
        # Existing entries without recorded arrival times remain unknown.
        sn['firstIndexedAt'] = old_sn[name].get('firstIndexedAt') if name in old_sn else checked
        for image in sn['observations']:
            row = public.get((image['obsId'], image['uri']))
            release = row.get('t_obs_release') if row else None
            try:
                release = float(release)
            except (TypeError, ValueError):
                release = None
            image['publicReleaseMjd'] = release if release is not None and math.isfinite(release) and 0 < release <= current_mjd else None
            # A new position changes the cutout ID, not the archive release date.
            prior = old.get((name, image['id'])) or old_uri.get((name, image['uri']))
            # Do not fabricate first-seen times for already-indexed legacy data.
            image['firstIndexedAt'] = prior.get('firstIndexedAt') if prior else checked
    return snapshot
