"""Exact SN-designation cross-matches; no proximity or abbreviated-year guesses."""
import re


def designation(value):
    value = re.sub(r'\s+', '', str(value)).lower()
    value = re.sub(r'^(sn|at)', '', value)
    return value if re.fullmatch(r'\d{4}[a-z]+', value) else None


def availability(images, spectra):
    result = []
    for kind, catalog, field in [('imagesName', images, 'observations'), ('spectraName', spectra, 'spectra')]:
        for obj in catalog.get('objects', []):
            if not any(p.get('status') == 'ready' for p in obj.get(field, [])):
                continue
            keys = sorted({key for value in [obj['name'], *obj.get('aliases', [])]
                           if (key := designation(value))})
            if keys:
                result.append({'keys': keys, kind: obj['name']})
    return result


def match_links(hiss_objects, available):
    lookup = {}
    for row in available:
        for key in row['keys']:
            for kind in ('imagesName', 'spectraName'):
                if row.get(kind):
                    lookup.setdefault(key, {}).setdefault(kind, set()).add(row[kind])
    matched = []
    for obj in hiss_objects:
        if obj.get('category') != 'transient' or not (obj.get('n', 0) > 0 or obj.get('has_lc')):
            continue
        keys = {key for value in [obj['id'], obj.get('name', '')] if (key := designation(value))}
        targets = {kind: set().union(*(lookup.get(key, {}).get(kind, set()) for key in keys))
                   for kind in ('imagesName', 'spectraName')}
        # Conflicting identities cannot safely identify a destination.
        if any(len(values) > 1 for values in targets.values()):
            continue
        row = {'hissId': obj['id']}
        row.update({kind: next(iter(values)) for kind, values in targets.items() if values})
        if len(row) > 1:
            matched.append(row)
    # Two HISS records sharing an ECHO object are ambiguous too.
    counts = {}
    for row in matched:
        for kind in ('imagesName', 'spectraName'):
            if row.get(kind):
                counts[(kind, row[kind])] = counts.get((kind, row[kind]), 0) + 1
    return [row for row in matched if all(counts[(kind, row[kind])] == 1
            for kind in ('imagesName', 'spectraName') if row.get(kind))]
