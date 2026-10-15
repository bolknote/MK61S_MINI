#!/usr/bin/env python3
'''Pin one unchanged APP to exact normal Flash prepare/emit implementations.'''
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from prepare_zx0_prototypes import ROOT,prepare
sys.path.insert(0,str(ROOT/'tests'))
from hil_packbits_firmware import firmware_info

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--firmware-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--corpus-header',type=Path,required=True)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True)
    a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    profiles=[];header=['struct FlashProfile {u32 crc,footer_address,prepare,emit;u8 footer[40],prepare_bytes[32],emit_bytes[32];};','static const FlashProfile flash_profiles[]={']
    for variant in ('control','candidate'):
        folder=a.firmware_dir/variant;elf=folder/'build/resident.elf';binary=folder/'build/resident.bin'
        data=binary.read_bytes();info=firmware_info(binary)
        reproduced=out/(variant+'-elf.bin')
        subprocess.run([a.arm_toolchain_bin/'arm-none-eabi-objcopy','-O','binary',elf,reproduced],check=True)
        assert reproduced.read_bytes()==data,'ELF does not reproduce sealed BIN'
        listing=subprocess.check_output([a.arm_toolchain_bin/'arm-none-eabi-nm','-S','-C',elf],text=True)
        symbols={}
        for line in listing.splitlines():
            parts=line.split(maxsplit=3)
            if len(parts)!=4:continue
            address,size,kind,name=parts
            for function in ('prepare','emit'):
                if name.startswith('zx0::'+function+'(') and '[clone' not in name:
                    assert function not in symbols and kind in ('T','t')
                    at=int(address,16);assert 0x08000000<=at and at+32<=0x08000000+len(data)
                    symbols[function]=dict(address=at|1,bytes=int(size,16),code_hex=data[at-0x08000000:at-0x08000000+32].hex())
        assert set(symbols)=={'prepare','emit'},symbols
        info['symbols']=symbols;profiles.append(dict(variant=variant,**info))
        arrays=[data[info['footer']:info['footer']+40],bytes.fromhex(symbols['prepare']['code_hex']),bytes.fromhex(symbols['emit']['code_hex'])]
        prefix='{'+','.join(str(x) for x in [int(info['build'],16),0x08000000+info['footer'],symbols['prepare']['address'],symbols['emit']['address']])+','
        header.append(prefix+','.join('{'+','.join(map(str,b))+'}' for b in arrays)+'},')
    header.append('};')
    fixture=a.corpus_header.read_text().replace('#define ZX0_BENCH_KIND 1','#define ZX0_BENCH_KIND 3')
    assert '#define ZX0_BENCH_KIND 3' in fixture
    (out/'zx0_bench_fixture.hpp').write_text(fixture+'\n'+'\n'.join(header)+'\n')
    transport=(ROOT/'tests/experimental/zx0_hil_transport.hpp').read_text()
    transport=transport.replace('static bool store_report(', 'static u32 resident_crc();\nstatic bool store_report(')
    transport=transport.replace('put32(48,checksum);put32(52,bench_case_count);','put32(48,checksum);put32(52,bench_case_count);put32(60,resident_crc());')
    transport=transport.replace("if(selected=='A')native_checks();",'native_checks();')
    (out/'zx0_flash_transport.hpp').write_text(transport)
    source=(ROOT/'tests/experimental/zx0_flash_hil.cpp').read_text()
    source+='\nstatic u32 resident_crc() {return selected_profile?selected_profile->crc:0;}\n'
    (out/'zx0_flash_hil.cpp').write_text(source)
    prepare(out/'variants')
    command=[sys.executable,ROOT/'tools/build_portable_app.py','--name','ZX0FLASH','--shared-runtime',
        '--source',out/'zx0_flash_hil.cpp','--source',out/'variants/scalar.cpp',
        '--include',ROOT/'tests/experimental','--include',out,'--arm-toolchain-bin',a.arm_toolchain_bin,
        '--output-dir',out/'build']
    subprocess.run(list(map(str,command)),check=True)
    import re
    cases=[dict(zip(('family','size','parameter','pattern'),map(int,m))) for m in re.findall(r'\{(\d+),(\d+),(\d+),(\d+)\},',fixture)]
    assert len(cases)==10 and all(c['family']==4 for c in cases)
    app=out/'build/ZX0FLASH.APP'
    manifest=dict(profiles=profiles,app=str(app),app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),
        corpus_header=str(a.corpus_header.resolve()),corpus_header_sha256=hashlib.sha256(a.corpus_header.read_bytes()).hexdigest(),
        job=dict(name='ZX0FLASH',kind=3,app=str(app),cases=cases,variants_by_family={'4':['resident_flash']}),
        metadata=json.loads((out/'build/ZX0FLASH.json').read_text()),
        scope='Actual normal resident prepare+emit in Flash; original scalar SRAM encoder outside timed intervals checks byte-identical streams and canaries.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Flash APP ready:',app,flush=True)
if __name__=='__main__':main()
