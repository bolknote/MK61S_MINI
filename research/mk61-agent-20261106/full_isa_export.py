"""Copy exact audited packets and disclose measured per-command capabilities."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM

from full_isa_common import ROOT,INITIAL,read,sha,write,allowed
from full_isa_protocol import prompt,REGISTERS
from native_export import packet
from native_quant import attach,export


def main():
    torch.set_num_threads(4);selection=json.loads((ROOT/'preselected.json').read_text());records={}
    for label in ['baseline','full-best','full-endpoint','protected-best','protected-endpoint']:
        arm=label.split('-')[0];role=label.split('-')[-1]
        source=INITIAL if label=='baseline'else ROOT/arm/('last'if role=='endpoint'else'best')
        audit=json.loads((ROOT/'results'/(label+'.json')).read_text());actual=ROOT/'results'/(label+'.mkqb')
        assert sha(actual)==audit['packed_sha256']
        model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False);attach(model,'q4')
        header,payload=packet(actual)
        with tempfile.TemporaryDirectory()as tmp:
            another=Path(tmp)/'again.mkqb';export(model,another,'q4');h,p=packet(another)
            assert payload==p and header['tensors']==h['tensors']
        folder=ROOT/'export'/label;folder.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(actual,folder/'model.mkqb');shutil.copytree(source,folder/'hf',dirs_exist_ok=True)
        write(folder/'output-token-ids.json',allowed());(folder/'prompt-template.txt').write_text(prompt('{USER_TASK}',angle='RAD'))
        cfg=model.config;manifest={'arm':arm,'role':role,'quantization_mode':'q4','format':'MKQBv1',
          'parameters':sum(p.numel()for p in model.parameters()),'packed_bytes':actual.stat().st_size,'packed_sha256':sha(actual),
          'payload_sha256':hashlib.sha256(payload).hexdigest(),'checkpoint_files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},
          'selected_step':0 if label=='baseline'else 8000 if role=='endpoint'else selection['choices'][arm]['best_step'],
          'original_russian_vocab':8192,'input_vocab_rows':cfg.vocab_size,'output_rows':len(allowed()),
          'training_context':cfg.max_position_embeddings,'native_context1024_also_exported':True,'native_kv_storage':'FP32',
          'fp16_kv_bytes_per_token':2*cfg.num_hidden_layers*cfg.num_key_value_heads*cfg.head_dim*2,
          'program_cells':105,'registers':REGISTERS,'angle_modes':['RAD','DEG','GRAD'],'max_new_tokens':352,
          'reply_protocol':'<write>HEX</write><run/>; <trace/>; <done/>','fixed_reply_prefix':'',
          'all_256_reference_opcodes_executed':True,'reference_coverage_is_not_model_mastery':True,'no_seven_operation_calc':True,
          'audited_packet_copied_without_requantization':True,'reexport_payload_identical':True,
          'output_ids_sha256':sha(folder/'output-token-ids.json'),'prompt_template_sha256':sha(folder/'prompt-template.txt'),
          'new_audit_used_for_selection':False,'physical_picocalc_measured':False}
        write(folder/'manifest.json',manifest)
        capabilities={'documented_instruction_scores':audit['main']['documented_instructions'],'by_group':audit['main']['by_group'],
          'scientific_and_control_scores':audit['main']['by_kind'],'natural_transfer':[audit['natural']['passed'],audit['natural']['total']],
          'user_reproductions':[audit['observed_user_reproductions']['passed'],audit['observed_user_reproductions']['total']],
          'explicit_numeric_literals':True,'program_continuations_tested':True,'reference_full_coverage':True,
          'all_operations_mastered':False,'physical_picocalc_measured':False}
        write(folder/'capabilities.json',capabilities);records[label]=manifest;del model
    chosen=selection['primary_selected_arm']+'-best'
    shutil.copytree(ROOT/'export'/chosen,ROOT/'export/selected-budget',dirs_exist_ok=True)
    write(ROOT/'final-export.json',{'selected_label':chosen,'exports':records,'selection_used_new_audit':False})
    print(json.dumps({'selected':chosen,'packets':{k:v['packed_sha256']for k,v in records.items()}}),flush=True)


if __name__=='__main__':main()
