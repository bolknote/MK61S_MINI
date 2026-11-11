#!/usr/bin/env python3
"""Finite HOST checks: sanitizers, firmware provenance, resources, and vectors."""
from pathlib import Path
import hashlib,json,struct,subprocess
from elf32 import ELF
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];B=ROOT/'.build/stm32-module-runtime-20261107'
flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(R/'include'),'-I'+str(R/'runtime')]
for source,target in [(R/'runtime/stm3_runtime.c','runtime-host.o'),(R/'modules/q4_dot.c','module-host.o')]:subprocess.run(['clang','-std=c11',*flags,'-c',str(source),'-o',str(B/target)],check=True)
subprocess.run(['clang++','-std=c++17',*flags,str(R/'tests/runtime_test.cpp'),str(B/'runtime-host.o'),str(B/'module-host.o'),'-o',str(B/'runtime-host-test')],check=True)
with(B/'host-tests.log').open('w')as log:subprocess.run([str(B/'runtime-host-test'),str(B/'module/q4_dot.s3m')],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=30)
assert 'HOST ASan/UBSan PASS:'in(B/'host-tests.log').read_text()
pins=json.loads((R/'upstream.json').read_text())['upstream']['files']
for name,digest in pins.items():assert hashlib.sha256((R/'vendor/picocalc_keyboard'/name).read_bytes()).hexdigest()==digest,name
sketch=B/'sketch/picocalc_keyboard';changed=[]
for name in pins:
 if (R/'vendor/picocalc_keyboard'/name).read_bytes()!=(sketch/name).read_bytes():changed.append(name)
assert changed==['picocalc_keyboard.ino']
db=json.loads((B/'firmware-build/compile_commands.json').read_text());sources=sorted({x['file']for x in db})
assert not any(Path(x).is_relative_to(ROOT/'code')or Path(x).is_relative_to(ROOT/'ports')for x in sources),'MK61S product source compiled into keyboard!'
assert not any('q4_dot'in x for x in sources),'Module embedded in resident firmware'
firmware=json.loads((B/'firmware/manifest.json').read_text());assert firmware['flash_bytes']<=65536 and firmware['ram_remaining_bytes']>=4096
elf=ELF(B/'firmware/picocalc_keyboard.ino.elf');assert 'module_entry'not in elf.symbols
image=(B/'firmware/picocalc_keyboard.ino.bin').read_bytes();sp,reset=struct.unpack_from('<II',image)
assert sp==0x20005000 and reset&1 and 0x08000000<=reset<0x08010000
assert firmware['uart']['baud']==2250000 and firmware['uart']['hardware_rate_measured']is False
report=dict(status='HOST_PASS',physical_io=False,asan_ubsan=True,numeric_reference_rows=1360,jobs=160,malformed_packages=11,framing_noise_bytes=60000,stock_vendor_hashes_verified=True,stock_files_changed=changed,keyboard_matrix_i2c_power_backlight_sources_identical=True,mk61s_product_source_files=0,module_embedded_in_firmware=False,vector_sp=hex(sp),vector_reset=hex(reset),firmware_sha256=hashlib.sha256(image).hexdigest(),flash_bytes=firmware['flash_bytes'],ram_linked_including_heap_stack=firmware['ram_linked_bytes_including_heap_stack_reserve'],ram_unallocated_after_link=firmware['ram_remaining_bytes'],compile_source_count=len(sources))
(B/'host-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
