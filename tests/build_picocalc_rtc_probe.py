#!/usr/bin/env python3
"""Build finite SRAM M3/APP probes. No devices, previous-image backups or writes."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import zlib

ROOT=Path(__file__).resolve().parents[1]
SDK=ROOT/'sdk/coproc'
sys.path.insert(0,str(SDK))
from elf32 import ELF


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(a):
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tool=lambda n:str(a.toolchain/('arm-none-eabi-'+n))
    source=ROOT/'tests/picocalc_rtc_m3_probe_module.c'
    elf,binary=out/'RTCPROBE.elf',out/'RTCPROBE.bin'
    flags=['-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-g',
           '-mword-relocations','-ffreestanding','-fno-builtin','-fno-common',
           '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
           '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-I'+str(SDK)]
    subprocess.run([tool('gcc'),*flags,'-nostdlib',str(source),'-Wl,-T,'+str(SDK/'module.ld'),
                    '-Wl,--emit-relocs,--gc-sections,-Map='+str(out/'RTCPROBE.map'),'-o',str(elf)],check=True)
    subprocess.run([tool('objcopy'),'-O','binary','-j','.image',str(elf),str(binary)],check=True)
    e=ELF(elf);image=binary.read_bytes();memory=e.symbols['__memory_end']['value']-0x20000000
    reloc=[]
    for at,kind in e.relocations():
        if kind==2:reloc.append(at-0x20000000)
        elif kind not in (3,10,30,42):raise ValueError('Unsupported relocation '+str(kind))
    reloc=sorted(set(reloc));assert memory<=6144 and len(reloc)<=64
    for at in reloc:
        assert at%4==0 and at+4<=len(image)
        assert 0x20000000<=struct.unpack_from('<I',image,at)[0]<=0x20000000+memory
    assert not any(s['index']==0 for s in e.symbols.values())
    payload=image+b''.join(struct.pack('<I',at)for at in reloc)
    words=[0x314d3353,1,64,64+len(payload),len(image),memory-len(image),e.entry-0x20000000,
           len(reloc),512,512,256,2000,zlib.crc32(payload),0,0x70301]
    header=struct.pack('<15I',*words)
    package=header+struct.pack('<I',zlib.crc32(header))+payload
    (out/'RTCPROBE.S3M').write_bytes(package)
    checks=[]
    for steps,work in [(8192,0),(4096,64),(256,4096)]:
        value=0x12345678
        for step in range(steps):
            for _ in range(work):value=(value*1664525+1013904223)&0xffffffff
            value^=step+0x9e3779b9
        checks.append(value)
    def array(name,data):return 'static const unsigned char '+name+'[]={'+','.join(map(str,data))+'};\n'
    (out/'rtc_probe_package.h').write_text(array('rtc_probe_package',package)+
        'static const unsigned rtc_probe_checksums[3]={'+','.join(map(str,checks))+'};\n')
    result={'physical_io':False,'module_memory_bytes':memory,'module_sha256':sha(out/'RTCPROBE.S3M'),
            'module_relocations':reloc,'checksums':checks,'apps':{},'images':{}}
    configs=[('RTCBENCH',None,None),('RTCCONT',a.control,a.control_elf),
             ('RTCCAND',a.candidate,a.candidate/'base/source/build/picocalc_BIOS_jcs.elf')]
    for name,folder,firmware_elf in configs:
        app=out/name;app.mkdir()
        wrapper=app/'probe.c'
        prefix='#define RTC_PROBE_VERIFY '+str(int(folder is not None))+'\n'
        if folder is not None:
            folder=folder.resolve();firmware_elf=firmware_elf.resolve()
            body=(folder/'bios.bin').read_bytes();boot=(folder/'boot.bin').read_bytes()
            linked=firmware_elf.with_suffix('.bin').read_bytes()
            assert body==linked+b'\xff'*((-len(linked))%4),name
            f=ELF(firmware_elf)
            date=f.symbols['rtc_date']['value'];time=f.symbols['rtc_time']['value'];calendar=f.symbols['hrtc']['value']+12
            prefix+=f'#define RTC_PROBE_ROLE "{name}"\n#define RTC_DATE_ADDRESS {date}u\n#define RTC_TIME_ADDRESS {time}u\n#define RTC_CALENDAR_ADDRESS {calendar}u\n'
            boot_reference=boot+b'\xff'*(8192-len(boot))
            metadata=(folder/'BIOS.M3U').read_bytes()[:32]+struct.pack('<I',0xc001cafe)
            (app/'rtc_probe_expected.h').write_text(array('expected_boot',boot_reference)+
                array('expected_bios',body)+array('expected_metadata',metadata))
            result['images'][name]={'body_sha256':sha(folder/'bios.bin'),'body_bytes':len(body),
                'body_crc32':f'{zlib.crc32(body):08X}','boot_sha256':sha(folder/'boot.bin'),
                'date_address':hex(date),'time_address':hex(time),'calendar_address':hex(calendar),
                'elf_sha256':sha(firmware_elf)}
        wrapper.write_text(prefix+'#include "'+str(ROOT/'tests/picocalc_rtc_probe_app.c')+'"\n')
        command=[sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),'--target','picocalc-pico-h',
                 '--name',name,'--arm-toolchain-bin',str(a.toolchain),'--include',str(SDK),'--include',str(out),
                 '--include',str(app),'--output-dir',str(app/'app')]
        for p in [wrapper,SDK/'stm3_client.c',SDK/'pico_uart1.c']:command+=['--source',str(p)]
        with (app/'build.log').open('w') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
        p=app/'app'/f'{name}.APP'
        linked_app=p.with_suffix('.bin').read_bytes()
        if folder is None:
            assert b'RTCBENCH rep=' in linked_app, 'Benchmark was optimized out'
        else:
            assert b'RTCPROBE IDENTITY role=' in linked_app, 'Image verifier was optimized out'
            assert len(linked_app)>len(body)+len(boot), 'Expected image bytes absent from verifier'
        result['apps'][name]={'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p),
                            'metadata':json.loads(p.with_suffix('.json').read_text())}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--control',type=Path,default=ROOT/'firmware/picocalc-m3-boot')
    ap.add_argument('--control-elf',type=Path,required=True)
    ap.add_argument('--toolchain',type=Path,required=True)
    build(ap.parse_args())
