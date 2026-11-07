"""CPU replay and actual FP16 KV probes for BOTH trained composition candidates."""
import argparse
import collections
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer

from compose_common import ARMS,read,sha
from course_eval import grading_tasks
from emulator import Emulator
from harness import extract_code,check_program
from native_verify import verify_export,generate


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root
    torch.set_num_threads(2);exports={};candidates={}
    for folder in sorted((root/'export').iterdir()):
        model,report=verify_export(folder);exports[folder.name]=report
        if folder.name in ARMS:candidates[folder.name]=model
    tasks={t['id']:t for t in grading_tasks(read(root/'fresh1.jsonl')+read(root/'fresh2.jsonl')+read(root/'fresh3.jsonl'))}
    em=Emulator();details=[]
    for arm,model in candidates.items():
        tokenizer=AutoTokenizer.from_pretrained(root/'export'/arm/'hf',local_files_only=True,trust_remote_code=False)
        fresh=json.loads((root/f'results/{arm}-final.json').read_text());probes=[]
        for part in ['manual1','manual2','manual3']:
            groups=collections.defaultdict(list)
            for row in fresh['metrics'][part]['program']['details']:groups[tasks[row['id']]['expression'][0]].append(row)
            probes += [(part,pool[0])for pool in groups.values()]
        for part in ['context1024','context2048']:
            probes += [(part,row)for row in fresh['metrics'][part]['program']['details'][:2]]
        for part,row in probes:
            reply,fp32=generate(model,tokenizer,row['prompt']);half_reply,fp16=generate(model,tokenizer,row['prompt'],True)
            code=extract_code(half_reply);task=tasks[row['id']]
            passed=bool(code and'<run/>'in half_reply and check_program(em,code,task['public_tests']+task['hidden_tests'])['pass'])
            details.append({'arm':arm,'part':part,'id':row['id'],'cpu_matches_b200':reply==row['reply'],
              'fp16_matches_fp32':reply==half_reply,'fp16_program_pass':passed,'original_program_pass':row['pass'],
              'fp32_cache':fp32,'fp16_cache':fp16,'cpu_reply':reply,'b200_reply':row['reply'],'fp16_reply':half_reply})
            if len(details)%5==0:print(json.dumps({'cpu_probes_checked':len(details)}),flush=True)
    frozen=json.loads((root/'frozen.json').read_text())
    for name,entry in frozen['files'].items():assert sha(root/name)==entry['sha256']
    result={'exports':exports,'compared':len(details),'cpu_b200_matches':sum(x['cpu_matches_b200']for x in details),
      'fp16_fp32_matches':sum(x['fp16_matches_fp32']for x in details),
      'fp16_kv_actual_storage_and_byte_count_verified':True,'frozen_file_hashes_verified':True,
      'max_actual_prompt_tokens':max(x['fp16_cache']['prompt_tokens']for x in details),'details':details,
      'host_attention_math':'FP32, persistent cache FP16 in half-storage probes','native_device_measured':False}
    (root/'local-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='details'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
