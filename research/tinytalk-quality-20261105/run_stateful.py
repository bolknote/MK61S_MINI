#!/usr/bin/env python3
"""Broaden conversation state supervision without changing quality gates or size."""
import hashlib
import json
from pathlib import Path
import shutil
import time

from run_remote import ROOT, container, command, status
from run_preferences import bottleneck


def main():
    origin=json.loads((ROOT/'stateful-origin.json').read_text())
    previous=Path(origin['previous_round'])
    status('waiting_for_matched_control_and_reference_audit')
    deadline=time.monotonic()+7200
    while True:
        selection=json.loads((previous/'selection.json').read_text()) if (previous/'selection.json').exists() else {}
        audit_path=ROOT/'contrastive-data/teacher-audit.json'
        if selection.get('comparison_finished') and audit_path.exists():
            break
        if time.monotonic()>deadline:
            raise TimeoutError('Parent comparison or reference audit did not finish')
        time.sleep(5)
    if selection['selected']['goal_met']:
        status('parent_requires_independent_audit',parent=selection['selected'])
        return
    audit=json.loads(audit_path.read_text())
    assert audit['pass_rate']>=.98,'Repair references before student training'
    assert hashlib.sha256((ROOT/'source-model/model.safetensors').read_bytes()).hexdigest()==origin['source_sha256']
    command(container(0,'combine_transfer.py'),'combine-data.log',600)
    snapshot=ROOT/'source'
    snapshot.mkdir()
    for path in ROOT.glob('*.py'):
        shutil.copyfile(path,snapshot/path.name)
    status('training_broader_conversational_state',steps=12000,source=origin['source_sha256'],
        contrastive_fraction=.5,natural_fraction=.35,reading_fraction=.05,earlier_acts_fraction=.1)
    command(container(0,'train.py','--mode','sft','--model','source-model','--data','data','--output','stateful',
        '--steps','12000','--batch-size','128','--lr','1e-5','--eval-every','1000','--qat-start','1',
        '--embedding-lr-scale','.3','--replay-fraction','0','--kl','.005','--intent-weight','1',
        '--natural-fraction','.35','--grounded-fraction','.05','--contrastive-fraction','.5',
        '--example-balanced-loss','--train-last-layers','8','--opened-audit-development','--balanced-selection',
        '--additional-development','suite/opened-audit2.jsonl',
        '--additional-scenarios','suite/opened-audit2-scenarios.json'),'stateful.log',14400)
    report=json.loads((ROOT/'stateful/training.json').read_text())
    chosen=next((v for v in report['history'] if v['step']==report['best_step']),report['baseline'])
    item={'mode':'stateful','step':report['best_step'],'goal_met':chosen['goal_met'],
        'score':chosen['selection_score'],'bottleneck_ratio':bottleneck(chosen),
        'development_partitions':chosen['development_partitions'],
        'two_consecutive_goal_checks':bool(report.get('early_stop_reason'))}
    command(container(0,'pack_candidate.py','--model','stateful/best','--output','stateful/model.ttq4',
        '--report','stateful/packed.json'),'stateful-packed.log')
    shutil.copyfile(ROOT/'source-model/tokenizer.ttbpe',ROOT/'stateful/tokenizer.ttbpe')
    packed=json.loads((ROOT/'stateful/packed.json').read_text())
    table=(ROOT/'stateful/tokenizer.ttbpe').stat().st_size
    total=packed['file_bytes']+table+1048576+262144
    assert total<8388608
    (ROOT/'stateful/memory-budget.json').write_text(json.dumps({'packed_bytes':packed['file_bytes'],
        'tokenizer_bytes':table,'fp16_kv_context128_bytes':1048576,'reserve_bytes':262144,
        'total_design_bytes':total,'remaining_from_8mib':8388608-total,'native_runtime_measured':False},indent=2))
    (ROOT/'selection.json').write_text(json.dumps({'selected':item,'candidates':[item],
        'reserved_audit3_opened':False,'comparison_finished':True},indent=2))
    status('development_target_met' if item['goal_met'] else 'needs_next_iteration',selected=item)


if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}')
        raise
