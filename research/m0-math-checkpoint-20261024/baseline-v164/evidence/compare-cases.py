"""Reproduce only changed original chunks and retain every V163/V164 case delta."""
import hashlib,json,struct,sys
from pathlib import Path
root=Path.cwd();work=Path(__file__).resolve().parent;parent=root/'.build/m0-sqrt-zero-tail-v163-20261023'
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine,nan
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
old=json.loads((parent/'matrix-subsets.json').read_text());new=json.loads((work/'matrix-subsets.json').read_text())
benchmark_path=root/'.build/m0-balanced-timing-v87-20261022/benchmark.json'
benchmark=json.loads(benchmark_path.read_text());specs={s['index']:s for s in benchmark['chunks']}
rom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
old_elf=parent/'firmware/mk61s-picocalc-pico-h.elf';new_elf=work/'firmware/mk61s-picocalc-pico-h.elf'
reference_elf=root/'.build/m0-balanced-timing-v87-20261022/firmware/mk61s-picocalc-pico-h.elf'
assert sha(reference_elf)==benchmark['elf_sha256']
before,after,reference=[Machine(p,True,stack_bytes=16384,instruction_budget=200000000,bootrom=rom)
    for p in (old_elf,new_elf,reference_elf)]
same=[];changed=[];all_original_rows=[]
for a,b in zip(old['chunks'],new['chunks'],strict=True):
    assert (a['index'],a['operation'],a['stream'],a['cases'])==(b['index'],b['operation'],b['stream'],b['cases'])
    if a==b:same.append(a['index']);continue
    assert a['operation'] in ('asin','acos')
    s=specs[a['index']];input_path=Path(s['input']);assert sha(input_path)==s['input_sha256']
    vectors=list(struct.iter_unpack('<3Q',input_path.read_bytes()[32:]));assert len(vectors)==a['cases']
    digests=[hashlib.sha256(),hashlib.sha256()];sums=[0,0,0];rows=[]
    for x,y,expected in vectors:
        ar,_,ac=before.call(s['own_symbol'],x,y,count=True)
        br,_,bc=after.call(s['own_symbol'],x,y,count=True)
        qr,_,qc=reference.call(s['qfplib_symbol'],x,y,count=True)
        assert ar==br==expected,(a['operation'],hex(x),hex(y),hex(ar),hex(br),hex(expected))
        correct=(nan(qr) and bool(qr&(1<<51))) if nan(expected) else qr==expected
        for digest,result,count in zip(digests,(ar,br),(ac,bc)):
            digest.update(struct.pack('<8Q',x,y,expected,result,qr,count,qc,(1<<64)-1))
        sums[0]+=ac;sums[1]+=bc;sums[2]+=qc
        row=dict(operation=a['operation'],stream=a['stream'],chunk=a['index'],x=f'{x:016X}',y=f'{y:016X}',
            expected=f'{expected:016X}',qfplib=f'{qr:016X}',before_instructions=ac,after_instructions=bc,
            qfplib_instructions=qc,qfplib_correct=correct,instruction_delta=bc-ac)
        rows.append(row);all_original_rows.append(row)
    assert digests[0].hexdigest()==a['result_sha256'] and digests[1].hexdigest()==b['result_sha256'],a['index']
    assert sums[0]/len(rows)==a['mean_instructions']['own'] and sums[1]/len(rows)==b['mean_instructions']['own']
    assert sums[2]/len(rows)==a['mean_instructions']['qfplib']==b['mean_instructions']['qfplib']
    changed.append(dict(index=a['index'],operation=a['operation'],stream=a['stream'],cases=len(rows),
        before=a['mean_instructions']['own'],after=b['mean_instructions']['own'],qfplib=b['mean_instructions']['qfplib'],
        rows_faster=sum(r['instruction_delta']<0 for r in rows),rows_equal=sum(r['instruction_delta']==0 for r in rows),
        rows_slower=sum(r['instruction_delta']>0 for r in rows),minimum_delta=min(r['instruction_delta'] for r in rows),
        maximum_delta=max(r['instruction_delta'] for r in rows),rows=rows))
independent_old=json.loads((parent/'result.json').read_text());independent_new=json.loads((work/'result.json').read_text())
changed_independent=[];same_independent=[]
for a,b in zip(independent_old['groups'],independent_new['groups'],strict=True):
    assert (a['operation'],a['stream'],a['cases'])==(b['operation'],b['stream'],b['cases'])
    if a==b:same_independent.append((a['operation'],a['stream']));continue
    assert a['operation'] in ('asin','acos')
    rows=[]
    for u,v in zip(a['rows'],b['rows'],strict=True):
        assert {k:z for k,z in u.items() if k!='own_instructions'}=={k:z for k,z in v.items() if k!='own_instructions'}
        rows.append(dict(operation=a['operation'],stream=a['stream'],x=v['x'],y=v['y'],expected=v['expected'],
            before_instructions=u['own_instructions'],after_instructions=v['own_instructions'],
            qfplib_instructions=v['qfplib_instructions'],qfplib_correct=v['qfplib_correct'],
            instruction_delta=v['own_instructions']-u['own_instructions']))
    changed_independent.append(dict(operation=a['operation'],stream=a['stream'],cases=len(rows),before=a['mean_instructions']['own'],
        after=b['mean_instructions']['own'],qfplib=b['mean_instructions']['qfplib'],
        rows_faster=sum(r['instruction_delta']<0 for r in rows),rows_equal=sum(r['instruction_delta']==0 for r in rows),
        rows_slower=sum(r['instruction_delta']>0 for r in rows),minimum_delta=min(r['instruction_delta'] for r in rows),
        maximum_delta=max(r['instruction_delta'] for r in rows),rows=rows))
new_slower=[g for g in changed+changed_independent if g['after']>g['before']]
record=dict(status='PASS_CHANGED_CHUNKS_REPRODUCED_AND_ALL_CASE_REGRESSIONS_RETAINED',
    old_elf_sha256=sha(old_elf),new_elf_sha256=sha(new_elf),reference_elf_sha256=sha(reference_elf),
    benchmark_sha256=sha(benchmark_path),unchanged_original_chunks=len(same),unchanged_original_chunk_indices=same,
    reexecuted_original_cases=len(all_original_rows),changed_original_chunks=changed,
    unchanged_independent_groups=len(same_independent),changed_independent_groups=changed_independent,
    groups_with_higher_mean=new_slower,
    original_case_deltas=dict(faster=sum(r['instruction_delta']<0 for r in all_original_rows),
        equal=sum(r['instruction_delta']==0 for r in all_original_rows),slower=sum(r['instruction_delta']>0 for r in all_original_rows)),
    producer_sha256=sha(__file__),
    scope='Only original chunks whose full record changes are reexecuted on V163,V164 and the pinned diagnostic Qfplib. Both full instruction/result digests exactly reproduce their existing reports. Unchanged chunks retain identical complete records/digests. Independent53 full rows are compared without reexecution. Every input and regression is retained; no all-input speed claim.',
    hardware_accessed=False,goal_complete=False)
(work/'case-comparison.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS:',len(changed),'changed original chunks/',len(all_original_rows),'reexecuted cases;',len(same),'exact chunks;',
    len(changed_independent),'changed independent groups;',len(new_slower),'higher means retained.')
