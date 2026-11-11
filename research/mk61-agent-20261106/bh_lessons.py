"""Natural translation, limited structured replay, and fresh strict-ROM tool cycles."""
import collections
import concurrent.futures
import copy
import json
import random
from bh_common import ROOT,PARENT,read,write,rows,save_rows,sha
from bh_spec import install
from be_language import question
from az_runtime import Session,goal_state
from ba_lessons import make_row,wrong_program
from bc_self import rejected_session
from ay_codec import compile_spec,encode
from ay_data import op_count
from az_teacher import pool_for
from full_isa_vm import FullVM,build
from ha_protocol import assemble
from ar_spec import verify

def goal_row(g,index,origin='natural'):
    return {'id':f'bh:{origin}:{index:06}','group_id':g['id'],'task_id':g['id'],'origin':origin,
        'family':g['family'],'action':'write','body':[],'state':goal_state(g),'target_spec':g['spec'],
        'reference_body':g['reference_body'],'spec_body':g['spec_body'],'simple':op_count(g['spec']['X'])<=2,
        'wording_source':g.get('wording_source','structured'),'point_edited':g.get('point_edited',False),'correctness':0}

def tool_chunk(goals):
    from az_lessons import mutant
    install();vm=FullVM();out=[];counts=collections.Counter()
    for g in goals:
        for case in [0,1]:
            for kind in ['operation','argument','order']:
                try:label,bad=mutant(g,vm,kind)
                except (ValueError,ArithmeticError):counts['unconstructable_pair']+=1;continue
                raw=assemble(bad,g['pool'],'asm')
                if not all(vm.execute(raw,x,angle=g['spec']['angle'],max_commands=128,max_frames=1024)[0]['status']=='stopped'for x in g['public_inputs']):
                    bad,plausible=wrong_program(g,vm,kind)
                    if not plausible:counts['non_stopped_pair_skipped']+=1;continue
                    label='plausible_fallback'
                if verify(vm,bad,g['pool'],g['spec'],g['audit_inputs'])['status']!='FAIL':continue
                counts['plausible_stopped_pairs']+=1
                good=Session(g,g['reference_body'],vm,'spec',g['spec'],True,start_case=case)
                wrong=Session(g,bad,vm,'spec',g['spec'],True,start_case=case)
                pair=g['id']+':'+str(case)+':'+kind
                for session,action,origin,correct in [(good,'done','pair_good',True),(wrong,'write','pair_bad',False)]:
                    row=make_row(g,session,action,origin,correct);row.update(pair_id=pair,pair_error=label,simple=False);out.append(row)
                good.apply_action('done',[]);assert good.finished
                wrong.apply_action('write',g['spec_body']);wrong.apply_action('run',[1-case]);wrong.apply_action('done',[]);assert wrong.finished
                assert verify(vm,wrong.body,wrong.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
                counts['pair_'+label]+=1
    return out,dict(counts)

def main():
    install();assert not(ROOT/'frozen.json').exists()
    if(ROOT/'lessons-frozen.json').exists():return
    f=read(ROOT/'teacher-frozen.json')
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    goals=rows(ROOT/'train-clean.jsonl');out=[goal_row(g,i)for i,g in enumerate(goals)];by_id={g['id']:g for g in goals}
    rng=random.Random(261110115);unique=list(by_id.values());rng.shuffle(unique)
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
    for row in rows(PARENT/'lessons.jsonl'):
        if row['origin'] in ['repair','run_0','run_1','done','unsure'] and not __import__('re').search(r'JSON|items|AST|local_scope_warnings',row['state']['view']['task'],__import__('re').I):
            out.append({**copy.deepcopy(row),'origin':'replay_'+row['origin'],'replay_source':'BF frozen successful lessons'})
    for i,r in enumerate(out):r['id']=f'bh:lesson:{i:06}'
    save_rows(ROOT/'lessons.jsonl',out)
    write(ROOT/'lessons-frozen.json',{'rows':len(out),'counts':dict(collections.Counter(r['origin']for r in out)),
        'source_counts':dict(collections.Counter(r.get('wording_source','tool')for r in out if r['origin']=='natural')),
        'old_preserved_natural':sum(r['origin']=='natural'and r['wording_source']=='old'and not r['point_edited']for r in out),
        'point_edits':sum(r['origin']=='natural'and r['point_edited']for r in out),
        'fresh_tool_cycles_use_new_strict_checker':True,'stats':dict(stats),'files':{'lessons.jsonl':sha(ROOT/'lessons.jsonl')}})
    print(json.dumps(read(ROOT/'lessons-frozen.json')),flush=True)

if __name__=='__main__':main()
