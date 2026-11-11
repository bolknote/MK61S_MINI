"""Apply exactly one of the three frozen BZ reductions to an original prompt."""
import re
from bj_runtime import Session as Parent,render as original_render,snapshot
from bz_runtime import CALLS,DIAG,WORK
from hf_runtime import GUIDE


def shorten(text,variant):
    assert variant in ['original','calls','diag','notes','all']
    parts={'calls','diag','notes'}if variant=='all'else set()if variant=='original'else{variant}
    lines=[];changed={'calls':0,'diag':0,'notes':0,'budget':0}
    for line in text.splitlines():
        if 'calls'in parts and line.startswith('Вызовы: '):
            lines.append(CALLS);changed['calls']+=1
        elif 'diag'in parts and line.startswith('DIAG: <diag>'):
            lines.append(DIAG);changed['diag']+=1
        elif 'notes'in parts and line=='Заметки: '+GUIDE:
            changed['notes']+=1
        elif 'notes'in parts and line.startswith('Осталось действий: '):
            match=re.match(r'Осталось действий: (\d+)\. ',line);assert match,line
            lines.append('Осталось действий: '+match[1]+'. '+WORK);changed['budget']+=1
        else:lines.append(line)
    assert changed=={'calls':int('calls'in parts),'diag':int('diag'in parts),'notes':int('notes'in parts),'budget':int('notes'in parts)},changed
    return '\n'.join(lines)


def render(state,variant):
    text=original_render(state,'spec')
    return shorten(text,variant)if state.get('body')is not None else text


def session_type(variant):
    assert variant in ['calls','diag','notes']
    class PartSession(Parent):
        def request(self):return render(snapshot(self),variant)
    return PartSession
