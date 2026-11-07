#!/usr/bin/env python3
"""Transfer an acquired reading skill to dialogue attributes, with a matched plain-output control."""
import hashlib
import json
from pathlib import Path
import shutil
import time
from run_remote import ROOT, container, command, status
from run_preferences import bottleneck


def main():
    origin = json.loads((ROOT/'transfer-origin.json').read_text())
    previous = Path(origin['previous_round'])
    deadline = time.monotonic() + 7200
    while not (previous/'selection.json').exists() or not (ROOT/'contrastive-data/teacher-audit.json').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Previous run or contrastive target audit not ready')
        time.sleep(5)
    previous_selection = json.loads((previous/'selection.json').read_text())['selected']
    if previous_selection['goal_met']:
        status('parent_requires_independent_audit', parent=previous_selection)
        return
    audit = json.loads((ROOT/'contrastive-data/teacher-audit.json').read_text())
    assert audit['pass_rate'] >= .98, 'Repair deterministic curriculum before training; do not weaken this gate'
    source = previous/'grounded65/last'
    assert hashlib.sha256((source/'model.safetensors').read_bytes()).hexdigest() == origin['reading_checkpoint_sha256']
    assert not any((ROOT/v).exists() for v in ['tagged','plain']), 'Do not overwrite a student run'
    if not (ROOT/'tagged-init').exists():
        shutil.copytree(source,ROOT/'tagged-init')
        shutil.copyfile(previous/'source-model/tokenizer.ttbpe',ROOT/'tagged-init/tokenizer.ttbpe')
    assert hashlib.sha256((ROOT/'tagged-init/model.safetensors').read_bytes()).hexdigest() == origin['reading_checkpoint_sha256']
    if not (ROOT/'base-data').exists():
        shutil.copytree(previous/'data',ROOT/'base-data')
    if not (ROOT/'data/manifest.json').exists():
        command(container(0,'combine_transfer.py'),'combine-data.log',600)
    if not (ROOT/'plain-data/manifest.json').exists():
        command(container(0,'strip_intents.py','--model','tagged-init','--data','data','--output-model','plain-init',
            '--output-data','plain-data','--device','cpu'),'strip-intents.log',600)
    snapshot = ROOT/'source'
    snapshot.mkdir(exist_ok=True)
    for path in ROOT.glob('*.py'):
        shutil.copyfile(path,snapshot/path.name)
    candidates = []
    # One student at a time: prevents its SGD from contending with the TP2 teacher during another student's grading.
    for gpu,label,data in [(0,'tagged','data'),(1,'plain','plain-data')]:
        status('training_attribute_transfer', mode=label, steps=8000, source=origin['reading_checkpoint_sha256'],
            contrastive_fraction=.5, natural_fraction=.35, reading_fraction=.05, earlier_acts_fraction=.1)
        command(container(gpu,'train.py','--mode','sft','--model',label+'-init','--data',data,'--output',label,
            '--steps','8000','--batch-size','128','--lr','1e-5','--eval-every','1000','--qat-start','1',
            '--embedding-lr-scale','.3','--replay-fraction','0','--kl','.005','--intent-weight','1',
            '--natural-fraction','.35','--grounded-fraction','.05','--contrastive-fraction','.5',
            '--example-balanced-loss','--train-last-layers','8','--opened-audit-development','--balanced-selection',
            '--additional-development','suite/opened-audit2.jsonl',
            '--additional-scenarios','suite/opened-audit2-scenarios.json'),label+'.log',14400)
        report = json.loads((ROOT/label/'training.json').read_text())
        chosen = next((v for v in report['history'] if v['step']==report['best_step']),report['baseline'])
        item = {'mode':label,'step':report['best_step'],'goal_met':chosen['goal_met'],
            'score':chosen['selection_score'],'bottleneck_ratio':bottleneck(chosen),
            'development_partitions':chosen['development_partitions'],
            'two_consecutive_goal_checks':bool(report.get('early_stop_reason'))}
        candidates.append(item)
        command(container(gpu,'pack_candidate.py','--model',label+'/best','--output',label+'/model.ttq4',
            '--report',label+'/packed.json'),label+'-packed.log')
        shutil.copyfile(ROOT/(label+'-init/tokenizer.ttbpe'),ROOT/label/'tokenizer.ttbpe')
        packed = json.loads((ROOT/label/'packed.json').read_text())
        table = (ROOT/label/'tokenizer.ttbpe').stat().st_size
        total = packed['file_bytes'] + table + 1048576 + 262144
        assert total < 8388608
        (ROOT/label/'memory-budget.json').write_text(json.dumps({'packed_bytes':packed['file_bytes'],
            'tokenizer_bytes':table,'fp16_kv_context128_bytes':1048576,'reserve_bytes':262144,
            'total_design_bytes':total,'remaining_from_8mib':8388608-total,'native_runtime_measured':False},indent=2))
        candidates.sort(key=lambda v:(v['goal_met'],v['bottleneck_ratio'],v['score']),reverse=True)
        (ROOT/'selection.json').write_text(json.dumps({'selected':candidates[0],'candidates':candidates,
            'reserved_audit3_opened':False,'comparison_finished':label=='plain' or item['two_consecutive_goal_checks']},indent=2))
        if item['goal_met'] and item['two_consecutive_goal_checks']:
            status('development_target_met',selected=item)
            return
    status('needs_next_iteration',selected=candidates[0])


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}')
        raise
