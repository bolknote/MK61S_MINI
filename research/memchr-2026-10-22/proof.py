#!/usr/bin/env python3
"""Record which exact tested kernel bodies are embedded in the prepared APPs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def body(image,name,size):
    start=image.symbols[name]&~1
    section=next(s for s in image.sections if s[2]&2 and s[3]<=start and start+size<=s[3]+s[5])
    at=section[4]+start-section[3]
    return image.data[at:at+size]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=a.build_root
    validations=[];proofs=[];checks=0
    for cpu in ('m0','m4'):
        reference=ElfImage(r/(cpu+'-v1')/'kernels.elf')
        layout=json.loads((r/(cpu+'-v1')/'kernels.json').read_text())
        assert layout['elf_sha256']==sha(r/(cpu+'-v1')/'kernels.elf')
        bodies={n:body(reference,n,f['bytes']) for n,f in layout['functions'].items()}
        for name,location,options in (
            (cpu+'-v1','validation.json',dict(input_address='0x20040000')),
            (cpu+'-app-v1','indirect-validation.json',dict(input_address='0x20040000',indirect_target='own64')),
            (cpu+'-flash-v1','validation.json',dict(input_address='0x10080000' if cpu=='m0' else '0x08040000'))):
            folder=r/name;v=json.loads((folder/location).read_text())
            elf=folder/('app/CHRBEN.elf' if 'app' in name else 'kernels.elf')
            assert v['elf_sha256']==sha(elf)
            assert all(row['status']=='PASS' for row in v['results'])
            checks+=sum(row['cases'] for row in v['results'])
            validations.append(dict(name=name,sha256=sha(folder/location),options=options,**v))
        flash=ElfImage(r/(cpu+'-flash-v1')/'kernels.elf')
        for n,raw in bodies.items():assert body(flash,n,len(raw))==raw,(cpu,n,'Flash body differs')
        for directory in sorted(r.glob(cpu+'-*-v1')):
            manifest_path=directory/'benchmark.json'
            if not manifest_path.exists():continue
            manifest=json.loads(manifest_path.read_text())
            assert not manifest['public_memchr_runtime']
            app=directory/'app/CHRBEN.APP';elf=directory/'app/CHRBEN.elf'
            assert manifest['app_sha256']==sha(app)
            for n,digest in manifest['sources'].items():assert digest==sha(directory/n),(directory,n,'source changed')
            image=ElfImage(elf);rows={}
            if manifest.get('placement','sram')=='sram':
                for n,raw in bodies.items():
                    actual=body(image,n,len(raw));assert actual==raw,(directory,n,'APP body differs')
                    rows[n]=dict(bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest())
            else:
                # The Flash APP retains its indirect veneer and calls frozen
                # absolute entries after checking the complete payload CRC.
                header=directory/'wrapper.c'
                assert manifest['flash_header_sha256']==sha(r/(cpu+'-flash-v1')/'flash-layout.h')
            proofs.append(dict(name=directory.name,manifest=manifest,elf_sha256=sha(elf),bodies=rows))
    result=dict(status='PASS',scope='Offline ARM correctness and exact code identity; no physical timings',
        arm_checks=checks,validations=validations,apps=proofs)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],arm_checks=checks,apps=len(proofs))))

if __name__=='__main__':main()
