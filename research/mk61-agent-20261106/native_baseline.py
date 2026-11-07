"""Score the previous 3M Q4 checkpoint on the same newly opened short audit."""
import hashlib
import json

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from native_eval import language_cases,summary,read
from quantization import load_q4
from tasks import BUILD


def main():
    root=BUILD/'native-mixed-v1'
    assert (root/'complete.json').exists()and(root/'winner-before-fresh.json').exists()
    source=BUILD/'capacity-v1/export/selected-budget'
    weights=source/'model.mkq4'
    expected='479ce04e7d36a6013812af270478e8389d14ddc360126a4982dd2998f98522ec'
    assert hashlib.sha256(weights.read_bytes()).hexdigest()==expected
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    model=AutoModelForCausalLM.from_pretrained(source/'hf',local_files_only=True,trust_remote_code=False)
    tokenizer=AutoTokenizer.from_pretrained(source/'hf',local_files_only=True,trust_remote_code=False)
    load_q4(model,weights);model.to('cuda').eval()
    tasks=read(root/'fresh-level1.jsonl')
    # No long-context wrappers are used: the previous architecture supports512.
    results={'manual':language_cases(model,tokenizer,tasks,audit=True)}
    result={'summary':summary(results),'metrics':results,'packed_sha256':expected,
            'parameters':sum(p.numel()for p in model.parameters()),'context':512,
            'fresh_sha256':hashlib.sha256((root/'fresh-level1.jsonl').read_bytes()).hexdigest(),
            'checkpoint_selected_before_this_experiment':True,'automatic_search':False,
            'used_for_new_model_selection':False,'native_device_measured':False}
    (root/'previous-3m-fresh.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['summary']),flush=True)


if __name__=='__main__':main()
