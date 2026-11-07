#!/usr/bin/env python3
"""Ablate private act prediction using the same language core and exactly the same training contexts."""
import json
import shutil
from run_remote import ROOT,container,command,status


def main():
    status('removing_private_act_prefix')
    command(container(0,'strip_intents.py','--model','/previous','--data','source-data','--output-model','text-init','--output-data','data'),'text-init.log')
    status('training_ordinary_text',steps=10000,comparison='round9 instruct: same pretrained core and contexts, ordinary text targets')
    command(container(0,'train.py','--mode','sft','--model','text-init','--output','text',
        '--steps','10000','--batch-size','64','--lr','2e-5','--eval-every','1000','--qat-start','1',
        '--embedding-lr-scale','1','--replay-fraction','0','--kl','0.01','--intent-weight','1','--uniform-groups',
        '--freeze-word-embeddings','--train-last-layers','8','--opened-audit-development',
        '--additional-development','suite/opened-audit2.jsonl','--additional-scenarios','suite/opened-audit2-scenarios.json'),'text.log',14400)
    report=json.loads((ROOT/'text/training.json').read_text())
    best=next((r for r in report['history']if r['step']==report['best_step']),report['baseline'])
    selected={'mode':'text','step':report['best_step'],'goal_met':best['goal_met'],'score':best['selection_score'],
        'acceptable':best['direct']['pass_rate'],'context':best['context_pass_rate'],'multi_turn':best['multi_turn']['pass_rate'],
        'development_partitions':best.get('development_partitions')}
    command(container(0,'pack_candidate.py','--model','text/best','--output','text/model.ttq4','--report','text/packed.json'),'text-packed.log')
    shutil.copyfile(ROOT/'text-init/tokenizer.ttbpe',ROOT/'text/tokenizer.ttbpe')
    packed=json.loads((ROOT/'text/packed.json').read_text());table=(ROOT/'text/tokenizer.ttbpe').stat().st_size
    total=packed['file_bytes']+table+1048576+262144;assert total<8388608
    (ROOT/'text/memory-budget.json').write_text(json.dumps({'packed_bytes':packed['file_bytes'],'tokenizer_bytes':table,
        'fp16_kv_context128_bytes':1048576,'reserve_bytes':262144,'total_design_bytes':total,
        'remaining_from_8mib':8388608-total,'native_runtime_measured':False},indent=2))
    (ROOT/'selection.json').write_text(json.dumps({'selected':selected,'third_reserved_audit_opened':False},indent=2))
    status('development_target_met'if selected['goal_met']else'needs_next_iteration',selected=selected)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}');raise
