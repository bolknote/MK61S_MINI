"""Export merged 3M Q4 profiles with two auxiliary scores in unused rows."""
import json
import shutil
import torch
from ai_common import ROOT,HERE,COMPILER,COMPILER_PACKET,COMPILER_SOURCE,ARMS,PANELS,ACTIONS,ACTION_IDS,CORRECT_IDS,output_ids,compact_head,read,write,sha
from ai_model import Agent
from ac_protocol import header_ids
from native_quant import attach,export
from native_export import packet


def manifest(folder,role,**extra):
    write(folder/'manifest.json',{'arm':'asm','quantization_mode':'q4','role':role,'packed_sha256':sha(folder/'model.mkqb'),
       'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'working_context':1024,
       'physical_picocalc_measured':False,**extra})


def terminal_diagnostics():
    # Fixed last block, never picked by exam performance and never promoted here.
    # This shows the actual SGD effect if the retention gate kept block zero.
    from ai_eval import panel
    report={};tasks=read(ROOT/'fresh.jsonl');block=json.loads((ROOT/'policy.json').read_text())['blocks']
    scratch=[t for level,n in [(1,24),(2,24),(3,16)]for t in[t for t in tasks if t['level']==level][:n]]
    generations=json.loads((ROOT/'scratch-compiler.json').read_text())
    scratch_seeds=[{'task_id':t['id'],'compiler_generation':g,'intentionally_correct':False}for t,g in zip(scratch,generations)]
    for arm in ARMS:
        path=ROOT/arm/'terminal-fresh-audit.json'
        if path.exists():report[arm]=json.loads(path.read_text());continue
        agent=Agent(arm,'cuda',ROOT/arm/'last.safetensors');model,_=agent.packed(ROOT/arm/'terminal.mkqb');tokenizer=agent.tokenizer
        folder=ROOT/'export'/(arm+'-terminal');folder.mkdir(parents=True,exist_ok=True);master=agent.merged_master()
        master.save_pretrained(folder/'hf',safe_serialization=True);tokenizer.save_pretrained(folder/'hf');attach(master,'q4');export(master,folder/'model.mkqb','q4')
        assert packet(folder/'model.mkqb')[1]==packet(ROOT/arm/'terminal.mkqb')[1]
        write(folder/'output-token-ids.json',output_ids(tokenizer))
        protocol=json.loads((ROOT/'export'/arm/'protocol.json').read_text())
        protocol['correctness_threshold']=json.loads((ROOT/arm/f'development-{block}.json').read_text())['threshold']
        write(folder/'protocol.json',protocol);manifest(folder,'diagnostic_terminal_tool',training_arm=arm,terminal_block=block,
          selected=False,exam_used_for_selection=False,parameter_count=sum(p.numel()for p in master.parameters()),trainable_parameters=agent.trainable_count())
        runtime=folder/'runtime';runtime.mkdir(exist_ok=True)
        for name in ['ac_runtime.py','ac_protocol.py','ha_protocol.py','hf_runtime.py','ha_runtime.py']:shutil.copyfile(HERE/name,runtime/name)
        del master
        del agent
        model.cuda().eval();compact_head(model,output_ids(tokenizer));result={}
        for part,taskfile,seedfile in PANELS:
            result[part]={'raw':panel(model,tokenizer,read(ROOT/taskfile.format(split='fresh')),read(ROOT/seedfile.format(split='fresh')))[0]}
        result['from_scratch']={'raw':panel(model,tokenizer,scratch,scratch_seeds)[0]}
        result.update(split='fresh',fixed_terminal_block=json.loads((ROOT/'policy.json').read_text())['blocks'],
            exam_used_for_selection=False,diagnostic_only=True,checkpoint_sha256=sha(ROOT/arm/'last.safetensors'),packet_sha256=sha(ROOT/arm/'terminal.mkqb'))
        write(path,result);report[arm]=result;del model;torch.cuda.empty_cache()
        print(json.dumps({'terminal_diagnostic':arm,'main_passed':result['main']['raw']['passed'],'main_false_DONE':result['main']['raw']['false_DONE']}),flush=True)
    write(ROOT/'terminal-diagnostics.json',{'diagnostic_only':True,'fixed_checkpoint':'last block for each arm; no exam selection',
        'preselected_sha256_unchanged':sha(ROOT/'preselected.json'),'reports':{arm:{k:{n:v for n,v in p['raw'].items()if n not in ['details','calibration']}for k,p in r.items()if isinstance(p,dict)and'raw'in p}for arm,r in report.items()}})


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
    pre_hash=sha(ROOT/'preselected.json');terminal_diagnostics();assert sha(ROOT/'preselected.json')==pre_hash


if __name__=='__main__':main()
