"""Pre-gradient correction: signed probes for sign operations, feasible count inputs."""
import hashlib
import json
import random

from emulator import Emulator
from harness import check_program
from tasks import BUILD, registers_used, save_jsonl, value_of


def sign_operation(expr):
    return isinstance(expr,list)and(expr[0]in['abs','neg']or any(sign_operation(x)for x in expr[1:]))


def main():
    root=BUILD/'distill-v1';rng=random.Random(6110605);em=Emulator()
    frozen=json.loads((root/'frozen.json').read_text())
    if (root/'frozen-v2.json').exists():raise SystemExit('Corrected probes already frozen')
    manifest={'revision':'pre-gradient numerical-domain correction; statements unchanged',
              'reason':'Positive-only inputs cannot distinguish abs from identity. Count stories should avoid negative source quantities/remaining counts.',
              'previous_freeze':frozen,'fresh_audit_used_for_training_or_selection':False,'files':{}}
    for name in ['validation','fresh-russian']:
        rows=[json.loads(x)for x in(root/(name+'.jsonl')).read_text().splitlines()]
        for task in rows:
            expr=task['expression'];signed=sign_operation(expr);tests=[]
            while len(tests)<9:
                values=[-12,-7,-3,-1,0,1,3,5,9,15]if signed else[1,2,3,4,5,7,9,12,15,20]
                registers={r:rng.choice(values)for r in sorted(registers_used(expr))}
                try:value=value_of(expr,registers)
                except ArithmeticError:continue
                if not value.is_finite()or abs(value)>1000000 or(not signed and value<0):continue
                case={'registers':registers,'expected_X':str(value.normalize())}
                if not check_program(em,task['reference_code'],[case])['pass']:continue
                tests.append(case)
            task['public_tests'],task['hidden_tests']=tests[:2],tests[2:]
            task['input_domain']='signed quantities for abs/neg; positive inputs and nonnegative result otherwise'
        path=root/(name+'-v2.jsonl');save_jsonl(path,rows)
        manifest['files'][path.name]={'rows':len(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (root/'frozen-v2.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest['files'],indent=2))


if __name__=='__main__':main()
