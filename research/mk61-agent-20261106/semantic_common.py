"""Isolated 3M HEX semantic-distillation experiment; previous runs are immutable."""
import json
from pathlib import Path

from tasks import BUILD
from codec_common import sha,read,protocol,allowed_ids,compact_head,OLD_VOCAB

ROOT=BUILD/'semantic-3m-v1'
ARMS=['direct','auxiliary']
INITIAL=BUILD/'codec-qat-v1/export/best/small-hex/hf'
if not INITIAL.exists():INITIAL=BUILD/'codec-qat-v1/server-results/export/best/small-hex/hf'
INITIAL_PACKET=INITIAL.parent/'model.mkqb'
INITIAL_MASTER_SHA='bda061aa48df2eade4f1bcd6d3a87e2be87246482cb7532c485df3cc6ff1f16f'
INITIAL_PACKET_SHA='d864d31b7a50de4676d39f97231dff5ea102fffaa1bcc59297198a4589f267df'


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def auxiliary_prompt(text):
    return ('МК-61. Объясни кратко роли входных регистров и порядок вычисления. '
            'Укажи промежуточные действия, затем префиксную формулу.\nУсловие: '+text+'\nРазбор: ')


def auxiliary_answer(row):
    from course_common import prefix
    roles='; '.join(k+' — '+v for k,v in sorted(row['roles'].items()))
    steps=' '.join(str(i+1)+'. '+s['explanation'].rstrip('.')+'.' for i,s in enumerate(row['steps']))
    return 'Входы: '+roles+'. Действия: '+steps+' Формула: '+prefix(row['expression'])
