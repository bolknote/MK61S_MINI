"""Retain the exact audited Q4 packets and both trainable master checkpoints."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM

from compose_common import ROOT,ARMS,sha
from native_export import packet
from native_quant import attach,export,plain_master
from course_common import program_prompt


def main():
    torch.set_num_threads(2);selection=json.loads((ROOT/'preselected.json').read_text());manifests={}
    for arm in ARMS:
        choice=selection['choices'][arm];source=Path(choice['model'])
        actual=ROOT/f'results/{arm}-final.mkqb';report=json.loads((ROOT/f'results/{arm}-final.json').read_text())
        assert sha(actual)==report['packed']['sha256']
        assert(ROOT/'preselected.json').stat().st_mtime<=actual.stat().st_mtime
        model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False);attach(model,'q4')
        header,payload=packet(actual)
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'repacked.mkqb';export(model,path,'q4');h,p=packet(path)
            assert p==payload and h['tensors']==header['tensors']
        folder=ROOT/'export'/arm;folder.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(actual,folder/'model.mkqb');shutil.copytree(source,folder/'hf',dirs_exist_ok=True)
        template=program_prompt({'task':'{USER_TASK}','public_tests':[],'hidden_tests':[]})
        (folder/'prompt-template.txt').write_text(template)
        raw=plain_master(model);c=raw.config;kv=2*c.num_hidden_layers*c.num_key_value_heads*c.head_dim*2
        manifest={'arm':arm,'quantization_mode':'q4','format':'q4','parameters':sum(p.numel()for p in raw.parameters()),
          'packed_bytes':actual.stat().st_size,'payload_bytes':len(payload),'packed_sha256':sha(actual),
          'payload_sha256':hashlib.sha256(payload).hexdigest(),'fp16_kv_bytes_per_token':kv,
          'fp16_kv_bytes':{str(n):n*kv for n in [512,1024,2048]},'context_configured':2048,
          'checkpoint_files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},
          'phase':choice['phase'],'best_step_in_phase':choice['step'],'validation_key':choice['key'],
          'quality_gate_on_validation':choice['quality_gate'],'fresh_used_for_selection':False,
          'source_packet_sha256':selection['frozen']['source_packets'][arm],
          'prompt_template_sha256':sha(folder/'prompt-template.txt'),'tokenizer_add_special_tokens':False,
          'audited_packet_copied_without_requantization':True,'reexport_payload_identical':True,
          'standard_program_bytes':105,'expanded_memory_commands_enabled':False,'native_device_measured':False}
        (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');manifests[arm]=manifest
    shutil.copytree(ROOT/'export'/selection['winner'],ROOT/'export/selected-budget',dirs_exist_ok=True)
    (ROOT/'final-export.json').write_text(json.dumps({'selected':selection['winner'],'exports':manifests,
      'selection':selection,'native_device_measured':False},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'selected':selection['winner'],'exports':{a:m['packed_sha256']for a,m in manifests.items()}}),flush=True)


if __name__=='__main__':main()
