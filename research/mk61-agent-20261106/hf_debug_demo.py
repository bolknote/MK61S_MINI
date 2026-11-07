"""Three observed native repair demos; grading never enters runtime feedback."""
import argparse
import json
from pathlib import Path

from ha_chat import Native
from hf_runtime import Session
from ha_protocol import constants,encode,assemble
from full_isa_math import literal
from full_isa_protocol import REGISTERS
from full_isa_vm import FullVM,state_match


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);a=parser.parse_args();root=a.root.resolve()
    label=json.loads((root/'final-export.json').read_text())['selected_label'];engine=Native(root/'export/selected-budget');vm=FullVM();details=[]
    states=[{'X':'-3','Y':'7','R0':'5'},{'X':'2.5','Y':'-4','R0':'.25'},{'X':'-.75','Y':'8','R0':'-4'}]
    for question,angle,wrong,reference in [
      ('Подсчитай синус 22.','DEG',literal(22)+[0x1D,0x50],literal(22)+[0x1C,0x50]),
      ('Вычисли квадрат текущего X.','RAD',[0x22,0x22,0x50],[0x22,0x50]),
      ('Выдай в X число 0.','DEG',literal(1)+[0x50],literal(0)+[0x50])]:
        task={'id':'observed-native-repair:'+str(len(details)),'task':question,'angle':angle,'constants':constants(question),
              'public_tests':[{'segments':[{'inputs':s}]}for s in states[:2]],'max_commands':256,'max_frames':4096}
        s=Session(task,'asm',body=encode(wrong,task['constants'],'asm'),vm=vm);s.run(0)
        for _ in range(6):
            try:reply=engine.generate(s.request())
            except ValueError as error:s.history.append({'kind':'generation_error','error':str(error)});break
            s.apply(reply)
            if s.finished:break
        try:
            code=assemble(s.body,s.pool,'asm');actual=[vm.execute(code,state,angle=angle)[0]for state in states]
            expected=[vm.execute(reference,state,angle=angle)[0]for state in states]
            correct=all(state_match(x,y,names=['X',*REGISTERS])for x,y in zip(actual,expected))
            values=[x['raw']['X']for x in actual]
        except (ValueError,ArithmeticError,RuntimeError):code=None;correct=False;values=[]
        details.append({'question':question,'angle':angle,'initial_program':wrong,'final_program':code,'program_correct':bool(correct),
                        'finished':s.finished,'pass':bool(correct and s.finished),'final_results':values,'history':s.history})
    result={'selected_label':label,'passed':sum(x['pass']for x in details),'total':len(details),'details':details,
            'native_model_inference':True,'oracle_answers_in_feedback':False,'used_for_selection':False,
            'observed_diagnostic_not_fresh_exam':True}
    (root/'native-repair-demo.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='details'}),flush=True)


if __name__=='__main__':main()
