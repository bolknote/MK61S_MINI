#!/usr/bin/env python3
"""Compare direct hard-example SFT with DPO using actual student mistakes on training contexts only."""
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
from run_remote import ROOT,container,command,status


def bottleneck(result):
    p=result['development_partitions']
    return min([p[k]/.8 for k in ['previous_dev_direct','opened_audit_direct','opened_audit2_direct']]+
               [v/.72 for v in p['context_rates']]+[v/.78 for v in p['multi_turn_rates']])


def main():
    status('probing_preference_pipeline')
    command(container(1,'make_pairs.py','--output','pairs-probe','--limit','64','--natural-only','--min-pairs','1'),'pairs-probe.log')
    status('mining_actual_training_mistakes',contexts=6000,new_audit_opened=False)
    command(container(1,'make_pairs.py','--output','pairs','--limit','6000','--natural-only'),'pairs.log',7200)
    status('training_preferences',steps=4000,arms=['dpo','hard_sft'])
    def worker(item):
        gpu,mode=item
        command(container(gpu,'train.py','--mode',mode,'--output',mode,'--steps','4000','--batch-size','64','--lr','8e-6',
            '--eval-every','500','--qat-start','1','--embedding-lr-scale','1','--replay-fraction','0','--kl','0.02',
            '--beta','0.1','--preference-weight','1','--intent-weight','1','--uniform-groups','--freeze-word-embeddings',
            '--train-last-layers','8','--opened-audit-development','--balanced-selection',
            '--additional-development','suite/opened-audit2.jsonl','--additional-scenarios','suite/opened-audit2-scenarios.json'),mode+'.log',14400)
    with ThreadPoolExecutor(max_workers=2)as pool:list(pool.map(worker,[(1,'dpo'),(0,'hard_sft')]))
    candidates=[]
    for gpu,mode in [(1,'dpo'),(0,'hard_sft')]:
        report=json.loads((ROOT/mode/'training.json').read_text())
        chosen=next((r for r in report['history']if r['step']==report['best_step']),report['baseline'])
        candidates.append({'mode':mode,'step':report['best_step'],'goal_met':chosen['goal_met'],'score':chosen['selection_score'],
            'bottleneck_ratio':bottleneck(chosen),'acceptable':chosen['direct']['pass_rate'],'context':chosen['context_pass_rate'],
            'multi_turn':chosen['multi_turn']['pass_rate'],'development_partitions':chosen['development_partitions']})
        command(container(gpu,'pack_candidate.py','--model',mode+'/best','--output',mode+'/model.ttq4','--report',mode+'/packed.json'),mode+'-packed.log')
        shutil.copyfile(ROOT/'source-model/tokenizer.ttbpe',ROOT/mode/'tokenizer.ttbpe')
        packed=json.loads((ROOT/mode/'packed.json').read_text());table=(ROOT/mode/'tokenizer.ttbpe').stat().st_size
        total=packed['file_bytes']+table+1048576+262144;assert total<8388608
        (ROOT/mode/'memory-budget.json').write_text(json.dumps({'packed_bytes':packed['file_bytes'],'tokenizer_bytes':table,
            'fp16_kv_context128_bytes':1048576,'reserve_bytes':262144,'total_design_bytes':total,
            'remaining_from_8mib':8388608-total,'native_runtime_measured':False},indent=2))
    candidates.sort(key=lambda r:(r['goal_met'],r['bottleneck_ratio'],r['score']),reverse=True)
    (ROOT/'selection.json').write_text(json.dumps({'selected':candidates[0],'candidates':candidates,'reserved_audit3_opened':False},indent=2))
    status('development_target_met'if candidates[0]['goal_met']else'needs_next_iteration',selected=candidates[0])


if __name__=='__main__':
    try:main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}');raise
