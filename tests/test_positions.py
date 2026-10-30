import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from astropy.io import fits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from positions import apply_refinements, fits_provenance

class Positions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'positions.json'
        self.row={'name':'SNtest','ra':10.,'dec':20.,'provenance':{'catalogue':'TNS'}}
        self.record={'status':'reviewed','reviewedAt':'2026-10-30','ra':10.00005,'dec':20.00006,
                     'catalogue':{'source':'TNS','ra':10.,'dec':20.},'references':[{'label':'Optical measurement','url':'https://example.org/measurement'}]}
        self.write(self.record)
    def tearDown(self):self.tmp.cleanup()
    def write(self,record):self.path.write_text(json.dumps({'version':1,'objects':{'SNtest':record}}))
    def test_reviewed_position_preserves_origin_and_is_idempotent(self):
        rows=[copy.deepcopy(self.row)];apply_refinements(rows,self.path)
        self.assertEqual(rows[0]['ra'],self.record['ra'])
        self.assertEqual(rows[0]['astrometry']['catalogue']['ra'],10.)
        self.assertGreater(rows[0]['astrometry']['offsetArcsec'],.2)
        first=copy.deepcopy(rows);apply_refinements(rows,self.path);self.assertEqual(rows,first)
        h=fits.Header();fits_provenance(h,rows[0]);self.assertEqual(h['CATRA'],10.)
        self.assertIn('optical',h['SNPSRC'])
    def test_changed_tns_coordinate_suspends_refinement(self):
        self.row['dec']+=.0001
        apply_refinements([self.row],self.path)
        self.assertEqual(self.row['dec'],20.0001)
        self.assertEqual(self.row['astrometry']['status'],'needs-review')
    def test_removal_reverts_to_catalogue(self):
        apply_refinements([self.row],self.path);self.path.unlink();apply_refinements([self.row],self.path)
        self.assertEqual(self.row['ra'],10.);self.assertNotIn('astrometry',self.row)
    def test_unreviewed_or_large_shift_rejected(self):
        self.record['status']='candidate';self.write(self.record)
        with self.assertRaises(ValueError):apply_refinements([self.row],self.path)
        self.record['status']='reviewed';self.record['dec']+=1;self.write(self.record)
        with self.assertRaises(ValueError):apply_refinements([self.row],self.path)
    def test_other_objects_unchanged(self):
        self.row['name']='SNother';before=copy.deepcopy(self.row)
        apply_refinements([self.row],self.path);self.assertEqual(self.row,before)

if __name__=='__main__':unittest.main()
