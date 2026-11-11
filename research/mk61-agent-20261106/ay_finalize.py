"""Remove cross-split equivalents and repeated questions before any SGD."""
import collections
import json
from ay_common import ROOT,rows,read,save_rows,write,sha
from ay_codec import decode
from ha_protocol import canonical


def normalized(expr):
    if isinstance(expr,str):return expr
    if isinstance(expr,dict):return {'pi':True}if'pi'in expr else{'constant':canonical(expr['constant'])}
    op,*args=expr;args=[normalized(x)for x in args]
    if op in ['+','*']:args.sort(key=lambda x:json.dumps(x,sort_keys=True))
    return [op,*args]


def angular(expr):
    return isinstance(expr,list)and(expr[0]in ['sin','cos','tan','asin','acos','atan']or any(angular(x)for x in expr[1:]))


def semantic_key(spec):
    return json.dumps([normalized(spec['X']),sorted(spec['writes']),spec['angle']if angular(spec['X'])else None],sort_keys=True)


def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'data-clean.json').exists():print('Clean splits already frozen');return
    seen=set();questions=set();counts={};files={}
    pilot=ROOT.parent/'spec-diagnostic-v1/goals.json'
    if pilot.exists():seen.update(semantic_key(g['spec'])for g in json.loads(pilot.read_text()))
    for split in ['train','development','closed']:
        groups=collections.defaultdict(list)
        for g in rows(ROOT/(split+'-goals.jsonl')):groups[g['id']].append(g)
        values=[];dropped=collections.Counter();new_keys=set();new_questions=set()
        for identifier,variants in sorted(groups.items()):
            key=semantic_key(variants[0]['spec'])
            if key in seen or key in new_keys:dropped['same_tree_up_to_commutativity_and_irrelevant_angle']+=1;continue
            unique=[];own=set()
            for g in variants:
                question=(g['spec']['angle'],g['task'])
                if question in questions or question in new_questions or question in own:continue
                own.add(question);unique.append(g)
            if not unique:dropped['repeated_question']+=1;continue
            # At most two teacher variants per training AST, one per evaluation AST.
            unique=unique[:2 if split=='train'else 1]
            new_keys.add(key);new_questions.update((g['spec']['angle'],g['task'])for g in unique);values.extend(unique)
        seen.update(new_keys);questions.update(new_questions)
        assert values and len(new_keys)>={'train':1100,'development':100,'closed':220}[split],(split,len(new_keys))
        path=ROOT/(split+'-clean.jsonl');save_rows(path,values);files[path.name]=sha(path)
        counts[split]={'trees':len(new_keys),'questions':len(values),'dropped':dict(dropped),
                       'panels':dict(collections.Counter(g['panel']for g in values))}
    write(ROOT/'data-clean.json',{'counts':counts,'files':files,'before_any_model_outputs':True,
      'commutative_operands_and_irrelevant_angle_normalized':True,'opened_pilot_signatures_excluded':True,
      'not_a_proof_of_no_equivalent_functions_under_all_algebraic_identities':True})
    print(json.dumps(counts,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
