"""Natural translation, limited structured replay, and fresh strict-ROM tool cycles."""
import collections
import concurrent.futures
import copy
import json
import random
from bf_common import ROOT,read,write,rows,save_rows,sha
from bf_spec import install
from be_language import question
from az_runtime import Session,goal_state
from ba_lessons import make_row,wrong_program
from bc_self import rejected_session
from ay_codec import compile_spec,encode
from ay_data import op_count
from az_teacher import pool_for
from full_isa_vm import FullVM,build
from ar_spec import verify

def goal_row(g,index,origin='natural'):
    return {'id':f'bf:{origin}:{index:06}','group_id':g['id'],'task_id':g['id'],'origin':origin,
        'family':g['family'],'action':'write','body':[],'state':goal_state(g),'target_spec':g['spec'],
        'reference_body':g['reference_body'],'spec_body':g['spec_body'],'simple':op_count(g['spec']['X'])<=2,
        'wording_source':g.get('wording_source','structured'),'point_edited':g.get('point_edited',False),'correctness':0}

def tool_chunk(goals):
    install();vm=FullVM();out=[];counts=collections.Counter()
    for g in goals:
        for case in [0,1]:
            s=Session(g,g['reference_body'],vm,'spec',g['spec'],True,start_case=case)
            s.apply_action('write',g['spec_body'])
            row=make_row(g,s,'run','run_'+str(1-case),True,[1-case]);row['simple']=False;out.append(row)
            s.apply_action('run',[1-case]);row=make_row(g,s,'done','done',True);row['simple']=False;out.append(row)
            s.apply_action('done',[]);assert s.finished
        try:
            bad,_=wrong_program(g,vm,'argument');s=Session(g,bad,vm,'spec',g['spec'],True)
            if verify(vm,bad,g['pool'],g['spec'],g['audit_inputs'])['status']=='FAIL':
                row=make_row(g,s,'write','repair',False);row['simple']=False;out.append(row)
            conflict=rejected_session(g,vm,'wrong_hypothesis')
            if not conflict.finished and conflict.history[-1]['kind']=='done_rejected':
                assert verify(vm,conflict.body,g['pool'],g['spec'],g['audit_inputs'])['status']=='TESTED'
                row=make_row(g,conflict,'unsure','unsure',True);row['simple']=False;out.append(row)
        except (ValueError,ArithmeticError):counts['unconstructable_negative']+=1
    return out,dict(counts)

def main():
    install();assert not(ROOT/'frozen.json').exists()
    if(ROOT/'lessons-frozen.json').exists():return
    f=read(ROOT/'teacher-frozen.json')
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    goals=rows(ROOT/'train-clean.jsonl');out=[goal_row(g,i)for i,g in enumerate(goals)];by_id={g['id']:g for g in goals}
    rng=random.Random(261108115);unique=list(by_id.values());rng.shuffle(unique)
    for i,g in enumerate(unique[:1600]):
        for style in ['bracket','named']:
            q=question(g['spec'],style,g['id']);p=pool_for(q);s={**g,'task':q,'pool':p,'style':'structured',
                'reference_body':compile_spec(g['spec'],p),'spec_body':encode(g['spec'],p)}
            out.append(goal_row(s,2*i+(style=='named'),'structured'))
    build();selected=unique[:1000];chunks=[selected[i:i+12]for i in range(0,len(selected),12)];stats=collections.Counter()
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for i,(values,c)in enumerate(pool.map(tool_chunk,chunks)):
            out+=values;stats.update(c)
            if i%10==0:print(json.dumps({'tool_chunks':i+1,'total':len(chunks),'rows':len(out)}),flush=True)
    for i,r in enumerate(out):r['id']=f'bf:lesson:{i:06}'
    save_rows(ROOT/'lessons.jsonl',out)
    write(ROOT/'lessons-frozen.json',{'rows':len(out),'counts':dict(collections.Counter(r['origin']for r in out)),
        'source_counts':dict(collections.Counter(r.get('wording_source','tool')for r in out if r['origin']=='natural')),
        'old_preserved_natural':sum(r['origin']=='natural'and r['wording_source']=='old'and not r['point_edited']for r in out),
        'point_edits':sum(r['origin']=='natural'and r['point_edited']for r in out),
        'fresh_tool_cycles_use_new_strict_checker':True,'stats':dict(stats),'files':{'lessons.jsonl':sha(ROOT/'lessons.jsonl')}})
    print(json.dumps(read(ROOT/'lessons-frozen.json')),flush=True)

if __name__=='__main__':main()
