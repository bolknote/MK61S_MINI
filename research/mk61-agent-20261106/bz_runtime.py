"""Shorten static guidance only; task, SPEC and emulator facts remain verbatim."""
import re
from bj_runtime import Session as Parent,render as old_render,snapshot
from hf_runtime import GUIDE

CALLS='Вызовы: WRITE=SPEC; RUN=номер случая HEX; TRACE; DIAG; DONE; UNSURE.'
DIAG=('DIAG TT HH LL AA BB: TT 00=верно,01=операция,02=аргумент,03=порядок; '
      'HH LL — первый индекс HEX, AA — текущий байт, BB — нужный. '
      'Верно: 00 FF FF 00 00. Диагноз — гипотеза.')
WORK=('WRITE с компактной SPEC. После правки RUN всех открытых случаев. '
      'stopped — только останов; проверь X. Верно: DONE; не решил: UNSURE.')


def shorten(text):
    lines=[];changed={'calls':0,'diag':0,'notes':0,'budget':0}
    for line in text.splitlines():
        if line.startswith('Вызовы: '):
            lines.append(CALLS);changed['calls']+=1
        elif line.startswith('DIAG: <diag>'):
            lines.append(DIAG);changed['diag']+=1
        elif line=='Заметки: '+GUIDE:
            changed['notes']+=1
        elif line.startswith('Осталось действий: '):
            match=re.match(r'Осталось действий: (\d+)\. ',line);assert match,line
            lines.append('Осталось действий: '+match[1]+'. '+WORK);changed['budget']+=1
        else:lines.append(line)
    assert changed=={'calls':1,'diag':1,'notes':1,'budget':1},changed
    return '\n'.join(lines)


def render(state,arm='spec'):
    text=old_render(state,arm)
    # Interpretation remains in exactly the old format, including code-free replans.
    return shorten(text)if state.get('body') is not None else text


class Session(Parent):
    def request(self):return render(snapshot(self),'spec')
