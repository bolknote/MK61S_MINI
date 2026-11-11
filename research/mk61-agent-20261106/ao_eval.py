"""Four-class decisions; false-correct rate is separate from class accuracy."""
import math
import torch
import torch.nn.functional as F
from ao_common import ROOT,CLASSES,DIAG_IDS,read
from ao_model import head
from ac_protocol import prompt_ids


def rows(split):return[r for g in read(ROOT/(split+'.jsonl'))for r in g['rows']]


def features(model,tokenizer,values):
    result=[]
    for at in range(0,len(values),32):
        chunk=values[at:at+32];enc=[prompt_ids(tokenizer,r['prompt'])for r in chunk]
        assert all(len(p)<1024 and not set(p)&set(DIAG_IDS)for p in enc)
        device=next(model.parameters()).device;n=max(map(len,enc));ids=torch.zeros((len(enc),n),device=device,dtype=torch.long);mask=torch.zeros_like(ids)
        for i,p in enumerate(enc):ids[i,:len(p)]=torch.tensor(p,device=device);mask[i,:len(p)]=1
        with torch.inference_mode():
            h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
            result.append(h[torch.arange(len(ids),device=device),mask.sum(1)-1].float().cpu())
    return torch.cat(result)


def metrics(labels,predictions):
    matrix=[[0]*4 for _ in range(4)]
    for y,p in zip(labels,predictions):matrix[y][p]+=1
    precision=[];recall=[];f1=[]
    for k in range(4):
        tp=matrix[k][k];support=sum(matrix[k]);called=sum(r[k]for r in matrix)
        p=tp/called if called else 0.;r=tp/support if support else 0.;precision.append(p);recall.append(r);f1.append(2*p*r/(p+r)if p+r else 0.)
    bad=sum(sum(r)for r in matrix[:3]);wrong_correct=sum(r[3]for r in matrix[:3]);good=sum(matrix[3])
    return{'total':len(labels),'correct':sum(matrix[i][i]for i in range(4)),'accuracy':sum(matrix[i][i]for i in range(4))/len(labels),
      'macro_F1':sum(f1)/4,'minimum_recall':min(recall),'precision':dict(zip(CLASSES,precision)),'recall':dict(zip(CLASSES,recall)),
      'false_correct':wrong_correct,'incorrect_total':bad,'false_correct_rate':wrong_correct/bad if bad else 0.,
      'false_error':good-matrix[3][3],'correct_total':good,'false_error_rate':(good-matrix[3][3])/good if good else 0.,
      'confusion_expected_rows_predicted_columns':matrix}


def evaluate(model,tokenizer,split,cached=None):
    values=rows(split);h=cached if cached is not None else features(model,tokenizer,values)
    with torch.inference_mode():logits=F.linear(h.to(next(model.parameters()).device),head(model)).float().cpu();pred=logits.argmax(-1).tolist()
    result=metrics([r['label']for r in values],pred);details=[]
    for r,p,v in zip(values,pred,logits.tolist()):
        details.append({'id':r['id'],'label':r['label'],'predicted':p,'family':r['family'],'pair_tag':r['pair_tag'],'logits':v})
    result['details']=details;result['by_family']={family:metrics([r['label']for r in values if r['family']==family],
        [p for r,p in zip(values,pred)if r['family']==family])for family in sorted({r['family']for r in values})}
    return result


def key(report):
    eligible=report['macro_F1']>=.85 and report['minimum_recall']>=.8 and report['false_correct_rate']<=.05
    return[eligible,report['macro_F1'],-report['false_correct_rate'],report['accuracy']]


def brief(report):return{k:v for k,v in report.items()if k not in ['details','by_family']}
