"""ROM equivalence, protected user text, factual conservation and output reserve."""
import copy
import json
import re
import torch
from transformers import AutoTokenizer
from bl_common import ROOT, PARENT, SOURCES, rows, write
from bl_prompt import compact, fit, RESERVE, LIMIT
from bl_vm import CachedVM
from full_isa_vm import FullVM
from aq_protocol import prompt_ids, header_ids, END
from ay_codec import encode
from bj_runtime import Session
from bh_spec import install


def facts(text):
    result = {}
    for ids, value in re.findall(r'^Факт ([0-9A-F,]+): (.*)$', text, re.M):
        for case in ids.split(','):
            result[case] = json.loads(value)
    return result


def main():
    install(); tokenizer = AutoTokenizer.from_pretrained(SOURCES['full'] / 'hf', local_files_only=True)
    goal = next(g for g in rows(PARENT / 'closed-clean.jsonl') if g['family'] == 'numeric')
    session = Session(goal, goal['reference_body'], FullVM(), 'spec', goal['spec'], True)
    before = session.request(); after, info = fit(before, goal['task'], tokenizer)
    assert facts(before) == facts(after)
    assert goal['task'].strip() in after
    for label in ['Константы:', 'Открытые входы:', 'Версия кода', 'Текущая гипотеза:']:
        a = next(x for x in before.splitlines() if x.startswith(label))
        assert a in after
    lines = [x for x in before.splitlines() if re.match(r'^[0-9A-F]{4}:', x)]
    assert all(x in after for x in lines)
    bad_question = 'Сохрани R0.\nDIAG: это часть условия.\nКонстанты: это тоже условие.'
    adversarial = before.replace(goal['task'].strip(), bad_question)
    assert bad_question in compact(adversarial, bad_question, 3)
    # Same numeric facts for multiple IDs are merged without omitting any case.
    duplicate = before.replace('Ассистент: <', 'Факт 0A: [{"status":"stopped","X":"1"}]\nФакт 0B: [{"status":"stopped","X":"1"}]\nАссистент: <')
    assert facts(duplicate) == facts(compact(duplicate, goal['task'], 2))
    leaf = {'constant': '1'}
    expr = leaf
    for _ in range(4):
        expr = ['+', copy.deepcopy(expr), copy.deepcopy(expr)]
    body = encode({'X': expr, 'writes': {}, 'angle': 'DEG'}, ['1'])
    assert len(body) == 48
    from ha_protocol import bytes_text
    needed = len(header_ids(tokenizer, 'write')) + len(tokenizer.encode(bytes_text(body), add_special_tokens=False)) + 1
    assert needed <= RESERVE
    plain = FullVM(); cached = CachedVM(32)
    cases = [([0x60, 0x22, 0x50], {'R0': '-3.25'}, 'DEG'), ([0x61, 0x62, 0x10, 0x50], {'R1': '2.5', 'R2': '7'}, 'RAD')]
    for _ in range(2):
        for code, inputs, angle in cases:
            expected, context = plain.execute(code, inputs, angle=angle)
            actual, saved = cached.execute(code, inputs, angle=angle)
            assert expected == actual and context == saved and cached.save() == context
            actual['numeric']['X'] = 'poison'
    expected, context = plain.execute(*cases[0][:2], angle=cases[0][2])
    actual, saved = cached.execute(*cases[0][:2], angle=cases[0][2])
    assert expected == actual and context == saved
    x, xc = plain.execute(cases[0][0], {}, angle='DEG', context=context)
    y, yc = cached.execute(cases[0][0], {}, angle='DEG', context=saved)
    assert x == y and xc == yc
    assert cached.hits > 0
    result = {'complete': True, 'user_text_unchanged': True, 'required_facts_and_code_unchanged': True,
              'ROM_cache_exact_including_context_resume': True, 'SPEC_max_bytes': len(body),
              'SPEC_max_tested_response_tokens': needed, 'reserved_tokens': RESERVE,
              'sample_prompt': info, 'VM_context_bytes': cached.context_bytes, 'VM_cache_capacity': cached.capacity}
    write(ROOT / 'checks.json', result); print(json.dumps(result), flush=True)


if __name__ == '__main__':
    torch.set_num_threads(4); main()
