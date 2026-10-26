"""Explicit retained-entry jobs; reuse the two completed immutable operations."""
import argparse,gzip,hashlib,json,struct
from pathlib import Path
import qualify as q
import corpora
from oracles import DirectMPFR
W=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--replay-all',action='store_true');a=p.parse_args()
    prior=W/'attempts/after-corpus-fix';reports={};provenance={}
    if not a.replay_all:
        checkpoint=json.loads((prior/'float-progress.json').read_text())
        pairs=corpora.float_pairs()
        assert set(checkpoint['operations'])=={'add','sub'}
        for op,r in checkpoint['operations'].items():
            assert r['status']=='PASS' and r['cases']==len(pairs)
            data=gzip.decompress((W/r['full_raw_records']).read_bytes())
            assert hashlib.sha256(data).hexdigest()==r['uncompressed_sha256']
            assert len(data)==48*len(pairs)
            for args,record in zip(pairs,struct.iter_unpack('<6Q',data)):
                assert record[:2]==args and record[2]==0 and record[3:]==(record[4],record[4],record[4]) or (record[:2]==args and record[2]==0 and q.equal(record[3],record[4],32) and q.equal(record[5],record[4],32))
            reports[op]=r
            provenance[op]=dict(completed_run='attempts/after-corpus-fix',checkpoint_sha256=q.sha(prior/'float-progress.json'),
                                producer_pins={n:q.sha(prior/n) for n in ['qualify.py','oracles.py','corpora.py']})
    hashes={str(p.relative_to(q.ROOT)):q.sha(p) for p in [q.ELF,q.RESIDENT,q.ROM,q.REFERENCE]}
    producer_pins={n:q.sha(W/n) for n in ['complete-float.py','qualify.py','oracles.py','corpora.py']}
    m=q.QMachine(q.ELF,True,stack_bytes=4096,bootrom=q.ROM)
    reference=q.arm.Machine(q.REFERENCE,True,stack_bytes=4096);oracle=DirectMPFR()
    pairs=corpora.float_pairs();values=corpora.float_values()
    jobs=[(op,'__aeabi_'+('frsub' if op=='frsub' else 'f'+op),pairs,32,32) for op in ['add','sub','frsub','mul','div']]
    jobs += [(op,'__aeabi_f'+op,pairs,32,32) for op in ['cmpeq','cmplt','cmple','cmpge','cmpgt','cmpun']]
    jobs += [('f2iz','__aeabi_f2iz',[(v,) for v in values],32,32),('f2uiz','__aeabi_f2uiz',[(v,) for v in values],32,32)]
    jobs += [(op,'__aeabi_'+op,[(v,) for v in corpora.integer_values()],32,32) for op in ['i2f','ui2f']]
    jobs += [('f2d','__aeabi_f2d',[(v,) for v in values],32,64),('d2f','__aeabi_d2f',[(v,) for v in corpora.double_values()],64,32),('sqrt','mk61_m0_sqrtf',[(v,) for v in corpora.sqrt_values()],32,32)]
    assert all(s in m.elf.symbols for _,s,_,_,_ in jobs),'Every job must reference a real retained entry before running'
    for op,symbol,inputs,width,rw in jobs:
        if op in reports:continue
        reports[op]=q.run_operation('float',op,symbol,inputs,width,rw,oracle,m,reference)
        provenance[op]=dict(completed_run='complete-float.py',producer_pins=producer_pins)
        (W/'float-completion-progress.json').write_text(json.dumps(dict(operations=reports,complete=False),indent=2)+'\n')
    assert hashes=={str(p.relative_to(q.ROOT)):q.sha(p) for p in [q.ELF,q.RESIDENT,q.ROM,q.REFERENCE]}
    assert producer_pins=={n:q.sha(W/n) for n in producer_pins}
    result=dict(status='PASS_FINITE_ARM_QUALIFICATION' if all(r['status']=='PASS' for r in reports.values()) else 'FAIL',
        mode='float',operations=reports,actual_public_calls=sum(r['cases'] for r in reports.values()),
        operation_provenance=provenance,ROM_initializers=m.rom_initializers,ROM_intrinsic_models=m.rom_models,
        MPFR_version=oracle.version,maximum_completion_MPFR_precision=oracle.max_precision,SIO_write_attempts=m.sio_writes,
        input_pins=hashes,producer_pins=producer_pins,
        limits=['Finite deterministic coverage, not exhaustive all2^32/2^64 inputs or an all-input proof',
                'RNE returned values; errno/fenv flags and other rounding modes outside runtime contract',
                'Out-of-range integer casts test implementation policy, not valid-range IEEE correctness',
                'SP sample16 calls per entry; all calls check bounded writes, R4-R11, restored SP and three SIO contexts',
                'Instruction samples retain all adverse cases; no physical cycle or universal speed claim',
                'Six comparison predicates have no matching Qfplib native ABI baseline in this packet'],
        source_recompiled=False,resident_changed=False,canonical_changed=False,hardware_accessed=False,goal_complete=False)
    (W/'float.json').write_text(json.dumps(result,indent=2)+'\n')
    print('FINAL float',result['status'],'public calls',result['actual_public_calls'],flush=True)
    assert result['status'].startswith('PASS')

if __name__=='__main__':main()
