#!/usr/bin/env python3
"""Compile the actual memchr sources and check ARM bounds, early hits and ABI.

These are functional Unicorn checks. Performance selection requires the
separate hardware evidence in research/memchr-2026-10-22.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from check_stm32_vectors import ElfImage
import system_memchr_arm_self_test as spans
import system_memchr_guard_self_test as guards

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    cases=[
        ('native-f411','m4','code/system_strings.c',['-DMK61_NATIVE_RUNTIME=1'],0x08010000,450),
        ('native-f401','m4','code/system_strings.c',['-DMK61_NATIVE_RUNTIME=1','-DSTM32F401xC'],0x08018000,270),
        ('sdk-normal','m4','sdk/portable/memory.c',[],0x20010000,450),
        ('sdk-shared','m4','sdk/portable/memory.c',['-DMK61_APP_SHARED_RUNTIME=1'],0x20018000,450),
        ('sdk-langin','m4','sdk/portable/memory.c',['-DMK61_APP_SHARED_RUNTIME=1','-DMK61_MEMCHR_WORDS=4'],0x20020000,270),
        ('sdk-m0-unchanged','m0','sdk/portable/memory.c',[],0x20010000,26),
    ]
    hashes={450:'bd4502b3460e1d7c13ffdfe257d0106099e36111433ba9b0e1565cc5172de521',
            270:'e5ce46b95e76623993455cd0ad24c51ca1d4a0e5a1bfcab2fbf7634db3c98a78'}
    seen={};results=[]
    for name,cpu,source,defines,address,expected_size in cases:
        folder=out/name;folder.mkdir()
        arch=['-mcpu='+('cortex-m4' if cpu=='m4' else 'cortex-m0plus'),'-mthumb']
        if cpu=='m4':arch+=['-mfpu=fpv4-sp-d16','-mfloat-abi=hard']
        common=[str(a.arm_toolchain_bin/'arm-none-eabi-gcc'),*arch]
        command=common+['-Os','-fno-builtin','-fno-lto','-ffunction-sections','-fdata-sections',
            '-Wall','-Wextra','-Werror','-I'+str(ROOT/'code'),*defines,'-c',str(ROOT/source),'-o',str(folder/'body.o')]
        subprocess.run(command,check=True)
        subprocess.run(common+['-nostdlib','-Wl,--gc-sections,-Ttext='+hex(address)+',-e,memchr',
            str(folder/'body.o'),'-o',str(folder/'body.elf')],check=True)
        elf=ElfImage(folder/'body.elf');section=elf.named_sections['.text'];raw=elf.bytes_at(section)
        size=elf.sizes['memchr'];start=(elf.symbols['memchr']&~1)-section[3]
        digest=hashlib.sha256(raw[start:start+size]).hexdigest()
        assert size==expected_size,(name,size,expected_size)
        expected_hash = hashes[size] if cpu=='m4' else 'b0e7e8be7f9f6ce95ec7d9c86f2996103968641c0a917b3fe7fd8687994e0acf'
        assert digest==expected_hash,(name,digest,'measured or retained body changed')
        row=dict(name=name,cpu=cpu,bytes=size,body_sha256=digest,command=command)
        # Shared SDK exports the same local body while the public optional
        # runtime extension is pending. Verify identity without repeating it.
        key=(cpu,digest,address>>28)
        if key in seen:
            row.update(status='PASS',same_code_and_placement_as=seen[key])
        else:
            span=spans.verify(folder/'body.elf',cpu,['memchr'])
            (folder/'span.json').write_text(json.dumps(span,indent=2)+'\n')
            boundaries=[]
            for boundary in (0x20080000,0x2007ffe0,0x2007ff00):
                result=guards.verify(folder/'body.elf',cpu,['memchr'],guard=boundary)
                assert result['status']=='PASS',(name,boundary,result)
                boundaries.append(result)
            (folder/'guards.json').write_text(json.dumps(boundaries,indent=2)+'\n')
            row.update(status='PASS',span_cases=span['results'][0]['cases'],
                       guard_cases=sum(x['results'][0]['cases'] for x in boundaries))
            seen[key]=name
        results.append(row)
    report=dict(status='PASS',scope='Actual source ARM functional regression, not timing',results=results,
        M0_performance_selection=False,optional_public_runtime_extension=False)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',linked_bodies=len(results),functional_calls=sum(r.get('span_cases',0)+r.get('guard_cases',0) for r in results))))


if __name__=='__main__':main()
