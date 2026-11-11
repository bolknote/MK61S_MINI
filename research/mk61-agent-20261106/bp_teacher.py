"""Use the unchanged blind DeepSeek wording checks only for a fresh closed exam."""
import collections
import concurrent.futures
import json
import time
from bp_common import ROOT,PREVIOUS,PRIOR_RESULTS,PRIORS,read,write,rows,save_rows,sha,signature
import bl_teacher as helper
from bl_spec import install
from az_teacher import pool_for
from ay_codec import compile_spec,encode
from ha_protocol import assemble
from be_language import question


def main():
    install();assert not(ROOT/'frozen.json').exists()
    if(ROOT/'teacher-frozen.json').exists():return
    ast=read(ROOT/'ast-frozen.json')
    for n,d in ast['files'].items():assert sha(ROOT/n)==d,n
    helper.ROOT=ROOT;helper.URL='http://127.0.0.1:18086/v1/chat/completions'
    client=helper.Client();goals=rows(ROOT/'closed-asts.jsonl');batches=[goals[i:i+4]for i in range(0,len(goals),4)];out=[];audit=[];processed=0;started=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(16)as pool:
        pending={pool.submit(helper.chunk,client,chunk):chunk for chunk in batches}
        for future in concurrent.futures.as_completed(pending):
            accepted,checks=future.result();audit.extend(checks)
            for g in pending[future]:
                if not accepted[g['id']]:continue
                c=accepted[g['id']][0];p=pool_for(c['text'])
                out.append({**g,'task':c['text'],'pool':p,'reference_body':compile_spec(g['spec'],p),'spec_body':encode(g['spec'],p),
                            'style':'natural','wording_source':c['source'],'point_edited':c['edited'],'dual_blind_checked':True})
            processed+=len(pending[future])
            if processed%20==0 or processed==len(goals):
                v={'processed':processed,'total':len(goals),'accepted':len(out),'seconds':round(time.monotonic()-started,1)};write(ROOT/'teacher-status.json',v);print(json.dumps(v),flush=True)
    out+=[{**g,'wording_source':'editorial'}for g in rows(ROOT/'closed-editorial.jsonl')]
    for i,g in enumerate(rows(ROOT/'closed-structured.jsonl')):
        q=question(g['spec'],['bracket','named','chain'][i%3],g['id']);p=pool_for(q)
        out.append({**g,'task':q,'pool':p,'reference_body':compile_spec(g['spec'],p),'spec_body':encode(g['spec'],p),'style':'structured','wording_source':'structured'})
    source={g['id']:g for n in ['closed-asts.jsonl','closed-editorial.jsonl','closed-structured.jsonl']for g in rows(ROOT/n)}
    seen_questions={(g['spec']['angle'],g['task'])for p in list(dict.fromkeys([*PRIORS,PRIOR_RESULTS]))for split in ['train','development','closed']for g in rows(p/(split+'-clean.jsonl'))}
    kept=[];seen=set()
    for g in sorted(out,key=lambda x:x['id']):
        q=(g['spec']['angle'],g['task'])
        if q in seen_questions or q in seen:continue
        seen.add(q);assert assemble(g['reference_body'],g['pool'],'asm')==assemble(source[g['id']]['reference_body'],source[g['id']]['pool'],'asm')
        kept.append(g)
    assert len(kept)>=900,len(kept)
    save_rows(ROOT/'closed-clean.jsonl',kept);save_rows(ROOT/'teacher-audit.jsonl',audit)
    write(ROOT/'teacher-frozen.json',{'teacher':helper.MODEL,'counts':{'questions':len(kept),'panels':dict(collections.Counter(g['panel']for g in kept))},
          'files':{'closed-clean.jsonl':sha(ROOT/'closed-clean.jsonl')},'audit_sha256':sha(ROOT/'teacher-audit.jsonl'),
          'same_teacher_two_blind_reviews_not_human_validation':True,'source_AST_never_shown_to_blind_review':True,
          'reference_ROM_verified_in_AST_generation':True,'SGD_started':False,'closed_model_generations_seen':False,'seconds':time.monotonic()-started})
    print(json.dumps({'closed_exam_ready':True,'count':len(kept)}),flush=True)


if __name__=='__main__':main()
