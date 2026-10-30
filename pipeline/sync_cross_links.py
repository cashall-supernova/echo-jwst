"""Refresh private object links from the published, encrypted HISS catalogue."""
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import re

import requests
from cross_archive import availability, match_links
from run_mac import HISS_CREDENTIALS, inspect_site, now, service_access
from site_access import site_headers

HISS = 'https://cashall-supernova.github.io/hiss-spectra/'


def read_hiss(path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if path.stat().st_mode & 0o077:
        raise RuntimeError('HISS access configuration must be private')
    config = configparser.ConfigParser(interpolation=None)
    config.read(path)
    response = requests.get(HISS, timeout=120)
    response.raise_for_status()
    header = re.search(r'window.HISS_LOCK\s*=\s*(\{[^\n]+\});', response.text)
    if not header:
        raise RuntimeError('Published HISS encrypted catalogue is unavailable')
    lock = json.loads(header[1])
    material = (config.get('access', 'username').strip().lower() + '\n' + config.get('access', 'password')).encode()
    key = hashlib.pbkdf2_hmac('sha256', material, base64.b64decode(lock['salt']), lock['iter'], 32)
    data = base64.b64decode(lock['index'])
    index = json.loads(AESGCM(key).decrypt(data[:12], data[12:], None))
    if not isinstance(index.get('objects'), list) or not index['objects']:
        raise RuntimeError('HISS catalogue is incomplete; retaining previous links')
    return index


def sync(credentials, catalogs=None):
    config_path = Path(os.environ.get('HISS_ACCESS_CONFIG', str(HISS_CREDENTIALS)))
    hiss = read_hiss(config_path)
    catalogs = catalogs or inspect_site(credentials)
    available = availability(catalogs['catalog'], catalogs['spectra'])
    updated = now()
    data = {'updatedAt': updated, 'hissRevision': hiss.get('data_revision', hiss.get('built', '')),
            'links': match_links(hiss['objects'], available)}
    headers = site_headers(credentials['token'], credentials['updater_token'])
    response = requests.post(credentials['site'] + '/api/ingest', headers=headers,
                             json={'action': 'cross_links', 'data': data}, timeout=120)
    response.raise_for_status()
    back = requests.get(credentials['site'] + '/api/cross-links', headers=headers, timeout=120)
    back.raise_for_status()
    if back.json() != data:
        raise RuntimeError('Cross-link publication readback mismatch')
    # HISS embeds the next build's matches inside its encrypted index.
    target = config_path.parent / 'echo-availability.json'
    temporary = target.with_suffix('.tmp')
    with temporary.open('w') as output:
        os.chmod(temporary, 0o600)
        json.dump({'updatedAt': updated, 'available': available}, output)
    temporary.replace(target)
    print(f'Cross-archive links verified: {len(data["links"])} shared objects.', flush=True)
    return data


if __name__ == '__main__':
    sync(service_access())
