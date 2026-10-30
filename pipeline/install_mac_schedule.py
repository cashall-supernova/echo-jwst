#!/usr/bin/env python3
"""Install the Mac schedule after a verified Mac publication and cloud pause."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from run_mac import LOCAL, PROJECT, read

LABEL = 'edu.hawaii.echo.website-updater'


def definition(hosting='sites'):
    runner='run_github_mac.py' if hosting=='github' else 'run_mac.py'
    return {'Label': LABEL, 'ProgramArguments': ['/usr/bin/caffeinate', '-i',
        str(PROJECT / '.venv/bin/python'), str(PROJECT / 'pipeline' / runner), '--publish', '--scheduled'],
        'WorkingDirectory': str(PROJECT), 'StartCalendarInterval': {'Hour': 6, 'Minute': 0},
        'RunAtLoad': False, 'ProcessType': 'Background',
        'StandardOutPath': str(LOCAL / 'logs/scheduled.log'),
        'StandardErrorPath': str(LOCAL / 'logs/scheduled-errors.log')}


def main():
    os.umask(0o077)
    config=read(LOCAL / 'config.json')
    hosting=config.get('hosting','sites')
    publication='github-publication.json' if hosting=='github' else 'publication.json'
    if not read(LOCAL / publication).get('published_at'):
        raise RuntimeError('Complete and verify a Mac publication before installing the schedule')
    if not config.get('cloud_schedule_paused'):
        raise RuntimeError('Verify the existing cloud task is paused before installing the schedule')
    if hosting=='github' and not Path(config.get('node_path','')).is_file():
        raise RuntimeError('Configure a persistent Node.js path before installing the schedule')
    if subprocess.check_output(['/bin/date', '+%Z'], text=True).strip() != 'HST':
        raise RuntimeError('The Mac clock must be in Hawaii time for this 06:00 calendar schedule')
    target = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    if target.exists() and plistlib.loads(target.read_bytes()).get('WorkingDirectory') != str(PROJECT):
        raise RuntimeError('An existing ECHO schedule points to another installation')
    (LOCAL / 'logs').mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}', str(target)], capture_output=True)
    target.write_bytes(plistlib.dumps(definition(hosting)))
    target.chmod(0o600)
    subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)], check=True)
    subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/{LABEL}'], check=True, stdout=subprocess.DEVNULL)
    if hosting=='github':
        from run_mac import save
        config['github_schedule_enabled']=True
        save(LOCAL/'config.json',config)
    print('ECHO Mac schedule installed: daily at 06:00 Hawaii time.')


if __name__ == '__main__':
    main()
