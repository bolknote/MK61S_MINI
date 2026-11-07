#!/usr/bin/env python3
"""Test stronger pretrained language representations with varied conversations and binding tasks."""
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import time
from run_remote import ROOT,container,command,status


def main():
    deadline=time.monotonic()+1800
    while not(ROOT/'everyday-data/manifest.json').exists()or not all((ROOT/(label+'-chat-init/config.json')).exists()for label in ['plain','instruct']):
        if time.monotonic()>deadline:raise TimeoutError('Language cores or everyday data not ready')
        time.sleep(3)
    status('preparing_compositional_conversation_data')
    if not(ROOT/'data/manifest.json').exists():command(container(0,'semantic_curriculum.py'),'semantic-data.log',600)
    status('reserving_third_audit')
    if not(ROOT/'reserved-audit3/manifest.json').exists():
        command(['python3','-u','reserve_audit.py','--output','reserved-audit3','--training','data/train.jsonl',
                 '--seed','557921','--strict-last-intent'],'reserve-audit3.log',1200)
    status('training_fully_pretrained_cores',steps=10000,arms=['plain','instruct'],all_260_previous_prompts_are_development=True,new_audit_opened=False)
    def worker(item):
        gpu,label=item
        command(container(gpu,'train.py','--mode','sft','--model',label+'-chat-init','--output',label,
            '--steps','10000','--batch-size','64','--lr','2e-5','--eval-every','1000','--qat-start','1',
            '--embedding-lr-scale','1','--replay-fraction','0','--kl','0.01','--intent-weight','4','--uniform-groups',
            '--freeze-word-embeddings','--train-last-layers','8','--opened-audit-development',
            '--additional-development','suite/opened-audit2.jsonl','--additional-scenarios','suite/opened-audit2-scenarios.json'),label+'.log',14400)
    with ThreadPoolExecutor(max_workers=2)as pool:list(pool.map(worker,enumerate(['plain','instruct'])))
    candidates=[]
    for gpu,label in enumerate(['plain','instruct']):
        report=json.loads((ROOT/label/'training.json').read_text())
        best=next((r for r in report['history']if r['step']==report['best_step']),report['baseline'])
        candidates.append({'mode':label,'step':report['best_step'],'goal_met':best['goal_met'],'score':best['selection_score'],
            'acceptable':best['direct']['pass_rate'],'context':best['context_pass_rate'],'multi_turn':best['multi_turn']['pass_rate'],
            'development_partitions':best.get('development_partitions')})
        command(container(gpu,'pack_candidate.py','--model',label+'/best','--output',label+'/model.ttq4','--report',label+'/packed.json'),label+'-packed.log')
        shutil.copyfile(ROOT/(label+'-chat-init/tokenizer.ttbpe'),ROOT/label/'tokenizer.ttbpe')
        packed=json.loads((ROOT/label/'packed.json').read_text());table=(ROOT/label/'tokenizer.ttbpe').stat().st_size
        total=packed['file_bytes']+table+1048576+262144;assert total<8388608
        (ROOT/label/'memory-budget.json').write_text(json.dumps({'packed_bytes':packed['file_bytes'],'tokenizer_bytes':table,
            'fp16_kv_context128_bytes':1048576,'reserve_bytes':262144,'total_design_bytes':total,
            'remaining_from_8mib':8388608-total,'native_runtime_measured':False},indent=2))
    candidates.sort(key=lambda r:(r['goal_met'],r['score']),reverse=True)
    (ROOT/'selection.json').write_text(json.dumps({'selected':candidates[0],'candidates':candidates,'first_two_audits_opened':True,
        'third_reserved_audit_opened':False},indent=2))
    status('development_target_met'if candidates[0]['goal_met']else'needs_next_iteration',selected=candidates[0])


if __name__=='__main__':
    try:main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}');raise
