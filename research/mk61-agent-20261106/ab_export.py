"""Exact audited Q4 exports. Research selection is separate from release approval."""
import hashlib
import json
import shutil
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM
from ab_common import ROOT,HERE,ARMS,read,write,sha
from native_quant import attach,export
from native_export import packet


def main():
    torch.set_num_threads(4);pre=json.loads((ROOT/'preselected.json').read_text());exports={}
    for arm in ARMS:
        source=ROOT/arm/'best';folder=ROOT/'export'/arm;folder.mkdir(parents=True,exist_ok=True)
        shutil.copytree(source,folder/'hf',dirs_exist_ok=True)
        model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True);attach(model,'q4');export(model,folder/'model.mkqb','q4')
        audit=ROOT/arm/'audit.mkqb'
        if audit.exists():assert packet(audit)[1]==packet(folder/'model.mkqb')[1]
        header,payload=packet(folder/'model.mkqb')
        shutil.copyfile(ROOT/'output-token-ids.json',folder/'output-token-ids.json')
        runtime=folder/'runtime';runtime.mkdir(exist_ok=True)
        for n in ['ab_common.py','ab_protocol.py','ab_runtime.py','hf_runtime.py','ha_protocol.py','ha_runtime.py','full_isa_math.py','full_isa_protocol.py']:
            shutil.copyfile(HERE/n,runtime/n)
        for n in ['aa_common.py','aa_runtime.py','aa_protocol.py']:shutil.copyfile(HERE/n,runtime/n)
        from transformers import AutoTokenizer
        from ab_protocol import header_ids
        tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True)
        write(folder/'protocol.json',{'wire_end_token':30,'segmented_primer':True,
              'neural_headers':{a:header_ids(tokenizer,a)for a in ['write','patch','run','diag']},
              'control_wire_token_is_not_input_to_KV':True,'header_chooses_no_instruction':True})
        manifest={'arm':'asm','strategy':arm,'quantization_mode':'q4','format':'MKQBv1','parameters':sum(p.numel()for p in model.parameters()),
                  'packed_sha256':sha(folder/'model.mkqb'),'payload_sha256':hashlib.sha256(payload).hexdigest(),
                  'packed_bytes':(folder/'model.mkqb').stat().st_size,'checkpoint_files':{p.name:sha(p)for p in source.iterdir()if p.is_file()},
                  'selected_stage':pre['choices'][arm]['stage'],'working_context':1024,'output_rows':31,'original_russian_input_rows':8192,
                  'action_ids':dict(zip(['WRITE','PATCH','RUN','TRACE','DIAG','DONE','UNSURE'],range(8192,8199))),
                  'control_tokens_are_existing_unused_rows':True,'runtime_contains_no_semantic_oracle':True,
                  'body_decoder_context_preserves_original_tag_prefix':True,'wire_end_token':30,
                  'reference_answers_in_feedback':False,'fresh_used_for_selection':False,'release_eligible':pre['choices'][arm]['key'][0],
                  'physical_picocalc_measured':False}
        write(folder/'manifest.json',manifest);exports[arm]=manifest
    selected=pre['selected_arm'];shutil.copytree(ROOT/'export'/selected,ROOT/'export/selected-research',dirs_exist_ok=True)
    write(ROOT/'final-export.json',{'selected_label':selected,'exports':exports,'release_eligible':pre['release_eligible'],
                                    'automatic_device_deployment':False})


if __name__=='__main__':main()
