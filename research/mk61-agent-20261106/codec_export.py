"""Preserve every endpoint and validation-best packet exactly as audited."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import torch
from transformers import AutoModelForCausalLM

from codec_common import ROOT,ARMS,MODES,sha,allowed_ids,protocol,OLD_VOCAB
from course_common import program_prompt
from native_export import packet
from native_quant import attach,export


def main():
    torch.set_num_threads(4);selection=json.loads((ROOT/'preselected.json').read_text());records={}
    for arm in ARMS:
        for mode in MODES:
            name=arm+'-'+mode;records[name]={}
            for role,checkpoint in [('endpoint','last'),('best','best')]:
                label=name+'-'+role;result=json.loads((ROOT/'results'/(label+'.json')).read_text())
                actual=ROOT/'results'/(label+'.mkqb');source=ROOT/name/checkpoint
                assert sha(actual)==result['packed_sha256']
                assert(ROOT/'preselected.json').stat().st_mtime<=actual.stat().st_mtime
                model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False);attach(model,'q4')
                header,payload=packet(actual)
                with tempfile.TemporaryDirectory()as tmp:
                    path=Path(tmp)/'again.mkqb';export(model,path,'q4');other,content=packet(path)
                    assert payload==content and header['tensors']==other['tensors']
                folder=ROOT/'export'/role/name;folder.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(actual,folder/'model.mkqb');shutil.copytree(source,folder/'hf',dirs_exist_ok=True)
                for src,dst in [(ROOT/'codebook-32.json',folder/'codebook-32.json'),(ROOT/f'output-{mode}.json',folder/'output-token-ids.json')]:shutil.copyfile(src,dst)
                template=protocol(mode).encode_text(program_prompt({'task':'{USER_TASK}','public_tests':[],'hidden_tests':[]}))
                (folder/'prompt-template.txt').write_text(template)
                c=model.config;kv=2*c.num_hidden_layers*c.num_key_value_heads*c.head_dim*2
                manifest={'arm':arm,'codec':mode,'role':role,'quantization_mode':'q4','format':'MKQBv1','parameters':sum(p.numel()for p in model.parameters()),
                  'packed_bytes':actual.stat().st_size,'packed_sha256':sha(actual),'payload_sha256':hashlib.sha256(payload).hexdigest(),
                  'checkpoint_files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},
                  'frozen_sha256':selection['frozen_sha256'],'original_russian_input_vocabulary':OLD_VOCAB,'total_input_rows':c.vocab_size,
                  'output_rows_computed':len(allowed_ids(mode)),'new_huffman_symbols':32,'huffman_symbol_id_start':OLD_VOCAB,
                  'fp16_kv_bytes_per_token':kv,'context_configured':c.max_position_embeddings,
                  'endpoint_step':8000,'selected_step':8000 if role=='endpoint'else selection['choices'][name]['best_step'],
                  'new_fresh_used_for_selection':False,'audited_packet_copied_without_requantization':True,'reexport_payload_identical':True,
                  'codebook_sha256':sha(folder/'codebook-32.json'),'output_ids_sha256':sha(folder/'output-token-ids.json'),
                  'prompt_template_sha256':sha(folder/'prompt-template.txt'),'standard_program_bytes':105,'extended_memory_enabled':False,
                  'audit_max_new_tokens_per_turn':160,'tested_natural_operations_max':3,'tested_formal_reference_bytes_max':16,
                  'decoder_is_lossless_only':True,'native_picocalc_measured':False}
                (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');records[name][role]=manifest
                del model
    (ROOT/'final-export.json').write_text(json.dumps({'exports':records,'primary':'endpoint','secondary':'best','native_picocalc_measured':False},indent=2)+'\n')
    print(json.dumps({name:{role:m['packed_sha256']for role,m in group.items()}for name,group in records.items()}),flush=True)


if __name__=='__main__':main()
