#!/usr/bin/env python3
"""Learn a private answer-form step while preserving the inherited language weights."""
import json
from pathlib import Path
import shutil
import time
from common import core
from run_remote import ROOT,container,command,status
from run_preferences import bottleneck


def main():
    deadline=time.monotonic()+14400
    while not (ROOT/'type-labels/manifest.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Answer-form labels did not finish')
        time.sleep(5)
    proof=json.loads((ROOT/'typed-preflight.json').read_text())
    assert proof['typed_wire_format_check']['all_private_headers_valid']
    assert proof['typed_wire_format_check']['prompt_facts_remain_copyable']
    assert proof['frozen_packed_payload_bytes_identical']==6022240
    assert not (ROOT/'typed').exists(),'Do not overwrite a student run'
    status('preparing_private_answer_form_model')
    if not (ROOT/'data/manifest.json').exists():
        command(container(0,'prepare_typed.py'),'prepare-typed.log',1200)
    model_meta=json.loads((ROOT/'typed-init/type-model.json').read_text())
    assert model_meta['ordinary_embeddings_exact'] and model_meta['parameters']==11636224
    merged=json.loads((ROOT/'data/manifest.json').read_text())
    assert merged['sha256']==core.digest(ROOT/'data/train.jsonl') and merged['contexts_and_spoken_targets_unchanged']
    snapshot=ROOT/'source';snapshot.mkdir()
    for path in ROOT.glob('*.py'):shutil.copyfile(path,snapshot/path.name)
    status('training_private_answer_forms',steps=10000,parameters=11636224,
        effective_trainable_elements=1058304,inherited_elements_frozen=10577920,
        intent_loss_weight=2,answer_type_loss_weight=2,decoder='Learned intent and type; generated-body-only trigram loop prevention')
    command(container(0,'train.py','--mode','sft','--model','typed-init','--output','typed',
        '--steps','10000','--batch-size','128','--lr','3e-5','--eval-every','1000','--qat-start','1',
        '--expanded-mlp-only','--embedding-lr-scale','1','--replay-fraction','0','--kl','.01','--intent-weight','2',
        '--branched-fraction','.3','--prefix-fraction','.15','--natural-fraction','.15',
        '--grounded-fraction','.05','--contrastive-fraction','.25','--example-balanced-loss',
        '--train-last-layers','8','--opened-audit-development','--balanced-selection',
        '--additional-development','suite/opened-audit2.jsonl',
        '--additional-scenarios','suite/opened-audit2-scenarios.json'),'typed.log',14400)
    report=json.loads((ROOT/'typed/training.json').read_text());assert report['inherited_parameters_verified']
    chosen=next((v for v in report['history'] if v['step']==report['best_step']),report['baseline'])
    item={'mode':'typed','step':report['best_step'],'goal_met':chosen['goal_met'],
        'score':chosen['selection_score'],'bottleneck_ratio':bottleneck(chosen),
        'development_partitions':chosen['development_partitions'],
        'two_consecutive_goal_checks':bool(report.get('early_stop_reason'))}
    command(container(0,'pack_candidate.py','--model','typed/best','--output','typed/model.ttq4',
        '--report','typed/packed.json'),'typed-packed.log')
    shutil.copyfile(ROOT/'typed-init/tokenizer.ttbpe',ROOT/'typed/tokenizer.ttbpe')
    packed=json.loads((ROOT/'typed/packed.json').read_text());table=(ROOT/'typed/tokenizer.ttbpe').stat().st_size
    total=packed['file_bytes']+table+1048576+262144;assert total<8388608
    core.save(ROOT/'typed/memory-budget.json',{'packed_bytes':packed['file_bytes'],'tokenizer_bytes':table,
        'tokenizer_sha256':core.digest(ROOT/'typed/tokenizer.ttbpe'),'fp16_kv_context128_bytes':1048576,
        'reserve_bytes':262144,'total_design_bytes':total,'remaining_from_8mib':8388608-total,
        'native_runtime_measured':False})
    core.save(ROOT/'selection.json',{'selected':item,'candidates':[item],'comparison_finished':True,
        'reserved_audit3_opened':False})
    status('development_target_met' if item['goal_met'] and item['two_consecutive_goal_checks'] else 'needs_next_iteration',selected=item)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}');raise
