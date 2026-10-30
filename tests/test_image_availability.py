import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from image_availability import enrich

class ImageAvailability(unittest.TestCase):
    def test_only_confirmed_public_rows_supply_release_dates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            rows=[{'obs_id':str(i),'dataURL':str(i),'dataRights':rights,'t_obs_release':date}
                  for i,rights,date in [(1,'PUBLIC',61342),(2,'EXCLUSIVE_ACCESS',61342),(3,'PUBLIC',90000)]]
            for file in ('all-jwst-mast.json','all-cal2-mast.json'):(root/file).write_text(json.dumps(rows))
            sn={'name':'SN2008S','observations':[{'id':str(i),'obsId':str(i),'uri':str(i)} for i in (1,2,3)]}
            snapshot={'updatedAt':'2026-10-30T18:00:00Z','objects':[sn]}
            previous=copy.deepcopy(snapshot)
            with patch('image_availability.validate',side_effect=lambda p:p):enrich(snapshot,previous,root)
            self.assertEqual(sn['observations'][0]['publicReleaseMjd'],61342)
            self.assertIsNone(sn['observations'][1]['publicReleaseMjd'])
            self.assertIsNone(sn['observations'][2]['publicReleaseMjd'])
            self.assertTrue(all(o['firstIndexedAt'] is None for o in sn['observations']))
            with patch('image_availability.validate',side_effect=lambda p:p):enrich(snapshot,None,root)
            self.assertTrue(all(o['firstIndexedAt']==snapshot['updatedAt'] for o in sn['observations']))

if __name__=='__main__':unittest.main()
