#!/usr/bin/env python3
"""Prepare exact math experiments, real-model fixtures and a private Pico APP."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from check_stm32_vectors import ElfImage
from tools.firmware.picocalc.build_picocalc import compiler_bin
VARIANTS=['resident_direct','lut8_full','lut8_bounded','zero_skip','prune_half','prune_last']
HOST_SOURCES=['code/mk61_ai_model.cpp','code/mk61_ai_tokenizer.cpp','code/mk61_ai_linear.cpp',
              'code/mk61_ai_model.hpp','code/mk61_ai_linear.hpp','code/mk61_ai_kernels.c',
              'code/mk61_ai_kernels.h','code/mk61_ai_half_product.hpp','code/mk61_ai_exact_fp32.hpp',
              'code/mk61_ai_math.hpp','code/worker_job_slot.hpp','tests/mk61_ai_math_candidates_self_test.cpp',
              'tests/fixtures/mk61_ai_math_candidates.hpp']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(command,log):
 subprocess.run([str(x) for x in command],stdout=log,stderr=subprocess.STDOUT,check=True)
def host_pins(model):return dict(model_sha256=sha(model),sources={p:sha(ROOT/p) for p in HOST_SOURCES},sanitizers=True,fp_contract=False)
def host(out,model,reuse):
 pins=host_pins(model);proof=out/'host-source-pins.json'
 if reuse:
  assert json.loads(proof.read_text())==pins,'HOST source/model changed; rebuild without --reuse-host'
  assert json.loads((out/'host-results.json').read_text())['status']=='PASS'
  return
 flags=['-O2','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(ROOT/'code')]
 with (out/'host-build.log').open('w') as log:
  run(['clang','-std=c11',*flags,'-c',ROOT/'code/mk61_ai_kernels.c','-o',out/'kernels.o'],log)
  run(['clang++','-std=c++17','-ffp-contract=off',*flags,
       '-Dlinear_batch_sram=reference_linear_batch_sram','-Dlinear_batch_flash=reference_linear_batch_flash',
       '-c',ROOT/'code/mk61_ai_linear.cpp','-o',out/'reference.o'],log)
  run(['clang++','-std=c++17','-ffp-contract=off','-Wall','-Wextra','-Werror',*flags,
       '-DMK61_AI_FAST_MATH=1',ROOT/'code/mk61_ai_model.cpp',ROOT/'code/mk61_ai_tokenizer.cpp',
       ROOT/'tests/mk61_ai_math_candidates_self_test.cpp',out/'reference.o',out/'kernels.o','-o',out/'host-test'],log)
 with (out/'host.log').open('w') as log:run([out/'host-test',model,out],log)
 proof.write_text(json.dumps(pins,indent=2)+'\n')
def records(raw):
 magic,version,count,size=struct.unpack_from('<4I',raw)
 assert magic==0x4d434e31 and version==1 and size==len(raw) and count<=32
 offset=16
 for _ in range(count):
  start=offset;header=struct.unpack_from('<16I',raw,offset);offset+=64
  rows,cols,groups=header[3:6]
  assert 0<rows<=28 and 0<cols<=384 and cols%32==0 and groups==cols//32
  assert header[11]==rows*cols//2 and header[12]==header[13]==rows*groups*2
  n=cols+groups*8+header[11]*2+header[12]+header[13]+rows*4
  assert n<=13000 and offset+n<=len(raw)
  yield start,header,raw[offset:offset+n]
  offset+=n
 assert offset==len(raw)
def decode(path):
 raw=path.read_bytes();h=struct.unpack_from('<12I',raw)
 assert h[:6]==(0x4d425431,1,125000000,270000000,125000000,1),h
 count,rounds,repeats,cores,workspace,failed=h[6:]
 assert count<=32 and rounds==6 and repeats==4 and cores==2 and failed==0xffffffff
 row_size=72;case_size=32+6*row_size
 assert len(raw)==48+count*case_size
 import statistics
 rows=[]
 for c in range(count):
  at=48+c*case_size;meta=struct.unpack_from('<8I',raw,at);variants=[]
  for v,name in enumerate(VARIANTS):
   r=struct.unpack_from('<18I',raw,at+32+v*row_size)
   if not r[0]:continue
   assert r[0]==r[1]==1,(c,name,r[:2])
   prep=[n/repeats for n in r[2:8]];compute=[n/repeats for n in r[8:14]]
   variants.append(dict(variant=name,prep_us=statistics.median(prep),compute_us=statistics.median(compute),
                        total_us=statistics.median([a+b for a,b in zip(prep,compute)]),
                        prep_samples_us=prep,compute_samples_us=compute,
                        groups=r[14],bounded=r[15],pruned=r[16],zero_products_skipped=r[17]))
  assert 0<meta[3]<=28 and 0<meta[4]<=384 and meta[4]%32==0
  assert [v['variant'] for v in variants]==VARIANTS[:6 if meta[7] else 4], 'Missing tested method'
  rows.append(dict(id=meta[0],tensor=meta[1],position=meta[2],rows=meta[3],columns=meta[4],
                   row_start=meta[5],total_rows=meta[6],classifier=bool(meta[7]),variants=variants))
 return dict(status='HARDWARE_MEASURED',cpu_hz=h[3],cores=cores,workspace_bytes=workspace,
             matrix_tiles=rows,scope='real SRAM matrix tiles, two cores, preparation included; not full inference')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--model',type=Path);p.add_argument('--resident-elf',type=Path);p.add_argument('--output-dir',type=Path)
 p.add_argument('--toolchain',type=Path);p.add_argument('--reuse-host',action='store_true')
 p.add_argument('--decode-result',type=Path)
 a=p.parse_args()
 if a.decode_result:
  print(json.dumps(decode(a.decode_result),indent=2));return
 if not a.model or not a.resident_elf or not a.output_dir:p.error('--model, --resident-elf and --output-dir are required')
 out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True);model=a.model.resolve();elf=a.resident_elf.resolve()
 host(out,model,a.reuse_host)
 path=out/'MATHCASE.BIN';raw=bytearray(path.read_bytes());case_meta=[]
 for at,h,data in records(raw):
  struct.pack_into('<I',raw,at+60,zlib.crc32(data))
  case_meta.append(dict(id=h[0],tensor=h[1],position=h[2],rows=h[3],columns=h[4],row_start=h[6],total_rows=h[7],classifier=bool(h[8])))
 path.write_bytes(raw)
 tc=compiler_bin(a.toolchain);image=ElfImage(elf);symbols={}
 for line in subprocess.check_output([str(tc/'arm-none-eabi-nm'),'--defined-only','--demangle',str(elf)],text=True).splitlines():
  parts=line.split(None,2)
  if len(parts)==3:symbols[parts[2]]=int(parts[0],16)|1
 def find(prefix):
  values=[v for n,v in symbols.items() if n.startswith(prefix)];assert len(set(values))==1,prefix;return values[0]
 names={'math_add_address':'mk61ai::math::add(','math_mul_address':'mk61ai::math::mul(',
        'math_initialize_address':'mk61ai::math::initialize(', 'linear_sram_address':'mk61ai::linear_batch_sram(',
        'submit_compute_address':'picocalc::io_worker::submit_compute(', 'join_compute_address':'picocalc::io_worker::join_compute(',
        'render_gate_address':'picocalc::NativeHost::ai_render(', 'clock_hz_address':'picocalc::ai_clock::hz(',
        'clock_begin_address':'picocalc::ai_clock::begin(', 'clock_end_address':'picocalc::ai_clock::restore('}
 lines=['#pragma once','#include <cstdint>']
 lines += [f'static constexpr std::uint32_t {name}={find(prefix):#x}U;' for name,prefix in names.items()]
 footer=image.named_sections['.mk61_fw_footer']
 lines += [f'static constexpr std::uint32_t footer_address={footer[3]:#x}U;',
           'static constexpr std::uint32_t footer_words[]={'+','.join(f'{x:#x}U' for x in struct.unpack('<10I',image.bytes_at(footer)))+'};']
 (out/'math-candidate-addresses.hpp').write_text('\n'.join(lines)+'\n')
 # The freestanding APP cannot include hosted <cmath>. Preserve the exact
 # production half-product body and use compiler constants for NaN/infinity.
 half=(ROOT/'code/mk61_ai_half_product.hpp').read_text().replace('#include <cmath>','')
 half=half.replace('NAN','__builtin_nanf("")').replace('INFINITY','__builtin_inff()')
 half=half.replace('std::memcpy','__builtin_memcpy')
 (out/'math-candidate-half.hpp').write_text(half)
 # Match the production linear kernel's -O3 rather than measuring the
 # APP default -Os and out-of-line four-byte bit-cast helper calls.
 (out/'candidate-kernels.c').write_text('#pragma GCC optimize("O3")\n'+(ROOT/'code/mk61_ai_kernels.c').read_text())
 with (out/'app-build.log').open('w') as log:
  run([sys.executable,ROOT/'tools/apps/portable/build_portable_app.py','--target','picocalc-pico-h',
       '--shared-runtime','--name','MATHCAND','--source',ROOT/'tests/fixtures/mk61_ai_math_candidates_app.cpp',
       '--source',out/'candidate-kernels.c','--include',ROOT/'code','--include',ROOT/'tests/fixtures',
       '--include',out,'--arm-toolchain-bin',tc,'--output-dir',out/'app'],log)
 source_files=[*HOST_SOURCES,'tests/fixtures/mk61_ai_math_candidates_app.cpp','tests/prepare_mk61_ai_math_candidates.py',
               'tests/mk61_ai_math_candidates_arm_self_test.py','tests/mk61_ai_math_candidates_cfg_self_test.py',
               'research/picocalc-ai-performance-20261111/math-candidates/regression-003/MATHCAND.elf',
               'research/picocalc-ai-performance-20261111/math-candidates/regression-003/MATHCAND.json']
 generated=['MATHCASE.BIN','host-results.json','host-source-pins.json','math-candidate-addresses.hpp','math-candidate-half.hpp','candidate-kernels.c',
            'app/MATHCAND.APP','app/MATHCAND.elf','app/MATHCAND.json']
 meta=dict(schema=1,status='BUILT_NOT_RUN_ON_DEVICE',resident_elf=str(elf),resident_elf_sha256=sha(elf),
           model=str(model),model_sha256=sha(model),variants=VARIANTS,cores=2,cpu_hz=270000000,
           source_pins={s:sha(ROOT/s) for s in source_files},generated={s:sha(out/s) for s in generated},
           cases=case_meta,scope='private APP, real SRAM tiles, all setup separately timed; no firmware patch')
 (out/'package.json').write_text(json.dumps(meta,indent=2)+'\n')
 print((out/'host.log').read_text(),end='')
 print('Built APP:',(out/'app/MATHCAND.APP').stat().st_size,'bytes; cases:',len(case_meta),'data:',len(raw))
if __name__=='__main__':main()
