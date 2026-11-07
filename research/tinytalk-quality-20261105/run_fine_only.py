#!/usr/bin/env python3
"""Compare one precise answer-form tag after the overlapping-tag run completes."""
import json
import os
import shutil
import sys
import time
from common import core
from run_remote import ROOT, container, command, status
from run_preferences import bottleneck


def main():
    parent=ROOT.parent/'round20';deadline=time.monotonic()+14400
    status('waiting_for_complete_keyword_comparison')
    while not(parent/'selection.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Parent keyword comparison did not finish')
        time.sleep(5)
    selected=json.loads((parent/'selection.json').read_text())['selected']
    if selected['goal_met']:
        status('parent_requires_stability_or_precision_validation',selected=selected);return
    proof=json.loads((ROOT/'fine-only-cpu-preflight.json').read_text())
    assert proof['typed_wire_format_check']['all_private_headers_valid']
    assert proof['typed_wire_format_check']['intent_header_emitted']is False
    assert proof['frozen_packed_payload_bytes_identical']==6022240
    assert not(ROOT/'fine').exists()
    if not(ROOT/'before-fine').exists():
        shutil.copytree(parent/'focused/best',ROOT/'before-fine',copy_function=os.link)
        shutil.copyfile(parent/'focused/tokenizer.ttbpe',ROOT/'before-fine/tokenizer.ttbpe')
    source_sha=core.digest(ROOT/'before-fine/model.safetensors')
    assert source_sha==core.digest(parent/'focused/best/model.safetensors')
    status('preparing_one_answer_form',source_sha256=source_sha)
    if not(ROOT/'data/manifest.json').exists():command(container(0,'prepare_fine_only.py'),'prepare-fine.log',1200)
    meta=json.loads((ROOT/'fine-init/fine-model.json').read_text());assert meta['raw_weights_unchanged']
    assert meta['parameters']==11636480
    use_graphs=False
    graph_file=ROOT/'q4-graph-preflight.json';training_proof=ROOT/'graph-training-preflight/preflight.json'
    if graph_file.exists() and training_proof.exists():
        graph=json.loads(graph_file.read_text());tested=json.loads(training_proof.read_text())
        use_graphs=(graph['all_outputs_bitwise_equal'] and tested['cuda_qat_graphs']
            and tested['frozen_packed_payload_bytes_identical']==6022240
            and not tested['typed_wire_format_check']['intent_header_emitted']
            and graph['quantizer_benchmark']['observed_speedup']>=1.2)
    snapshot=ROOT/'source';snapshot.mkdir()
    for path in ROOT.glob('*.py'):shutil.copyfile(path,snapshot/path.name)
    core.save(ROOT/'fine-origin.json',{'source_sha256':source_sha,'parent':selected,
        'policy':'One finer learned answer-form tag; no emitted overlapping coarse-act tag',
        'spoken_targets_contexts_and_answer_keywords_unchanged':True,'cuda_qat_graphs':use_graphs})
    status('training_one_answer_form',steps=10000,parameters=11636480,
        effective_trainable_elements=1058560,inherited_elements_frozen=10577920,cuda_qat_graphs=use_graphs)
    extra=['--cuda-qat-graphs']if use_graphs else[]
    command(container(0,'train.py','--mode','sft','--model','fine-init','--output','fine',
        '--steps','10000','--batch-size','128','--lr','3e-5','--eval-every','1000','--qat-start','1',
        '--expanded-mlp-only','--embedding-lr-scale','1','--replay-fraction','0','--kl','.01','--intent-weight','2',
        '--branched-fraction','.3','--prefix-fraction','.15','--natural-fraction','.15',
        '--grounded-fraction','.05','--contrastive-fraction','.25','--example-balanced-loss',
        '--train-last-layers','8','--opened-audit-development','--balanced-selection',
        '--additional-development','suite/opened-audit2.jsonl',
        '--additional-scenarios','suite/opened-audit2-scenarios.json',*extra),'fine.log',14400)
    report=json.loads((ROOT/'fine/training.json').read_text());assert report['inherited_parameters_verified']
    chosen=next((v for v in report['history']if v['step']==report['best_step']),report['baseline'])
    item={'mode':'fine','step':report['best_step'],'goal_met':chosen['goal_met'],
        'score':chosen['selection_score'],'bottleneck_ratio':bottleneck(chosen),
        'development_partitions':chosen['development_partitions'],
        'two_consecutive_goal_checks':bool(report.get('early_stop_reason'))}
    command(container(0,'pack_candidate.py','--model','fine/best','--output','fine/model.ttq4',
        '--report','fine/packed.json'),'fine-packed.log')
    shutil.copyfile(ROOT/'fine-init/tokenizer.ttbpe',ROOT/'fine/tokenizer.ttbpe')
    packed=json.loads((ROOT/'fine/packed.json').read_text());table=(ROOT/'fine/tokenizer.ttbpe').stat().st_size
    total=packed['file_bytes']+table+1048576+262144;assert total<8388608
    core.save(ROOT/'fine/memory-budget.json',{'packed_bytes':packed['file_bytes'],'tokenizer_bytes':table,
        'fp16_kv_context128_bytes':1048576,'reserve_bytes':262144,'total_design_bytes':total,
        'remaining_from_8mib':8388608-total,'native_runtime_measured':False})
    (ROOT/'operations').mkdir(exist_ok=True)
    command([sys.executable,'verify_inherited_payload.py','--source',str(ROOT.parent/'round17/expanded/model.ttq4'),
        '--trained','fine/model.ttq4','--output','operations/inherited-packed-after-training.json'],'inheritance.log',120)
    core.save(ROOT/'selection.json',{'selected':item,'candidates':[item],'comparison_finished':True,'reserved_audit3_opened':False})
    status('development_target_met'if item['goal_met']and item['two_consecutive_goal_checks']else'needs_next_iteration',selected=item)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}');raise
