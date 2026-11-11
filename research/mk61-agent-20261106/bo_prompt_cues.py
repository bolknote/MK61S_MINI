"""Post-hoc prompt-cue interventions; no weight change or deployment claims."""
import hashlib
import json
import re
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from lowbit import load as load_q4
from bn_common import ROOT,PREVIOUS,NEW,ACTIONS,ACTION_IDS,read,write,rows,sha,check
from bn_actions import forward,logits,metrics
from aq_protocol import prompt_ids


ADVICE='Повторный разбор SPEC уже выполнен. Если гипотеза всё ещё неверна, UNSURE.'


def changed(prompt,question,kind):
    start=prompt.index('Задача: ')+len('Задача: ');assert prompt[start:start+len(question)]==question
    marker='\x00Q'+hashlib.sha256(question.encode()).hexdigest()+'\x00';assert marker not in prompt
    text=prompt[:start]+marker+prompt[start+len(question):]
    if kind in ['no_fallback_sentence','no_both_cues']:
        text=text.replace(ADVICE,'Повторный разбор SPEC уже выполнен.'if kind=='no_fallback_sentence'else'')
    if kind in ['no_review_counter','no_both_cues']:text=re.sub(r'^Разборов SPEC осталось: [01]\.\n','',text,flags=re.M)
    if kind=='neutral_review_reminder':
        text=text.replace(ADVICE,'Повторный разбор SPEC уже выполнен. Проверь программу по условию и результатам RUN.')
    return text.replace(marker,question)


def main():
    check();plan=read(ROOT/'prompt-cue-plan.json');assert sha(__file__)==plan['source_sha256']
    data=[r for r in rows(ROOT/'states.jsonl')if r['source']=='new'];goals={g['id']:g for g in rows(PREVIOUS/'closed-clean.jsonl')}
    tok=AutoTokenizer.from_pretrained(NEW/'hf',local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained(NEW/'hf',local_files_only=True).float();load_q4(model,NEW/'model.mkqb');model.cuda().eval().requires_grad_(False)
    head=model.get_input_embeddings().weight[ACTION_IDS].detach().cpu();result={};predictions={}
    for kind in ['original',*plan['variants']]:
        prompts=[r['prompt']if kind=='original'else changed(r['prompt'],goals[r['task_id']]['task'],kind)for r in data]
        encoded=[prompt_ids(tok,p)for p in prompts];assert all(len(x)<1016 for x in encoded)
        h=forward(model,encoded);s=logits(h,head);pred=s.argmax(1)
        if kind=='original':assert all(ACTIONS[int(a)]==r['recorded_action']for a,r in zip(pred,data))
        result[kind]={**metrics(s,data),'changed_prompts':sum(p!=r['prompt']for p,r in zip(prompts,data))}
        predictions[kind]=[ACTIONS[int(x)]for x in pred]
        print(json.dumps({'variant':kind,'metrics':result[kind]}),flush=True)
    transitions=[]
    for i,r in enumerate(data):
        transitions.append({k:r[k]for k in ['id','episode_id','task_id','expected_action','recorded_action','code_correct','spec_correct','abstained','pass']}|{'actions':{k:v[i]for k,v in predictions.items()}})
    write(ROOT/'prompt-cue-results.json',{'metrics':result,'transitions':transitions,'optimizer_updates':0,
          'held_out_validation':False,'same_weights_all_variants':True,'only_protocol_prose_edited':True,
          'user_question_and_code_and_runs_and_hypothesis_preserved':True,'no_end_to_end_completion_claims':True})
    write(ROOT/'cues-complete.json',{'complete':True,'optimizer_updates':0});check()


if __name__=='__main__':torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;main()
