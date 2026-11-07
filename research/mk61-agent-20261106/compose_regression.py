"""Post-selection regression on the previously observed98-task formal panel."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys

from compose_common import ROOT,ARMS,sha
from run_experiment import REPO,SCRIPT,run
from tasks import BUILD


def assess(arm,which):
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from evaluate_batched import evaluate
    from lowbit import load
    from compose_common import read
    selection=json.loads((ROOT/'preselected.json').read_text())
    source=selection['choices'][arm]['model']if which=='final'else ROOT/'initial'/arm
    packet=ROOT/f'results/{arm}-{which}.mkqb';previous=json.loads((ROOT/f'results/{arm}-{which}.json').read_text())
    assert sha(packet)==previous['packed']['sha256']
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False)
    tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,trust_remote_code=False)
    load(model,packet);model.to('cuda').eval()
    result=evaluate(model,tokenizer,read(BUILD/'tasks/test-extended-v2.jsonl'),plan=False,max_new=160,batch_size=24)
    report={**result,'actual_packet_sha256':sha(packet),'new_independent_fresh_panel':False,
      'previously_observed_formal_regression':True,'native_device_measured':False}
    (ROOT/f'results/full-formal-{arm}-{which}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    extra=ROOT/'fresh4-structure.jsonl'
    if extra.exists():
        from native_eval import language_cases
        frozen=json.loads((ROOT/'frozen-structural4.json').read_text());assert sha(extra)==frozen['sha256']
        result=language_cases(model,tokenizer,read(extra),audit=True)
        (ROOT/f'results/structural4-{arm}-{which}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


def main():
    if len(sys.argv)>1 and sys.argv[1]=='assess':assess(*sys.argv[2:4]);return
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm=sys.argv[2]
        for which in ['final','baseline']:
            if not(ROOT/f'results/full-formal-{arm}-{which}.json').exists()or((ROOT/'fresh4-structure.jsonl').exists()and not(ROOT/f'results/structural4-{arm}-{which}.json').exists()):
                run(f'composition-v1/full-formal-{arm}-{which}.log',SCRIPT+'compose_regression.py','assess',arm,which,timeout=3600)
        return
    assert(ROOT/'complete.json').exists()
    def worker(arm,gpu):
        with(ROOT/f'{arm}-regression-controller.log').open('a')as log:
            result=subprocess.run([sys.executable,'-u',SCRIPT+'compose_regression.py','worker',arm],cwd=REPO,
              env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError('Formal regression failed '+arm)
    with ThreadPoolExecutor(max_workers=2)as executor:
        for future in [executor.submit(worker,arm,i)for i,arm in enumerate(ARMS)]:future.result()
    (ROOT/'regression-complete.json').write_text(json.dumps({'completed':True})+'\n')


if __name__=='__main__':main()
