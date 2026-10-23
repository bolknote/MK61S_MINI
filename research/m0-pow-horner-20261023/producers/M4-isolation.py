from pathlib import Path
import hashlib
import json
import subprocess
import sys

root=Path.cwd()
sys.path.insert(0,str(root/'tests'))
from check_stm32_vectors import ElfImage
baseline=root/'.build/picocalc-native-complete-20261020/source'
current=Path(__file__).resolve().parent/'source'
out=Path(__file__).resolve().parent/'m4-check'
out.mkdir(exist_ok=True)
compiler='/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin/arm-none-eabi-g++'
sources=['native_eabi_m0.cpp','native_eabi_m0.hpp','native_eabi_m0.S','native_eabi_m0_rp2040.S','compact_math.cpp','native_eabi_m0_cr.cpp']
rows=[]
for abi,extra in [('soft',['-mfloat-abi=soft']),('hard',['-mfpu=fpv4-sp-d16','-mfloat-abi=hard'])]:
    for name in sources:
        results=[]
        for label,tree in [('baseline',baseline),('current',current)]:
            source=tree/'code'/name
            if not source.exists():
                assert name=='native_eabi_m0_cr.cpp'
                results.append(None)
                continue
            assembler=name.endswith('.S')
            flags=['-mcpu=cortex-m4','-mthumb',*extra,'-O3','-DNDEBUG','-fno-lto',
                   '-DMK61_USE_M0_EABI=0','-DMK61_USE_NATIVE_EABI=1','-DMK61_USE_COMPACT_LIBM=1',
                   '-I'+str(tree/'code'),'-x','assembler-with-cpp' if assembler else 'c++']
            if not assembler:
                flags+=['-std=c++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-fno-asynchronous-unwind-tables']
            pp=subprocess.check_output([compiler,*flags,'-E','-P',str(source)])
            allocated=None
            if not name.endswith('.hpp'):
                obj=out/(name+'.'+abi+'.'+label+'.o')
                subprocess.run([compiler,*flags,'-g0','-c',str(source),'-o',str(obj)],check=True)
                elf=ElfImage(obj)
                allocated={name:elf.bytes_at(s).hex()
                           for name,s in elf.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
            results.append((b' '.join(pp.split()),allocated))
        before,after=results
        assert after is not None
        if before is None:
            assert not after[1],(name,abi,'New M0 unit emitted M4 code/data')
        else:
            assert before==after,(name,abi,'M4 preprocessing or allocated bytes changed')
        rows.append(dict(source=name,abi=abi,preprocessed_sha256=hashlib.sha256(after[0]).hexdigest(),
                         allocated_bytes=sum(len(v)//2 for v in (after[1] or {}).values()),
                         new_translation_unit=before is None))
for name in ['native_eabi.cpp','native_eabi.hpp','native_eabi_arm.S','native_eabi_fixed.S']:
    assert (baseline/'code'/name).read_bytes()==(current/'code'/name).read_bytes(),name
report=dict(status='PASS',baseline=str(baseline),current=str(current),
            scope='Cortex-M4 O3 release, both soft and hard float ABIs: normalized preprocessing and every allocated code/data section identical; existing M4 runtime sources byte-identical',results=rows)
(out/'m4-isolation.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: Cortex-M4 code/data unchanged for soft and hard ABIs')
