#!/usr/bin/env python3
"""Read-only A748 source/ABI/peripheral audit. Does not inspect live hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--apps',type=Path,default=ROOT/'.build/rp2040-interpolator-20261023/app/app-manifest.json');a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);tc=compiler_bin(None)
 base=ROOT/'.build/picocalc-apps-lcd-chain-20261021'
 source=base/'source';restore=base/'verified-restore-0.8.15-a7483ae6'
 receipt=json.loads((restore/'RESTORE.json').read_text());manifest=json.loads((restore/'manifest.json').read_text())
 files=sorted([source/'tools/build_picocalc.py',source/'tools/seal_picocalc.py',
  *(p for folder in ('code','ports/picocalc','third_party/fatfs') for p in (source/folder).rglob('*')
    if p.is_file() and (p.suffix in ('.c','.cpp','.h','.hpp','.S','.inc','.ld','.pio') or p.name=='CMakeLists.txt'))])
 h=hashlib.sha256()
 for f in files:h.update(str(f.relative_to(source)).encode()+b'\0');h.update(f.read_bytes())
 assert h.hexdigest()==receipt['source_sha256']==manifest['source_sha256']
 assert receipt['build_id']==manifest['build_id']=='a7483ae6'
 assert sha(restore/receipt['uf2'])==receipt['uf2_sha256']==manifest['uf2_sha256']
 pattern=re.compile(r'\b(?:interp[01]|hardware_interp|interp_claim_lane|interp_save|interp_restore)\b|0[xX][dD]00000[89a-fA-F][0-9a-fA-F]')
 users=[]
 for f in files:
  for n,line in enumerate(f.read_text(errors='replace').splitlines(),1):
   if pattern.search(line):users.append([str(f.relative_to(source)),n,line.strip()])
 assert not users,users
 firmware_elf=restore/'mk61s-picocalc-pico-h.elf'
 dis=subprocess.run([str(tc/'arm-none-eabi-objdump'),'-d',str(firmware_elf)],check=True,capture_output=True,text=True).stdout
 control_writes=[line.strip() for line in dis.splitlines() if re.search(r'\bmsr\s+CONTROL\b',line,re.I)]
 assert not control_writes,control_writes
 map_text=(restore/'mk61s-picocalc-pico-h.elf.map').read_text()
 assert not re.search(r'hardware_interp|interp_claim_lane|interp_save|interp_restore',map_text)
 probe=r'''
#include "loadable_app_api.h"
#include "loadable_app_services.h"
#include "portable_app_config.h"
#include <stddef.h>
const uint32_t probe[] __attribute__((section(".proof")))={
 MK61_CURRENT_APP_ABI,MK61_APP_API_MAGIC,MK61_APP_API_VERSION,
 offsetof(mk61_app_api,service),offsetof(mk61_app_api,query_service),
 MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,offsetof(mk61_app_services,call),
 MK61_SERVICE_CAP_FILES,MK61_SERVICE_CAPABILITIES,MK61_SERVICE_FILE_RESOLVE,
 MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
 sizeof(mk61_service_file),sizeof(mk61_service_write)};
'''
 values={}
 for name,tree in (('frozen',source),('current',ROOT)):
  c=out/(name+'.c');obj=out/(name+'.o');raw=out/(name+'.bin');c.write_text(probe)
  subprocess.run([str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-I'+str(tree/'code'),'-c',str(c),'-o',str(obj)],check=True)
  subprocess.run([str(tc/'arm-none-eabi-objcopy'),'-O','binary','--only-section=.proof',str(obj),str(raw)],check=True)
  values[name]=list(struct.unpack('<16I',raw.read_bytes()))
 assert values['frozen']==values['current'] and values['frozen'][0]==6,values
 app_manifest=a.apps
 apps=json.loads(app_manifest.read_text())['apps']
 free=manifest['main_ram_region_bytes']-manifest['static_ram_bytes']
 assert max(v['memory_bytes'] for v in apps.values())<=24576<free
 decoder=out/'accepted-decoder'
 subprocess.run(['c++','-std=c++17','-O2','-DMK61_CORE_STANDALONE=1','-I'+str(source/'code'),
  str(HERE/'decode-proof.cpp'),str(source/'code/loadable_module_format.cpp'),str(source/'code/zx0.cpp'),'-o',str(decoder)],check=True)
 decoded=json.loads(subprocess.run([str(decoder),*[v['app'] for v in apps.values()]],check=True,capture_output=True,text=True).stdout)
 assert [r['memory_bytes'] for r in decoded]==[v['memory_bytes'] for v in apps.values()]
 native=source/'ports/picocalc/native_app.cpp'
 report=dict(status='PASS_OFFLINE',hardware_verified=False,target_build='A7483AE6',uid=receipt['uid'],
  source_sha256=h.hexdigest(),source_files=len(files),restore_uf2_sha256=sha(restore/receipt['uf2']),
  firmware_elf_sha256=sha(firmware_elf),firmware_disassembly_sha256=hashlib.sha256(dis.encode()).hexdigest(),
  no_named_or_literal_interp_clients_in_frozen_product_source=True,no_linked_interp_helpers=True,
  privilege_evidence='No MSR CONTROL in accepted ELF; direct normal C entry at native_app.cpp:1323. APP independently requires Thread/privileged/core0/PRIMASK0.',
  abi_probe=values,accepted_loader_decode=decoded,app_abi=6,app_nominal_limit=49152,static_main_ram_headroom=free,
  app_memory_bytes={k:v['memory_bytes'] for k,v in apps.items()},
  arena_limit='Each APP <=24 KiB, below 30,760 B static headroom. Live allocator availability still requires preflight; allocation is delegated to the unchanged accepted loader.',
  loader_peak='A748 reads a 64-byte header and streams compressed input into calloc(memory_size+7); it releases the old drawing before allocation. No full compressed APP buffer is allocated. Decoder workspace uses the reserved CPU stack; no decoder heap allocation.',
  exclusion='One foreground APP on core0. Core1 INTERP banks are independent. Firmware source and linked-object audit found no core0/IRQ INTERP clients; service callbacks run with original state restored.',
  restore='ACCUM0/1, BASE0/1/2, writable CTRL0/1 for both core0 INTERP banks. Never snapshot POP. Idle SIO divider operands/results also restored/read back.',
  scope='Offline source/ABI audit, not a fresh device-state receipt or a hardware lease.',
  source_anchors={str(p.relative_to(source)):sha(p) for p in (native,source/'code/loadable_module_format.hpp',source/'code/mpu_guard.hpp',source/'ports/picocalc/main.cpp')})
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('abi_probe','source_anchors')},indent=2))
if __name__=='__main__':main()
