"""The remote-read optimization must preserve Astropy pixels and WCS."""
import io
import sys
import unittest
from pathlib import Path

import numpy as np
import astropy.units as u
from astropy.io import fits
from astropy.nddata import Cutout2D
from astropy.wcs import WCS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from update import read_window, science_cutout


class Cutouts(unittest.TestCase):
    def test_pixels_and_wcs_at_center_and_edges(self):
        rng = np.random.default_rng(42)
        pixels = rng.normal(size=(80, 100)).astype(np.float32)
        pixels[40, 50] = np.nan
        wcs = WCS(naxis=2)
        wcs.wcs.crpix = [50, 40]
        wcs.wcs.cd = np.array([[-0.7, 0.2], [0.2, 0.7]]) / 3600
        wcs.wcs.crval = [359.999, -30]
        wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
        stream = io.BytesIO()
        fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(pixels, name='SCI')]).writeto(stream)
        stream.seek(0)
        with fits.open(stream) as hdul:
            for width in [10,15]:
                for x, y in [(50, 40), (1, 1), (98, 78), (-2, 40)]:
                    with self.subTest(x=x, y=y,width=width):
                        pos = wcs.pixel_to_world(x, y)
                        expected = Cutout2D(pixels, pos, (width*u.arcsec, width*u.arcsec), wcs=wcs, mode='partial', fill_value=np.nan)
                        cut, actual = science_cutout(hdul['SCI'], wcs, pos,width)
                        np.testing.assert_array_equal(actual, expected.data)
                        self.assertEqual(cut.wcs.to_header_string(), expected.wcs.to_header_string())

    def test_quality_bit_values_are_preserved(self):
        dq = np.arange(80*100, dtype=np.uint32).reshape(80, 100)
        stream = io.BytesIO()
        fits.PrimaryHDU(dq).writeto(stream)
        stream.seek(0)
        with fits.open(stream) as hdul:
            selection = (slice(11, 31), slice(7, 24))
            np.testing.assert_array_equal(read_window(hdul[0], selection), dq[selection])


if __name__ == '__main__':
    unittest.main()
