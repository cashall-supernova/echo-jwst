"""Build an encrypted static archive. Public output contains no API credentials."""
import argparse
import base64
import concurrent.futures
import configparser
import gzip
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cross_archive import availability, match_links
from run_mac import HISS_CREDENTIALS, PROJECT, now, save
from sync_cross_links import read_hiss

ITERATIONS = 600000
MAX_SITE_BYTES = 950_000_000  # leave room below GitHub Pages' 1 GB cap


def compact(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


def login(path=HISS_CREDENTIALS):
    path = Path(path)
    if path.stat().st_mode & 0o077:
        raise RuntimeError('Team login configuration must be private')
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(path)
    return cp.get('access', 'username'), cp.get('access', 'password')


def derive(username, password):
    salt = hashlib.sha256(('ECHO static archive v1|' + username.strip().lower()).encode()).digest()[:16]
    key = hashlib.pbkdf2_hmac('sha256', (username.strip().lower() + '\n' + password).encode(), salt, ITERATIONS, 32)
    return salt, key


def seal(raw, path, key):
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    # An unchanged path + compressed plaintext produces the same ciphertext.
    # The secret-key HMAC nonce changes whenever either input changes; this
    # avoids rewriting every asset in Git for an unchanged daily publication.
    nonce = hmac.new(key, b'ECHO nonce v1\0' + path.encode() + b'\0' + hashlib.sha256(compressed).digest(), hashlib.sha256).digest()[:12]
    return b'ECHO' + nonce + AESGCM(key).encrypt(nonce, compressed, path.encode())


def unseal(raw, path, key):
    if raw[:4] != b'ECHO':
        raise ValueError('Invalid encrypted archive')
    return gzip.decompress(AESGCM(key).decrypt(raw[4:16], raw[16:], path.encode()))


def files_for(catalogs, cache):
    files = {}
    for obj in catalogs['catalog']['objects']:
        for product in obj['observations'] + obj.get('colorComposites', []):
            if product['status'] == 'ready':
                for ext, mime in [('png', 'image/png'), ('fits', 'application/fits')]:
                    identifier = product['id']
                    if not re.fullmatch(r'[a-f0-9]{24}', identifier):
                        raise ValueError('Invalid image identifier')
                    files[f'/api/stamps/{identifier}.{ext}'] = (cache / 'stamps' / f'{identifier}.{ext}', mime)
    for obj in catalogs['spectra']['objects']:
        for product in obj['spectra']:
            if product['status'] == 'ready':
                identifier = product['id']
                if not re.fullmatch(r'[a-f0-9]{24}', identifier):
                    raise ValueError('Invalid spectrum identifier')
                files[f'/api/spectra/{identifier}'] = (cache / 'spectra/assets' / f'{identifier}.json', 'application/json')
    return files


def validate_catalogs(catalogs):
    c, s = catalogs['catalog'], catalogs['spectra']
    audit = c['catalogueAudit']
    if not c['scanComplete'] or audit['eligibleSn'] != audit['representedSn'] or c['total'] != len(c['objects']):
        raise ValueError('Incomplete imaging catalogue; publication stopped')
    if not s['objects'] or s['audit']['readySpectra'] != sum(p['status'] == 'ready' for o in s['objects'] for p in o['spectra']):
        raise ValueError('Incomplete spectral catalogue; publication stopped')


def export(cache, out, access=HISS_CREDENTIALS, hiss_index=None, schedule=None):
    cache, out = Path(cache), Path(out)
    catalogs = {'catalog': json.loads((cache / 'snapshot.json').read_text()),
                'spectra': json.loads((cache / 'spectra/snapshot.json').read_text())}
    validate_catalogs(catalogs)
    if not (out / 'index.html').is_file() or not (out / 'spectra/index.html').is_file():
        raise ValueError('Run npm run build:github before exporting data')
    assets = files_for(catalogs, cache)
    missing = [path for path, (file, _) in assets.items() if not file.is_file()]
    if missing:
        raise ValueError(f'{len(missing)} ready archive files are missing; hydrate the migration cache before publication')
    if schedule is not None:
        catalogs['catalog']['schedule'] = schedule
    # The legacy catalogue uses API-relative URLs, including cached /stamps URLs.
    for obj in catalogs['catalog']['objects']:
        for product in obj['observations'] + obj.get('colorComposites', []):
            if product['status'] == 'ready':
                for ext in ('png', 'fits'):
                    product[ext] = f'/api/stamps/{product["id"]}.{ext}'
    hiss_index = hiss_index or read_hiss(Path(access))
    available = availability(catalogs['catalog'], catalogs['spectra'])
    cross = {'updatedAt': now(), 'hissRevision': hiss_index.get('data_revision', hiss_index.get('built', '')),
             'links': match_links(hiss_index['objects'], available)}
    salt, key = derive(*login(access))
    data_dir = out / 'data'
    data_dir.mkdir(exist_ok=True)
    def write(raw, path, mime):
        encrypted = seal(raw, path, key)
        filename = hashlib.sha256(encrypted).hexdigest() + '.bin'
        target = data_dir / filename
        if not target.exists():
            target.write_bytes(encrypted)
        return {'file': 'data/' + filename, 'type': mime}
    resources = {}
    def process(item):
        path, (file, mime) = item
        raw = file.read_bytes()
        if mime == 'image/png' and not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid PNG input')
        if mime == 'application/fits' and not raw.startswith(b'SIMPLE'):
            raise ValueError('Invalid FITS input')
        if mime == 'application/json' and json.loads(raw).get('id') != path.rsplit('/', 1)[1]:
            raise ValueError('Spectral asset identifier mismatch')
        return path, write(raw, path, mime)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i, (path, entry) in enumerate(pool.map(process, assets.items()), 1):
            resources[path] = entry
            if i % 1000 == 0:
                print(f'Encrypted {i}/{len(assets)} archive assets.', flush=True)
    for path, data in [('/api/catalog', catalogs['catalog']), ('/api/spectra', catalogs['spectra']), ('/api/cross-links', cross)]:
        resources[path] = write(compact(data), path, 'application/json')
    manifest = {'version': 1, 'updatedAt': now(), 'resources': resources}
    entry = write(compact(manifest), 'manifest', 'application/json')
    lock = {'version': 1, 'iterations': ITERATIONS, 'salt': base64.b64encode(salt).decode(), 'manifest': entry['file']}
    (out / 'lock.json').write_bytes(compact(lock))
    (out / '.nojekyll').touch()
    (out / 'robots.txt').write_text('User-agent: *\nDisallow: /\n')
    shutil.copyfile(PROJECT / 'public/favicon.svg', out / 'favicon.svg')
    referenced = {entry['file'], *(v['file'] for v in resources.values())}
    for file in data_dir.glob('*.bin'):
        if 'data/' + file.name not in referenced:
            file.unlink()  # disposable output only; never remove source/cache files
    total = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    if total > MAX_SITE_BYTES:
        raise ValueError('Encrypted output exceeds the GitHub Pages size budget; publication stopped')
    # Verify every encrypted output using the existing team key before any push.
    for path, value in resources.items():
        raw = unseal((out / value['file']).read_bytes(), path, key)
        if path in assets and hashlib.sha256(raw).digest() != hashlib.sha256(assets[path][0].read_bytes()).digest():
            raise ValueError('Encrypted asset round-trip mismatch')
    save(cache / 'github-export.json', {'builtAt': manifest['updatedAt'], 'bytes': total,
         'resources': len(resources), 'objects': len(catalogs['catalog']['objects']),
         'spectralObjects': len(catalogs['spectra']['objects']), 'sharedObjects': len(cross['links'])})
    save(Path(access).parent / 'echo-availability.json', {'updatedAt': cross['updatedAt'], 'available': available})
    print(f'Validated {len(resources)} encrypted resources; {total / 1e6:.1f} MB.', flush=True)
    return lock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=PROJECT / 'local/cache')
    parser.add_argument('--out', type=Path, default=PROJECT / 'local/github-site')
    args = parser.parse_args()
    os.umask(0o077)
    export(args.cache, args.out)


if __name__ == '__main__':
    main()
