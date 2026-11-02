import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from github_workspace import fresh_build, workspace_root
from publish_github import prepare_checkout


class GithubWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'ECHO_GITHUB_WORK_DIR': str(self.root / 'publishing')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_fresh_build_recovers_after_failure_without_touching_old_output(self):
        old = workspace_root() / 'github-site'
        old.mkdir()
        (old / 'data 2').write_text('preserve sync-conflict evidence')
        with self.assertRaisesRegex(RuntimeError, 'simulated build failure'):
            with fresh_build() as first:
                (first / 'partial-output').write_text('unfinished')
                raise RuntimeError('simulated build failure')
        self.assertFalse(first.exists())
        with fresh_build() as second:
            self.assertNotEqual(first, second)
            self.assertEqual(list(second.iterdir()), [])
        self.assertEqual((old / 'data 2').read_text(), 'preserve sync-conflict evidence')

    def make_remote(self):
        remote = self.root / 'remote.git'
        seed = self.root / 'seed'
        self.git(self.root, 'init', '--bare', str(remote))
        self.git(self.root, 'init', '-b', 'main', str(seed))
        (seed / 'index.html').write_text('published version')
        self.git(seed, 'add', 'index.html')
        self.git(seed, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '-m', 'Seed')
        self.git(seed, 'remote', 'add', 'origin', str(remote))
        self.git(seed, 'push', 'origin', 'main')
        return str(remote)

    @staticmethod
    def git(cwd, *args):
        return subprocess.run(['git', '-C', str(cwd), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_dirty_publication_is_preserved_and_next_run_recovers(self):
        remote = self.make_remote()
        checkout = workspace_root() / 'github-publication'
        prepare_checkout(checkout, remote)
        (checkout / 'index.html').write_text('interrupted tracked edit')
        (checkout / 'index 2.html').write_text('duplicate generated file')
        prepare_checkout(checkout, remote)
        self.assertEqual((checkout / 'index.html').read_text(), 'published version')
        self.assertEqual(self.git(checkout, 'status', '--porcelain'), '')
        backups = list(workspace_root().glob('github-publication-recovery-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'index.html').read_text(), 'interrupted tracked edit')
        self.assertEqual((backups[0] / 'index 2.html').read_text(), 'duplicate generated file')
        prepare_checkout(checkout, remote)
        self.assertEqual(len(list(workspace_root().glob('github-publication-recovery-*'))), 1)

    def test_unexpected_remote_is_not_replaced(self):
        remote = self.make_remote()
        checkout = workspace_root() / 'github-publication'
        prepare_checkout(checkout, remote)
        (checkout / 'index 2.html').write_text('preserve')
        with self.assertRaisesRegex(RuntimeError, 'Unexpected publication remote'):
            prepare_checkout(checkout, 'https://example.invalid/wrong/repo')
        self.assertTrue((checkout / 'index 2.html').exists())
        self.assertFalse(list(workspace_root().glob('github-publication-recovery-*')))


if __name__ == '__main__':
    unittest.main()
