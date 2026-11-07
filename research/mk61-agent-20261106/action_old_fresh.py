"""Post-selection system comparison on the same new final tasks."""
import argparse
import json
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from aa_common import INITIAL,INITIAL_PACKET,SOURCE,read,write,sha,compact_head
from hf_eval import evaluate,tool_panel
from lowbit import load


def normalize(panel,tasks,seeds):
    lookup={t['id']:t for t in tasks};details=[]
    for row,item in zip(panel['details'],seeds):
        total=len(lookup[item['task_id']]['public_tests'])
        executed=set(range(total))if item.get('pre_run_all')else{0}
        for event in row['history']:
            kind=event['kind']
            if kind in ['write','patch']:executed.clear()
            if kind in ['write','patch','run']:
                try:executed.add(int(json.loads(event['observation'])['case'],16))
                except (ValueError,KeyError,TypeError):pass
        covered=len(executed)==total
        # Correct programs already satisfy the stopped-state contract in grading.
        details.append({'id':row['id'],'pass':row['program_correct']and row['finished']and covered,
                        'false_DONE':row['finished']and not row['program_correct'],
                        'public_cases':total,'all_public_cases_covered':covered,
                        'initially_correct':item['intentionally_correct']})
    def stats(rows):
        return {'total':len(rows),'passed':sum(r['pass']for r in rows),'false_DONE':sum(r['false_DONE']for r in rows)}
    return {**stats(details),'initially_wrong':sum(not r['initially_correct']for r in details),
            'repaired':sum(r['pass']and not r['initially_correct']for r in details),
            'by_public_count':{str(n):stats([r for r in details if r['public_cases']==n])for n in range(1,5)},
            'details':details,'coverage_reconstructed_from_actual_run_events':True}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    assert(root/'preselected.json').exists(),'Only after checkpoint choices are frozen'
    torch.set_num_threads(4);tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load(model,INITIAL_PACKET);model.eval()
    compact_head(model,json.loads((SOURCE/'output-token-ids.json').read_text()))
    tasks=read(root/'fresh.jsonl');seeds=read(root/'fresh-seeds.jsonl')
    lang=evaluate(model,tokenizer,tasks);panel=tool_panel(model,tokenizer,tasks,seeds,gate=False,max_turns=10)
    result={'label':'old-v3-original-protocol','language':lang,'tools':panel,'strict_tools':normalize(panel,tasks,seeds),
            'source_packet_sha256':sha(INITIAL_PACKET),'source_master_sha256':sha(INITIAL/'model.safetensors'),
            'used_for_selection':False,'runtime_has_hidden_answers':False,
            'comparison_is_training_and_harness_together':True}
    write(root/'old-v3-final.json',result)
    print(json.dumps({'old_language':[lang['passed'],lang['total']],
                      'old_strict_tools':{k:v for k,v in result['strict_tools'].items()if k not in ['details','by_public_count']}}),flush=True)


if __name__=='__main__':main()
