"""Export merged 3M Q4 profiles with two auxiliary scores in unused rows."""
import json
import shutil
import torch
from af_common import ROOT,HERE,COMPILER,COMPILER_PACKET,COMPILER_SOURCE,ARMS,ACTIONS,ACTION_IDS,CORRECT_IDS,output_ids,write,sha
from af_model import Agent
from ac_protocol import header_ids
from native_quant import attach,export
from native_export import packet


def manifest(folder,role,**extra):
    write(folder/'manifest.json',{'arm':'asm','quantization_mode':'q4','role':role,'packed_sha256':sha(folder/'model.mkqb'),
       'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'working_context':1024,
       'physical_picocalc_measured':False,**extra})


def main():
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False
    pre=json.loads((ROOT/'preselected.json').read_text());folder=ROOT/'export/compiler';folder.mkdir(parents=True,exist_ok=True)
    shutil.copytree(COMPILER,folder/'hf',dirs_exist_ok=True);shutil.copyfile(COMPILER_PACKET,folder/'model.mkqb')
    shutil.copyfile(COMPILER_SOURCE/'output-token-ids.json',folder/'output-token-ids.json');manifest(folder,'immutable_compiler')
    for arm in ARMS:
        agent=Agent(arm,'cuda',ROOT/arm/'best.safetensors');master=agent.merged_master();folder=ROOT/'export'/arm;folder.mkdir(parents=True,exist_ok=True)
        master.save_pretrained(folder/'hf',safe_serialization=True);agent.tokenizer.save_pretrained(folder/'hf');attach(master,'q4');export(master,folder/'model.mkqb','q4')
        assert packet(folder/'model.mkqb')[1]==packet(ROOT/arm/'audit.mkqb')[1]
        write(folder/'output-token-ids.json',output_ids(agent.tokenizer))
        write(folder/'protocol.json',{'wire_end_token':30,'segmented_primer':True,'action_ids':dict(zip(ACTIONS,ACTION_IDS)),
            'neural_headers':{a:header_ids(agent.tokenizer,a)for a in ['write','run']},
            'correctness_ids':CORRECT_IDS,'correctness_order':['incorrect','correct'],
            'correctness_threshold':pre['choices'][arm]['threshold'],'auxiliary_rows_never_input_or_wire_actions':True,
            'single_weight_buffer_reused':True,'input_Russian_vocabulary_preserved':True})
        manifest(folder,'tool_and_semantic_head',selected_block=pre['choices'][arm]['block'],training_arm=arm,
            trainable_parameters=agent.trainable_count(),parameter_count=sum(p.numel()for p in master.parameters()),
            auxiliary_parameter_rows_folded_in_original_vocabulary=True,wire_output_rows=29)
        runtime=folder/'runtime';runtime.mkdir(exist_ok=True)
        for name in ['ac_runtime.py','ac_protocol.py','ha_protocol.py','hf_runtime.py','ha_runtime.py']:
            shutil.copyfile(HERE/name,runtime/name)
    shutil.copytree(ROOT/'export'/pre['selected_arm'],ROOT/'export/selected-research',dirs_exist_ok=True)
    write(ROOT/'final-export.json',{'selected_arm':pre['selected_arm'],'compiler_packet_sha256':sha(COMPILER_PACKET),
        'source_compiler_unchanged':True,'release_eligible_on_development':pre['release_eligible'],'parameter_count':3022080})


if __name__=='__main__':main()
