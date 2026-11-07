"""Cross-language check of revision invalidation and execution-only gating."""
import ctypes as C
from pathlib import Path
import random
import subprocess

from hd_common import HERE,sha,write
from hd_runtime import Session
from full_isa_vm import FullVM


def verify(out):
    out.mkdir(exist_ok=True,parents=True);path=out/'debug-gate.dylib'
    subprocess.run(['c++','-std=c++17','-O2','-shared','-fPIC',str(HERE/'hd_gate_probe.cpp'),'-o',str(path)],check=True,capture_output=True)
    lib=C.CDLL(str(path));lib.hd_gate_init.argtypes=[C.c_void_p,C.c_uint,C.c_int]
    lib.hd_gate_edit.argtypes=[C.c_void_p];lib.hd_gate_run.argtypes=[C.c_void_p,C.c_uint,C.c_int]
    lib.hd_gate_can.argtypes=[C.c_void_p];lib.hd_gate_revision.argtypes=[C.c_void_p]
    vm=FullVM();rng=random.Random(6120799);checks=0
    for cases in [1,2,16]:
        task={'id':'gate-crosscheck','task':'Выдай в X число 0.','angle':'DEG',
              'public_tests':[{'segments':[{'inputs':{'X':str(i-3)}}]}for i in range(cases)]}
        s=Session(task,'asm',body=[0xFF,1,0,0x50],vm=vm);buffer=C.create_string_buffer(lib.hd_gate_bytes())
        assert lib.hd_gate_init(buffer,cases,1)==0
        for _ in range(100):
            op=rng.randrange(6)
            if op in [0,1,2]:
                index=rng.randrange(cases);s.apply(f'<run>{index:02X}</run>')
                assert lib.hd_gate_run(buffer,index,int(all(x['status']=='stopped'for x in s.runs[index])))==1
            elif op==3:
                reply='<write>FF 01 '+('00 50'if rng.random()<.7 else'02 21 50')+'</write><run/>'
                assert s.apply(reply)=='write';lib.hd_gate_edit(buffer)
                assert lib.hd_gate_run(buffer,s.case,int(all(x['status']=='stopped'for x in s.runs[s.case])))==1
            elif op==4:
                assert s.apply('<patch>00 00 FF 01 FE 50</patch><run/>')=='error'
            else:
                if s.last_trace is not None:s.apply('<trace/>')
            assert bool(lib.hd_gate_can(buffer))==s.eligibility()[0]
            assert lib.hd_gate_revision(buffer)==s.revision
            assert lib.hd_gate_run(buffer,cases,1)==0
            checks+=1
    result={'python_cpp_state_transitions_matched':checks,'state_bytes':lib.hd_gate_bytes(),
            'max_public_cases':16,'allocation_free':True,'semantic_correctness_checked':False,
            'expected_answers_accessed':False,'sources':{n:sha(HERE/n)for n in ['hd_gate.hpp','hd_gate_probe.cpp']}}
    write(out/'debug-gate-verification.json',result);return result


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();print(json.dumps(verify(a.out)))
