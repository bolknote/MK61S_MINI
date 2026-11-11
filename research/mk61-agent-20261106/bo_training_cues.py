"""Exact draw replay to audit review-used shortcuts in the trained curriculum."""
import collections
import json
import re
import sys
from bn_common import ROOT,PREVIOUS,RESULTS,read,write
import bl_course


def main():
    counts=collections.defaultdict(collections.Counter);budgets=collections.defaultdict(collections.Counter);misflags=collections.Counter()
    def encoded(tokenizer,row,arm='spec'):
        if row['origin']in ['natural','review_fix','review_keep']:return [1],[-100],0,0
        reviewed=row.get('replan_attempted',row['state'].get('replan_attempted',False));key='review_used'if reviewed else'review_available'
        remaining=int(re.search(r'Осталось действий: (\d+)',row['raw_prompt']).group(1))if'raw_prompt'in row else row['state']['remaining']
        counts[key][row['action']]+=1
        if 'raw_prompt'not in row and (row['state'].get('observation')or'').startswith('SPEC_REVISED')and not reviewed:
            misflags[row['origin']]+=1
        if row['action']=='unsure':budgets[key][remaining]+=1
        return [1],[-100],0,0
    bl_course.encoded=encoded;course=bl_course.Course(None)
    for step in range(1,read(PREVIOUS/'policy.json')['steps']+1):course.batch(step,'cpu')
    assert all(course.digest==read(RESULTS/a/'training.json')['draw_digest']for a in ['lora','full'])
    result={'digest_exactly_matches_both_trainings':True,'draw_digest':course.digest,'actions_by_review_flag':{k:dict(v)for k,v in counts.items()},
            'UNSURE_remaining_budget':{k:dict(v)for k,v in budgets.items()},'misflagged_review_successes_actually_sampled':dict(misflags),'optimizer_updates':0,
            'note':'Correlation in labels is evidence of a shortcut opportunity, not by itself proof the model uses it.'}
    write(ROOT/'training-cue-audit.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
