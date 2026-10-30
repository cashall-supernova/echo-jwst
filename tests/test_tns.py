import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from merge_tns import merge, read_snapshot


def record(name='2025aico', **kwargs):
    return {'name': name, 'name_prefix': 'SN', 'ra': '172.3181846', 'declination': '20.585629',
            'redshift': '0.00455', 'type': 'SN IIb', 'internal_names': 'GOTO25mmu, , ZTF25ackyfnb', **kwargs}


def historical(name, aliases=()):
    return {'name': name, 'aliases': list(aliases), 'ra': 172.318, 'dec': 20.5856,
            'redshift': 0.0046, 'types': ['Candidate'], 'hosts': ['Existing host'], 'references': []}


class TnsTests(unittest.TestCase):
    def test_missing_recent_sn_and_alias_upgrade(self):
        rows, audit, _ = merge([historical('AT2025aico')], [record()], '2026-10-29T00:00:00Z')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'SN2025aico')
        self.assertEqual(rows[0]['types'], ['IIb'])
        self.assertEqual(rows[0]['ra'], 172.3181846)
        self.assertEqual(audit['representedSn'], 1)
        self.assertIn('ZTF25ackyfnb', rows[0]['aliases'])
        self.assertEqual(rows[0]['hosts'], ['Existing host'])

    def test_strict_boundary_unknown_and_negative_redshifts(self):
        inputs = [record('2026a', redshift='0.02'), record('2026b', redshift=''),
                  record('2026c', redshift='NaN'), record('2026d', redshift='-0.001'),
                  record('2026e', name_prefix='AT')]
        rows, audit, _ = merge([historical('SN2026a')], inputs, '2026-10-29T00:00:00Z')
        self.assertEqual([r['name'] for r in rows], ['SN2026d'])
        self.assertEqual(audit['unknownRedshift'], 2)
        self.assertEqual(audit['removedByTnsRedshift'], 1)

    def test_survey_alias_deduplicates_and_other_historical_survives(self):
        rows, audit, _ = merge([historical('SN1987A'), historical('AT2025aico'), historical('ZTF25ackyfnb')], [record()], '2026-10-29T00:00:00Z')
        self.assertEqual({r['name'] for r in rows}, {'SN1987A', 'SN2025aico'})
        self.assertEqual(audit['mergedHistoricalDuplicates'], 1)

    def test_stale_feed_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tns.csv'
            path.write_text('2026-10-20 00:00:00\nname,name_prefix,ra,declination,redshift,type\na,SN,1,1,.01,SN\n')
            with self.assertRaisesRegex(ValueError, 'stale'):
                read_snapshot(path, datetime(2026, 10, 29, tzinfo=timezone.utc))

    def test_reused_survey_alias_does_not_erase_iau_designation(self):
        rows, audit, _ = merge([], [record('2019lqo', internal_names='ZTF19abgbbzy'), record('2024gzk', internal_names='ZTF19abgbbzy')], '2026-10-29T00:00:00Z')
        self.assertEqual({r['name'] for r in rows}, {'SN2019lqo', 'SN2024gzk'})
        self.assertEqual(audit['ambiguousSurveyAliases'], 1)


if __name__ == '__main__':
    unittest.main()
