"""Generate actual paired outcomes, then freeze gate targets and cached features."""
import collections
import hashlib
import json
import torch
from safetensors.torch import load_file,save_file
from cd_common import ROOT,ACTOR,PARENT,read,write,rows,save_rows,sha,check_frozen,ACTIONS,output_ids,compact_head
from cd_rollout import Decoder,feature,rollout,label,OTHER
from be_model import load
from bl_spec import install
from bl_vm import CachedVM

def make_labels(policy,progress):
    if(ROOT/'utility-frozen.json').exists():
        info=read(ROOT/'utility-frozen.json')
        for n,d in info['files'].items():assert sha(ROOT/n)==d,n
        return info
    check_frozen();install();vm=CachedVM(2048);actor,tok=load(ACTOR,'cuda:0');translator,t=load(PARENT,'cuda:0')
    assert t.get_vocab()==tok.get_vocab();compact_head(actor,output_ids(tok));compact_head(translator,output_ids(tok))
    decoder=Decoder(actor,translator,tok,policy,progress);goals={r['key']:r['goal']for r in rows(ROOT/'utility-goals.jsonl')};seeds=rows(ROOT/'utility-seeds.jsonl')
    cache=load_file(str(ROOT/'parent-features.safetensors'));audit_path=ROOT/'counterfactual-audit.jsonl'
    previous={r['id']:r for r in rows(audit_path)}if audit_path.exists()else{};audit=[];counts=collections.Counter();cache_checks=[]
    for i,seed in enumerate(seeds):
        decoder.current_case=seed['id']
        if seed['id']in previous:
            result=previous[seed['id']];assert result['prompt_sha256']==seed['prompt_sha256']
        else:
            g=goals[seed['goal_key']];index=seed.get('cache_index')
            if index is not None:
                h=cache['hidden'][index];logits=cache['teacher_logits'][index]
                if len(cache_checks)<8:
                    fresh,fl=feature(actor,tok,seed['prompt']);error=max(float((fresh-h).abs().max()),float((fl-logits).abs().max()))
                    assert torch.allclose(fresh,h,atol=1e-5,rtol=1e-5)and torch.allclose(fl,logits,atol=1e-5,rtol=1e-5)
                    cache_checks.append({'case':seed['id'],'maximum_error':error,'same_action':int(fl.argmax())==int(logits.argmax())})
            else:h,logits=feature(actor,tok,seed['prompt'])
            nonreview=ACTIONS[max(OTHER,key=lambda j:float(logits[j]))]
            a=rollout(seed,g,'diag',decoder,vm);b=rollout(seed,g,nonreview,decoder,vm);review,reason=label(a,b)
            result={'id':seed['id'],'prompt_sha256':seed['prompt_sha256'],'goal_key':seed['goal_key'],'review':review,'reason':reason,
                'nonreview_action':nonreview,'hidden':h.tolist(),'teacher_logits':logits.tolist(),'branches':{'review':a,'nonreview':b}}
            with audit_path.open('a')as stream:stream.write(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
        audit.append(result);counts['review'if result['review']is True else'nonreview'if result['review']is False else'unlabelled']+=1;counts[result['reason']]+=1
        if(i+1)%8==0:progress('paired_utility_cases',completed=i+1,maximum=len(seeds),counts=dict(counts),model_calls=decoder.calls)
        end_group=i+1==len(seeds)or seeds[i+1]['goal_key']!=seed['goal_key']
        if i+1>=policy['minimum_utility_cases']and counts['review']>=policy['minimum_review_positives']and counts['nonreview']>=policy['minimum_nonreview_labels']and end_group:break
    assert len(audit)>=policy['minimum_utility_cases']or len(audit)==len(seeds)
    seedmap={s['id']:s for s in seeds};utility=[]
    for r in audit:
        if r['review']is None:continue
        seed=seedmap[r['id']]
        utility.append({'id':r['id'],'task_id':goals[r['goal_key']]['id'],'prompt':seed['prompt'],'input_tokens':seed['input_tokens'],
            'review':r['review'],'action':'diag'if r['review']else r['nonreview_action'],'retain':False,'origin':'measured_utility',
            'reason':r['reason'],'repair_replay':False,'correct_done':False,'hidden':r['hidden'],'teacher_logits':r['teacher_logits']})
    replay=rows(ROOT/'replay.jsonl');labels=collections.defaultdict(set)
    for r in [*utility,*replay]:labels[hashlib.sha256(r['prompt'].encode()).hexdigest()].add(r['review'])
    conflicts={h for h,v in labels.items()if len(v)>1};output=[];features=[];teachers=[];seen=set()
    for row in [*utility,*replay]:
        digest=hashlib.sha256(row['prompt'].encode()).hexdigest()
        if digest in conflicts or digest in seen:continue
        seen.add(digest);r=dict(row)
        if r['origin']=='measured_utility':h=torch.tensor(r.pop('hidden'));t=torch.tensor(r.pop('teacher_logits'))
        else:h=cache['hidden'][r['cache_index']];t=cache['teacher_logits'][r['cache_index']]
        output.append(r);features.append(h);teachers.append(t)
    assert any(r['review']for r in output)and any(r['origin']=='measured_utility'and not r['review']for r in output)
    assert any(r['repair_replay']for r in output)and any(r['correct_done']for r in output)
    tensors={'hidden':torch.stack(features).contiguous(),'teacher_logits':torch.stack(teachers).contiguous(),
        'review':torch.tensor([r['review']for r in output],dtype=torch.float32),'retain':torch.tensor([r['retain']for r in output])}
    save_file(tensors,str(ROOT/'features.safetensors'));save_rows(ROOT/'lessons.jsonl',output)
    write(ROOT/'utility-summary.json',{'paired_cases':len(audit),'counts':dict(counts),'conflicting_public_prompts_excluded':len(conflicts),
        'training_rows':len(output),'utility_rows':sum(r['origin']=='measured_utility'for r in output),'review_positive_rows':sum(r['review']for r in output),
        'parent_cache_checks':cache_checks,'all_branch_answers_generated_by_frozen_models':True,'gold_used_only_for_grading':True,
        'both_failed_not_mislabeled_as_success':True,'only_training_states_used':True,'optimizer_updates':0})
    names=['features.safetensors','lessons.jsonl','counterfactual-audit.jsonl','utility-summary.json']
    info={'complete':True,'files':{n:sha(ROOT/n)for n in names},'summary':read(ROOT/'utility-summary.json')}
    write(ROOT/'utility-frozen.json',info);del actor,translator;torch.cuda.empty_cache();check_frozen();return info
