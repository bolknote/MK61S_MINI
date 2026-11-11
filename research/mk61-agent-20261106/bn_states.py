"""All comparable terminal decisions from the already-opened full-model exam."""
import collections
import copy
import json
import re
import time
from transformers import AutoTokenizer
from bn_common import ROOT,PREVIOUS,RESULTS,OLD,NEW,HERE,read,write,rows,save_rows,sha,ACTIONS,ACTION_IDS,check_previous
from aq_protocol import prompt_ids


def label(record,prompt):
    # Labels use already-recorded real-ROM audit results, never a new critic.
    remaining=int(re.search(r'Осталось действий: (\d+)',prompt).group(1))
    missing=re.search(r'не запускались: ([^\n]*)',prompt).group(1)
    count=len(re.findall(r'\b0[01]\b',missing))
    spec_ok=record['final_spec_intent']['tested_equal']
    code_ok=record['candidate_correct_at_exit']
    reviewed=record['replans']>0
    if not spec_ok:return 'diag'if not reviewed and remaining>=(3+count if code_ok else 5)else'unsure'
    if not code_ok:return 'write'if remaining>=3 else'unsure'
    if count:return 'run'if remaining>=count+1 else'unsure'
    return 'done'


def main():
    check_previous();ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    tok=AutoTokenizer.from_pretrained(NEW/'hf',local_files_only=True)
    reports={k:read(RESULTS/a/'closed.json')for k,a in [('old','parent_full'),('new','fixed3000_full')]}
    output=[];skipped=collections.Counter()
    for source,x in reports.items():
        old_by_id={r['id']:r for r in reports['old']['self']['records']}
        for r in x['self']['records']:
            h=r['history'][-1]
            if not h.get('prompt')or not h.get('generation')or h['kind']not in ['done','done_rejected','unsure']:skipped[source+'_no_final_neural_decision']+=1;continue
            p=h['prompt'];ids=prompt_ids(tok,p)
            if len(ids)>=1016:skipped[source+'_unreachable_overflow']+=1;continue
            if set(ids)&set(ACTION_IDS):raise ValueError('Action rows appear in input')
            if h.get('harness_forced'):skipped[source+'_forced_RUN']+=1;continue
            # The final action has not yet consumed the visible remaining budget.
            expected=label(r,p)
            output.append({'id':source+':'+r['id'],'source':source,'episode_id':r['id'],'task_id':r['task_id'],
                           'prompt':p,'input_tokens':len(ids),'expected_action':expected,'recorded_action':h['generation'].get('action'),
                           'finished':r['finished'],'pass':r['pass'],'abstained':r['abstained'],
                           'code_correct':r['candidate_correct_at_exit'],'spec_correct':r['final_spec_intent']['tested_equal'],
                           'old_episode_pass':old_by_id[r['id']]['pass'],'initially_correct':r['initially_correct']})
    assert len([r for r in output if r['source']=='new'])==512
    save_rows(ROOT/'states.jsonl',output)
    # Predeclare all block interventions before examining their outcomes.
    plan={'optimizer_updates':0,'diagnostic_opened_exam_only':True,'fresh_closed_test':False,
          'models':['old_master','new_master','old_Q4','new_Q4'],
          'ablations':['old_action_rows','old_all_attention','old_all_MLP','old_input_embeddings_except_action_rows','old_norms',*[f'old_layer_{i}'for i in range(10)]],
          'margin_decomposition':'delta_logit = delta_head dot mean_hidden + mean_head dot delta_hidden',
          'cross_runtime':'new Q4 full3000 in original long BJ harness on existing development; other3 cells already measured',
          'no_checkpoint_selection_or_promotion':True,'no_model_writes_outside_diagnostic_copies':True,
          'counts':dict(collections.Counter(r['source']for r in output)),'skipped':dict(skipped),
          'labels':dict(collections.Counter(r['expected_action']for r in output)),
          'caveat':'Terminal states are on-policy observations from different trajectories, not an independent exam; paired models see exactly identical prompts.',
          'unix':time.time()}
    write(ROOT/'plan.json',plan)
    def model_files(folder):return{str(p.relative_to(folder)):sha(p)for p in [folder/'model.mkqb',*sorted((folder/'hf').iterdir())]if p.is_file()}
    write(ROOT/'frozen.json',{'sources':{p.name:sha(p)for p in HERE.glob('bn_*.py')},
          'files':{n:sha(ROOT/n)for n in ['plan.json','states.jsonl']},'models':{'old':model_files(OLD),'new':model_files(NEW)},'unix':time.time()})
    print(json.dumps(plan),flush=True)


if __name__=='__main__':main()
