import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from release_watch import reconcile
from mast_index import validate
from update import stamp


def row(**changes):
    return {**{'obsid':123,'obs_id':'jw123','instrument_name':'MIRI/IMAGE',
               'filters':'F770W','proposal_id':'7041','t_min':60000,'t_max':60000.1,
               't_obs_release':60001,'calib_level':3,'dataRights':'EXCLUSIVE_ACCESS',
               's_region':'CIRCLE ICRS 359.999 25 0.001'},**changes}


class ReleaseWatch(unittest.TestCase):
    def setUp(self):self.objects=[{'name':'SNtest','ra':359.999,'dec':25,'observations':[]}]

    def test_expected_date_never_unlocks_protected_data(self):
        result=reconcile(self.objects,[row()],[],[],'2026-10-29T00:00:00Z')
        self.assertEqual(result['matchedObjects'],1)
        self.assertEqual(self.objects[0]['releaseWatch'][0]['status'],'exclusive')
        self.assertEqual(self.objects[0]['observations'],[])
        with patch('update.fits.open') as read:
            with self.assertRaisesRegex(ValueError,'metadata-only'):
                stamp(self.objects[0],{'dataRights':'EXCLUSIVE_ACCESS'})
            read.assert_not_called()

    def test_public_transition_retains_discovery_and_history(self):
        reconcile(self.objects,[row()],[],[],'2026-10-29T00:00:00Z')
        previous=copy.deepcopy(self.objects)
        reconcile(self.objects,[],[row(dataRights='PUBLIC',t_obs_release=90000)],previous,'2026-10-30T00:00:00Z')
        r=self.objects[0]['releaseWatch'][0]
        self.assertEqual(r['status'],'public')
        self.assertEqual(r['firstSeen'],'2026-10-29T00:00:00Z')
        self.assertEqual(r['releasedAt'],'2026-10-30T00:00:00Z')

    def test_disappearing_record_is_retained_without_assuming_release(self):
        reconcile(self.objects,[row()],[],[],'2026-10-29T00:00:00Z')
        previous=copy.deepcopy(self.objects)
        reconcile(self.objects,[],[],previous,'2026-10-30T00:00:00Z')
        self.assertEqual(self.objects[0]['releaseWatch'][0]['status'],'unconfirmed')
        reconcile(self.objects,[row(t_obs_release=62000)],[],self.objects,'2026-10-31T00:00:00Z')
        r=self.objects[0]['releaseWatch'][0]
        self.assertEqual(r['status'],'exclusive');self.assertEqual(r['release'],62000)
        self.assertEqual(r['firstSeen'],'2026-10-29T00:00:00Z')

    def test_missing_or_changed_footprint_is_not_current_coverage(self):
        result=reconcile(self.objects,[row(s_region=None)],[],[],'2026-10-29T00:00:00Z')
        self.assertEqual(result['missingFootprints'],1);self.assertEqual(result['matchedObjects'],0)
        reconcile(self.objects,[row()],[],[],'2026-10-29T00:00:00Z')
        previous=copy.deepcopy(self.objects)
        result=reconcile(self.objects,[row(s_region='CIRCLE ICRS 180 0 0.001')],[],previous,'2026-10-30T00:00:00Z')
        self.assertEqual(result['matchedObjects'],0)
        self.assertEqual(self.objects[0]['releaseWatch'][0]['status'],'unconfirmed')

    def test_an_empty_exclusive_index_is_valid_but_must_be_complete(self):
        payload={'status':'COMPLETE','paging':{'rowsFiltered':0,'pagesFiltered':1},'data':[]}
        self.assertEqual(validate(payload,allow_empty=True),[])
        with self.assertRaises(RuntimeError):validate(payload)
        payload['paging']['rowsFiltered']=10
        with self.assertRaises(RuntimeError):validate(payload,allow_empty=True)


if __name__=='__main__':unittest.main()
