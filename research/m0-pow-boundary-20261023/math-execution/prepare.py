"""Offline math-only V138 package: never opens a device or changes the candidate."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path.cwd()
WORK = Path(__file__).resolve().parent
BASE = ROOT/'.build/m0-pow-horner-final-v138-20261023'
PRIOR = ROOT/'.build/m0-balanced-timing-v87-20261022'
TC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'tools')]
from check_stm32_vectors import ElfImage
from check_m0_math_layout import symbol_types
from m0_mpfr_oracle import Oracle, bits, real
from native_eabi_m0_arm_self_test import f_bits, f_real, signed


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2)+'\n')


elf_path = BASE/'firmware/mk61s-picocalc-pico-h.elf'
assert sha(elf_path) == 'f4010ce9153d8b9776b236751fcfe67da5e528c2bff5725f87478fec74a42895'
manifest = json.loads((BASE/'firmware/manifest.json').read_text())
assert manifest['build_id'].upper() == '83CF4AC4'
elf = ElfImage(elf_path)
types = symbol_types(elf)
reference_base = 0x10180000
assert manifest['flash_bytes'] == 1537008 < reference_base-0x10000000
assert elf.symbols['__flash_binary_end'] == 0x10000000+manifest['flash_bytes']

# Link only an isolated, RAM-free reference. No production symbols are
# supplied: --no-undefined makes any accidental owned-math dependency fail.
linked = WORK/'sources/qfplib-linked.S'
original = linked.read_text().replace('.section .m0_qfplib,"ax",%progbits\n', '', 1)
assert hashlib.sha256(original.encode()).hexdigest() == 'c9db54280a92c30e7c3b55adda24a8a540d33d52b7cba6185f9735c5efdd4654'
(WORK/'sources/qfplib-original.S').write_text(original)
refdir = WORK/'reference'
refdir.mkdir(exist_ok=True)
flags = ['-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft', '-Os', '-fno-lto',
         '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-ffunction-sections', '-fdata-sections']
objects = []
for name in ('qfplib-linked.S', 'adapters.S', 'compositions.c'):
    obj = refdir/(name+'.o')
    subprocess.run([str(TC/'arm-none-eabi-gcc'), *flags, '-c', str(WORK/'sources'/name), '-o', str(obj)], check=True)
    objects.append(obj)
linker = refdir/'reference.ld'
linker.write_text('ENTRY(qfp_dadd)\nSECTIONS {\n .m0_qfplib 0x10180000 : { KEEP(*(.m0_qfplib)) *(.text*) *(.rodata*) }\n .reference_ram (NOLOAD) : { *(.data*) *(.bss*) *(COMMON) }\n /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) }\n ASSERT(SIZEOF(.reference_ram)==0,"Reference must not add RAM state")\n}\n')
refelf = refdir/'reference.elf'
subprocess.run([str(TC/'arm-none-eabi-gcc'), *flags, '-nostdlib', '-Wl,--no-undefined',
                '-Wl,-T,'+str(linker), '-Wl,-Map='+str(refdir/'reference.map'),
                *map(str, objects), '-o', str(refelf)], check=True)
ref = ElfImage(refelf)
section = ref.named_sections['.m0_qfplib']
assert section[3] == reference_base and section[3]+section[5] < 0x101FE000
blob = ref.bytes_at(section)
(refdir/'reference.bin').write_bytes(blob)
assert hashlib.sha256(blob).hexdigest() == '8a71ababc3538394b49590350fb0b4602b1253736543dd80391514c84bf235f3'
for s in ref.sections:
    if s[2]&2 and s[5]:
        assert s[1] != 8 and reference_base <= s[3] and s[3]+s[5] <= reference_base+len(blob)
assert not subprocess.check_output([str(TC/'arm-none-eabi-nm'), '-u', str(refelf)]).strip()

# An explicitly separate sector-aligned flash addon. Its UF2 has no blocks
# in the V138 image or settings sectors; transaction code owns installation.
addon = blob.ljust((len(blob)+4095)//4096*4096, b'\xff')
(refdir/'reference-sectors.bin').write_bytes(addon)
uf2 = bytearray()
count = len(addon)//256
for i in range(count):
    uf2 += struct.pack('<8I', 0x0A324655, 0x9E5D5157, 0x2000, reference_base+i*256,
                       256, i, count, 0xE48BFF56)
    uf2 += addon[i*256:(i+1)*256]+bytes(220)+struct.pack('<I', 0x0AB16F30)
(refdir/'reference-only.uf2').write_bytes(uf2)
reference_fnv = 2166136261
for byte in blob:
    reference_fnv = ((reference_fnv^byte)*16777619)&0xFFFFFFFF

def read_at(address, size):
    s = next(s for s in elf.sections if s[1] != 8 and s[2]&2 and s[3] <= address and address+size <= s[3]+s[5])
    return elf.bytes_at(s)[address-s[3]:address-s[3]+size]

runtime_address = 0x10093EA8
slots = struct.unpack('<26I', read_at(runtime_address, 104))
names = re.findall(r'^MK61_RUNTIME(?:_ISO_C)?\(([^,)]+)', (BASE/'source/code/loadable_system_runtime.def').read_text(), re.M)
assert len(names) == len(slots) == 26
for name, value in zip(names, slots):
    assert value in {elf.symbols[n]|1 for n in (name, '__wrap_'+name) if n in elf.symbols}, name

# Preserve the qualified harness and its wire format. Only add pre/post
# guards outside timing, plus one small audit file. There are no key waits.
fixture = (WORK/'sources/TIMING-original.c').read_text()
guard = '''
extern const mk61_service_runtime_function* mk61_app_runtime;
static struct { uint32_t magic,version,runtime,count,reference_fnv,clock_before,clock_after,footer_crc; } audit;
static uint32_t resident_clock(void) { return ((uint32_t(*)(unsigned))CLOCK_FN)(5); }
static int guard_begin(void) {
 audit.magic=0x56313338U;audit.version=1;audit.runtime=(uintptr_t)mk61_app_runtime;
 audit.count=26;audit.reference_fnv=2166136261U;
 if(audit.runtime!=RUNTIME_ADDR) return 0;
 RUNTIME_CHECKS
 const volatile uint8_t* ref=(const volatile uint8_t*)REFERENCE_ADDR;
 for(unsigned i=0;i<REFERENCE_BYTES;++i) audit.reference_fnv=(audit.reference_fnv^ref[i])*16777619U;
 audit.footer_crc=*(const volatile uint32_t*)FOOTER_CRC_ADDR;
 audit.clock_before=resident_clock();audit.clock_after=0;
 return audit.reference_fnv==REFERENCE_FNV && audit.footer_crc==FOOTER_CRC && audit.clock_before==125000000U;
}
'''.replace('CLOCK_FN', hex(elf.symbols['clock_get_hz']|1)+'U').replace('RUNTIME_ADDR', hex(runtime_address)+'U')
guard = guard.replace('RUNTIME_CHECKS', '\n '.join('if((uintptr_t)mk61_app_runtime['+str(i)+']!='+hex(v)+'U) return 0;' for i,v in enumerate(slots)))
guard = guard.replace('REFERENCE_ADDR', hex(reference_base)+'U').replace('REFERENCE_BYTES', str(len(blob))+'U')
guard = guard.replace('REFERENCE_FNV', hex(reference_fnv)+'U')
footer = manifest['firmware_integrity']
crc_at = 0x10000000+footer['footer_offset']+20
# The footer layout is checked against the sealed BIN before embedding.
from seal_picocalc import FOOTER, verify
base_bin = (BASE/'firmware/mk61s-picocalc-pico-h.bin').read_bytes()
verify(base_bin, footer['footer_offset'])
crc = int(footer['crc32'], 16)
assert struct.unpack_from('<I', base_bin, crc_at-0x10000000)[0] == crc
guard = guard.replace('FOOTER_CRC_ADDR', hex(crc_at)+'U').replace('FOOTER_CRC', hex(crc)+'U')
fixture = fixture.replace('NO_TABLES int main(void) {', guard+'\nNO_TABLES int main(void) {\n    if(!guard_begin()) return MK61_APP_RUNTIME_ERROR;')
needle = '    mk61_service_write out={"RESULT",'
assert fixture.count(needle) == 1
extra = '''    audit.clock_after=resident_clock();
    if(audit.clock_after!=audit.clock_before) return MK61_APP_RUNTIME_ERROR;
    mk61_service_write check={"GUARD",(const uint8_t*)&audit,sizeof(audit),MK61_SERVICE_INVALID_ID};
    if(!s->call(MK61_SERVICE_FILE_WRITE,file.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&check)) return MK61_APP_IO_ERROR;
'''
fixture = fixture.replace(needle, extra+needle)
(WORK/'TIMING-fixture.c').write_text(fixture)
directory = '/MK61S-M0-V138-20261023'
(WORK/'TIMING.c').write_text('#define MK61_M0_TIMING_CACHE 1\n#define MK61_MATH_COMPARE_ROOT "'+directory+'"\n#include "'+str(WORK/'TIMING-fixture.c')+'"\n')

# V138 freezes the resident ABI headers, not the portable SDK tree. Pin the
# SDK inputs to their committed bytes, then check the resident ABI separately.
sdk_inputs=['sdk/portable/start.c','sdk/portable/memory.c','sdk/portable/shared_runtime.c',
            'sdk/portable/system/runtime.S','sdk/portable/include/mk61_app.h']
for name in sdk_inputs:
    committed=subprocess.check_output(['git','show','e640d20cd:'+name],cwd=ROOT)
    assert (ROOT/name).read_bytes()==committed,name
for name in ('loadable_app_api.h','loadable_app_services.h','loadable_system_runtime.def'):
    assert sha(ROOT/'code'/name)==sha(BASE/'source/code'/name)
command = [sys.executable, str(ROOT/'tools/build_portable_app.py'), '--target', 'picocalc-pico-h',
           '--name', 'TIMING', '--source', str(WORK/'TIMING.c'), '--shared-runtime',
           '--arm-toolchain-bin', str(TC), '--output-dir', str(WORK/'app')]
with (WORK/'app-build.log').open('w') as log:
    subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)

previous = json.loads((PRIOR/'benchmark.json').read_text())
inputs = WORK/'inputs'
inputs.mkdir(exist_ok=True)
oracle = Oracle()
chunks=[];oracle_counts={}
def expected(kind, op, a, b):
    if op in oracle.NAMES:
        return oracle.reference(op, a, b) if op in oracle.BINARY else oracle.reference(op, a)
    if kind in (2,3,4,5):
        n=signed(a&((1<<32)-1),32) if kind==2 else signed(a,64) if kind==4 else a
        return bits(float(n))
    if kind in (6,7,8,9):
        width=32 if kind in (6,7) else 64;is_signed=kind in (6,8)
        value=int(real(a));low=-(1<<(width-1)) if is_signed else 0
        high=(1<<(width-1))-1 if is_signed else (1<<width)-1
        return max(low,min(high,value))&((1<<width)-1)
    if kind==10:return bits(f_real(a))
    if kind==11:return f_bits(real(a))
    if kind==12:
        x,y=real(a),real(b)
        return int({'dcmpeq':x==y,'dcmplt':x<y,'dcmple':x<=y,'dcmpge':x>=y,'dcmpgt':x>y}[op])
    raise AssertionError((kind,op))

for old in previous['chunks']:
    original=Path(old['input']).read_bytes()
    assert hashlib.sha256(original).hexdigest()==old['input_sha256']
    header=list(struct.unpack_from('<8I',original));assert len(original)==32+24*old['cases']
    own=elf.symbols[old['own_symbol']]|1;qfp=ref.symbols[old['qfplib_symbol']]|1
    assert types[old['own_symbol']]==2 and 0x10000000<own<0x10200000
    header[6:8]=own,qfp
    for a,b,want in struct.iter_unpack('<3Q',original[32:]):
        got=expected(old['kind'],old['operation'],a,b)
        assert got==want,(old['index'],old['operation'],hex(a),hex(b),hex(got),hex(want))
        oracle_counts[old['operation']]=oracle_counts.get(old['operation'],0)+1
    path=inputs/f"{old['index']:03d}.bin"
    path.write_bytes(struct.pack('<8I',*header)+original[32:])
    row=dict(old,input=str(path),input_sha256=sha(path),own_address=own,qfplib_address=qfp,
             original_input_sha256=old['input_sha256'])
    chunks.append(row)
assert len(chunks)==119 and len({c['stream_index'] for c in chunks})==117
save(WORK/'oracle.json',dict(status='PASS_ALL_FROZEN_EXPECTED_RESULTS_REVALIDATED',
    mpfr_version=oracle.version,mpfr_directed_bound_operations=sorted(oracle.NAMES),
    conversions_and_comparisons='Independent exact integer clipping, Python integer-to-binary64 RNE and binary32 packing; finite corpus only.',
    cases=sum(oracle_counts.values()),operations=oracle_counts,producer_sha256=sha(__file__),
    oracle_source_sha256=sha(ROOT/'tests/m0_mpfr_oracle.py')))
save(WORK/'reference-proof.json',dict(status='PASS_SEPARATE_REFERENCE_NO_V138_MODIFICATIONS',
    address=reference_base,bytes=len(blob),sector_bytes=len(addon),reference_sha256=sha(refdir/'reference.bin'),
    padded_sector_sha256=sha(refdir/'reference-sectors.bin'),uf2_sha256=sha(refdir/'reference-only.uf2'),
    source_sha256=sha(WORK/'sources/qfplib-original.S'),undefined_symbols=[],reference_ram_bytes=0,
    firmware_image_ends_at=0x10000000+len(base_bin),settings_begin=0x101FE000,
    existing_candidate_bytes_changed=0,scope='Diagnostic reference-only Flash addon, outside the firmware CRC extent. Installer must verify this layer separately and restore fresh full Flash afterward.'))
save(WORK/'benchmark.json',dict(status='BUILT_OFFLINE_NOT_RUN_ON_DEVICE',directory=directory,
    firmware_elf=str(elf_path),elf_sha256=sha(elf_path),firmware_manifest=manifest,
    reference_elf=str(refelf),reference_bin=str(refdir/'reference.bin'),reference_address=reference_base,
    reference_sha256=sha(refdir/'reference.bin'),reference_bytes=len(blob),reference_fnv=reference_fnv,
    runtime_table_address=runtime_address,runtime_slots=list(slots),footer_crc=crc,
    app=str(WORK/'app/TIMING.APP'),app_sha256=sha(WORK/'app/TIMING.APP'),
    fixture_sha256=sha(WORK/'TIMING-fixture.c'),rounds=12,report_version=4,app_warmup_us=1000000,
    chunks=chunks,streams=117,cases=23352,clock_hz=125000000,
    primary_estimator='order_balanced_median',cache_counters=True,
    cycle_reporting='TIMERAWL microseconds times125 at checked125MHz; physical cycle equivalents with125-cycle batch quantization, not an independent core cycle counter.',
    bootrom=str(ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'),
    method=previous['method'],build_command=command))
print('PASS: exact V138 addresses, separate identical Qfplib reference, guarded APP,119 chunks/23352 revalidated inputs.',flush=True)
