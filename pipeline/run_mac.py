#!/usr/bin/env python3
"""Run the ECHO refresh on this Mac, with persistent caches and Keychain access."""
import argparse
import configparser
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import fcntl
import io
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import termios
from site_access import site_headers

PROJECT = Path(__file__).resolve().parent.parent
LOCAL = PROJECT / 'local'
SITE = 'https://echo-nearby-supernova-atlas.chris-ashall-1598.chatgpt.site'
PROJECT_ID = 'appgprj_6ae3a53631a48191a400416ade5ae725'
SERVICE = 'edu.hawaii.echo.site-updater'
UPDATER_SERVICE = 'edu.hawaii.echo.updater-token'
HISS_CREDENTIALS = Path.home() / 'Documents/ChatGPT/HISS website/hiss-updater/local/credentials.ini'


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def service_access():
    result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-a', PROJECT_ID,
                             '-s', SERVICE, '-w'], capture_output=True, text=True)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError('ECHO Site access is unavailable in the login Keychain')
    updater = subprocess.run(['/usr/bin/security', 'find-generic-password', '-a', PROJECT_ID,
                              '-s', UPDATER_SERVICE, '-w'], capture_output=True, text=True)
    if updater.returncode or not updater.stdout.strip():
        raise RuntimeError('ECHO updater access is unavailable in the login Keychain')
    return {'site': SITE, 'token': result.stdout.strip(), 'updater_token': updater.stdout.strip()}


