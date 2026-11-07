"""Observed user-style boundary checks in the native inference/tool loop.

Reference results stay in this grader; the model sees only public inputs and
actual emulator observations. This diagnostic is never used for selection.
"""
import argparse
import json
from pathlib import Path

from ha_chat import Native
from ha_protocol import assemble,constants
from he_runtime import Session
from full_isa_math import literal
from full_isa_protocol import REGISTERS
from full_isa_vm import FullVM,state_match


def fixtures():
    states=[{'X':'-3','Y':'7','R0':'5','R1':'-2'},
            {'X':'2.5','Y':'-4','R0':'0.25','R1':'11'},
            {'X':'-0.75','Y':'8','R0':'-4','R1':'3'}]
    rows=[]
    for value in ['0','1','-1','0.125','-0.875']:
        rows.append((f'Выдай в X число {value}.','DEG',literal(value)+[0x50],states))
    for angle in ['DEG','RAD','GRAD']:
        for number in ['0','22']:
            rows.append((f'Подсчитай синус {number}.',angle,literal(number)+[0x1C,0x50],states))
    rows.extend([
        ('Вычисли квадрат текущего X.','RAD',[0x22,0x50],states),
        ('Вычисли квадратный корень текущего X.','RAD',[0x21,0x50],
         [{**state,'X':value}for state,value in zip(states,['4','0.25','16'])]),
        ('Вычисли квадрат числа из R0.','RAD',[0x60,0x22,0x50],states),
        ('Вычисли (X+1)*(X+1).','RAD',literal(1)+[0x10,0x22,0x50],states),
        ('Вычисли квадрат R1.','RAD',[0x61,0x22,0x50],states),
    ])
    return rows


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    selected=json.loads((root/'final-export.json').read_text())['selected_label'];vm=FullVM();result={}
    for label in ['asm-baseline',selected]:
        engine=Native(root/'export'/label);details=[]
        for i,(question,angle,reference,states)in enumerate(fixtures()):
            task={'id':f'native-boundary:{i}','task':question,'angle':angle,'constants':constants(question),
                  'public_tests':[{'segments':[{'inputs':state}]}for state in states[:2]],
                  'max_commands':256,'max_frames':4096}
            expected=[vm.execute(reference,state,angle=angle)[0]for state in states]
            def grade(body):
                if body is None:return False,[]
                try:
                    code=assemble(body,session.pool,'asm')
                    actual=[vm.execute(code,state,angle=angle)[0]for state in states]
                    correct=all(state_match(x,y,names=['X',*REGISTERS])for x,y in zip(actual,expected))
                    return correct,[x['raw']['X']for x in actual]
                except (ValueError,RuntimeError,ArithmeticError):return False,[]
            session=Session(task,'asm',vm=vm);first=None;first_values=[]
            for turn in range(6):
                try:reply=engine.generate(session.request())
                except ValueError as error:
                    session.history.append({'kind':'generation_error','error':str(error)});break
                session.apply(reply)
                if turn==0:first,first_values=grade(session.body)
                if session.finished:break
            correct,values=grade(session.body)
            details.append({'question':question,'angle':angle,'first_program_correct':bool(first),
                            'program_correct':bool(correct),'finished':session.finished,
                            'pass':bool(correct and session.finished),'first_results':first_values,
                            'final_results':values,'history':session.history})
        result[label]={'first_program_correct':sum(x['first_program_correct']for x in details),
                       'program_correct':sum(x['program_correct']for x in details),
                       'finished_correct':sum(x['pass']for x in details),'total':len(details),'details':details}
        print(json.dumps({'label':label,**{k:v for k,v in result[label].items()if k!='details'}},ensure_ascii=False),flush=True)
    result.update(selected_label=selected,native_model_inference=True,used_for_selection=False,
                  independent_human_benchmark=False,oracle_answers_in_feedback=False,
                  public_input_states=2,additional_grader_only_states=1)
    (root/'boundary-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
