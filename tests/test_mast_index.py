import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from mast_index import validate


class MastIndexTests(unittest.TestCase):
    def test_complete_result(self):
        result = {'status': 'COMPLETE', 'paging': {'rowsFiltered': 2, 'pagesFiltered': 1}, 'data': [{'obsid': 1}, {'obsid': 2}]}
        self.assertEqual(len(validate(result)), 2)

    def test_overlapping_pages_cannot_pass_row_count(self):
        result = {'status': 'COMPLETE', 'paging': {'rowsFiltered': 2, 'pagesFiltered': 1}, 'data': [{'obsid': 1}, {'obsid': 1}]}
        with self.assertRaisesRegex(RuntimeError, 'duplicate'):
            validate(result)

    def test_truncation_and_incomplete_results_rejected(self):
        for result in [
            {'status': 'COMPLETE', 'paging': {'rowsFiltered': 3, 'pagesFiltered': 2}, 'data': [{'obsid': 1}, {'obsid': 2}]},
            {'status': 'EXECUTING', 'paging': {'rowsFiltered': 1}, 'data': [{'obsid': 1}]},
            {'status': 'COMPLETE', 'paging': {}, 'data': [{'obsid': 1}]},
        ]:
            with self.assertRaises(RuntimeError):
                validate(result)
