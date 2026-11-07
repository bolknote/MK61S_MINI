"""Local host demo: a neural expression/code reply and a real MK-61 execution."""
import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from course_common import calc_prompt,program_prompt
from emulator import Emulator
from evaluate_batched import generate_many
from harness import extract_code
from lowbit import load as load_lowbit,MAGIC
from quantization import load_q4


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--weights',type=Path,required=True)
    p.add_argument('--text',required=True);p.add_argument('--registers',default='{}');p.add_argument('--parse-only',action='store_true')
    a=p.parse_args();torch.set_num_threads(2)
    registers=json.loads(a.registers)
    if not isinstance(registers,dict)or any(k not in ['R0','R1','R2','R3']for k in registers):
        p.error('--registers: JSON object with R0-R3 values')
    model=AutoModelForCausalLM.from_pretrained(a.model,local_files_only=True,trust_remote_code=False).eval()
    tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
    with a.weights.open('rb')as stream:magic=stream.read(8)
    if magic==MAGIC:load_lowbit(model,a.weights)
    else:load_q4(model,a.weights)
    task={'task':a.text,'public_tests':[],'hidden_tests':[]}
    prompt=calc_prompt(a.text)if a.parse_only else program_prompt(task)
    reply=generate_many(model,tokenizer,[prompt],plan=False,context=model.config.max_position_embeddings,
                        max_new=64 if a.parse_only else 128)[0]
    print('Модель:',reply)
    if a.parse_only:return
    code=extract_code(reply)
    if code is None or'<run/>'not in reply:raise SystemExit('Модель не выдала корректный вызов эмулятора')
    result=Emulator().run(code,registers,max_commands=256,max_frames=2048,memory=True)
    print('Эмулятор:',json.dumps(result,ensure_ascii=False))
    print('Это исполнение программы модели; правильность условия здесь автоматически не оценивается.')


if __name__=='__main__':main()
