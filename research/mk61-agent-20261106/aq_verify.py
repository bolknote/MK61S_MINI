"""Native checks plus an independent check for the former budget shortcut."""
import json
from pathlib import Path
import sys
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer
from ap_verify import main
from aq_common import read,write,ACTION_IDS,compact_head,output_ids
from aq_runtime import render
from aq_protocol import prompt_ids
from native_verify import verify_export


def budget_probe(root):
    groups=read(root/'development.jsonl')[:32];out={}
    for arm in ['full','short']:
        folder=root/'export'/(arm+'-terminal');model,_=verify_export(folder)
        tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True);out[arm]={}
        for budget in [10,12]:
            prompts=[render({**g['rows'][3]['state'],'body':None,'runs':{},'diagnosis':None,'remaining':budget},arm)for g in groups]
            enc=[prompt_ids(tokenizer,p)for p in prompts];width=max(map(len,enc));ids=torch.zeros((len(enc),width),dtype=torch.long);mask=torch.zeros_like(ids)
            for i,p in enumerate(enc):ids[i,:len(p)]=torch.tensor(p);mask[i,:len(p)]=1
            with torch.inference_mode():
                h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
                actions=F.linear(h[torch.arange(len(ids)),mask.sum(1)-1],model.get_input_embeddings().weight[ACTION_IDS]).argmax(-1)
            out[arm][str(budget)]={'total':len(groups),'write_actions':int((actions==0).sum())}
        del model
    write(root/'budget-sensitivity.json',{'control_only':True,'used_for_selection':False,'terminal_profiles':out})
    print(json.dumps({'budget_shortcut_probe':out}),flush=True)


if __name__=='__main__':
    main()
    budget_probe(Path(sys.argv[sys.argv.index('--root')+1]))
