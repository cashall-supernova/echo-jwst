"""Disposable publishing work stays outside the synced scientific project."""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile


def workspace_root():
    configured = os.environ.get('ECHO_GITHUB_WORK_DIR')
    if configured:
        root = Path(configured).expanduser()
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library/Caches/edu.hawaii.echo'
    else:
        root = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'echo'
    root = root.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


@contextmanager
def fresh_build():
    # Never clear/reuse a folder that a sync service may have duplicated or locked.
    with tempfile.TemporaryDirectory(prefix='build-', dir=workspace_root()) as folder:
        yield Path(folder)
