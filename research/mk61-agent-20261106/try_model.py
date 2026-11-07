"""Run a local checkpoint through the bounded calculator harness on a supplied task."""
import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from emulator import Emulator
from evaluate import generator
from harness import agent_run
from quantization import load_q4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--task-file", type=Path, required=True)
    parser.add_argument("--no-plan", action="store_true")
    parser.add_argument("--hide-public-inputs", action="store_true")
    parser.add_argument("--repair-budget", type=int, default=0)
    args = parser.parse_args()
    if not 0<=args.repair_budget<=512:parser.error('--repair-budget должен быть от 0 до 512')
    torch.set_num_threads(2)
    model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True, trust_remote_code=False).eval()
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, trust_remote_code=False)
    if args.weights: load_q4(model, args.weights)
    task = json.loads(args.task_file.read_text())
    task.setdefault("id", "interactive")
    task.setdefault("kind", "interactive")
    task.setdefault("hidden_tests", task["public_tests"])
    result = agent_run(task, generator(model, tokenizer, plan=not args.no_plan,hide_public_inputs=args.hide_public_inputs), Emulator())
    for entry in result["history"]:
        print("Модель:", entry["reply"])
        print("Эмулятор:", entry["feedback"])
    print("Проверка переданных примеров:", "PASS" if result["pass"] else "FAIL")
    if args.repair_budget and not result['pass'] and not result.get('public_pass',False):
        from evaluate_repairs import repair_result
        from tasks import program_text
        repaired=repair_result(result,task,Emulator(),budget=args.repair_budget)
        tool=repaired.get('repair',{})
        print('Автопочинка харнесса:',tool.get('reason'),'проб:',tool.get('trials',0))
        if tool.get('found'):print('Программа харнесса:',program_text(tool['code']))
        print('Проверка гибрида:','PASS'if repaired['hybrid_pass']else'FAIL')
        raise SystemExit(0 if repaired['hybrid_pass'] else 1)
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__": main()
