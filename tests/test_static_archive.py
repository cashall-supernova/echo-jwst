import json
from pathlib import Path
import sys
import unittest
from cryptography.exceptions import InvalidTag
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from export_github import derive, seal, unseal, files_for


class StaticArchiveTests(unittest.TestCase):
    def test_encryption_and_content_stability(self):
        _, key = derive('team', 'test-only-password')
        payload = b'SIMPLE FITS bytes\0' * 100
        encrypted = seal(payload, '/api/stamps/example.fits', key)
        self.assertNotIn(payload[:30], encrypted)
        self.assertEqual(unseal(encrypted, '/api/stamps/example.fits', key), payload)
        self.assertEqual(encrypted, seal(payload, '/api/stamps/example.fits', key))
        self.assertNotEqual(encrypted[4:16], seal(payload+b'changed', '/api/stamps/example.fits', key)[4:16])
        _, wrong = derive('team', 'wrong-password')
        with self.assertRaises(InvalidTag):
            unseal(encrypted, '/api/stamps/example.fits', wrong)
        with self.assertRaises(InvalidTag):
            unseal(encrypted, '/api/stamps/different.fits', key)
        with self.assertRaises(InvalidTag):
            unseal(encrypted[:-1]+bytes([encrypted[-1]^1]), '/api/stamps/example.fits', key)

    def test_export_includes_ready_images_colours_and_spectra_only(self):
        catalogs = {'catalog': {'objects': [{'observations': [{'id':'a'*24,'status':'ready'},
                    {'id':'b'*24,'status':'pending'}], 'colorComposites':[{'id':'c'*24,'status':'ready'}]}]},
                    'spectra': {'objects':[{'spectra':[{'id':'d'*24,'status':'ready'}, {'id':'e'*24,'status':'error'}]}]}}
        files = files_for(catalogs,Path('/cache'))
        self.assertEqual(len(files),5)
        self.assertIn('/api/stamps/'+'c'*24+'.fits',files)
        self.assertIn('/api/spectra/'+'d'*24,files)
        self.assertNotIn('/api/stamps/'+'b'*24+'.fits',files)


if __name__ == '__main__':
    unittest.main()
