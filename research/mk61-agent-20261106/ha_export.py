"""Export exact audited Q4 packets with the corresponding tool contract."""
import hashlib
import json
import shutil
import tempfile

import torch
from transformers import AutoModelForCausalLM

from ha_common import ROOT,INITIAL,ARMS,HERE,sha,write,allowed
from ha_protocol import prompt
from native_quant import attach,export
from native_export import packet


def main():
    torch.set_num_threads(4);selection=json.loads((ROOT/'preselected.json').read_text());policy=json.loads((ROOT/'policy.json').read_text());records={}
    for arm in ARMS:
        for role in ['baseline','best','endpoint']:
            label=arm+'-'+role;source=INITIAL if role=='baseline'else ROOT/arm/('last'if role=='endpoint'else'best')
            audit=json.loads((ROOT/'results'/(label+'.json')).read_text());actual=ROOT/'results'/(label+'.mkqb')
            assert sha(actual)==audit['packed_sha256']
            model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False);attach(model,'q4')
            header,payload=packet(actual)
            with tempfile.TemporaryDirectory()as tmp:
                another=__import__('pathlib').Path(tmp)/'again.mkqb';export(model,another,'q4');h,p=packet(another)
                assert p==payload and h['tensors']==header['tensors']
            folder=ROOT/'export'/label;folder.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(actual,folder/'model.mkqb');shutil.copytree(source,folder/'hf',dirs_exist_ok=True)
            write(folder/'output-token-ids.json',allowed());example={'task':'Подсчитай синус 22.','angle':'DEG'}
            (folder/'prompt-template.txt').write_text(prompt(example,arm))
            manifest={'arm':arm,'role':role,'quantization_mode':'q4','format':'MKQBv1','parameters':sum(x.numel()for x in model.parameters()),
              'packed_sha256':sha(actual),'packed_bytes':actual.stat().st_size,'payload_sha256':hashlib.sha256(payload).hexdigest(),
              'checkpoint_files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},
              'selected_step':0 if role=='baseline'else policy['steps_each']if role=='endpoint'else selection['choices'][arm]['best_step'],
              'input_vocab_rows':model.config.vocab_size,'original_russian_vocab':8192,'output_rows':len(allowed()),
              'working_context':1024,'training_context':1024,'model_config_context':model.config.max_position_embeddings,
              'program_cells':105,'max_serialized_bytes':512,'max_new_tokens':512,'fixed_reply_prefix':'',
              'reply_protocol':'write+run, suffix patch+run, indexed run, trace, done',
              'numeric_pool':'Lexical decimal extraction from task, with fixed 0, 1, -1; identical pool supplied to both arms',
              'assembler_directives':{}if arm=='direct'else{'FF00':'raw FF','FF01kk':'load constant kk','FF02ll':'define label ll','FF03ll':'emit BCD address of label ll'},
              'model_selects_operations':True,'all_256_raw_opcodes_available':True,'russian_free_text_reasoning_output':False,
              'runtime_feedback_contains_expected_answers':False,'fresh_used_for_selection':False,
              'native_kv_storage':'FP32','physical_picocalc_measured':False,'reexport_payload_identical':True,
              'output_ids_sha256':sha(folder/'output-token-ids.json'),'prompt_template_sha256':sha(folder/'prompt-template.txt')}
            write(folder/'manifest.json',manifest)
            write(folder/'protocol.json',{'arm':arm,'working_context':1024,'working_state_external':True,
              'protocol_source_sha256':sha(HERE/'ha_protocol.py'),'runtime_source_sha256':sha(HERE/'ha_runtime.py'),
              'patch':'first two bytes encode a body offset; replace the entire suffix from that offset',
              'trace':'actual executed PC/opcode/X, requested explicitly','run':'only public supplied inputs; hidden cases inaccessible',
              'metadata':manifest['assembler_directives']})
            runtime=folder/'runtime';runtime.mkdir(exist_ok=True)
            for name in ['ha_protocol.py','ha_runtime.py','full_isa_math.py','full_isa_protocol.py']:
                shutil.copyfile(HERE/name,runtime/name)
            records[label]=manifest;del model
    chosen=selection['primary_selected_arm']+'-best'
    shutil.copytree(ROOT/'export'/chosen,ROOT/'export/selected-budget',dirs_exist_ok=True)
    write(ROOT/'final-export.json',{'selected_label':chosen,'exports':records,'fresh_used_for_selection':False})
    print(json.dumps({'selected':chosen,'exports':len(records)}),flush=True)


if __name__=='__main__':main()

