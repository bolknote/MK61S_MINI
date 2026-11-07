#!/usr/bin/env python3
"""Retain inherited weights; learn added capacity on coherent branched dialogues."""
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
    previous=ROOT.parent/'round17';deadline=time.monotonic()+14400
    status('waiting_for_complete_width_comparison')
    while True:
        selection=json.loads((previous/'selection.json').read_text()) if (previous/'selection.json').exists() else {}
        if selection.get('comparison_finished'):break
        if time.monotonic()>deadline:raise TimeoutError('Parent comparison did not complete')
        time.sleep(5)
    parent=selection['selected']
    if parent['goal_met'] and parent.get('two_consecutive_goal_checks'):
        status('parent_requires_independent_audit',parent=parent);return
    assert not (ROOT/'added-only').exists(), 'Do not overwrite a student run'
    folder=previous/parent['mode']
    if not (ROOT/'selected-source').exists():
        shutil.copytree(folder/'best',ROOT/'selected-source',copy_function=os.link)
        shutil.copyfile(folder/'tokenizer.ttbpe',ROOT/'selected-source/tokenizer.ttbpe')
    assert core.digest(ROOT/'selected-source/model.safetensors')==core.digest(folder/'best/model.safetensors')
    config=json.loads((ROOT/'selected-source/config.json').read_text())
    if not (ROOT/'source-model').exists():
        if config['intermediate_size']==1280:
            shutil.copytree(ROOT/'selected-source',ROOT/'source-model',copy_function=os.link)
        else:
            assert config['intermediate_size']==1024
            command(container(0,'expand_mlp.py','--model','selected-source','--output','source-model',
                '--tokenizer-table','selected-source/tokenizer.ttbpe'),'expand-mlp.log',600)
    for name,destination in [('data','base-data'),('branched-data','branched-source'),('babi-probe','babi-probe')]:
        if not (ROOT/destination).exists():shutil.copytree(previous/name,ROOT/destination,copy_function=os.link)
    existing=ROOT/'new-units-origin.json'
    if existing.exists():
        old=json.loads(existing.read_text())
        assert old['source_sha256']==core.digest(ROOT/'source-model/model.safetensors')
        assert old['selected_parent_sha256']==core.digest(ROOT/'selected-source/model.safetensors')
    core.save(ROOT/'new-units-origin.json',{'parent':parent,
        'source_sha256':core.digest(ROOT/'source-model/model.safetensors'),
        'selected_parent_sha256':core.digest(ROOT/'selected-source/model.safetensors')})
    status('screening_complete_teacher_prefixes')
    core.save(ROOT/'reference-calibration.json',calibrate(ROOT/'reference-calibration-cache'))
    if not (ROOT/'prefix-data/manifest.json').exists():
        command(container(0,'prepare_prefixes.py'),'prefixes.log',14400)
    if not (ROOT/'data/manifest.json').exists():
        command(container(0,'combine_prefixes.py'),'combine-data.log',600)
    merged=json.loads((ROOT/'data/manifest.json').read_text())
    assert merged['sha256']==core.digest(ROOT/'data/train.jsonl')
    snapshot=ROOT/'source';snapshot.mkdir()
    for path in ROOT.glob('*.py'):shutil.copyfile(path,snapshot/path.name)
    status('training_added_mlp_units_only',steps=10000,active_parameter_elements=1050624,
        inherited_parameter_elements_frozen=10577920,branched=.3,prefix=.15,contrastive=.25,
        natural=.15,reading=.05,earlier_acts=.1)
    command(container(0,'train.py','--mode','sft','--model','source-model','--output','added-only',
        '--steps','10000','--batch-size','128','--lr','3e-5','--eval-every','1000','--qat-start','1',
        '--expanded-mlp-only','--embedding-lr-scale','0','--replay-fraction','0','--kl','.01','--intent-weight','1',
        '--branched-fraction','.3','--prefix-fraction','.15','--natural-fraction','.15',
        '--grounded-fraction','.05','--contrastive-fraction','.25','--example-balanced-loss',
        '--train-last-layers','8','--opened-audit-development','--balanced-selection',
        '--additional-development','suite/opened-audit2.jsonl',
        '--additional-scenarios','suite/opened-audit2-scenarios.json'),'added-only.log',14400)
    report=json.loads((ROOT/'added-only/training.json').read_text())
    assert report['inherited_parameters_verified']
    chosen=next((v for v in report['history'] if v['step']==report['best_step']),report['baseline'])
    item={'mode':'added-only','step':report['best_step'],'goal_met':chosen['goal_met'],
        'score':chosen['selection_score'],'bottleneck_ratio':bottleneck(chosen),
        'development_partitions':chosen['development_partitions'],
        'two_consecutive_goal_checks':bool(report.get('early_stop_reason'))}
    command(container(0,'pack_candidate.py','--model','added-only/best','--output','added-only/model.ttq4',
        '--report','added-only/packed.json'),'added-only-packed.log')
    shutil.copyfile(ROOT/'source-model/tokenizer.ttbpe',ROOT/'added-only/tokenizer.ttbpe')
    packed=json.loads((ROOT/'added-only/packed.json').read_text());table=(ROOT/'added-only/tokenizer.ttbpe').stat().st_size
    total=packed['file_bytes']+table+1048576+262144;assert total<8388608
    core.save(ROOT/'added-only/memory-budget.json',{'packed_bytes':packed['file_bytes'],'tokenizer_bytes':table,
        'fp16_kv_context128_bytes':1048576,'reserve_bytes':262144,'total_design_bytes':total,
        'remaining_from_8mib':8388608-total,'native_runtime_measured':False})
    core.save(ROOT/'selection.json',{'selected':item,'candidates':[item],'comparison_finished':True,
        'reserved_audit3_opened':False})
    status('development_target_met' if item['goal_met'] and item['two_consecutive_goal_checks'] else 'needs_next_iteration',selected=item)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}');raise
