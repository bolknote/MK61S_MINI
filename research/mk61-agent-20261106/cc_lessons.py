"""Four-way SPEC/code contrasts and verified replay in the unchanged public format."""
import collections
import concurrent.futures
import hashlib
import json
from cc_common import ROOT,CB_ROOT,CB_RESULTS,ACTOR,read,write,rows,save_rows,sha
from cb_lessons import clean_chunk,target
from cb_runtime import session_type,snapshot,render
from ar_spec import infer
from bl_spec import install
from bl_vm import CachedVM
from be_language import paths3
from aq_protocol import prompt_ids,header_ids,NO_BODY,END
from ha_protocol import bytes_text
from transformers import AutoTokenizer

def onpolicy(goals,held):
    install();vm=CachedVM(2048);Session=session_type('original');byid={g['id']:g for g in goals};out=[];counts=collections.Counter()
    sources=[]
    for split in ['development','retention']:
        for role in ['parent','step-1200']:
            for form in ['original','notes']:sources.append(CB_RESULTS/f'{role}-{split}-{form}.json')
    for role in ['parent','final']:
        for form in ['original','notes']:sources.append(CB_RESULTS/f'closed-{role}-{form}.json')
    for path in sources:
        for record in read(path)['own']['records']:
            g=byid.get(record['task_id'])
            if g is None:continue
            s=Session(g,g['reference_body']if record['initially_correct']else g['bad_body'],vm,'spec',record['initial_spec'],True)
            for h in record['history']:
                generation=h.get('generation',{})
                if generation.get('profile')=='actor':
                    action,body,hyp,good=target(s,g,vm)
                    out.append({'task_id':g['id'],'question':g['task'],'family':g['family'],'state':snapshot(s),
                        'target_spec':g['spec'],'action':action,'body':body,'origin':'onpolicy_'+action,
                        'spec_correct':hyp,'code_correct':good,'retain':record['pass']and hyp,
                        'successful_repair_replay':record['pass']and not record['initially_correct'],
                        'missed_review':action=='diag'and generation.get('action')in ['write','done'],
                        'source_report':path.name,'source_action':generation.get('action')})
                if h['kind']=='generation_error':break
                if h['kind']=='replan':
                    s.pending_replan=False;s.replan_attempted=True;s.apply_replan(h['body'])
                elif h.get('harness_forced')=='missing_public_run':
                    assert s.pending_runs and s.pending_runs.pop(0)==h['body'][0];s.apply_action('run',h['body'])
                elif generation and generation.get('action'):
                    try:s.apply_action(generation['action'],generation['body'])
                    except(ValueError,ArithmeticError,RuntimeError)as error:
                        s.observation='ERROR '+str(error);s.history.append({'kind':'error','observation':s.observation})
                    if h['kind']=='write':assert s.body==h['body']
            counts['episodes']+=1
    return out,dict(counts)

def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'lessons-frozen.json').exists():return
    assert read(ROOT/'teacher-frozen.json')['complete'];goals=rows(ROOT/'retired-train.jsonl')+rows(ROOT/'train.jsonl')
    retained={g['id']for g in rows(ROOT/'retention.jsonl')};assert not retained&{g['id']for g in goals}
    held={tuple(t)for v in read(ROOT/'ast-frozen.json')['held_triples'].values()for t in v}
    out=[];chunks=[goals[i:i+12]for i in range(0,len(goals),12)]
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for i,batch in enumerate(pool.map(clean_chunk,chunks)):
            out.extend(batch)
            if i%8==0:print({'clean_chunks':i+1,'of':len(chunks),'states':len(out)},flush=True)
    additional,info=onpolicy(goals,held);out.extend(additional)
    tok=AutoTokenizer.from_pretrained(ACTOR/'hf',local_files_only=True);kept=[];stats=collections.Counter();labels=collections.defaultdict(set)
    for row in out:
        state=row['state'];action=row['action']
        # Legacy prompts do not always reveal an already-used review. Do not
        # assign a different target solely from that hidden flag.
        if state['replan_attempted']and not row['spec_correct']:
            stats['used_wrong_review_unobservable_excluded']+=1;continue
        if any(paths3(s['X'])&held for s in [row['target_spec'],state['declared_spec']]):
            stats['held_path_excluded']+=1;continue
        try:
            if paths3(infer(state['body'],state['pool'],state['view']['angle'])['X'])&held:
                stats['held_path_excluded']+=1;continue
        except(ValueError,ArithmeticError,KeyError):pass
        text=render(state,'original');tokens=prompt_ids(tok,text)
        tail=[]if action in NO_BODY else header_ids(tok,action)+tok.encode(bytes_text(row['body']),add_special_tokens=False)+[END]
        if len(tokens)+len(tail)>1000:stats['overlength_excluded']+=1;continue
        assert not set(tokens)&set(__import__('cc_common').ACTION_IDS)
        row.update(prompt=text,input_tokens=len(tokens))
        if row['origin']=='clean_initial':
            row['quad_id']=row['task_id']+':'+hashlib.sha256(row['question'].encode()).hexdigest()[:12]+':'+str(state['case'])
            row['quad_side']=str(int(row['spec_correct']))+str(int(row['code_correct']))
        labels[text].add(action);kept.append(row)
    conflicts={p for p,v in labels.items()if len(v)>1};unique={}
    for row in kept:
        if row['prompt']in conflicts:stats['conflicting_prompt_rows_excluded']+=1;continue
        key=(row['prompt'],row['action']);old=unique.get(key)
        if old is not None:
            for field in ['retain','successful_repair_replay','missed_review']:old[field]=old.get(field,False)or row.get(field,False)
            if row.get('quad_id'):old.update(quad_id=row['quad_id'],quad_side=row['quad_side'])
            continue
        unique[key]=row
    kept=list(unique.values());groups=collections.defaultdict(dict)
    for i,row in enumerate(kept):
        row['id']=f'cc:state:{i:06}'
        if row.get('quad_id'):groups[row['quad_id']][row['quad_side']]=i
        stats['action_'+row['action']]+=1
    quads=[list(v[x]for x in ['00','01','10','11'])for v in groups.values()if set(v)=={'00','01','10','11'}]
    assert quads and any(r.get('missed_review')for r in kept)and any(r.get('successful_repair_replay')for r in kept)
    save_rows(ROOT/'lessons.jsonl',kept);write(ROOT/'quadruples.json',quads)
    write(ROOT/'label-check.json',{'original_conflicting_prompts':len(conflicts),'retained_conflicting_prompts':0,'hidden_review_flag_not_used_for_targets':True,
        'retention_goal_ids_excluded':True,'states':len(kept),'complete_four_way_groups':len(quads),'onpolicy':info,'counts':dict(stats)})
    names=['lessons.jsonl','quadruples.json','label-check.json']
    write(ROOT/'lessons-frozen.json',{'complete':True,'files':{n:sha(ROOT/n)for n in names},'states':len(kept),'four_way_groups':len(quads),'onpolicy':info,'stats':dict(stats)})
    print(read(ROOT/'lessons-frozen.json'),flush=True)

if __name__=='__main__':main()
