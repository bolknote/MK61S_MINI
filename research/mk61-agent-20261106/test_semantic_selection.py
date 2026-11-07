import copy
import unittest

from semantic_eval import selection


def panel():
    result={}
    for name,rate in [('new1',.8),('observed1',.8),('new2',.2),('new3',.1),('observed2',.25),('observed3',.1)]:
        part={'rate':rate,'passed':int(rate*100),'total':100}
        result[name]={'program':part,'parse':dict(part)}
    result['formal']={'pass_rate':1.}
    return result


class SelectionTests(unittest.TestCase):
    def test_composition_gain_cannot_override_simple_regression_guard(self):
        baseline=panel();candidate=copy.deepcopy(baseline)
        for name in ['new2','new3']:candidate[name]['program']['rate']=.9
        for name in ['new1','observed1']:candidate[name]['program']['passed']=70
        self.assertLess(selection(candidate,.8),selection(baseline,.8))

    def test_gain_is_allowed_when_simple_and_formal_are_preserved(self):
        baseline=panel();candidate=copy.deepcopy(baseline)
        candidate['new2']['program']['rate']=.5
        candidate['new3']['program']['rate']=.25
        self.assertGreater(selection(candidate,.8),selection(baseline,.8))
        candidate['formal']['pass_rate']=.94
        self.assertLess(selection(candidate,.8),selection(baseline,.8))


if __name__=='__main__':unittest.main()
