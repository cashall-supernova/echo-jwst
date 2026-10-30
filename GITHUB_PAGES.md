# ECHO · JWST Supernova Archive

ECHO displays archival JWST images, colour previews and extracted spectra at supernova positions. The GitHub Pages edition keeps the same image and spectrum tools while serving encrypted static files. Its team login unlocks those files locally in the browser; the password is never sent to GitHub.

## Build

Use Node 22.13 or newer and Python 3.11 or newer:

```
npm ci
npm run build:github
python -m venv .venv
.venv/bin/pip install -r pipeline/requirements.txt
.venv/bin/python pipeline/export_github.py
```

The frontend is built from `static/`, using the existing `app/` components. `vite.github.config.ts` uses `/echo-jwst/` by default; set `ECHO_PAGES_BASE` when using a different repository path. Images and spectra have separate `index.html` entry points, so direct SN links work without server routing.

Export requires a complete local archive cache and a private team access configuration. This installation reuses the existing HISS `[access]` username and password in its private local configuration. Credentials are not part of this repository. A fresh installation must provision its own access file and update the local configuration paths before running the updater.

`pipeline/hydrate_github.py` is the one-time migration helper for the legacy Sites-hosted archive; it imports missing assets with existing local Keychain authorization. Routine GitHub updates do not use Sites or its credentials.

## Data and access

`docs/` contains the deployed static website. Catalogues, SN associations, PNG stamps, calibrated FITS cutouts and spectrum JSON are gzip-compressed and encrypted with AES-256-GCM. A PBKDF2-SHA256 key is derived from the team username and password with 600,000 iterations. Each encrypted payload is bound to its resource path, and unchanged payloads keep stable content-addressed filenames. Decrypted images use temporary browser blob URLs; FITS downloads reproduce the original bytes.

GitHub serves the encrypted files publicly. This is client-side encryption, not server-side account access: it has no server login throttling, per-person permissions or remote session revocation. The derived key is kept only in the browser tab's session storage for up to 12 hours; sign-out clears it. Previously downloaded data cannot be revoked, and an old password can still unlock old encrypted Git history. Choose a strong, unique team password and use a fresh encryption generation when changing access policy. API keys, publishing tokens and the team password must never be committed.

Public output is validated with an explicit file allowlist. Every exported resource is decrypted and byte-checked before publication. Builds fail if any ready asset is missing or the site exceeds a conservative 950 MB size budget. Source data remain in the local cache; an unsuccessful build never replaces the live Pages deployment. GitHub Pages has a 1 GB published-site limit, so growing archives may eventually need a different storage layout.

## Local updates

```
.venv/bin/python pipeline/run_github_mac.py --check
/usr/bin/caffeinate -i .venv/bin/python pipeline/run_github_mac.py --publish
```

The updater downloads the daily TNS catalogue using locally stored bot access, checks public and restricted MAST metadata, generates/reuses image cutouts and colour previews, updates the all-redshift spectral catalogue, and refreshes HISS cross-links. Restricted images remain metadata-only until MAST confirms public access. It then encrypts the completed archive and publishes the generated site to `main:/docs`. Publication requires a local GitHub credential with access to the repository and Pages configuration; it is never uploaded to the site.

The Mac schedule is installed separately after a verified publication and confirmation that the obsolete cloud task is paused. The website remains available when the Mac is asleep; new data wait for its next successful run. Inspect `local/github-status.json`, `local/github-publication.json` and `local/logs/` for local operation status. These files are ignored by Git.

The HISS reciprocal links should use the public ECHO origin `https://cashall-supernova.github.io/echo-jwst/`. Individual destinations are `#SN2023ixf` for imaging and `spectra/#SN2023ixf` for spectra. HISS includes its matched links in its encrypted index on subsequent builds.

## Scientific scope

The image catalogue selects reported z < 0.02. The spectra catalogue searches all redshifts and opens with the same nearby filter. TNS is supplemented by historical OSC and SIMBAD records. Missing redshifts, unclassified objects and incomplete historical catalogues limit the sample; archive footprint coverage is not a confirmed SN detection.

Colour previews currently require three usable filters from the same UTC day, instrument and program; MIRI and NIRCam remain separate. Multi-day mosaics are deliberately excluded. Display contrast, spectral binning, smoothing, epoch offsets and line markers change the visualisation, not the original downloaded measurements. No forced photometry or independent star-based registration is performed.
