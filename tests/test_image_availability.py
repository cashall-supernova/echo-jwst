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
            # Recentring makes new cutout IDs, but must not announce an old image as new.
            previous=copy.deepcopy(snapshot)
            snapshot['updatedAt']='2026-10-31T18:00:00Z'
            for image in sn['observations']:image['id']='recentered-'+image['id']
            with patch('image_availability.validate',side_effect=lambda p:p):enrich(snapshot,previous,root)
            self.assertTrue(all(o['firstIndexedAt']==previous['updatedAt'] for o in sn['observations']))

    def test_new_sn_arrival_is_stable_and_legacy_dates_stay_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for file in ('all-jwst-mast.json','all-cal2-mast.json'):(root/file).write_text('[]')
            previous={'objects':[{'name':'SN2008S','observations':[]}]}
            snapshot={'updatedAt':'2026-11-04T16:00:00Z','objects':[
                {'name':'SN2008S','observations':[]},
                {'name':'AT2026ahvu','observations':[{'id':'original','uri':'same-image','obsId':'one'}]}]}
            with patch('image_availability.validate',side_effect=lambda p:p):enrich(snapshot,previous,root)
            self.assertIsNone(snapshot['objects'][0]['firstIndexedAt'])
            self.assertEqual(snapshot['objects'][1]['firstIndexedAt'],snapshot['updatedAt'])
            previous=copy.deepcopy(snapshot)
            snapshot['updatedAt']='2026-11-05T16:00:00Z'
            sn=snapshot['objects'][1];sn['name']='SN2026ahvu'
            sn['observations'][0]['id']='new-centre'
            sn['observations'].append({'id':'new-image','uri':'another-image','obsId':'two'})
            with patch('image_availability.validate',side_effect=lambda p:p):enrich(snapshot,previous,root)
            self.assertEqual(sn['firstIndexedAt'],previous['updatedAt'])
            self.assertEqual(sn['observations'][0]['firstIndexedAt'],previous['updatedAt'])
            self.assertEqual(sn['observations'][1]['firstIndexedAt'],snapshot['updatedAt'])
            self.assertIsNone(snapshot['objects'][0]['firstIndexedAt'])

if __name__=='__main__':unittest.main()
