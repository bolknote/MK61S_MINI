"""Choose correction strength on development states before inspecting the exam."""
import argparse
import json
import math
import torch
import torch.nn.functional as F
from safetensors.torch import load_file,save_file
from ak_common import ROOT,PANELS,ACTIONS,ACTION_IDS,ARMS,read,write,sha
from ak_model import load,set_heads
from ak_jobs import evaluate,score,brief,export_profile
from aj_teacher import make_session,row
from full_isa_vm import FullVM
from ac_protocol import prompt_ids
from af_model import aligned_q4


def prepare():
    base=json.loads((ROOT/'initial-development.json').read_text());vm=FullVM();states={}
    for name,taskfile,seedfile in PANELS:
        tasks={t['id']:t for t in read(ROOT/taskfile.format(split='development'))};seeds=read(ROOT/seedfile.format(split='development'))
        for seed,episode in zip(seeds,base[name]['details']):
            t=tasks[seed['task_id']];s=make_session(t,seed,vm)
            for h in episode['history']:
                if'prompt'not in h or'generation'not in h:continue
                assert s.request()==h['prompt'];r=row(s,t,'calibration_only');states[r['prompt']]=r
                g=h['generation']
                if g.get('codec_error'):break
                s.apply_action(g['action'],g['body'])
                if s.finished or s.abstained:break
    rows=list(states.values());model,tokenizer=load();features=[];labels=[]
    for at in range(0,len(rows),32):
        chunk=rows[at:at+32];enc=[prompt_ids(tokenizer,r['prompt'])for r in chunk];keep=[i for i,p in enumerate(enc)if len(p)<1016]
        if not keep:continue
        n=max(len(enc[i])for i in keep);ids=torch.zeros((len(keep),n),dtype=torch.long,device='cuda');mask=torch.zeros_like(ids)
        for j,i in enumerate(keep):ids[j,:len(enc[i])]=torch.tensor(enc[i],device='cuda');mask[j,:len(enc[i])]=1
        with torch.inference_mode():h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state;features.append(h[torch.arange(len(ids),device='cuda'),mask.sum(1)-1].float())
        labels += [rows[at+i]['action']=='done'and rows[at+i]['correctness']and rows[at+i]['eligible_for_DONE']for i in keep]
    h=torch.cat(features);ready=torch.tensor(labels,device='cuda',dtype=torch.bool);original=model.get_input_embeddings().weight.detach()[ACTION_IDS].clone()
    initial=F.linear(h,original).argmax(-1);done=ACTIONS.index('done');candidates={};curves={}
    for arm in ARMS:
        heads=load_file(str(ROOT/arm/'research.safetensors'))['heads'].cuda();curve=[]
        for alpha in [0.,.01,.025,.05,.075,.1,.15,.2,.3,.4,.5,.65,.8,1.]:
            mixed=aligned_q4(original+alpha*(heads-original));pred=F.linear(h,mixed).argmax(-1)
            false=int(((pred==done)&~ready).sum());lost=int(((initial==done)&ready&(pred!=done)).sum());good=int(((pred==done)&ready).sum())
            curve.append({'alpha':alpha,'false_DONE_on_fixed_states':false,'lost_correct_DONE_on_fixed_states':lost,'correct_DONE_on_fixed_states':good})
        limit=max(1,math.floor(int(((initial==done)&ready).sum())*.02))
        eligible=[x for x in curve if x['alpha']>0 and x['lost_correct_DONE_on_fixed_states']<=limit and x['false_DONE_on_fixed_states']<=curve[0]['false_DONE_on_fixed_states']]
        ranked=sorted(eligible,key=lambda x:(x['false_DONE_on_fixed_states'],x['lost_correct_DONE_on_fixed_states'],-x['correct_DONE_on_fixed_states']))
        chosen=[]
        for x in ranked:
            q=aligned_q4(original+x['alpha']*(heads-original))
            if any(torch.equal(q,aligned_q4(original+a*(heads-original)))for a in chosen):continue
            chosen.append(x['alpha'])
            if len(chosen)==2:break
        candidates[arm]=chosen;curves[arm]=curve
    write(ROOT/'calibration-plan.json',{'development_only':True,'fresh_results_not_inspected':True,'alphas':candidates,'curves':curves,
      'static_preselection_max_lost_positive_fraction':.02,'closed_loop_selection_retains_original_strict_nonregression':True})
    print(json.dumps({'calibration_candidates':candidates,'states':len(h)}),flush=True)


def control(arm):
    plan=json.loads((ROOT/'calibration-plan.json').read_text());base=json.loads((ROOT/'initial-development.json').read_text());model,tokenizer=load()
    original=model.get_input_embeddings().weight.detach()[ACTION_IDS].clone();learned=load_file(str(ROOT/arm/'research.safetensors'))['heads'].cuda()
    best={'alpha':0.,'key':score(base,base)};save_file({'heads':original.cpu()},str(ROOT/arm/'calibrated.safetensors'));records=[]
    for alpha in plan['alphas'][arm]:
        heads=original+alpha*(learned-original);set_heads(model,heads);report=evaluate(model,tokenizer,'development');key=score(report,base)
        item={'alpha':alpha,'key':key,'summary':brief(report)};records.append(item)
        if key>best['key']:
            save_file({'heads':heads.cpu()},str(ROOT/arm/'calibrated.safetensors'));best={'alpha':alpha,'key':key}
    best['sha256']=sha(ROOT/arm/'calibrated.safetensors');write(ROOT/arm/'calibrated.json',best);write(ROOT/arm/'calibration-development.json',records)
    print(json.dumps({'arm':arm,'calibration':best}),flush=True)


def audit(arm):
    assert(ROOT/'calibration-preselected.json').exists();heads=load_file(str(ROOT/arm/'calibrated.safetensors'))['heads'];model,tokenizer=load(heads=heads)
    report=evaluate(model,tokenizer,'fresh');write(ROOT/arm/'calibrated-fresh.json',report)
    del model;model,tokenizer=load('cpu');export_profile(model,tokenizer,heads,ROOT/'export'/(arm+'-calibrated'),'development_calibration',json.loads((ROOT/arm/'calibrated.json').read_text()))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','control','audit']);ap.add_argument('--arm',choices=ARMS);a=ap.parse_args()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='prepare':prepare()
    elif a.action=='control':control(a.arm)
    else:audit(a.arm)
