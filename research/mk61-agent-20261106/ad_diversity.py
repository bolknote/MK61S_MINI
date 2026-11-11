"""Development-only wider sampling diagnostic, without changing the sealed experiment."""
import json
import time
import torch
import ad_inference
from ad_inference import Bank
from ad_common import ROOT,read,write
from ad_experiment import grade
from ac_common import END
from full_isa_vm import FullVM


class WideSampling(ad_inference.IndependentSampling):
    def __call__(self,ids,logits):
        out=torch.full_like(logits,-float('inf'))
        for i,g in enumerate(self.generators):
            if END in ids[i,self.start:].tolist():token=END
            else:
                values,order=torch.sort(logits[i].float()/1.1,descending=True);p=values.softmax(-1)
                p[(p.cumsum(0)-p)>.98]=0;p/=p.sum();token=int(order[torch.multinomial(p.cpu(),1,generator=g)])
            out[i,token]=0
        return out


def main():
    assert(ROOT/'verification.json').exists()
    protocol={'development_only':True,'original_candidate_count':4,'additional_candidates':12,
      'temperature':1.1,'top_p':.98,'candidate_ids':list(range(100,112)),
      'no_exam_tuning_or_new_exam_claim':True,'optimizer_updates':0}
    write(ROOT/'diversity-development-protocol.json',protocol)
    panel=json.loads((ROOT/'development-candidate-panel.json').read_text());items=[r for r in panel['details']if not r['initially_correct']]
    tasks={t['id']:t for t in read(ROOT/'development.jsonl')};ad_inference.IndependentSampling=WideSampling
    bank=Bank();vm=FullVM();details=[];started=time.monotonic()
    for at in range(0,len(items),16):
        batch=items[at:at+16];texts=[r['prompt']for r in batch];columns=[]
        for number in range(100,112):columns.append(bank.writes(texts,number))
        for i,r in enumerate(batch):
            extra=[]
            for col in columns:
                g=col[i];extra.append({'generation':g,'correct':grade(vm,tasks[r['id']],g['body'])if not g.get('codec_error')else False})
            old=[c['correct_offline']for c in r['candidates']]
            details.append({'id':r['id'],'level':r['level'],'first_correct':old[0],'any_correct_4':any(old),
                'any_correct_16':any(old)or any(c['correct']for c in extra),'extra':extra})
        print(json.dumps({'diversity_development_states':len(details),'total':len(items),'seconds':time.monotonic()-started}),flush=True)
    write(ROOT/'diversity-development.json',{'protocol':protocol,'total':len(details),
       'greedy_correct':sum(r['first_correct']for r in details),'oracle_4':sum(r['any_correct_4']for r in details),
       'oracle_16':sum(r['any_correct_16']for r in details),'details':details,'seconds':time.monotonic()-started})


if __name__=='__main__':main()
