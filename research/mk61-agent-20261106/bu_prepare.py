"""Freeze phase routing, natural corpus, QAT schedule, and protected selection."""
import time
import json
import torch
from bu_common import ROOT,HERE,SOURCE,BT_ROOT,read,write,rows,sha,previous_check,body_ids
from bu_model import Translator,actor,frozen_digest
from bu_course import Course,loss
from be_language import paths3
from az_data import numbers
from bt_common import rows as old_rows
from native_export import packet
import bu_eval


def main():
    previous_check();assert not(ROOT/'frozen.json').exists();ast=read(ROOT/'ast-frozen.json');teacher=read(ROOT/'teacher-frozen.json')
    preflight=read(ROOT/'GPU-preflight.json');assert preflight['complete']and preflight['optimizer_updates']==0 and preflight['peak_reserved_MiB']<=1536
    policy={'steps':1500,'checkpoints':[500,1500],'lr':8e-5,'weight_decay':.001,'effective_batch':32,'microbatch':8,'accumulation':4,
        'data_seed':261123118,'model_seed':261123119,'context':1024,'KV':'FP32','Q4_every_forward':True,
        'LoRA_rank':16,'LoRA_alpha':32,'trainable_parameters':317440,'train_action_heads':False,'train_input_embeddings':False,
        'routing':'translator: forced primary/replan WRITE only; unchanged actor: all ordinary decisions and bodies',
        'old_translation_fraction':.5,'order_pair_fraction':.25,'other_new_fraction':.25,'review_fraction':.25,
        'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,'Qwen_service_changes':False,
        'max_actions':12,'dev_own_goals':64,'closed_own_goals':256,'closed_composition_families':32,
        'selection':'development only; +4/80 composition translations; no overall or unary/binary loss; retention total retained, at most 2 formerly correct lost; no decreased completions/repairs/correct finishes or increased corruption/false DONE/false claims/wrong-SPEC false DONE',
        'fallback':'unchanged translator and unchanged actor',
        'closed_confirmation':'fixed selected checkpoint: improved first SPEC; no loss in completions/repairs/correct finishes or increase in false DONE/corruption/false-claim episodes; closed may reject the claim of improvement but never choose another checkpoint',
        'main_profile_replacement':False,'physical_device_access':False}
    write(ROOT/'policy.json',policy)
    for collection in [ast['files'],teacher['files']]:
        for n,d in collection.items():assert sha(ROOT/n)==d,n
    held={tuple(t)for t in ast['all_training_excluded_triples']};valid=rows(ROOT/'train.jsonl')+rows(ROOT/'replay.jsonl')
    language_labels={}
    for g in valid:
        assert not paths3(g['spec']['X'])&held,g['id']
        assert not numbers(g['spec']['X'])&set(ast['fresh_dev_literals']+ast['fresh_test_literals']),g['id']
        label=json.dumps(g['spec'],sort_keys=True,ensure_ascii=False);identity=(g['spec']['angle'],g['task'])
        assert identity not in language_labels or language_labels[identity]==label,('conflicting_condition_labels',g['id'])
        language_labels[identity]=label
    a=Translator('cpu');a.save_checkpoint(ROOT/'initial.safetensors');packed,_=a.packed(ROOT/'initial.mkqb')
    assert packet(ROOT/'initial.mkqb')[1]==packet(SOURCE/'model.mkqb')[1]
    assert a.trainable_count()==317440;before=frozen_digest(a);course=Course(a.tokenizer);head=torch.tensor(body_ids(a.tokenizer))
    with torch.nn.utils.parametrize.cached():value=loss(a,course.step(1,'cpu')[0],head)
    value.backward();assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in a.parameters()if p.grad is not None)
    assert frozen_digest(a)==before
    base,tok=actor('cpu');bu_eval.headroom=lambda *args:None
    original_rows=bu_eval.rows;original_decode=bu_eval.decode;small=old_rows(BT_ROOT/'diagnostic.jsonl');small=[next(g for g in small if g['family']==f)for f in ['unary','composition']]
    bu_eval.rows=lambda p:small
    chosen=[]
    def spy(model,tokenizer,prompts,config,forced_action=None):
        assert model is(packed if forced_action=='write'else base)
        chosen.append('translator'if forced_action=='write'else'actor')
        return original_decode(model,tokenizer,prompts,config,forced_action)
    bu_eval.decode=spy
    try:smoke=bu_eval.evaluate(base,packed,tok,'development',{'GPU_duty_fraction':1.,'minimum_free_MiB':0})
    finally:bu_eval.rows=original_rows;bu_eval.decode=original_decode
    assert 'actor'in chosen and'translator'in chosen
    for mode in ['own','wrong']:
        for row in smoke[mode]['records']:
            for h in row['history']:
                if 'generation'not in h:continue
                assert h['generation']['profile']==('translator'if h['kind']=='replan'else'unchanged_actor')
    write(ROOT/'router-smoke.json',{'complete':True,'integration':bu_eval.brief(smoke),'calls':smoke['calls']['count'],
         'normal_actor_only_and_forced_translation_only_verified':True,'student_closed_generations_seen':False})
    del base,packed;course=Course(a.tokenizer)
    for step in range(1,policy['steps']+1):course.step(step,'cpu')
    assert course.counts['initial']==36000 and course.counts['review']==12000
    files={**ast['files'],**teacher['files'],**{n:sha(ROOT/n)for n in ['ast-frozen.json','teacher-frozen.json','teacher-audit.jsonl','policy.json','initial.safetensors','initial.mkqb','model-smoke.json','router-smoke.json','GPU-preflight.json']}}
    sources={**read(BT_ROOT/'frozen.json')['sources'],**{p.name:sha(p)for p in HERE.glob('bu_*.py')if p.name not in ['bu_native.py','bu_finish.py']},
             **{n:sha(HERE/n)for n in ['bs_resources.py','bs_model.py']}}
    parent={str(p.relative_to(SOURCE)):sha(p)for p in [SOURCE/'model.mkqb',SOURCE/'model.mka',*sorted((SOURCE/'hf').iterdir())]if p.is_file()}
    write(ROOT/'inputs-frozen.json',{'sources':sources,'files':files,'parent':parent,'optimizer_updates':0,'closed_student_generations_seen':False,'unix':time.time()})
    write(ROOT/'frozen.json',{'files':files,'expected_draw_digest':course.digest,'expected_counts':dict(course.counts),'closed_student_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'optimizer_updates':0,'trainable_parameters':317440,'finite_CPU_gradient':True,
         'body_loss':float(value.detach()),'initial_Q4_payload_identical':True,'frozen_translator_digest':before,
         'expected_draw_digest':course.digest,'expected_counts':dict(course.counts)})
    print(read(ROOT/'prepared.json'),flush=True)


if __name__=='__main__':torch.set_num_threads(3);main()
