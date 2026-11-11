"""Correct exactly5344 flags, preserving all row IDs, labels and sampling inputs."""
import copy
import json
import shutil
import torch
from transformers import AutoTokenizer
from bp_common import ROOT,PREVIOUS,PRIOR_RESULTS,DIAGNOSIS,SOURCES,HERE,read,write,rows,save_rows,sha,check_previous
from bo_review_state_fix import corrected,snapshot
from bp_course import encoded
from bc_pools import lesson_layout
from bj_runtime import SPEC_DIAG
from bl_runtime import Session,render
from bl_vm import CachedVM
from bl_spec import install


def main():
    check_previous();assert not(ROOT/'frozen.json').exists()
    if(ROOT/'training-inputs.json').exists():return
    fixes=read(DIAGNOSIS/'review-state-fix-checks.json');assert sha(PREVIOUS/'lessons.jsonl')==fixes['source_lessons_sha256']
    patch=rows(DIAGNOSIS/'review-state-corrections.jsonl');expected={x['index']for x in patch};values=rows(PREVIOUS/'lessons.jsonl');out=[];changed=[]
    for i,row in enumerate(values):
        new=corrected(row)
        if new!=row:
            assert i in expected
            a=copy.deepcopy(row);a['state']['replan_attempted']=True;assert a==new
            changed.append(i)
        out.append(new)
    assert set(changed)==expected and len(changed)==5344
    save_rows(ROOT/'lessons.jsonl',out)
    for name in ['policy.json','valid-ids.json','train-clean.jsonl','development-clean.jsonl','initial-lora.safetensors','initial-full.safetensors']:
        shutil.copyfile(PREVIOUS/name,ROOT/name)
    for arm in ['lora','full']:
        for prefix in ['parent-','compact-parent-','baseline-']:
            name=prefix+arm+('-receipt.json'if prefix=='baseline-'else'-development.json')
            shutil.copyfile(PRIOR_RESULTS/name,ROOT/name)
    tok=AutoTokenizer.from_pretrained(SOURCES['full']/'hf',local_files_only=True);valid=set(read(ROOT/'valid-ids.json'))
    for count,i in enumerate(changed):
        assert i in valid
        for mode in ['default','full','distractors']:
            row=lesson_layout(out[i],mode,f'bl:check:{i}:{mode}');assert len(encoded(tok,row)[0])<=1024
        if count%1000==0:print(json.dumps({'corrected_encodings_checked':count,'total':len(changed)}),flush=True)
    install();g=rows(PREVIOUS/'train-clean.jsonl')[0];s=Session(g,g['reference_body'],CachedVM(),'spec',g['spec'],True)
    s.apply_action('diag',SPEC_DIAG);s.replan_attempted=True;s.apply_replan(g['spec_body']);state=snapshot(s)
    p,_=render(state,tok);assert 'Разборов SPEC осталось: 0.'in p and state['body']==g['reference_body']
    old=[read(PRIOR_RESULTS/a/'training.json')for a in ['lora','full']];assert old[0]['draw_digest']==old[1]['draw_digest']
    write(ROOT/'repeat-plan.json',{'only_training_change':'5344 state.replan_attempted False -> True',
          'original_rows':len(values),'corrected_rows':len(changed),'valid_IDs_identical':True,'all_other_lesson_fields_identical':True,
          'original_draw_digest':old[0]['draw_digest'],'old_policy_sha256':sha(PREVIOUS/'policy.json'),'new_policy_sha256':sha(ROOT/'policy.json'),
          'steps_per_branch':3000,'checkpoints':[1000,2000,3000],'original_parents':{a:sha(ROOT/('initial-'+a+'.safetensors'))for a in ['lora','full']},
          'same_open_development_for_diagnostic_and_selection':True,'fresh_closed_before_SGD':True,
          'fresh_closed_roles':['parent_lora','parent_full','bad_lora','bad_full','fixed3000_lora','fixed3000_full'],
          'causal_primary_endpoint':'fixed3000 corrected vs bad3000 in same compact protocol',
          'closed_concurrency':6,'max_jobs_per_GPU':3,'main_profile_changed':False,'physical_device_access':False})
    assert sha(ROOT/'policy.json')==sha(PREVIOUS/'policy.json')
    names=['lessons.jsonl','policy.json','valid-ids.json','train-clean.jsonl','development-clean.jsonl','initial-lora.safetensors','initial-full.safetensors','repeat-plan.json']
    names+=[p.name for p in ROOT.glob('*-development.json')]+[p.name for p in ROOT.glob('baseline-*-receipt.json')]
    write(ROOT/'training-inputs.json',{'complete':True,'files':{n:sha(ROOT/n)for n in names},'corrected_rows':5344,
          'only_flag_changes':True,'real_review_snapshot_regression_passed':True,'SGD_started':False})
    print(json.dumps({'training_inputs_ready':True,'corrected_rows':5344,'identical_policy_and_valid_IDs':True}),flush=True)


if __name__=='__main__':torch.set_num_threads(4);main()
