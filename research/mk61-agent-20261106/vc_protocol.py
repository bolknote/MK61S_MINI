"""A binary critic sees raw code and actual public runs, never expected values."""
import json
import re
from ha_protocol import bytes_text
from hf_runtime import Session


def prompt(task,code,runs):
    names=set(re.findall(r'\bR[0-9A-E]\b|\bX\b|\bY\b',task['task']))|{'X','Y'}
    for op in code:
        if 0x40<=op<=0x4E:names.add(f'R{op-0x40:X}')
        if 0x60<=op<=0x6E:names.add(f'R{op-0x60:X}')
    lines=[f'Проверка программы МК-61. Режим {task["angle"]}.',
           'HEX: '+bytes_text(code)]
    for index,case in enumerate(task['public_tests']):
        values={k:v for k,v in case['segments'][0]['inputs'].items()if k in names}
        lines.append(f'Вход {index:02X}: '+json.dumps(values,ensure_ascii=False,separators=(',',':')))
        if index in runs:lines.append('Факт: '+json.dumps(runs[index],ensure_ascii=False,separators=(',',':')))
    lines+=['Условие: '+task['task'],
            'Код решает условие? d — верно; t — есть ошибка. Остановка сама по себе не доказывает верность.',
            'Ассистент: <']
    return '\n'.join(lines)


def executed_prompt(task,code,vm):
    session=Session(task,'direct',body=list(code),vm=vm)
    for index in range(len(task['public_tests'])):session.run(index)
    return prompt(task,code,session.runs)
