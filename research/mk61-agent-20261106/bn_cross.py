"""Missing factorial cell: newly trained Q4 weights in the unchanged long harness."""
import json
import time
import torch
from transformers import AutoTokenizer
from native_verify import verify_export
from bn_common import ROOT,NEW,write,check,output_ids,compact_head
from bl_eval import evaluate,brief


def main():
    check();model,receipt=verify_export(NEW);model.cuda().eval().requires_grad_(False)
    tok=AutoTokenizer.from_pretrained(NEW/'hf',local_files_only=True);compact_head(model,output_ids(tok))
    started=time.monotonic();result=evaluate(model,tok,'development',profile='long')
    write(ROOT/'new-weights-long-development.json',result)
    write(ROOT/'cross-complete.json',{'complete':True,'optimizer_updates':0,'seconds':time.monotonic()-started,'export':receipt})
    print(json.dumps(brief(result)),flush=True);check()


if __name__=='__main__':
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;main()
