from pathlib import Path
import hashlib,json,subprocess,sys
root=Path.cwd();work=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tests'))
from check_stm32_vectors import ElfImage
compiler='/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin/arm-none-eabi-g++'
before=root/'.build/m0-qpi-integration-v60-20261021/source'
after=work/'source';out=work/'generic-check';out.mkdir(exist_ok=True)
flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-DNDEBUG',
 '-DMK61_USE_M0_EABI=1','-DMK61_USE_COMPACT_LIBM=1','-DMK61_M0_RP2040_EABI=0',
 '-fno-lto','-ffunction-sections','-fdata-sections','-fno-exceptions','-fno-rtti',
 '-fno-unwind-tables','-fno-asynchronous-unwind-tables']
rows=[]
for filename in ['native_eabi_m0.cpp','native_eabi_m0.S','native_eabi_m0_rp2040.S','compact_math.cpp','native_eabi_m0_cr.cpp']:
 results=[]
 for label,tree in [('before',before),('after',after)]:
  source=tree/'code'/filename;obj=out/(filename+'.'+label+'.o')
  options=[*flags,'-I'+str(tree/'code'),'-x','assembler-with-cpp' if filename.endswith('.S') else 'c++']
  if not filename.endswith('.S'):options+=['-std=c++17']
  subprocess.run([compiler,*options,'-g0','-c',str(source),'-o',str(obj)],check=True)
  image=ElfImage(obj)
  sections={n:image.bytes_at(s).hex() for n,s in image.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
  results.append(sections)
 assert results[0]==results[1],(filename,'Generic M0 allocated bytes changed')
 rows.append(dict(source=filename,allocated_bytes=sum(len(x)//2 for x in results[1].values()),sha256=hashlib.sha256(json.dumps(results[1],sort_keys=True).encode()).hexdigest()))
report=dict(status='PASS',scope='Non-RP2040 generic ARMv6-M: every allocated code/data section remains byte-identical to V60. The generic spelling has an extra expression macro; normalized preprocessing identity is not claimed.',results=rows)
(work/'generic-m0-isolation.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS generic-M0 allocated code/data identity')
