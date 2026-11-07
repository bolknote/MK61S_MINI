"""Export the precise audited baseline, validation-best and endpoint packets."""
import hashlib
import json
import shutil
import tempfile

import torch
from transformers import AutoModelForCausalLM

from semantic_common import ROOT,ARMS,INITIAL,read,sha,write_json,allowed_ids
from course_common import program_prompt
from native_export import packet
from native_quant import attach,export


def main():
    torch.set_num_threads(4);selection=json.loads((ROOT/'preselected.json').read_text());records={}
    for label in ['baseline',*[a+'-'+r for a in ARMS for r in ['best','endpoint']]]:
        arm=label.split('-')[0];role=label.split('-')[-1]
        source=INITIAL if label=='baseline'else ROOT/arm/('last'if role=='endpoint'else'best')
        result=json.loads((ROOT/'results'/(label+'.json')).read_text());actual=ROOT/'results'/(label+'.mkqb')
        assert sha(actual)==result['packed_sha256']
        assert sha(ROOT/'audit.jsonl')==result['audit_sha256']
        header,payload=packet(actual)
        model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False);attach(model,'q4')
        with tempfile.TemporaryDirectory()as tmp:
            path=__import__('pathlib').Path(tmp)/'again.mkqb';export(model,path,'q4');other,content=packet(path)
            assert payload==content and header['tensors']==other['tensors']
        target=ROOT/'export'/label;target.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(actual,target/'model.mkqb');shutil.copytree(source,target/'hf',dirs_exist_ok=True)
        template=program_prompt({'task':'{USER_TASK}','public_tests':[],'hidden_tests':[]})
        (target/'prompt-template.txt').write_text(template);write_json(target/'output-token-ids.json',allowed_ids('hex'))
        c=model.config
        manifest={'arm':arm,'role':role,'quantization_mode':'q4','format':'MKQBv1',
          'parameters':sum(p.numel()for p in model.parameters()),'packed_bytes':actual.stat().st_size,
          'packed_sha256':sha(actual),'payload_sha256':hashlib.sha256(payload).hexdigest(),
          'checkpoint_files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},
          'selected_step':0 if label=='baseline'else 2000 if role=='endpoint'else selection['choices'][arm]['best_step'],
          'source_starting_checkpoint':'codec-qat-v1/best/small-hex/step2000',
          'input_vocabulary_rows':c.vocab_size,'original_russian_input_rows':8192,'output_rows':len(allowed_ids('hex')),
          'fp16_kv_bytes_per_token':2*c.num_hidden_layers*c.num_key_value_heads*c.head_dim*2,
          'context':c.max_position_embeddings,'auxiliary_explanations_required_at_inference':False,
          'audit_used_for_selection':False,'audit_sha256':result['audit_sha256'],'inference_protocol':'calc+ordinary HEX+tools',
          'audited_packet_copied_without_requantization':True,'reexport_payload_identical':True,
          'output_ids_sha256':sha(target/'output-token-ids.json'),'prompt_template_sha256':sha(target/'prompt-template.txt'),
          'standard_mk61_program_bytes':105,'extended_memory_enabled':False,'physical_picocalc_measured':False}
        write_json(target/'manifest.json',manifest);records[label]=manifest;del model
    selected=selection['primary_selected_arm']+'-best'
    shutil.copytree(ROOT/'export'/selected,ROOT/'export/selected-budget',dirs_exist_ok=True)
    write_json(ROOT/'final-export.json',{'exports':records,'selected_label':selected,'primary_selection':'validation-best','audit_used_for_selection':False})
    print(json.dumps({k:v['packed_sha256']for k,v in records.items()}),flush=True)


if __name__=='__main__':main()