def configure():
    """Receive existing Site service access over hidden stdin; never write a key file."""
    original = termios.tcgetattr(sys.stdin) if sys.stdin.isatty() else None
    try:
        if original:
            hidden = original.copy()
            hidden[3] &= ~termios.ECHO
            termios.tcsetattr(sys.stdin, termios.TCSANOW, hidden)
        print('Ready for ECHO service access JSON on stdin (input is hidden).', flush=True)
        credentials = json.loads(sys.stdin.readline())
    finally:
        if original:
            termios.tcsetattr(sys.stdin, termios.TCSANOW, original)
    if credentials.get('site', '').rstrip('/') != SITE or not re.fullmatch(r'[A-Za-z0-9_-]{20,200}', credentials.get('token', '')):
        raise ValueError('Unexpected ECHO Site access configuration')
    # security's interactive stdin keeps the value out of argv, files and logs.
    command = f'add-generic-password -U -a {PROJECT_ID} -s {SERVICE} -w {credentials["token"]}\n'
    result = subprocess.run(['/usr/bin/security', '-i'], input=command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Could not verify saved Keychain access')
    save(LOCAL / 'config.json', {'site': SITE, 'project_id': PROJECT_ID,
         'tns_credentials': str(HISS_CREDENTIALS), 'time': '06:00 Pacific/Honolulu',
         'cloud_schedule_paused': False})
    print('Existing Site access saved in the login Keychain; no credential file created.')


def download_tns(destination):
    import requests
    from merge_tns import read_snapshot
    path = Path(read(LOCAL / 'config.json').get('tns_credentials', str(HISS_CREDENTIALS)))
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise RuntimeError('HISS TNS credentials must be readable only by this account')
    credentials = configparser.ConfigParser(interpolation=None)
    credentials.read(path)
    bot_id, name, key = (credentials.get('tns', item, fallback='') for item in ('bot_id', 'bot_name', 'api_key'))
    if not bot_id.isdigit() or not name or not key:
        raise RuntimeError('The existing HISS TNS configuration is incomplete')
    marker = 'tns_marker' + json.dumps({'tns_id': int(bot_id), 'type': 'bot', 'name': name})
    url = 'https://www.wis-tns.org/system/files/tns_public_objects/tns_public_objects.csv.zip'
    response = requests.post(url, headers={'User-Agent': marker}, data={'api_key': key}, timeout=120, allow_redirects=False)
    if response.status_code != 200:
        raise RuntimeError(f'TNS bulk download returned HTTP {response.status_code}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp.zip')
    temporary.write_bytes(response.content)
    read_snapshot(temporary)  # No stale or invalid catalogue can replace a valid cache.
    temporary.replace(destination)


def inspect_site(credentials):
    import requests
    result = {}
    for endpoint in ('catalog', 'spectra'):
        response = requests.get(SITE + '/api/' + endpoint,
            headers=site_headers(credentials['token'], credentials['updater_token']), timeout=120, allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError(f'ECHO {endpoint} readback returned HTTP {response.status_code}')
        data = response.json()
        if not data.get('updatedAt') or not data.get('objects'):
            raise RuntimeError(f'ECHO {endpoint} readback is incomplete')
        result[endpoint] = data
    return result


def summarize(data):
    catalogue, spectra = data['catalog'], data['spectra']
    return {'catalogue_updated_at': catalogue['updatedAt'], 'spectra_updated_at': spectra['updatedAt'],
            'objects': len(catalogue['objects']),
            'ready_stamps': sum(o['status'] == 'ready' for s in catalogue['objects'] for o in s['observations']),
            'failed_stamps': sum(o['status'] == 'error' for s in catalogue['objects'] for o in s['observations']),
            'ready_spectra': spectra.get('audit', {}).get('readySpectra')}


def verify_local_publication(data, cache):
    for endpoint, path in [('catalog', cache / 'snapshot.json'), ('spectra', cache / 'spectra/snapshot.json')]:
        local = read(path)
        if local.get('updatedAt') != data[endpoint]['updatedAt']:
            raise RuntimeError(f'{endpoint} does not match this Mac run; another publisher may have run')
    audit = data['catalog'].get('catalogueAudit', {})
    if not data['catalog'].get('scanComplete') or audit.get('eligibleSn') != audit.get('representedSn'):
        raise RuntimeError('Catalogue completeness audit failed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--configure-stdin', action='store_true')
    parser.add_argument('--check', action='store_true', help='Validate TNS and Site reads without publishing')
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--scheduled', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    LOCAL.mkdir(exist_ok=True)
    if args.configure_stdin:
        configure()
        return 0
    config = read(LOCAL / 'config.json')
    if args.scheduled and not config.get('cloud_schedule_paused'):
        raise RuntimeError('Cloud schedule pause must be verified before unattended Mac updates')
    if not args.check and not args.publish:
        parser.error('Use --check or --publish')
    with (LOCAL / 'run.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another ECHO update is running; skipped.')
            return 0
        credentials = service_access()
        os.environ['ECHO_UPDATER_TOKEN'] = credentials['updater_token']
        cache = LOCAL / 'cache'
        cache.mkdir(exist_ok=True)
        os.environ['ECHO_WORK_DIR'] = str(cache)
        logs = LOCAL / 'logs'
        logs.mkdir(exist_ok=True)
        for old in sorted(logs.glob('update-*.log'))[:-29]:
            old.unlink()
        log_path = logs / ('update-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.log')
        status = {'status': 'running', 'started_at': now(), 'mode': 'check' if args.check else 'publish', 'log': str(log_path)}
        save(LOCAL / 'status.json', status)
        original_stdin, original_argv = sys.stdin, sys.argv
        try:
            with log_path.open('w', buffering=1) as log, redirect_stdout(log), redirect_stderr(log):
                print('Downloading the current public TNS catalogue.', flush=True)
                download_tns(cache / 'tns-public.zip')
                before = inspect_site(credentials)
                print('Existing publication:', json.dumps(summarize(before)), flush=True)
                if args.publish:
                    sys.stdin = io.StringIO(json.dumps(credentials) + '\n')
                    sys.argv = [str(PROJECT / 'pipeline/update.py'), '--refresh', '--publish', '--workers', '6',
                                '--tns-catalog', str(cache / 'tns-public.zip')]
                    runpy.run_path(str(PROJECT / 'pipeline/update.py'), run_name='__main__')
                    after = inspect_site(credentials)
                    verify_local_publication(after, cache)
                    from sync_cross_links import sync
                    sync(credentials, after)
                    status.update(summarize(after))
                    save(LOCAL / 'publication.json', {'published_at': now(), **summarize(after)})
                else:
                    status.update(summarize(before))
            status.update(status='success', finished_at=now())
            print('ECHO Mac ' + ('access check' if args.check else 'update and publication') + ' succeeded.')
            return 0
        except Exception as error:
            # Secrets stay out of reports, including accidental exception content.
            message = str(error).replace(credentials['token'], '[redacted]').replace(credentials['updater_token'], '[redacted]')[:1000]
            status.update(status='failed', finished_at=now(), error_type=type(error).__name__, error=message)
            with log_path.open('a') as log:
                log.write(f'\nStopped: {type(error).__name__}: {message}. Last successful manifests remain available.\n')
            print(f'ECHO update stopped: {type(error).__name__}. See {log_path}', file=sys.stderr)
            return 1
        finally:
            sys.stdin, sys.argv = original_stdin, original_argv
            save(LOCAL / 'status.json', status)


if __name__ == '__main__':
    raise SystemExit(main())
