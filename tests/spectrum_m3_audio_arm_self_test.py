#!/usr/bin/env python3
"""Execute the actual relocated M3 sound module through the compact loader."""
import argparse
import binascii
from bisect import bisect_right
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
from spectrum_m3_runtime_fixture import prepare

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sdk/coproc'),str(ROOT/'tools/firmware/picocalc')]
from build_picocalc import compiler_bin
vectors=None

def build_harness(folder):
    out=folder/'arm-harness';out.mkdir(parents=True,exist_ok=True)
    compiler=compiler_bin(None)/'arm-none-eabi-gcc'
    runtime=folder/'runtime'
    pins=prepare(runtime)
    inputs=[runtime/'stm3_runtime.c',runtime/'stm3_runtime.h',runtime/'arm_harness.c',runtime/'harness.ld',ROOT/'sdk/coproc/stm3_module.h']
    cmd=[str(compiler),'-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-g',
         '-ffreestanding','-fno-builtin','-fno-common','-fno-stack-protector','-fno-unwind-tables',
         '-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
         '-I'+str(ROOT/'sdk/coproc'),'-I'+str(runtime),'-nostdlib',str(inputs[0]),str(inputs[2]),
         '-Wl,-T,'+str(inputs[3]),'-Wl,-Map='+str(out/'harness.map'),'-o',str(out/'harness.elf')]
    with (out/'build.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
    return out/'harness.elf',pins

def deferred(t,module,packet,count):
    t.seq=(t.seq+1)&65535
    payload=struct.pack('<IIII',module,len(packet),10,count)
    raw=struct.pack('<BBHHH',1,11,t.seq,len(payload),0)+payload
    raw+=struct.pack('<I',binascii.crc32(raw));frame=b'\0'+vectors.encode(raw)+b'\0'
    response=t.send(frame)
    if not response:
        assert t.call('harness_state')==3
        assert t.send(frame)==b'', 'Pending replay must not restart or acknowledge an unfinished job'
        for _ in range(9):
            t.call('harness_tick')
            n=t.call('harness_transmit',t.scratch,272)
            if n:
                response=bytes(t.u.mem_read(t.scratch,n));break
        else:raise AssertionError('No pushed completion from cooperative module')
    def decode(response):
        assert response.endswith(b'\0');decoded=vectors.decode(response[:-1])
        version,op,seq,n,flags=struct.unpack_from('<BBHHH',decoded)
        assert (version,op,seq,flags)==(1,139,t.seq,0) and len(decoded)==12+n
        assert binascii.crc32(decoded[:-4])==struct.unpack_from('<I',decoded,len(decoded)-4)[0]
        assert struct.unpack_from('<I',decoded,8)[0]==0
        job,slice_us=struct.unpack_from('<II',decoded,12)
        assert job and slice_us<=2000 and n==12+count
        return job,decoded[20:-4]
    job,output=decode(response)
    assert t.send(frame)==response, 'Lost completion replay changed bytes or ran the job again'
    return job,output

def main():
    global vectors
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-dir',type=Path,default=ROOT/'.build/spectrum-m3-audio-20261107')
    folder=ap.parse_args().build_dir.resolve()
    raw=(folder/'arm-vectors.bin').read_bytes();magic,count=struct.unpack_from('<II',raw)
    assert magic==0x31564153 and count==32
    harness,pins=build_harness(folder);checked_samples=0;instructions=0;render_instructions=Counter()
    spec=importlib.util.spec_from_file_location('stm3_arm_vectors',folder/'runtime/arm_execution.py')
    vectors=importlib.util.module_from_spec(spec);spec.loader.exec_module(vectors)
    elf=vectors.ELF(folder/'module/AY.elf')
    functions=sorted((s['value']&~1,s['size'],name)for name,s in elf.symbols.items()if s['info']&15==2 and s['size'])
    starts=[f[0]for f in functions]
    for pushed in (False,True):
        t=vectors.Target(harness);module=t.load((folder/'module/AY.S3M').read_bytes())
        profile={'active':False}
        def executed(uc,address,size,unused):
            if not profile['active'] or not(t.module_range[0]<=address<t.module_range[1]):return
            linked=address-t.module_range[0]+0x20000000;i=bisect_right(starts,linked)-1
            if i>=0 and linked<functions[i][0]+functions[i][1]:render_instructions[functions[i][2]]+=1
        t.u.hook_add(vectors.UC_HOOK_CODE,executed)
        assert t.module_range[0]!=0x20000000
        hello=t.request(1);assert struct.unpack_from('<I',hello,32)[0]&4
        at=8
        for _ in range(count):
            n,out_n=struct.unpack_from('<II',raw,at);at+=8
            packet=raw[at:at+n];at+=n;expected=raw[at:at+out_n];at+=out_n
            for offset in range(0,n,252):t.request(5,struct.pack('<I',offset)+packet[offset:offset+252])
            profile['active']=packet[4]==1
            if pushed:
                received=min(244,out_n);job,actual=deferred(t,module,packet,received)
                for offset in range(received,out_n,252):
                    actual+=t.request(8,struct.pack('<III',job,offset,min(252,out_n-offset)))
            else:
                job=struct.unpack('<I',t.request(6,struct.pack('<III',module,n,100)))[0]
                for tick in range(9):
                    if t.call('harness_state')==4:break
                    t.call('harness_tick')
                else:raise AssertionError('Cooperative sound job did not complete')
                status=struct.unpack('<7I',t.request(7,struct.pack('<I',job)))
                assert status[1]==4 and status[2]==0 and status[4]==out_n
                actual=b''.join(t.request(8,struct.pack('<III',job,offset,min(252,out_n-offset))) for offset in range(0,out_n,252))
            assert actual==expected,'ARM PCM or state differs from verified local HOST vectors'
            profile['active']=False
            if packet[4]==1:checked_samples+=packet[5]
        assert at==len(raw)
        t.request(10);assert t.call('harness_empty')==1;instructions+=t.module_instructions
    result=dict(status='PASS',jobs=2*count,legacy_jobs=count,pushed_jobs=count,exact_PCM_samples=checked_samples,
                module_instructions=instructions,real_relocated_Thumb2=True,real_compact_loader=True,
                pushed_replay_byte_exact=True,pushed_readiness_polls=0,physical_hardware=False,source_pins=pins)
    result['render_instruction_counts']=dict(render_instructions.most_common())
    result['instruction_counts_are_not_cycle_timings']=True
    (folder/'arm-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
