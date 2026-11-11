"""Merged Q4 tool profiles and an immutable compiler profile, same architecture."""
import json
import shutil
import torch
from ac_common import ROOT,SOURCE,INITIAL,INITIAL_PACKET,HERE,ARMS,write,sha,output_ids,ACTIONS,ACTION_IDS
from ac_model import Agent
from ac_protocol import header_ids
from native_quant import attach,export
from native_export import packet


def manifest(folder,source,role,**extra):
    write(folder/'manifest.json',{'arm':'asm','quantization_mode':'q4','role':role,'packed_sha256':sha(folder/'model.mkqb'),
          'checkpoint_files':{p.name:sha(p)for p in source.iterdir()if p.is_file()},'working_context':1024,
          'physical_picocalc_measured':False,**extra})


def main():
    torch.set_num_threads(4);pre=json.loads((ROOT/'preselected.json').read_text())
    folder=ROOT/'export/compiler';folder.mkdir(parents=True,exist_ok=True)
    shutil.copytree(INITIAL,folder/'hf',dirs_exist_ok=True);shutil.copyfile(INITIAL_PACKET,folder/'model.mkqb')
    shutil.copyfile(SOURCE/'output-token-ids.json',folder/'output-token-ids.json');manifest(folder,folder/'hf','immutable_compiler')
    for arm in ARMS:
        agent=Agent('cpu',ROOT/arm/'best.safetensors');master=agent.merged_master();folder=ROOT/'export'/arm;folder.mkdir(parents=True,exist_ok=True)
        master.save_pretrained(folder/'hf',safe_serialization=True);agent.tokenizer.save_pretrained(folder/'hf')
        attach(master,'q4');export(master,folder/'model.mkqb','q4')
        assert packet(folder/'model.mkqb')[1]==packet(ROOT/arm/'audit.mkqb')[1]
        write(folder/'output-token-ids.json',output_ids(agent.tokenizer))
        write(folder/'protocol.json',{'wire_end_token':30,'segmented_primer':True,'action_ids':dict(zip(ACTIONS,ACTION_IDS)),
              'neural_headers':{a:header_ids(agent.tokenizer,a)for a in ['write','run']},
              'single_program_representation':'full HEX with unchanged lossless FF macros','retired_actions':['patch','diag'],
              'initial_generation_profile':'compiler','existing_program_profile':arm,'same_weight_buffer_reused':True})
        manifest(folder,folder/'hf','tool_adapter_merged',rank=4,adapter_parameters=17920,action_parameters=640,
                 selected_block=pre['choices'][arm]['block'],adapter_sha256=sha(ROOT/arm/'best.safetensors'),
                 frozen_base_digest=json.loads((ROOT/'prepared.json').read_text())['frozen_base_digest'],
                 parameter_count=sum(p.numel()for p in master.parameters()),output_rows=29)
        runtime=folder/'runtime';runtime.mkdir(exist_ok=True)
        for n in ['ac_runtime.py','ac_protocol.py','ac_common.py','hf_runtime.py','ha_runtime.py','ha_protocol.py','full_isa_math.py','full_isa_protocol.py']:
            shutil.copyfile(HERE/n,runtime/n)
    shutil.copytree(ROOT/'export'/pre['selected_arm'],ROOT/'export/selected-research',dirs_exist_ok=True)
    write(ROOT/'final-export.json',{'selected_arm':pre['selected_arm'],'compiler_packet_sha256':sha(INITIAL_PACKET),
                                  'release_eligible_on_validation':pre['release_eligible'],'runtime_profiles_share_one_buffer':True})


if __name__=='__main__':main()
