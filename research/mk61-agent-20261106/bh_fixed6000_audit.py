"""Secondary fixed-step audit, declared before opening closed; never selects weights."""
import argparse,shutil,json,time
import torch
from bh_common import ROOT,HERE,read,write,sha,check_frozen,output_ids,compact_head
from bh_model import agent
from bh_eval import evaluate

def main(arm):
    check_frozen();assert(ROOT/'preselected.json').exists();assert all(read(ROOT/a/'training.json')['optimizer_updates']==6000 for a in ['lora','full'])
    role='fixed6000_'+arm;out=ROOT/role;out.mkdir(exist_ok=True);folder=ROOT/'export'/role;folder.mkdir(parents=True,exist_ok=True)
    checkpoint=ROOT/arm/'last.safetensors';a=agent(arm,checkpoint=checkpoint);tokenizer=a.tokenizer
    model,_=a.packed(folder/'model.mkqb');a.merged_master().save_pretrained(folder/'hf',safe_serialization=True);tokenizer.save_pretrained(folder/'hf')
    write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','training_arm':arm,'quantization_mode':'q4','parameter_count':3022080,
        'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,
        'selected_step':6000,'selected_checkpoint_sha256':sha(checkpoint),'selection_used_closed_test':False,
        'fixed_step_diagnostic_not_selected_profile':True,'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()}})
    shutil.copyfile(ROOT/'export'/arm/'protocol.json',folder/'protocol.json')
    model.cuda().eval();compact_head(model,output_ids(tokenizer));result=evaluate(model,tokenizer,'closed');write(out/'closed.json',result)
    write(folder/'output-token-ids.json',output_ids(tokenizer));write(out/'complete.json',{'complete':True,'step_fixed_before_closed':6000,
        'checkpoint_sha256':sha(checkpoint),'packed_sha256':sha(folder/'model.mkqb'),'driver_sha256':sha(HERE/'bh_fixed6000_audit.py'),'unix':time.time()})
    check_frozen();print(json.dumps({'complete':role}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['lora','full'],required=True);a=p.parse_args()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;main(a.arm)
