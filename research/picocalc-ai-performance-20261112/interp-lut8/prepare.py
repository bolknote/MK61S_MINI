#!/usr/bin/env python3
"""Build a private APP against one exact resident ELF, with no device I/O."""
import argparse,hashlib,json,shutil,struct,subprocess,sys,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from check_stm32_vectors import ElfImage
from tools.firmware.picocalc.build_picocalc import compiler_bin
from prepare_mk61_ai_math_candidates import records
VARIANTS=['resident_hybrid','scalar_row','scalar_group','packed_row','packed_group','interp_row','interp_group']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def decode(path):
 import statistics
 raw=path.read_bytes();h=struct.unpack_from('<12I',raw)
 assert h[:6]==(0x49505431,1,125000000,270000000,125000000,1),h
 count,rounds,repeats,cores,workspace,failed=h[6:]
 assert 0<count<=32 and (rounds,repeats,cores,workspace,failed)==(7,8,2,8200,0xffffffff)
 assert len(raw)==48+count*396
 cases=[]
 for i in range(count):
  at=48+i*396;meta=struct.unpack_from('<8I',raw,at);rows=[]
  for v,name in enumerate(VARIANTS):
   r=struct.unpack_from('<13I',raw,at+32+v*52)
   if not r[0]:continue
   assert r[0]==r[1]==r[9]==1,(i,name,r)
   assert r[10:12]==(meta[3]*(meta[4]//32),meta[3])
   samples=[n/repeats for n in r[2:9]]
   rows.append(dict(variant=name,us=statistics.median(samples),samples_us=samples,checksum=r[12],SIO_state_restored=True))
  assert [x['variant']for x in rows]==VARIANTS[:7 if meta[4]==128 else 1]
  assert len({x['checksum']for x in rows})==1
  cases.append(dict(id=meta[0],tensor=meta[1],position=meta[2],rows=meta[3],columns=meta[4],row_start=meta[5],total_rows=meta[6],classifier=bool(meta[7]),variants=rows))
 return dict(status='HARDWARE_MATRIX_MEASURED',cores=2,cpu_hz=270000000,workspace_bytes=8200,
             exact_results=True,setup_save_restore_in_timed_region=True,LUT_prepared_once_per_input=True,
             scope='SRAM matrix tiles; not a full token/inference measurement',cases=cases)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--resident-elf',type=Path);p.add_argument('--output-dir',type=Path)
 p.add_argument('--fixtures',type=Path,default=ROOT/'.build/mk61ai/math-candidates-20261111/MATHCASE.BIN')
 p.add_argument('--decode',type=Path);a=p.parse_args()
 if a.decode:print(json.dumps(decode(a.decode),indent=2));return
 if not a.resident_elf or not a.output_dir:p.error('--resident-elf and --output-dir required')
 elf=a.resident_elf.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
 image=ElfImage(elf);tc=compiler_bin(None);symbols={}
 for line in subprocess.check_output([str(tc/'arm-none-eabi-nm'),'--defined-only','--demangle',str(elf)],text=True).splitlines():
  parts=line.split(None,2)
  if len(parts)==3:symbols[parts[2]]=int(parts[0],16)|1
 def find(prefix):
  result={v for n,v in symbols.items()if n.startswith(prefix)};assert len(result)==1,(prefix,result)
  return result.pop()
 names={'math_add_address':'mk61ai::math::add(','math_mul_address':'mk61ai::math::mul(',
        'math_initialize_address':'mk61ai::math::initialize(',
        'linear_lut8_address':'mk61ai::linear_batch_lut8_sram(',
        'linear_direct_address':'mk61ai::linear_batch_sram(',
        'dot_lut8_address':'mk61ai_dot_lut8_q4_a8_32',
        'prepare_lut8_address':'mk61ai_prepare_lut8x32',
        'submit_compute_address':'picocalc::io_worker::submit_compute(',
        'join_compute_address':'picocalc::io_worker::join_compute(',
        'render_gate_address':'picocalc::NativeHost::ai_render(',
        'clock_hz_address':'picocalc::ai_clock::hz(',
        'clock_begin_address':'picocalc::ai_clock::begin(',
        'clock_end_address':'picocalc::ai_clock::restore('}
 lines=['#pragma once','#include <cstdint>']
 lines += [f'static constexpr std::uint32_t {n}={find(prefix):#x}U;'for n,prefix in names.items()]
 footer=image.named_sections['.mk61_fw_footer'];words=struct.unpack('<10I',image.bytes_at(footer))
 lines += [f'static constexpr std::uint32_t footer_address={footer[3]:#x}U;',
           'static constexpr std::uint32_t footer_words[]={'+','.join(f'{x:#x}U'for x in words)+'};']
 (out/'addresses.hpp').write_text('\n'.join(lines)+'\n')
 half=(ROOT/'code/mk61_ai_half_product.hpp').read_text().replace('#include <cmath>','')
 half=half.replace('NAN','__builtin_nanf("")').replace('INFINITY','__builtin_inff()').replace('std::memcpy','__builtin_memcpy')
 (out/'math-candidate-half.hpp').write_text(half)
 raw=a.fixtures.read_bytes();metadata=[]
 for _,h,data in records(raw):
  assert zlib.crc32(data)==h[15]
  metadata.append(dict(id=h[0],rows=h[3],columns=h[4],classifier=bool(h[8])))
 shutil.copyfile(a.fixtures,out/'MATHCASE.BIN')
 with (out/'app-build.log').open('w')as log:
  subprocess.run([sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),
    '--target','picocalc-pico-h','--shared-runtime','--name','INTERP',
    '--source',str(HERE/'app.cpp'),'--source',str(HERE/'kernels.S'),
    '--include',str(HERE),'--include',str(ROOT/'code'),'--include',str(ROOT/'tests/fixtures'),
    '--include',str(out),'--arm-toolchain-bin',str(tc),'--output-dir',str(out/'app')],
    stdout=log,stderr=subprocess.STDOUT,check=True)
 source_paths=[HERE/'app.cpp',HERE/'kernels.S',HERE/'interp.hpp',HERE/'prepare.py',HERE/'arm_test.py',
   ROOT/'tests/fixtures/mk61_ai_math_candidates.hpp',ROOT/'code/mk61_ai_linear.hpp',
   ROOT/'code/mk61_ai_kernels.h',ROOT/'code/mk61_ai_half_product.hpp']
 generated=['addresses.hpp','math-candidate-half.hpp','MATHCASE.BIN','app/INTERP.APP','app/INTERP.elf','app/INTERP.json']
 package=dict(schema=1,status='BUILT_NOT_RUN_ON_DEVICE',resident_elf=str(elf),resident_elf_sha256=sha(elf),
   footer_words=list(words),variants=VARIANTS,cores=2,cpu_hz=270000000,
   source_pins={str(x.relative_to(ROOT)):sha(x)for x in source_paths},
   generated={x:sha(out/x)for x in generated},cases=metadata,
   scope='private APP; no resident Flash, M3, global model or settings writes; exact reference is current resident hybrid LUT8')
 (out/'package.json').write_text(json.dumps(package,indent=2)+'\n')
 manifest=json.loads((out/'app/INTERP.json').read_text())
 print('Built',out/'app/INTERP.APP','memory',manifest['memory_bytes'],'workspace',8200,'cases',len(metadata))
if __name__=='__main__':main()
