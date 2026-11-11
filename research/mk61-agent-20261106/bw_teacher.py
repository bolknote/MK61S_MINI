"""Word the fixed closed ASTs; blind double review, no student learning."""
import concurrent.futures
import copy
import time
from bw_common import ROOT,read,write,rows,save_rows,sha
from bl_spec import install
from az_teacher import pool_for
from ay_codec import encode,compile_spec
from ha_protocol import assemble
import bj_teacher as teacher

teacher.ROOT=ROOT;teacher.URL='http://127.0.0.1:18089/v1/chat/completions'


def chunk(goals,round_id,client):
    query=copy.deepcopy(goals)
    for g in query:g['id']+=':bw-wording:'+str(round_id);g.pop('original_questions',None)
    accepted,audit=teacher.chunk(client,query)
    return {a['id']:accepted[b['id']]for a,b in zip(goals,query)},audit


def main():
    install();assert not(ROOT/'frozen.json').exists()
    if(ROOT/'teacher-frozen.json').exists():return
    ast=read(ROOT/'ast-frozen.json')
    for n,d in ast['files'].items():assert sha(ROOT/n)==d,n
    goals=rows(ROOT/'closed-asts.jsonl');accepted={g['id']:[]for g in goals};client=teacher.Client();audit=[];started=time.monotonic()
    for round_id in range(4):
        pending=[g for g in goals if not accepted[g['id']]]
        if not pending:break
        batches=[pending[i:i+4]for i in range(0,len(pending),4)];done=0
        with concurrent.futures.ThreadPoolExecutor(6)as pool:
            jobs={pool.submit(chunk,b,round_id,client):b for b in batches}
            for future in concurrent.futures.as_completed(jobs):
                values,checks=future.result();audit.extend(checks)
                for g in jobs[future]:accepted[g['id']].extend(values[g['id']])
                done+=len(jobs[future])
                if done%16==0 or done==len(pending):
                    v={'round':round_id,'processed':done,'pending':len(pending),'accepted':sum(bool(v)for v in accepted.values()),'seconds':round(time.monotonic()-started,1)}
                    write(ROOT/'teacher-status.json',v);print(v,flush=True)
    assert all(accepted.values()),[k for k,v in accepted.items()if not v]
    out=[];questions=set()
    for g in goals:
        text=accepted[g['id']][0]['text'];key=(g['spec']['angle'],text);assert key not in questions;questions.add(key)
        pool=pool_for(text);r={**g,'task':text,'pool':pool,'reference_body':compile_spec(g['spec'],pool),'spec_body':encode(g['spec'],pool),
            'bad_body':compile_spec(g['bad_spec'],pool),'bad_spec_body':encode(g['bad_spec'],pool),'wording_source':'DeepSeek',
            'blind_ambiguity_checked':True,'dual_blind_checked':True}
        for key in ['reference_body','bad_body']:assert assemble(r[key],pool,'asm')==assemble(g[key],g['pool'],'asm')
        out.append(r)
    save_rows(ROOT/'closed.jsonl',out);save_rows(ROOT/'teacher-audit.jsonl',audit)
    write(ROOT/'teacher-frozen.json',{'complete':True,'teacher':teacher.MODEL,'closed_goals':len(out),
        'files':{n:sha(ROOT/n)for n in ['closed.jsonl','teacher-audit.jsonl']},'all_held_ASTs_retained':True,
        'blind_reverse_reviews':2,'same_teacher_not_independent_human_labels':True,'optimizer_updates':0,
        'closed_student_generations_seen':False,'seconds':time.monotonic()-started})
    print({'complete':True,'closed_goals':len(out)},flush=True)


if __name__=='__main__':main()
