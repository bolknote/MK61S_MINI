import unittest
from codec_stats import comparison


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.tasks=[{'id':f'new{level}:0:{i}','level':level}for level in [1,2,3]for i in [0,1]]
    def test_identical(self):
        a=[{'id':t['id'],'pass':True}for t in self.tasks];s=comparison(self.tasks,a,a,100)
        self.assertEqual(s['macro_delta_h32_minus_hex'],0)
        self.assertEqual(s['macro_delta_bootstrap95'],[0,0])
        self.assertEqual(s['scenario_clusters'],4)
    def test_full_paired_difference(self):
        a=[{'id':t['id'],'pass':False}for t in self.tasks];b=[{'id':t['id'],'pass':True}for t in self.tasks]
        s=comparison(self.tasks,a,b,100);self.assertEqual(s['macro_delta_h32_minus_hex'],1)
        self.assertEqual(s['macro_delta_bootstrap95'],[1,1])
        with self.assertRaises(AssertionError):comparison(self.tasks,a[:-1],b,100)


if __name__=='__main__':unittest.main()
