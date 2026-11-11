"""Review isolation, review budget visibility and bounded numeric semantics."""
import copy
import json
import time
from transformers import AutoTokenizer
from bl_common import ROOT, PARENT, SOURCES, rows, write
from bl_runtime import Session, render
from bl_vm import CachedVM
from bl_spec import install
from bh_spec import value as old_value


def main():
    tokenizer=AutoTokenizer.from_pretrained(SOURCES['full']/'hf',local_files_only=True)
    goals=rows(PARENT/'development-clean.jsonl'); selected=goals[:40]
    inputs=[(g['spec']['X'], {k:float(v)for k,v in x.items()},g['spec']['angle'])for g in selected for x in g['public_inputs']]
    expected=[old_value(*x)for x in inputs];install()
    from bl_spec import value
    assert all(value(*x)==y for x,y in zip(inputs,expected))
    start=time.monotonic()
    try:value(['pow10',['int',{'constant':'1000000000'}]],{},'DEG')
    except (ArithmeticError,ValueError):pass
    else:raise AssertionError('unbounded power accepted')
    assert time.monotonic()-start<1
    vm=CachedVM();g=selected[0]
    a=Session(g,g['reference_body'],vm,'spec',g['spec'],True)
    b=Session(g,[0,0x50],vm,'spec',g['spec'],True)
    p,info=render(a.replan_state(),tokenizer);q,_=render(b.replan_state(),tokenizer)
    assert p==q and 'Первая гипотеза:'in p and 'Текущий HEX'not in p and 'Факт 00:'not in p
    assert 'Разборов SPEC осталось: 1'in render({**__import__('bj_runtime').snapshot(a),'replan_attempted':False},tokenizer)[0]
    a.replan_attempted=True
    Session.tokenizer=tokenizer
    assert 'Разборов SPEC осталось: 0'in a.request()
    write(ROOT/'runtime-checks.json',{'complete':True,'code_free_review_independent_of_current_program':True,
          'own_prior_hypothesis_visible':True,'remaining_review_budget_visible':True,'float_reference_cases_unchanged':len(inputs),
          'unbounded_integer_power_prevented':True,'optimizer_updates':0})
    print(json.dumps({'runtime_checks':True}),flush=True)


if __name__=='__main__':main()
