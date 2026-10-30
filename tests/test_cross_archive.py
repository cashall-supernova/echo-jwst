import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from cross_archive import availability, designation, match_links


class CrossArchiveTests(unittest.TestCase):
    def test_names_and_no_abbreviated_year_guess(self):
        self.assertEqual(designation('SN 2023ixf'), '2023ixf')
        self.assertEqual(designation('AT2023ixf'), '2023ixf')
        self.assertEqual(designation('SN1987A'), '1987a')
        self.assertIsNone(designation('23ixf'))
        self.assertIsNone(designation('NGC 2023'))

    def test_only_available_data_and_alias_destination(self):
        images = {'objects': [{'name': 'SN2023ixf', 'observations': [{'status': 'ready'}]},
                              {'name': 'SN2023aaa', 'observations': [{'status': 'pending'}]}]}
        spectra = {'objects': [{'name': 'SN2023ixf', 'spectra': [{'status': 'ready'}]},
                               {'name': 'ZTF-example', 'aliases': ['SN2023bbb'], 'spectra': [{'status': 'ready'}]}]}
        hiss = [{'id': name, 'category': 'transient', 'n': n, 'has_lc': lc}
                for name, n, lc in [('2023ixf', 7, True), ('2023aaa', 1, False),
                                    ('2023bbb', 0, True), ('2023ccc', 0, False)]]
        self.assertEqual(match_links(hiss, availability(images, spectra)), [
            {'hissId': '2023ixf', 'imagesName': 'SN2023ixf', 'spectraName': 'SN2023ixf'},
            {'hissId': '2023bbb', 'spectraName': 'ZTF-example'}])

    def test_ambiguous_and_no_hiss_data(self):
        available = [{'keys': ['2023ixf'], 'imagesName': name} for name in ('first', 'second')]
        hiss = [{'id': '2023ixf', 'category': 'transient', 'n': 7}]
        self.assertEqual(match_links(hiss, available), [])
        self.assertEqual(match_links(hiss * 2, available[:1]), [])
        self.assertEqual(match_links([dict(hiss[0], n=0)], available[:1]), [])


if __name__ == '__main__':
    unittest.main()
