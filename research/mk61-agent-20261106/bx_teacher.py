"""DeepSeek wording and blind reverse checks; all held goals must survive."""
import collections
import concurrent.futures
import copy
import time
from bx_common import ROOT,read,write,rows,save_rows,sha
from bl_spec import install
from az_teacher import pool_for
from ay_codec import encode,compile_spec
from ha_protocol import assemble
import bj_teacher as teacher


teacher.ROOT=ROOT;teacher.URL='http://127.0.0.1:18090/v1/chat/completions'


def chunk(goals,round_id,client):
    query=copy.deepcopy(goals)
    for g in query:
        g['id']=g['id']+':wording-round:'+str(round_id);g.pop('original_questions',None)
    accepted,audit=teacher.chunk(client,query)
    return {original['id']:accepted[g['id']]for original,g in zip(goals,query)},audit


def main():
    install();assert not(ROOT/'frozen.json').exists()
    if(ROOT/'teacher-frozen.json').exists():return
    ast=read(ROOT/'ast-frozen.json')
    for n,d in ast['files'].items():assert sha(ROOT/n)==d,n
    client=teacher.Client();output={s:[]for s in ['train','development','closed']};audit=[];start=time.monotonic()
    for split in output:
        source=rows(ROOT/(split+'-asts.jsonl'));accepted={g['id']:[]for g in source}
        for round_id in range(4):
            pending=[g for g in source if not accepted[g['id']]]
            if not pending:break
            batches=[pending[i:i+4]for i in range(0,len(pending),4)];done=0
            with concurrent.futures.ThreadPoolExecutor(6)as pool:
                jobs={pool.submit(chunk,b,round_id,client):b for b in batches}
                for future in concurrent.futures.as_completed(jobs):
                    values,checks=future.result();audit.extend(checks)
                    for g in jobs[future]:accepted[g['id']].extend(values[g['id']])
                    done+=len(jobs[future])
                    if done%16==0 or done==len(pending):
                        status={'split':split,'round':round_id,'processed':done,'total_pending':len(pending),
                            'accepted_trees':sum(bool(v)for v in accepted.values()),'seconds':round(time.monotonic()-start,1)}
                        write(ROOT/'teacher-status.json',status);print(status,flush=True)
        missing=[g['id']for g in source if not accepted[g['id']]]
        seedfile=ROOT/'manual-wording-seeds.json'
        if missing and seedfile.exists():
            seeds=read(seedfile);candidates=[]
            for g in source:
                if g['id']not in missing:continue
                for i,text in enumerate(seeds.get(g['id'],[])):
                    candidates.append({'id':g['id']+f':manual_seed:{i}','goal':g,'text':text,'original':text,'source':'manual_seed','edited':False})
            values,checks=teacher.check_candidates(client,candidates,True)if candidates else([],[])
            audit.extend(checks)
            for value in values:accepted[value['goal']['id']].append(value)
        missing=[g['id']for g in source if not accepted[g['id']]]
        assert not missing,(split,'teacher_failed_to_word_fixed_goals',missing)
        questions=set()
        for g in source:
            wanted=2 if split=='train'else 1
            for i,c in enumerate(accepted[g['id']][:wanted]):
                text=c['text'];key=(g['spec']['angle'],text);assert key not in questions,(split,text);questions.add(key)
                pool=pool_for(text);row={**g,'task':text,'pool':pool,'reference_body':compile_spec(g['spec'],pool),
                    'spec_body':encode(g['spec'],pool),'bad_body':compile_spec(g['bad_spec'],pool),'bad_spec_body':encode(g['bad_spec'],pool),
                    'paraphrase':i,'wording_source':'DeepSeek'if c['source']!='manual_seed'else'manual seed + dual DeepSeek blind review','blind_ambiguity_checked':True,'dual_blind_checked':split!='train'}
                assert assemble(row['reference_body'],pool,'asm')==assemble(g['reference_body'],g['pool'],'asm')
                assert assemble(row['bad_body'],pool,'asm')==assemble(g['bad_body'],g['pool'],'asm')
                output[split].append(row)
        if split=='train':
            groups=collections.defaultdict(list)
            for row in output[split]:
                if 'contrast_id'in row:groups[row['contrast_id']].append(row)
            for key,group in groups.items():
                assert {row['contrast_side']for row in group}=={0,1}
                shared=sorted({value for row in group for value in row['pool']})
                for row in group:
                    previous=assemble(row['reference_body'],row['pool'],'asm');bad=assemble(row['bad_body'],row['pool'],'asm')
                    row.update(pool=shared[:],reference_body=compile_spec(row['spec'],shared),spec_body=encode(row['spec'],shared),bad_body=compile_spec(row['bad_spec'],shared),bad_spec_body=encode(row['bad_spec'],shared),matched_literal_pool=True)
                    assert assemble(row['reference_body'],shared,'asm')==previous and assemble(row['bad_body'],shared,'asm')==bad
        save_rows(ROOT/(split+'.jsonl'),output[split]);print({'worded':split,'rows':len(output[split])},flush=True)
    # The source AST partition, not question wording, enforces the semantic holdout.
    counts={s:{'trees':len({g['id']for g in v}),'questions':len(v),'families':dict(collections.Counter(g['family']for g in v))}for s,v in output.items()}
    assert counts['closed']['trees']==256 and counts['development']['trees']==128
    save_rows(ROOT/'teacher-audit.jsonl',audit)
    write(ROOT/'teacher-frozen.json',{'complete':True,'teacher':teacher.MODEL,'counts':counts,
        'files':{**{s+'.jsonl':sha(ROOT/(s+'.jsonl'))for s in output},**{n:sha(ROOT/n)for n in ['teacher-audit.jsonl','manual-wording-seeds.json','manual-wording-validation.json']if(ROOT/n).exists()}},'audit_sha256':sha(ROOT/'teacher-audit.jsonl'),
        'blind_review_no_source_AST':True,'all_held_ASTs_retained':True,'ROM_program_bytes_unchanged':True,
        'same_teacher_not_independent_human_labels':True,'student_generations_seen':False,'optimizer_updates':0,
        'seconds':time.monotonic()-start})
    print({'complete':True,'counts':counts},flush=True)


if __name__=='__main__':main()
