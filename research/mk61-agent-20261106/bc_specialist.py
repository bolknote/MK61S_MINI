"""Supplementary self-check profile, chosen on development before viewing exam results."""
import json
import time
import torch
from aq_protocol import header_ids
from bc_common import ROOT,HERE,read,write,sha,check_frozen,ACTIONS,ACTION_IDS,CORRECT_IDS,output_ids,compact_head
from bc_model import Agent
from bc_eval import evaluate


def main():
    check_frozen();policy=read(ROOT/'specialist-policy.json')
    assert sha(HERE/'bc_specialist.py')==policy['source_sha256']
    checkpoint=ROOT/'seed-b/blend-0p75.safetensors'
    assert sha(checkpoint)==policy['checkpoint_sha256']
    assert sha(ROOT/'preselected.json')==policy['balanced_selection_sha256']
    out=ROOT/'safety';out.mkdir(exist_ok=True)
    assert not(out/'closed.json').exists()
    folder=ROOT/'export/safety';folder.mkdir(parents=True,exist_ok=True)
    agent=Agent(checkpoint=checkpoint);tokenizer=agent.tokenizer
    model,_=agent.packed(folder/'model.mkqb')
    agent.merged_master().save_pretrained(folder/'hf',safe_serialization=True);tokenizer.save_pretrained(folder/'hf')
    write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','profile':'supplementary-self-check',
        'quantization_mode':'q4','parameter_count':3022080,'packed_sha256':sha(folder/'model.mkqb'),
        'packed_bytes':(folder/'model.mkqb').stat().st_size,'selected_step':4000,'recovery_alpha':.75,
        'checkpoint_sha256':sha(checkpoint),'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},
        'selection_used_closed_test':False,'passes_balanced_retention_guards':False,
        'selection_policy_sha256':sha(ROOT/'specialist-policy.json')})
    write(folder/'protocol.json',{'kind':'semantic-spec-selfcheck-v1','arm':'spec','context':1024,
        'codec':'ay_codec.py','actions':ACTIONS,'action_ids':ACTION_IDS,'correct_ids':CORRECT_IDS,
        'neural_headers':{a:header_ids(tokenizer,a)for a in ['write','run','diag']}})
    write(out/'status.json',{'phase':'closed_Q4','unix':time.time()})
    model.cuda().eval();compact_head(model,output_ids(tokenizer))
    write(out/'closed.json',evaluate(model,tokenizer,'closed'))
    from bc_retired import evaluate as known_regression
    write(out/'retired19-regression.json',known_regression(model,tokenizer))
    write(folder/'output-token-ids.json',output_ids(tokenizer));check_frozen()
    assert sha(ROOT/'preselected.json')==policy['balanced_selection_sha256']
    write(out/'status.json',{'phase':'complete','optimizer_updates':0,'unix':time.time()})
    print(json.dumps({'supplementary_self_profile_complete':True,'optimizer_updates':0}),flush=True)


if __name__=='__main__':
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;main()
