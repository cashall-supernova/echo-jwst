import sys,tempfile,unittest
from pathlib import Path
import numpy as np
from astropy.io import fits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from spectra import parse_spectrum,source_association,validate_observations,region_candidates
from geometry import unit
from scipy.spatial import cKDTree
class SpectraTests(unittest.TestCase):
 def setUp(self):self.sn={'name':'SNtest','ra':10.,'dec':20.};self.obs={'instrument_name':'NIRSPEC/SLIT','nameMatched':True,'target_name':'SNtest'}
 def test_other_slit_is_not_sn_even_when_primary_target_matches(self):
  a=source_association({'SLIT_RA':10.01,'SLIT_DEC':20.},{'TARG_RA':10.,'TARG_DEC':20.},self.sn,True,'NRS_FIXEDSLIT')
  self.assertIsNone(a[0]);self.assertGreater(a[1],1)
 def test_mos_pointing_is_not_source_coordinate(self):
  self.assertIsNone(source_association({}, {'TARG_RA':10.,'TARG_DEC':20.},self.sn,True,'NRS_MSASPEC')[0])
 def test_unknown_redshift_is_not_needed_for_association(self):
  self.assertEqual(source_association({'SOURCE_RA':10.,'SOURCE_DEC':20.},{},{**self.sn,'z':None},False,'NRC_WFSS')[0],'source-position')
 def test_gap_dq_units_and_negative_flux_are_retained(self):
  with tempfile.TemporaryDirectory() as d:
   cols=[fits.Column(name='WAVELENGTH',format='D',unit='nm',array=[1000,1100,1200,1300]),fits.Column(name='FLUX',format='D',unit='mJy',array=[1.,np.nan,-.2,3.]),fits.Column(name='FLUX_ERROR',format='D',unit='mJy',array=[.1,.1,.1,.2]),fits.Column(name='DQ',format='J',array=[0,1,0,2])]
   h=fits.BinTableHDU.from_columns(cols,name='EXTRACT1D');h.header['SLIT_RA']=10.;h.header['SLIT_DEC']=20.
   p=Path(d)/'s.fits';fits.HDUList([fits.PrimaryHDU(),h]).writeto(p)
   s=parse_spectrum(p,self.sn,self.obs)['segments'][0]['points'];self.assertEqual(len(s),4);self.assertEqual(s[0][0],1.);self.assertAlmostEqual(s[0][1],.001);self.assertIsNone(s[1][1]);self.assertEqual(s[1][3],1);self.assertLess(s[2][1],0);self.assertEqual(s[3][3],2)
 def test_vector_sources_filtered_individually(self):
  with tempfile.TemporaryDirectory() as d:
   cols=[fits.Column(name='WAVELENGTH',format='3D',unit='um',array=[[1,2,3],[1,2,3]]),fits.Column(name='FLUX',format='3D',unit='Jy',array=[[1,2,3],[4,5,6]]),fits.Column(name='SOURCE_RA',format='D',array=[10,11]),fits.Column(name='SOURCE_DEC',format='D',array=[20,20])]
   h=fits.BinTableHDU.from_columns(cols,name='EXTRACT1D');primary=fits.PrimaryHDU();primary.header['EXP_TYPE']='NRC_WFSS';p=Path(d)/'s.fits';fits.HDUList([primary,h]).writeto(p)
   s=parse_spectrum(p,self.sn,self.obs);self.assertEqual(len(s['segments']),1);self.assertEqual(s['skippedExtractions'],1)
 def test_duplicates_allowed_only_when_identical_and_complete(self):
  row={'obsid':1,'dataproduct_type':'spectrum','dataURL':'uri','dataRights':'PUBLIC'}
  data={'status':'COMPLETE','paging':{'rowsFiltered':2,'pagesFiltered':1},'data':[row,dict(row)]};self.assertEqual(len(validate_observations(data,'PUBLIC')),1)
  data['data'][1]['extra']='conflict'
  with self.assertRaises(RuntimeError):validate_observations(data,'PUBLIC')
  data['paging']['rowsFiltered']=3
  with self.assertRaises(RuntimeError):validate_observations(data,'PUBLIC')
 def test_spatial_index_preserves_ra_wrap(self):
  points=unit([359.999,0.001,180],[0,0,0]);tree=cKDTree(points)
  self.assertEqual(set(region_candidates('CIRCLE 0 0 0.01',tree,points)),{0,1})
if __name__=='__main__':unittest.main()
