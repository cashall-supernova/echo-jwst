import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from geometry import unit,contains
class Footprints(unittest.TestCase):
 def test_ra_wrap(self):
  points=unit([0,359.9,180],[0,0,0])
  self.assertEqual(contains('POLYGON 359 -1 1 -1 1 1 359 1',points).tolist(),[0,1])
 def test_polar(self):
  self.assertEqual(contains('POLYGON 0 88 120 88 240 88',unit([0,0],[90,80])).tolist(),[0])
 def test_union(self):
  region='POLYGON 9 -1 11 -1 11 1 9 1 POLYGON 19 -1 21 -1 21 1 19 1'
  self.assertEqual(contains(region,unit([10,15,20],[0,0,0])).tolist(),[0,2])
 def test_circle(self):
  self.assertEqual(contains('CIRCLE ICRS 0 0 1',unit([0,.5,2],[0,0,0])).tolist(),[0,1])
 def test_invalid_not_silent(self):
  with self.assertRaises(ValueError):contains('POLYGON nan 0 1 1 0 1',unit([0],[0]))
if __name__=='__main__':unittest.main()
