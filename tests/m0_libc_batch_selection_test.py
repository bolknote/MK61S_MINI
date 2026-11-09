#!/usr/bin/env python3
"""Regression checks for unresolved ties and matched stratum validation."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/m0-libc-batch-2026-11-07'))
from selection import choose,compare_matched

def sample(profile,ratio,noise,short,size,cases=80):
    return dict(profile=profile,ratio=ratio,noise_ratio=noise,
                resolved_gain=1-ratio>noise,weighted_short_ratio=short,
                body_bytes=size,physical_cases=cases,sensitivity_ratios={"equal-length":.9,"inverse-work":ratio,"ternary":ratio})

def main():
    byte4=sample(4,.803,.015,.70,40)
    word2=sample(16,.800,.014,1.30,72)
    result=choose([word2,byte4])
    assert result['picked']['profile']==4 and result['fastest_sample_mean']['profile']==16
    assert set(result['unresolved_ties'])=={4,16}
    assert choose([dict(word2,ratio=.70),byte4])['picked']['profile']==16
    assert choose([sample(4,.999,.01,.8,40)])['verdict']=='KEEP_CURRENT_NO_RESOLVED_GAIN'
    # Native and standalone SDK have different measured baselines.
    native4=sample(4,.86743,.01612,.70123,40);native4['sensitivity_ratios']['equal-length']=1.69017
    native16=sample(16,.86454,.01777,.87287,72);native16['sensitivity_ratios']['equal-length']=.79732
    assert choose([native4,native16])['picked']['profile']==16
    sdk4=sample(4,.75048,.01264,.84979,40);sdk4['sensitivity_ratios']['equal-length']=.60835
    sdk16=sample(16,.74754,.01380,1.05704,72);sdk16['sensitivity_ratios']['equal-length']=.28682
    assert choose([sdk4,sdk16])['picked']['profile']==4
    # A disclosed short-input loss is compared with the SAME primary subset.
    reference=sample(4,1.08,.01,1.08,40)
    assert compare_matched(reference,sample(4,1.085,.01,1.085,40))['no_resolved_extra_regression']
    assert not compare_matched(reference,sample(4,1.20,.01,1.20,40))['no_resolved_extra_regression']
    for bad in [sample(4,1.08,.01,1.08,40,cases=79),sample(16,1.08,.01,1.08,72)]:
        try:compare_matched(reference,bad)
        except AssertionError:pass
        else:raise AssertionError('Unmatched subset or body accepted')
    print('Unresolved tie/short-input policy and matched-stratum regression checks PASS; synthetic only')
if __name__=='__main__':main()
