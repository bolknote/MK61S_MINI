#!/usr/bin/env python3
"""Recover from self-generated context errors and test genuinely active attention capacity."""
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from run_remote import ROOT, container, command, status


def main():
    status('reserving_new_independent_audit')
    command(['python3','-u','reserve_audit.py','--training','data/train.jsonl'], 'reserve-audit.log', 900)
    status('activating_unused_attention_directions')
    command(container(0,'activate_attention.py','--model','source-model','--data','data','--output','capacity-init',
                      '--control-output','control-init','--device','cuda'), 'capacity-init.log')
    status('training', steps=6000, arms=['capacity','control'], old_audit_is_development=True, new_audit_opened=False)
    def worker(arm):
        gpu=0 if arm=='capacity' else 1
        command(container(gpu,'train.py','--mode','sft','--model',arm+'-init','--output',arm,
                          '--steps','6000','--batch-size','64','--lr','1e-5','--eval-every','500',
                          '--qat-start','1','--embedding-lr-scale','1','--replay-fraction','0','--kl','0.02',
                          '--intent-weight','4','--uniform-groups','--freeze-word-embeddings','--train-last-layers','8',
                          '--opened-audit-development'), arm+'.log',10800)
    with ThreadPoolExecutor(max_workers=2)as pool:list(pool.map(worker,['capacity','control']))
    candidates=[]
    for gpu,arm in enumerate(['capacity','control']):
        report=json.loads((ROOT/arm/'training.json').read_text())
        chosen=next((r for r in report['history']if r['step']==report['best_step']),report['baseline'])
        candidates.append({'mode':arm,'step':report['best_step'],'goal_met':chosen['goal_met'],'score':chosen['selection_score'],
            'acceptable':chosen['direct']['pass_rate'],'context':chosen['context_pass_rate'],'multi_turn':chosen['multi_turn']['pass_rate'],
            'development_partitions':chosen.get('development_partitions')})
        command(container(gpu,'quantize.py','--model',arm+'/best','--output',arm+'/model.ttq4','--report',arm+'/packed.json'),arm+'-packed.log')
        shutil.copyfile(ROOT/'source-model/tokenizer.ttbpe',ROOT/arm/'tokenizer.ttbpe')
        packed=json.loads((ROOT/arm/'packed.json').read_text());table=(ROOT/arm/'tokenizer.ttbpe').stat().st_size
        total=packed['file_bytes']+table+1048576+262144;assert total<8388608
        (ROOT/arm/'memory-budget.json').write_text(json.dumps({'packed_bytes':packed['file_bytes'],'tokenizer_bytes':table,
            'fp16_kv_context128_bytes':1048576,'reserve_bytes':262144,'total_design_bytes':total,
            'remaining_from_8mib':8388608-total,'native_runtime_measured':False},indent=2))
    candidates.sort(key=lambda r:(r['goal_met'],r['score']),reverse=True)
    (ROOT/'selection.json').write_text(json.dumps({'selected':candidates[0],'candidates':candidates,
        'first_audit_opened':True,'reserved_audit2_opened':False},indent=2))
    status('development_target_met'if candidates[0]['goal_met']else'needs_next_iteration',selected=candidates[0])


if __name__=='__main__':
    try:main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}');raise
