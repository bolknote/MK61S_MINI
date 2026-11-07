import hashlib
import json
import shutil
import tempfile
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM
from hd_common import ROOT,INITIAL,HERE,sha,write
from ha_common import allowed
from hd_runtime import prompt
from native_quant import attach,export
from native_export import packet


def main():
    torch.set_num_threads(4);selection=json.loads((ROOT/'preselected.json').read_text());records={}
    for label,source in [('asm-baseline',INITIAL),('safe-best',ROOT/'safe/best'),('active-best',ROOT/'active/best')]:
        audit=json.loads((ROOT/'results'/(label+'.json')).read_text());actual=ROOT/'results'/(label+'.mkqb');assert sha(actual)==audit['packed_sha256']
        model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False);attach(model,'q4');header,payload=packet(actual)
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp)/'again.mkqb';export(model,p,'q4');h,data=packet(p);assert data==payload and h['tensors']==header['tensors']
        folder=ROOT/'export'/label;folder.mkdir(parents=True,exist_ok=True);shutil.copyfile(actual,folder/'model.mkqb');shutil.copytree(source,folder/'hf',dirs_exist_ok=True)
        write(folder/'output-token-ids.json',allowed());(folder/'prompt-template.txt').write_text(prompt({'task':'Подсчитай синус 0.','angle':'DEG'},'asm'))
        strategy=label.split('-')[0];manifest={'arm':'asm','strategy':strategy,'role':'baseline'if label=='asm-baseline'else'best',
          'quantization_mode':'q4','format':'MKQBv1','parameters':sum(p.numel()for p in model.parameters()),'packed_sha256':sha(actual),
          'packed_bytes':actual.stat().st_size,'payload_sha256':hashlib.sha256(payload).hexdigest(),
          'checkpoint_files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},
          'selected_step':0 if label=='asm-baseline'else selection['choices'][strategy]['best_step'],'working_context':1024,'training_context':1024,
          'input_vocab_rows':model.config.vocab_size,'original_russian_vocab':8192,'output_rows':len(allowed()),'program_cells':105,'max_serialized_bytes':512,
          'max_new_tokens':512,'fixed_reply_prefix':'','numeric_pool':'same lexical pool 0,1,-1 plus task literals; unchanged from original ablation',
          'harness_generation':'harness-debug-v1','done_gate_checks_semantics':False,'max_tool_turns':6,'runtime_feedback_contains_expected_answers':False,'fresh_used_for_selection':False,'reexport_payload_identical':True,
          'output_ids_sha256':sha(folder/'output-token-ids.json'),'prompt_template_sha256':sha(folder/'prompt-template.txt'),'physical_picocalc_measured':False}
        write(folder/'manifest.json',manifest);write(folder/'protocol.json',{'arm':'asm','working_context':1024,'parent_contract':'harness-ablation-v1/asm-best','harness_generation':'harness-debug-v1','done_gate':'all public cases executed on current revision and stopped; no expected answers',
          'macros':{'FF00':'raw FF','FF01kk':'constant kk','FF02ll':'label ll','FF03ll':'label address'},'oracle_free_feedback':True})
        runtime=folder/'runtime';runtime.mkdir(exist_ok=True)
        for n in ['hd_runtime.py','ha_protocol.py','ha_runtime.py','full_isa_math.py','full_isa_protocol.py']:shutil.copyfile(HERE/n,runtime/n)
        records[label]=manifest;del model
    chosen=selection['primary_selected_arm']+'-best';shutil.copytree(ROOT/'export'/chosen,ROOT/'export/selected-budget',dirs_exist_ok=True)
    write(ROOT/'final-export.json',{'selected_label':chosen,'exports':records,'fresh_used_for_selection':False})


if __name__=='__main__':main()

