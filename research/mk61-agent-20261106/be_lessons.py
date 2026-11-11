"""Translation-heavy clean course with a small identical tool-skill replay."""
import collections
import copy
import json
import random
from be_common import ROOT,PARENT,read,write,rows,save_rows,sha
from be_language import question,parse_question
from be_data import clean_spec
from az_runtime import goal_state
from ay_codec import encode,compile_spec
from bc_pools import lesson_layout

def goal_row(g,index):
    return {'id':f'be:goal:{index:06}','group_id':g['id'],'task_id':g['id'],'origin':'goal','family':g['family'],
        'action':'write','body':[],'state':goal_state(g),'target_spec':g['spec'],'reference_body':g['reference_body'],
        'spec_body':g['spec_body'],'simple':__import__('ay_data').op_count(g['spec']['X'])<=2,'correctness':0}

def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'lessons-frozen.json').exists():return
    data=read(ROOT/'data-frozen.json')
    for n,d in data['files'].items():assert sha(ROOT/n)==d
    values=[goal_row(g,i)for i,g in enumerate(rows(ROOT/'train-clean.jsonl'))]
    old=rows(PARENT/'lessons.jsonl');pools=collections.defaultdict(list)
    for row in old:
        if row['state'].get('diagnosis'):continue
        if row['origin']in ['repair','self_repair']:key='repair'
        elif row['action']=='run':key='run_'+str(row['body'][0])
        elif row['action']=='done':key='done'
        elif row['action']=='unsure':key='unsure'
        else:continue
        pools[key].append(row)
    rng=random.Random(26110894);counts={}
    for key in ['repair','run_0','run_1','done','unsure']:
        source=rng.sample(pools[key],min(1400,len(pools[key])));counts[key]=len(source)
        for i,row in enumerate(source):
            r=copy.deepcopy(row);spec=clean_spec(r['target_spec']);r['target_spec']=spec
            r['state']['view']['task']=question(spec,['bracket','named','chain'][i%3],key+':'+str(i))
            assert parse_question(r['state']['view']['task'],spec['angle'])==spec
            r['id']=f'be:replay:{key}:{i:05}';r['origin']=key;r['simple']=False
            # Remapping rebuilds target SPEC and constant indices without touching real results.
            r=lesson_layout(r,'default',r['id']);values.append(r)
    save_rows(ROOT/'lessons.jsonl',values)
    write(ROOT/'lessons-frozen.json',{'rows':len(values),'goal_rows':sum(r['origin']=='goal'for r in values),
        'clean_tool_replay':counts,'all_replay_conditions_regenerated_from_gold_AST':True,'old_ambiguous_text_reused':False,
        'files':{'lessons.jsonl':sha(ROOT/'lessons.jsonl')}})
    print(json.dumps(read(ROOT/'lessons-frozen.json')),flush=True)

if __name__=='__main__':main()
