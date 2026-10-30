#!/usr/bin/env python3
"""Refresh TNS/JWST locally and publish the encrypted GitHub Pages archive."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import fcntl
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from run_mac import PROJECT, LOCAL, now, read, save, download_tns
from export_github import export, validate_catalogs, files_for
from publish_github import publish, verify_live, PUBLIC_URL


def catalogs(cache):
    return {'catalog':read(cache/'snapshot.json'),'spectra':read(cache/'spectra/snapshot.json')}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--publish',action='store_true')
    p.add_argument('--check',action='store_true')
    p.add_argument('--scheduled',action='store_true')
    p.add_argument('--export-only',action='store_true',help='Publish the already verified cache without an archive rescan')
    args=p.parse_args()
    if not args.publish and not args.check:
        p.error('Use --publish or --check')
    os.umask(0o077)
    LOCAL.mkdir(exist_ok=True)
    config=read(LOCAL/'config.json')
    if args.scheduled and not config.get('cloud_schedule_paused'):
        raise RuntimeError('Pause the obsolete cloud schedule before activating unattended Mac updates')
    with (LOCAL/'run.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another ECHO update is running; skipped.');return 0
        cache=LOCAL/'cache';cache.mkdir(exist_ok=True)
        os.environ['ECHO_WORK_DIR']=str(cache)
        logs=LOCAL/'logs';logs.mkdir(exist_ok=True)
        logpath=logs/('github-update-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.log')
        status={'status':'running','started_at':now(),'hosting':'github','log':str(logpath)}
        save(LOCAL/'github-status.json',status)
        oldargv=sys.argv
        try:
            with logpath.open('w',buffering=1) as log,redirect_stdout(log),redirect_stderr(log):
                if not args.export_only:
                    download_tns(cache/'tns-public.zip')
                if args.publish and not args.export_only:
                    sys.argv=[str(PROJECT/'pipeline/update.py'),'--refresh','--tns-catalog',str(cache/'tns-public.zip'),'--workers','6']
                    runpy.run_path(str(PROJECT/'pipeline/update.py'),run_name='__main__')
                    from spectra import run
                    run(cache/'spectra',cache/'tns-public.zip',cache/'catalog.json',refresh=True,workers=6)
                data=catalogs(cache);validate_catalogs(data)
                missing=[path for path,(file,_) in files_for(data,cache).items() if not file.is_file()]
                if missing:raise RuntimeError(f'{len(missing)} ready files are missing; publication stopped')
                if args.publish:
                    node=config.get('node_path') or shutil.which('node')
                    if not node or not Path(node).is_file():raise RuntimeError('Node.js is required to build the static site')
                    subprocess.run([node,str(PROJECT/'node_modules/vite/bin/vite.js'),'build','--config','vite.github.config.ts'],cwd=PROJECT,check=True,stdout=log,stderr=log)
                    schedule={'enabled':bool(config.get('github_schedule_enabled')),'time':'Mac updater · daily at 06:00 Hawaii time'}
                    export(cache,LOCAL/'github-site',schedule=schedule)
                    sha=publish()
                    for attempt in range(30):
                        try:
                            if verify_live():break
                        except Exception:
                            if attempt==29:raise
                        time.sleep(20)
                    else:raise RuntimeError('GitHub Pages deployment has not completed; inspect GitHub Actions')
                    status.update(commit=sha,url=PUBLIC_URL)
            status.update(status='success',finished_at=now())
            print('ECHO GitHub '+('publication' if args.publish else 'readiness check')+' succeeded.')
            return 0
        except Exception as error:
            # The log may contain ordinary archive diagnostics, but credentials
            # never enter HTTP exception bodies or subprocess arguments here.
            status.update(status='failed',finished_at=now(),error_type=type(error).__name__)
            # Only locally generated RuntimeError messages are safe to retain;
            # third-party exception strings may contain request details.
            if isinstance(error,RuntimeError):
                status['error']=str(error)
                with logpath.open('a') as log:log.write('\nUpdate failed: '+str(error)+'\n')
            print(f'ECHO GitHub update failed ({type(error).__name__}); see {logpath}',file=sys.stderr)
            return 1
        finally:
            sys.argv=oldargv;save(LOCAL/'github-status.json',status)


if __name__=='__main__':
    raise SystemExit(main())
