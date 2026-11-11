"""Post-exam diagnostic: distinguish numerical equivalence from literal AST identity."""
from be_common import ROOT,read,rows,write
from ay_finalize import semantic_key

def audit(root):
    goals={g['id']:g for g in rows(root/'closed-clean.jsonl')};result={}
    for arm in ['parent','lora','full']:
        records=read(root/arm/'closed.json')['primary']['records'];same=[];coincidences=[];execution=[]
        for r in records:
            spec=r['declared_spec'];equal=spec is not None and semantic_key(spec)==semantic_key(goals[r['id']]['spec'])
            if equal:same.append(r['id'])
            if r['intent']['tested_equal']and not equal:
                row={'id':r['id'],'task':r['task'],'target':goals[r['id']]['spec'],'predicted':spec,
                    'program_correct_on_fixed_audit':r['program_correct']}
                coincidences.append(row)
                if not r['program_correct']:execution.append({**row,'task_audit':r['task_audit']})
        result[arm]={'total':len(records),'AST_equal_up_to_commutativity_and_irrelevant_angle':len(same),
            'numerically_equal_but_different_AST':len(coincidences),'examples':coincidences[:8],
            'numerically_equal_SPEC_but_program_failed':execution}
    out={'models':result,'posthoc_diagnostic':True,'primary_scores_thresholds_and_selections_unchanged':True,
        'different_AST_may_be_a_valid_algebraic_alternative':True,'frozen_absolute_relative_tolerance':2e-6}
    write(root/'semantic-audit.json',out);return out
