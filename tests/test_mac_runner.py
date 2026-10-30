import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import run_mac
import install_mac_schedule


class MacRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'spectra').mkdir()
        self.data = {'catalog': {'updatedAt': '2026-10-30T16:00:00Z', 'scanComplete': True,
                                'catalogueAudit': {'eligibleSn': 10, 'representedSn': 10}},
                     'spectra': {'updatedAt': '2026-10-30T16:01:00Z'}}
        for key, path in [('catalog', 'snapshot.json'), ('spectra', 'spectra/snapshot.json')]:
            (self.root / path).write_text(json.dumps(self.data[key]))

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_publication_required(self):
        run_mac.verify_local_publication(self.data, self.root)
        self.data['spectra']['updatedAt'] = '2026-10-29T16:01:00Z'
        with self.assertRaisesRegex(RuntimeError, 'spectra does not match'):
            run_mac.verify_local_publication(self.data, self.root)

    def test_missing_tns_rows_fail_validation(self):
        self.data['catalog']['catalogueAudit']['representedSn'] = 9
        with self.assertRaisesRegex(RuntimeError, 'completeness'):
            run_mac.verify_local_publication(self.data, self.root)

    def test_schedule_requires_both_verified_run_and_cloud_pause(self):
        with patch.object(install_mac_schedule, 'LOCAL', self.root):
            with self.assertRaisesRegex(RuntimeError, 'Mac publication'):
                install_mac_schedule.main()
            (self.root / 'publication.json').write_text('{"published_at":"2026-10-30"}')
            with self.assertRaisesRegex(RuntimeError, 'cloud task is paused'):
                install_mac_schedule.main()

    def test_schedule_uses_persistent_runtime_and_no_secret_arguments(self):
        definition = install_mac_schedule.definition()
        self.assertEqual(definition['StartCalendarInterval'], {'Hour': 6, 'Minute': 0})
        self.assertIn('--scheduled', definition['ProgramArguments'])
        self.assertIn(str(run_mac.PROJECT / '.venv/bin/python'), definition['ProgramArguments'])
        self.assertFalse(definition['RunAtLoad'])
        self.assertNotIn('token', json.dumps(definition))


if __name__ == '__main__':
    unittest.main()
