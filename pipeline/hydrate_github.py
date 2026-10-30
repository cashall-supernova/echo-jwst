"""One-time import from the existing authenticated ECHO publication."""
import concurrent.futures
import json
from pathlib import Path
from export_github import files_for, validate_catalogs
from run_mac import PROJECT, inspect_site, service_access, save
from site_access import site_headers
from update import http


def main():
    access = service_access()
    catalogs = inspect_site(access)
    validate_catalogs(catalogs)
    cache = PROJECT / 'local/cache'
    files = files_for(catalogs, cache)
    def retrieve(item):
        path, (file, mime) = item
        if file.is_file():
            return False
        response = http('GET', access['site'] + path,
                        headers=site_headers(access['token'], access['updater_token']))
        raw = response.content
        if mime == 'image/png' and not raw.startswith(b'\x89PNG'):
            raise ValueError('Invalid image response')
        if mime == 'application/fits' and not raw.startswith(b'SIMPLE'):
            raise ValueError('Invalid FITS response')
        if mime == 'application/json':
            json.loads(raw)
        file.parent.mkdir(parents=True, exist_ok=True)
        temp = file.with_suffix(file.suffix + '.tmp')
        temp.write_bytes(raw)
        temp.replace(file)
        return True
    missing = [(path, info) for path, info in files.items() if not info[0].is_file()]
    print(f'Importing {len(missing)} missing assets from the existing publication.', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i, _ in enumerate(pool.map(retrieve, missing), 1):
            if i % 50 == 0 or i == len(missing):
                print(f'Imported {i}/{len(missing)}.', flush=True)
    save(cache / 'snapshot.json', catalogs['catalog'])
    save(cache / 'spectra/snapshot.json', catalogs['spectra'])
    print('Migration cache complete; original site unchanged.', flush=True)


if __name__ == '__main__':
    main()
