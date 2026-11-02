"""Publish reviewed source and encrypted data to GitHub Pages from this Mac."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

import requests
from export_github import derive, login, unseal, MAX_SITE_BYTES
from run_mac import PROJECT, LOCAL, save, now
from github_workspace import workspace_root

REPOSITORY = 'cashall-supernova/echo-jwst'
PUBLIC_URL = 'https://cashall-supernova.github.io/echo-jwst/'
TOKEN_FILE = Path.home() / 'Documents/ChatGPT/HISS website/hiss-updater/local/github_token.txt'
ASKPASS = TOKEN_FILE.parent / 'git-askpass'


def client():
    if TOKEN_FILE.stat().st_mode & 0o077:
        raise RuntimeError('GitHub credential file must be private')
    s = requests.Session()
    s.headers.update({'Authorization': 'Bearer ' + TOKEN_FILE.read_text().strip(),
                      'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    return s


def check(response, allowed=(200,)):
    if response.status_code not in allowed:
        raise RuntimeError(f'GitHub returned HTTP {response.status_code}; publication stopped')
    return response


def validate_output(source):
    lock = json.loads((source / 'lock.json').read_text())
    _, key = derive(*login())
    manifest = json.loads(unseal((source / lock['manifest']).read_bytes(), 'manifest', key))
    allowed = {'index.html', 'spectra/index.html', 'lock.json', 'robots.txt', '.nojekyll', 'favicon.svg', lock['manifest']}
    allowed.update(v['file'] for v in manifest['resources'].values())
    if set(manifest['resources']).issuperset({'/api/catalog','/api/spectra','/api/cross-links'}) is False:
        raise RuntimeError('Incomplete encrypted publication')
    total = 0
    for file in source.rglob('*'):
        if file.is_symlink():
            raise RuntimeError('Publication must not contain symlinks')
        if not file.is_file():
            continue
        name = file.relative_to(source).as_posix()
        if name not in allowed and not re.fullmatch(r'assets/[A-Za-z0-9_.-]+\.(js|css|svg|woff2?)',name):
            raise RuntimeError('Unexpected public output file: '+name)
        if name.startswith('data/') and not file.read_bytes().startswith(b'ECHO'):
            raise RuntimeError('Unencrypted data file in publication')
        total += file.stat().st_size
    if total > MAX_SITE_BYTES:
        raise RuntimeError('GitHub Pages size budget exceeded')
    for name in allowed:
        if not (source / name).is_file():
            raise RuntimeError('Missing required publication file: '+name)
    return lock


def stage_source(checkout):
    """Explicit allowlist: never publish local files, catalogue snapshots or secrets."""
    roots = ['app', 'lib', 'static', 'pipeline', 'tests']
    excluded = {'app/layout.tsx','app/chatgpt-auth.ts','app/spectra/layout.tsx','lib/access.ts'}
    for root in roots:
        for file in (PROJECT / root).rglob('*'):
            name = file.relative_to(PROJECT).as_posix()
            if not file.is_file() or file.is_symlink() or '__pycache__' in file.parts or name.startswith('app/api/') or name in excluded:
                continue
            if file.suffix not in ('.ts','.tsx','.mts','.py','.mjs','.css','.html','.txt','.adql'):
                continue
            target = checkout / name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(file,target)
    for name in ['vite.github.config.ts','postcss.config.mjs','tsconfig.json','public/favicon.svg','GITHUB_PAGES.md']:
        target = checkout / name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PROJECT / name,target)
    package = json.loads((PROJECT / 'package.json').read_text())
    package['name'] = 'echo-jwst'
    package['scripts'] = {'build':'vite build --config vite.github.config.ts','build:github':'vite build --config vite.github.config.ts','check':'tsc --noEmit'}
    (checkout / 'package.json').write_text(json.dumps(package,indent=2)+'\n')
    # Keep the lockfile dependency graph reproducible; only the root name changes.
    lock = json.loads((PROJECT / 'package-lock.json').read_text())
    lock['name']='echo-jwst'
    lock['packages']['']['name']='echo-jwst'
    (checkout / 'package-lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    (checkout / '.gitignore').write_text('node_modules/\nlocal/\nwork/\n.venv/\n.env*\n.dev.vars*\n__pycache__/\n*.pyc\n*.tsbuildinfo\n.DS_Store\n')
    (checkout / 'README.md').write_text((PROJECT / 'GITHUB_PAGES.md').read_text())


def git(checkout, *args):
    env = dict(os.environ,GIT_ASKPASS=str(ASKPASS),GIT_TERMINAL_PROMPT='0',HISS_GITHUB_TOKEN_FILE=str(TOKEN_FILE))
    result = subprocess.run(['git','-C',str(checkout),*args],env=env,capture_output=True,text=True)
    if result.returncode:
        # Git credentials are supplied by askpass, never embedded in the remote.
        raise RuntimeError('Git '+args[0]+' failed: '+result.stderr[-500:])
    return result.stdout.strip()


def prepare_checkout(checkout, remote, existing_repo=True):
    """Keep interrupted work for inspection, then recover an owned checkout."""
    if (checkout / '.git').exists():
        if git(checkout,'remote','get-url','origin') != remote:
            raise RuntimeError('Unexpected publication remote')
        if git(checkout,'status','--porcelain'):
            recovery = checkout.with_name('github-publication-recovery-'+uuid.uuid4().hex[:12])
            checkout.rename(recovery)
            print('Preserved unfinished publication checkout: '+str(recovery),flush=True)
    elif checkout.exists() and any(checkout.iterdir()):
        raise RuntimeError('Publication directory contains unexpected files without Git metadata')
    if not (checkout / '.git').exists():
        checkout.mkdir(mode=0o700,parents=True,exist_ok=True)
        git(checkout,'init','-b','main')
        git(checkout,'remote','add','origin',remote)
        if existing_repo:
            git(checkout,'fetch','--depth=1','origin','main')
            git(checkout,'checkout','-B','main','origin/main')
    elif git(checkout,'ls-remote','--heads','origin','main'):
        git(checkout,'pull','--ff-only','origin','main')


def publish(source=None, create=False):
    source = Path(source) if source is not None else workspace_root() / 'github-site'
    lock = validate_output(source)
    s = client()
    endpoint = 'https://api.github.com/repos/'+REPOSITORY
    repo = s.get(endpoint,timeout=60)
    if repo.status_code == 404 and create:
        owner = check(s.get('https://api.github.com/user',timeout=30)).json()['login']
        if owner != REPOSITORY.split('/')[0]:
            raise RuntimeError('Wrong GitHub account')
        repo = check(s.post('https://api.github.com/user/repos',json={'name':REPOSITORY.split('/')[1],
            'description':'ECHO: JWST images and spectra of supernovae. Encrypted team archive.',
            'homepage':PUBLIC_URL,'private':False,'auto_init':False},timeout=60),(201,))
    else:
        check(repo)
    remote = repo.json()['clone_url']
    checkout = workspace_root() / 'github-publication'
    prepare_checkout(checkout,remote,existing_repo=repo.json().get('size',0)>0)
    docs = checkout / 'docs'
    if docs.exists():
        shutil.rmtree(docs)  # this owned checkout contains only generated output
    shutil.copytree(source,docs)
    stage_source(checkout)
    git(checkout,'add','--all')
    if git(checkout,'diff','--cached','--name-only'):
        git(checkout,'-c','user.name=ECHO updater','-c','user.email=cashall-supernova@users.noreply.github.com',
            'commit','-m','Update ECHO encrypted JWST archive')
        print('Uploading encrypted archive to GitHub.',flush=True)
    # Also retry an interrupted initial upload when the local commit exists.
    git(checkout,'push','-u','origin','main')
    sha = git(checkout,'rev-parse','HEAD')
    pages = s.get(endpoint+'/pages',timeout=60)
    if pages.status_code == 404 and create:
        check(s.post(endpoint+'/pages',json={'source':{'branch':'main','path':'/docs'}},timeout=60),(201,))
    else:
        check(pages)
        if pages.json().get('source') != {'branch':'main','path':'/docs'}:
            raise RuntimeError('Unexpected Pages source; inspect before changing it')
    save(LOCAL/'github-push.json',{'pushedAt':now(),'commit':sha,'repository':REPOSITORY,'url':PUBLIC_URL,'manifest':lock['manifest']})
    print('GitHub push complete; waiting for the Pages deployment.',flush=True)
    return sha


def verify_live():
    expected=json.loads((LOCAL/'github-push.json').read_text())
    r=requests.get(PUBLIC_URL+'lock.json',params={'verify':expected['commit']},timeout=60)
    if r.status_code!=200 or r.json().get('manifest')!=expected['manifest']:
        return False
    lock=r.json();_,key=derive(*login())
    r=requests.get(PUBLIC_URL+lock['manifest'],timeout=60);r.raise_for_status()
    manifest=json.loads(unseal(r.content,'manifest',key))
    for path in ['/api/catalog','/api/spectra','/api/cross-links']:
        entry=manifest['resources'][path]
        r=requests.get(PUBLIC_URL+entry['file'],timeout=60);r.raise_for_status()
        value=json.loads(unseal(r.content,path,key))
        if path!='/api/cross-links' and not value.get('objects'):
            raise RuntimeError('Empty published catalogue')
    save(LOCAL/'github-publication.json',{'published_at':now(),**expected,'resources':len(manifest['resources'])})
    print('Live GitHub Pages publication verified: '+PUBLIC_URL,flush=True)
    return True


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--create',action='store_true');p.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.verify:
        raise SystemExit(0 if verify_live() else 2)
    publish(create=a.create)
