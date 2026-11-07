#!/usr/bin/env python3
"""Train alternative final requests; try additional MLP capacity within 8 MiB."""
import json
import os
from pathlib import Path
import shutil
import time

from common import core
from grade import calibrate
from run_remote import ROOT,container,command,status
from run_preferences import bottleneck


def main():
    previous=ROOT.parent/'round16'
    status('waiting_for_state_curriculum_result')
    deadline=time.monotonic()+7200
    while not (previous/'selection.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Parent student did not finish')
        time.sleep(5)
    parent=json.loads((previous/'selection.json').read_text())['selected']
    if parent['goal_met'] and parent.get('two_consecutive_goal_checks'):
        status('parent_requires_independent_audit',parent=parent);return
    assert not any((ROOT/name).exists() for name in ['expanded','compact']), 'Do not overwrite student training'
    if not (ROOT/'source-model').exists():
        shutil.copytree(previous/'stateful/best',ROOT/'source-model',copy_function=os.link)
        shutil.copyfile(previous/'stateful/tokenizer.ttbpe',ROOT/'source-model/tokenizer.ttbpe')
    if not (ROOT/'state-base-data').exists():
        shutil.copytree(previous/'data',ROOT/'state-base-data',copy_function=os.link)
    if not (ROOT/'babi-probe').exists():
        shutil.copytree(previous/'babi-probe',ROOT/'babi-probe',copy_function=os.link)
    source_sha=core.digest(ROOT/'source-model/model.safetensors')
    assert source_sha==core.digest(previous/'stateful/best/model.safetensors')
    (ROOT/'branched-origin.json').write_text(json.dumps({'parent':parent,'source_sha256':source_sha},indent=2))
    if not (ROOT/'branched-data/manifest.json').exists():
        status('generating_and_screening_alternative_requests',contexts=6000,branches=4)
        core.save(ROOT/'reference-calibration.json',calibrate(ROOT/'reference-calibration-cache'))
        command(container(0,'branching_dialogues.py','--contexts','6000','--workers','12'),
            'generate-branched.log',14400)
    generated=json.loads((ROOT/'branched-data/manifest.json').read_text())
    assert generated['all_targets_graded'] and generated['sha256']==core.digest(ROOT/'branched-data/train.jsonl')
    if not (ROOT/'data/manifest.json').exists():
        command(container(0,'combine_branched.py'),'combine-data.log',600)
    merged=json.loads((ROOT/'data/manifest.json').read_text())
    assert merged['sha256']==core.digest(ROOT/'data/train.jsonl')
    status('expanding_mlp_without_initial_behavior_change',old=1024,new=1280)
    command(container(0,'expand_mlp.py','--model','source-model','--output','expanded-init',
        '--tokenizer-table','source-model/tokenizer.ttbpe'),'expand-mlp.log',600)
    snapshot=ROOT/'source';snapshot.mkdir()
    for path in ROOT.glob('*.py'):shutil.copyfile(path,snapshot/path.name)
    candidates=[]
    for gpu,label,model in [(0,'expanded','expanded-init'),(1,'compact','source-model')]:
        status('training_alternative_final_requests',arm=label,steps=8000,
            branched_fraction=.5,contrastive_fraction=.25,natural_fraction=.15,reading_fraction=.05,earlier_acts_fraction=.05)
        command(container(gpu,'train.py','--mode','sft','--model',model,'--output',label,
            '--steps','8000','--batch-size','128','--lr','1e-5','--eval-every','1000','--qat-start','1',
            '--embedding-lr-scale','.3','--replay-fraction','0','--kl','.005','--intent-weight','1',
            '--branched-fraction','.5','--natural-fraction','.15','--grounded-fraction','.05','--contrastive-fraction','.25',
            '--example-balanced-loss','--train-last-layers','8','--opened-audit-development','--balanced-selection',
            '--additional-development','suite/opened-audit2.jsonl',
            '--additional-scenarios','suite/opened-audit2-scenarios.json'),label+'.log',14400)
        report=json.loads((ROOT/label/'training.json').read_text())
        chosen=next((h for h in report['history'] if h['step']==report['best_step']),report['baseline'])
        item={'mode':label,'step':report['best_step'],'goal_met':chosen['goal_met'],
            'score':chosen['selection_score'],'bottleneck_ratio':bottleneck(chosen),
            'development_partitions':chosen['development_partitions'],
            'two_consecutive_goal_checks':bool(report.get('early_stop_reason'))}
        command(container(gpu,'pack_candidate.py','--model',label+'/best','--output',label+'/model.ttq4',
            '--report',label+'/packed.json'),label+'-packed.log')
        shutil.copyfile(ROOT/'source-model/tokenizer.ttbpe',ROOT/label/'tokenizer.ttbpe')
        packed=json.loads((ROOT/label/'packed.json').read_text())
        table=(ROOT/label/'tokenizer.ttbpe').stat().st_size
        total=packed['file_bytes']+table+1048576+262144;assert total<8388608
        core.save(ROOT/label/'memory-budget.json',{'packed_bytes':packed['file_bytes'],'tokenizer_bytes':table,
            'fp16_kv_context128_bytes':1048576,'reserve_bytes':262144,'total_design_bytes':total,
            'remaining_from_8mib':8388608-total,'native_runtime_measured':False})
        candidates.append(item)
        candidates.sort(key=lambda v:(v['goal_met'] and v['two_consecutive_goal_checks'],
            v['goal_met'],v['bottleneck_ratio'],v['score']),reverse=True)
        qualified=item['goal_met'] and item['two_consecutive_goal_checks']
        core.save(ROOT/'selection.json',{'selected':candidates[0],'candidates':candidates,
            'reserved_audit3_opened':False,'comparison_finished':label=='compact' or qualified})
        if qualified:
            status('development_target_met',selected=item);return
    status('needs_next_iteration',selected=candidates[0])


if __name__=='__main__':
    try:main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}');raise
