import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from color_images import groups, wavelength, reproject_bilinear, make_composite, add_composites


def product(band, index, **extra):
    return dict(id=f'{index:024x}',filter=band,start=60000.1+index*.01,
                end=60000.11+index*.01,status='ready',instrument='MIRI/IMAGE',
                proposal='1234',uri=f'mast:JWST/product/test{index}_i2d.fits',
                coverage=1,validatedUnix=100,**extra)


class ColorImages(unittest.TestCase):
    def test_epoch_instrument_program_and_filter_boundaries(self):
        rows=[product(b,i) for i,b in enumerate(['F770W','F1130W','F1800W'])]
        self.assertEqual([o['filter'] for o in groups(rows)[0][1]],['F1800W','F1130W','F770W'])
        self.assertEqual(wavelength('F444W;F405N'),4.05)
        for field,value in [('end',60001.01),('proposal','5678'),('instrument','NIRCAM/IMAGE'),('status','outside'),('filter','F770W')]:
            changed=copy.deepcopy(rows);changed[2][field]=value
            self.assertEqual(groups(changed),[],(field,value))
        duplicate=copy.deepcopy(rows[0]);duplicate['id']='f'*24;duplicate['uri']='mast:JWST/product/test_cal.fits'
        self.assertEqual(len(groups(rows+[duplicate])[0][1]),3)
        self.assertNotIn(duplicate,groups(rows+[duplicate])[0][1])

    def test_reprojection_alignment_surface_brightness_and_invalid_mask(self):
        target=WCS(naxis=2);target.wcs.crpix=[51,51];target.wcs.crval=[359.999,25]
        target.wcs.cdelt=[-.1/3600,.1/3600];target.wcs.ctype=['RA---TAN','DEC--TAN']
        source=target.deepcopy();theta=np.deg2rad(29)
        source.wcs.pc=[[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]]
        source.wcs.crpix=[47.3,55.8]
        y,x=np.indices((101,101));sx,sy=source.world_to_pixel_values(359.999,25)
        data=np.exp(-((x-sx)**2+(y-sy)**2)/8).astype(np.float32)
        out=reproject_bilinear(data,source,target,(101,101))
        self.assertEqual(np.unravel_index(np.nanargmax(out),out.shape),(50,50))
        flat=reproject_bilinear(np.full((101,101),17.5),source,target,(101,101))
        np.testing.assert_allclose(flat[np.isfinite(flat)],17.5)
        data[54:58,45:49]=np.nan
        self.assertTrue(np.isnan(reproject_bilinear(data,source,target,(101,101))[50,50]))

    def test_narrow_shared_coverage_uses_labelled_smaller_field(self):
        rows=[product(b,i,widthArcsec=15) for i,b in enumerate(['F770W','F1130W','F1800W'])]
        sn={'name':'SNtest','ra':20.,'dec':30.,'observations':rows}
        with tempfile.TemporaryDirectory() as temp:
            cache=Path(temp)/'stamps';cache.mkdir()
            w=WCS(naxis=2);w.wcs.crpix=[76,76];w.wcs.crval=[20,30]
            w.wcs.cdelt=[-.1/3600,.1/3600];w.wcs.ctype=['RA---TAN','DEC--TAN']
            for o in rows:
                h=w.to_header();h['BUNIT']='MJy/sr'
                data=np.full((151,151),np.nan,dtype=np.float32);data[35:116,35:116]=1
                fits.PrimaryHDU(data,h).writeto(cache/(o['id']+'.fits'),checksum=True)
            snapshot={'objects':[sn]};add_composites(snapshot,None,temp)
            self.assertEqual(sn['colorIssues'],[])
            self.assertEqual(sn['colorComposites'][0]['widthArcsec'],10)
            self.assertIn('limited shared coverage',sn['colorComposites'][0]['fieldNote'])
            self.assertTrue(all(o['widthArcsec']==15 for o in rows))

    def test_cube_provenance_and_cold_cache_reuse(self):
        rows=[product(b,i) for i,b in enumerate(['F770W','F1130W','F1800W'])]
        sn={'name':'SNtest','ra':20.,'dec':30.,'observations':rows}
        with tempfile.TemporaryDirectory() as temp:
            cache=Path(temp)/'stamps';cache.mkdir()
            w=WCS(naxis=2);w.wcs.crpix=[51,51];w.wcs.crval=[20,30]
            w.wcs.cdelt=[-.1/3600,.1/3600];w.wcs.ctype=['RA---TAN','DEC--TAN']
            before=[]
            for i,o in enumerate(rows):
                h=w.to_header();h['BUNIT']='MJy/sr'
                fits.PrimaryHDU((np.arange(10201).reshape(101,101)*(i+1)).astype(np.float32),h).writeto(cache/(o['id']+'.fits'),checksum=True)
                before.append((cache/(o['id']+'.fits')).read_bytes())
            key,selected=groups(rows)[0];result=make_composite(sn,key,selected,cache)
            with fits.open(cache/(result['id']+'.fits'),checksum=True) as hdul:
                self.assertEqual(hdul[0].verify_checksum(),1)
                self.assertEqual(hdul[0].data.shape[0],3)
                self.assertEqual(hdul[0].header['FILTER1'],'F1800W')
                self.assertEqual(hdul[0].header['RGBORDER'],'RED,GREEN,BLUE')
            self.assertEqual(before,[(cache/(o['id']+'.fits')).read_bytes() for o in rows])
            old={'objects':[{**sn,'colorComposites':[result]}]};new={'objects':[copy.deepcopy(sn)]}
            add_composites(new,old,Path(temp)/'cold',lambda o:self.fail('Unchanged source was downloaded'))
            self.assertEqual(new['objects'][0]['colorComposites'],[result])


if __name__=='__main__':unittest.main()
