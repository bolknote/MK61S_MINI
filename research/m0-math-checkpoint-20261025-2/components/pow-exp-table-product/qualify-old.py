"""Freshly profile the candidate on the complete inherited 111912-pair corpus."""
from collections import Counter
import gzip,json,time,sys
sys.dont_write_bytecode=True
from harness import *

binding=json.loads((W/'corpus-binding.json').read_text())
assert sha(W/'old-corpus.jsonl.gz')==binding['corpus_sha256']
m=machine('candidate');calls=hook_products(m,'candidate');roots,_=table();root_set=set(roots)
comparison=Counter();deltas=Counter();remaining=[];new_losses=[];fixed_pairs=set();old_loss_pairs=set();loss_pairs=set()
wrong_reference=variants=checked_known_parent=state_count=0
start=time.monotonic();all_parent_raw_bits=True
with gzip.open(W/'old-corpus.jsonl.gz','rt') as source,gzip.GzipFile(filename=str(W/'old-records.jsonl.gz'),mode='wb',mtime=0) as saved:
    for i,line in enumerate(source):
        row=json.loads(line);state=states[row['SIO']]
        calls.clear();m.uc.mem_write(0xd0000060,state)
        got,_,cost=m.call('_ZN12compact_math3powEdd',int(row['x'],16),int(row['y'],16),count=True)
        state_after(m,state)
        assert got==int(row['parent_R_output'],16),(i,row,hex(got))
        general=[c for c in calls if c['kind']=='general']
        tables=[c for c in calls if c['kind']=='table']
        for call in tables:assert int(call['a'],16) in root_set
        dyadic=sum(int(c['a'],16)==1<<62 for c in tables)
        generic=len(tables)-dyadic
        logical=len(general)+dyadic
        assert len(general)>=generic
        gate_delta=2*generic-67*dyadic
        parent_C77_cost=cost-gate_delta
        predicted_R=parent_C77_cost+7*logical
        if predicted_R!=row['parent_R_cost']:
            (W/'old-cost-mismatch.json').write_text(json.dumps(dict(index=i,row=row,candidate=cost,
                predicted_R=predicted_R,products=calls),indent=2)+'\n')
            raise AssertionError(('old R/source cost identity',i,predicted_R,row['parent_R_cost']))
        if 'known_C77_cost' in row:
            assert parent_C77_cost==row['known_C77_cost'] and logical==row['known_C77_logical_product_calls'],(i,row,calls,cost)
            checked_known_parent+=1
        assert cost<=row['parent_R_cost']
        deltas[gate_delta]+=1
        new=dict(row,candidate=f'{got:016X}',candidate_instructions=cost,
                 parent_C77_instructions=parent_C77_cost,
                 parent_C77_cost_acquisition='previous fresh C77 loss replay' if 'known_C77_cost' in row else 'source-bound R minus7 per actual product call',
                 products=list(calls),logical_old_product_calls=logical,
                 table_dyadic_calls=dyadic,table_generic_calls=generic)
        for reference in row['references'].values():
            variants+=1
            if not reference['correct_Qfplib']:
                wrong_reference+=1;continue
            q=reference['instructions'];pair=(row['x'],row['y'])
            direction='faster' if cost<q else 'equal' if cost==q else 'slower'
            comparison[direction]+=1
            if parent_C77_cost>q:old_loss_pairs.add(pair)
            if cost>q:
                loss_pairs.add(pair);remaining.append(dict(x=row['x'],y=row['y'],SIO=row['SIO'],
                    reference=reference['reference'],candidate=cost,parent_C77=parent_C77_cost,Qfplib=q,
                    expected=row['expected'],candidate_output=f'{got:016X}',Qfplib_output=reference['output']))
                if parent_C77_cost<=q:new_losses.append(remaining[-1])
        saved.write((json.dumps(new,separators=(',',':'))+'\n').encode())
        state_count=i+1
        if i%512==0:
            progress=dict(completed_states=state_count,total_states=binding['state_jobs'],elapsed_seconds=time.monotonic()-start,
                          observed_raw_loss_pairs=len(loss_pairs),candidate_wrong=0,new_loss_state_variants=len(new_losses))
            (W/'progress.json').write_text(json.dumps(progress,indent=2)+'\n')
            print('old-full',state_count,'/',binding['state_jobs'],'elapsed',round(progress['elapsed_seconds'],1),flush=True)
assert state_count==223824 and variants==223976 and checked_known_parent==10081
assert len(old_loss_pairs)==7901
fixed_pairs=old_loss_pairs-loss_pairs
out=dict(status='PASS_COMPLETE_INHERITED_111912_PAIR_CANDIDATE_REPLAY',candidate_ELF_sha256=sha(W/'candidate.elf'),
    corpus_sha256=sha(W/'old-corpus.jsonl.gz'),record_sha256=sha(W/'old-records.jsonl.gz'),
    unique_pairs=111912,profiled_states=state_count,retained_reference_state_variants=variants,
    fresh_candidate_ARM_calls=state_count,fresh_parent_or_Qfplib_or_MPFR_calls=0,
    inherited_parent_R_and_Qfplib_records_not_fresh=True,known_fresh_C77_counts_rechecked=checked_known_parent,
    every_old_candidate_return_bit_matches_R=True,every_cost_matches_source_bound_R_delta=True,
    no_nominal_reference_domain_filter=True,candidate_wrong=0,wrong_Qfplib_state_variants_retained=wrong_reference,
    correct_Qfplib_comparison=dict(comparison),parent_C77_raw_loss_pairs=len(old_loss_pairs),
    candidate_raw_loss_pairs=len(loss_pairs),fixed_raw_pairs=len(fixed_pairs),
    fixed_pair_values=sorted(fixed_pairs),new_loss_state_variants=new_losses,
    parent_C77_cost_deltas=dict(sorted(deltas.items())),observed_stack_bytes=SP-m.stack_lowest,
    elapsed_seconds=time.monotonic()-start,remaining=remaining,hardware_accessed=False)
(W/'old-qualification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('remaining','fixed_pair_values','new_loss_state_variants')},indent=2))
