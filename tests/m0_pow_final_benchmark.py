#!/usr/bin/env python3
"""Build the final RP2040 pow benchmark and verify its raw results."""
import argparse
from pathlib import Path
import shutil
import hashlib
import json
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'dev/lib'),str(ROOT/'ports/picocalc')]
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle, bits
from seal_picocalc import BASE, FOOTER, verify
from tools.firmware.picocalc.build_picocalc import TARGET, compiler_bin
from uf2 import validate

DIR='/MK61S-POW-EXACT'
APP='POWEXACT.APP'
HEADER=struct.Struct('<6I')
SAMPLE=struct.Struct('<12IQ')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_bytes())

CASES=(
    ('full_chain_maximum_products',0x000fffffffffffff,0xbbffffffffffffff,bits(1.0),1),
    ('exact_integer_inverse',bits(1.0)-1,bits(-511/128),bits(1.0)+2,0),
    ('exact_even_lower_tie',bits(3.),bits(34.),0x434d9fe779881944,0),
    ('exact_zero_subnormal_tie',bits(2.),bits(-1075.),0,0),
)
STREAMING_INVERSE=('exact_streaming_inverse',bits(1.0)-1,bits(-1023/128),bits(1.0)+3,0)

def decode(raw,metadata):
    version=metadata.get('wire_version',1)
    assert version in (1,2)
    cases=CASES+(STREAMING_INVERSE,) if version==2 else CASES
    head=HEADER.unpack_from(raw)
    assert head==(0x544f5730+version,int(metadata['firmware']['build_id'],16),len(cases),8000,0,0),head
    assert len(raw)==HEADER.size+len(cases)*SAMPLE.size and len(metadata['rows'])==len(cases)
    out=[]
    for row,packet in zip(metadata['rows'],SAMPLE.iter_unpack(raw[HEADER.size:])):
        prefix,tail,total,early,entry,after,max_gap,age,hz_before,hz_after,caller,stage4096,result=packet
        assert prefix+tail==total and hz_before==hz_after==125000000
        assert early<=entry<=after and (row['full'] or early==entry)
        assert result==row['expected'] and max_gap<8000 and age<8000000
        assert 0<caller<=32768-20480
        if version==2 and row['full']:
            assert 0<stage4096<=prefix
        else:
            assert stage4096==0
        if row['full'] or tail>=30000:
            assert after>entry
        out.append(dict(name=row['name'],prefix_us=prefix,final_us=tail,chain_us=total,
                        stage4096_us=stage4096,reloads_prefix=entry-early,
                        entry_reloads=entry,after_reloads=after,reloads_inside=after-entry,
                        max_watchdog_gap_ms=max_gap,last_feed_age_us=age,caller_stack_bytes=caller,rounded=f'{result:016x}'))
    return out

def build(args):
    work=args.output.resolve()
    firmware=args.production.resolve()
    elf_path=firmware/(TARGET+'.elf')
    bin_path=firmware/(TARGET+'.bin')
    uf2_path=firmware/(TARGET+'.uf2')
    f=read(firmware/'manifest.json')
    raw=bin_path.read_bytes()
    assert len(raw)==f['flash_bytes'] and sha(bin_path)==f['bin_sha256'] and sha(uf2_path)==f['uf2_sha256']
    validate(uf2_path.read_bytes(),raw)
    off=f['firmware_integrity']['footer_offset']
    assert verify(raw,off)==f['firmware_integrity']
    elf=ElfImage(elf_path)
    for kind,offset,_,load,size,*rest in elf.segments:
        if kind==1 and size:
            assert BASE<=load and load+size<=BASE+len(raw)
            assert raw[load-BASE:load+size-BASE]==elf.data[offset:offset+size]
    addresses=dict(POW_512='m0_pow_interval5FixedILj512EE8evaluateEyyRy',
        POW_1024='m0_pow_interval5FixedILj1024EE8evaluateEyyRy',
        POW_EXACT='mk61_m0_pow_exact_small', POW_4096='PowerBoundsILj256EE4sideEyyy',
        POW_FINAL='mk61_m0_pow_round_final',POW_STREAM='m0_pow_stream12_GLOBAL__N_14sideEyyy',
        POW_FEED='diagnostics13feed_watchdogEv',POW_CLOCK='clock_get_hz',
        POW_WATCHDOG='diagnostics12_GLOBAL__N_18watchdogE',
        POW_LAST_FEED='diagnostics12_GLOBAL__N_19last_feedE',POW_FW_FOOTER='mk61_picocalc_firmware_footer')
    constants=[]
    bindings={}
    for key,substring in addresses.items():
        ((name,addr),)=tuple((k,v) for k,v in elf.symbols.items() if substring in k and elf.sizes[k])
        if key=='POW_FW_FOOTER':
            assert addr==BASE+off and elf.sizes[name]==FOOTER.size
        elif key in ('POW_WATCHDOG','POW_LAST_FEED'):
            assert addr%4==0 and 0x20000000<=addr<0x20038000
            assert elf.sizes[name]==(24 if key=='POW_WATCHDOG' else 8)
        else:
            assert BASE<addr<BASE+len(raw)
            addr|=1
        constants.append(f'#define {key} 0x{addr:08x}U')
        bindings[key]=dict(symbol=name,address=addr,size=elf.sizes[name])
    top=elf.symbols['__StackTop']
    assert top-elf.symbols['__StackBottom']==32768
    constants.append(f'#define POW_STACK_TOP 0x{top:08x}U')
    constants.append('#define POW_FOOTER_WORDS '+','.join(f'0x{x:08x}U' for x in struct.unpack_from('<10I',raw,off)))
    constants.append('#define POW_BUILD_ID 0x'+f['build_id']+'U')
    if args.detailed:
        constants.append('#define POW_BENCH_DETAILED 1')
    work.mkdir(parents=True)
    source=work/'POWEXACT.c'
    shutil.copy2(ROOT/'tests/fixtures/m0_pow_final_benchmark.c',source)
    (work/'pow_total_locations.h').write_text('\n'.join(constants)+'\n')
    oracle=Oracle()
    rows=[]
    inp=bytearray()
    cases=CASES+(STREAMING_INVERSE,) if args.detailed else CASES
    for name,x,y,lower,full in cases:
        want=oracle.reference('pow',x,y)
        assert want in (lower,lower+1),(name,hex(want),hex(lower))
        rows.append(dict(name=name,x=x,y=y,lower=lower,expected=want,full=full))
        inp.extend(struct.pack('<4Q2I',x,y,lower,want,full,0))
    (work/'INPUT.bin').write_bytes(inp)
    command=[sys.executable,'-B',str(ROOT/'tools/apps/portable/build_portable_app.py'),
             '--target','picocalc-pico-h','--name','POWEXACT','--source',str(work/'POWEXACT.c'),
             '--shared-runtime','--arm-toolchain-bin',str(compiler_bin(args.toolchain)),'--output-dir',str(work/'app')]
    with (work/'build-app.log').open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    app=work/'app'/APP
    out=dict(firmware=f,elf_sha256=sha(elf_path),wire_version=2 if args.detailed else 1,
        app=str(app),app_sha256=sha(app),input=str(work/'INPUT.bin'),input_sha256=sha(work/'INPUT.bin'),
        rows=rows,bindings=bindings,mpfr=oracle.version,erase_end=hex(BASE+((len(raw)+4095)&~4095)))
    (work/'benchmark.json').write_text(json.dumps(out,indent=2)+'\n')

def main():
    if sys.flags.optimize:
        raise SystemExit('Benchmark checks require Python assertions')
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_subparsers(dest='mode', required=True)
    prepare=modes.add_parser('prepare')
    prepare.add_argument('--production', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--toolchain', type=Path)
    prepare.add_argument('--detailed', action='store_true', help='Time the 4096-bit stage separately and include a longer exact inverse')
    replay=modes.add_parser('verify')
    replay.add_argument('--benchmark', type=Path, required=True)
    replay.add_argument('--result', type=Path, required=True)
    args=parser.parse_args()
    if args.mode=='prepare':
        build(args)
    else:
        print(json.dumps(decode(args.result.read_bytes(),read(args.benchmark)),indent=2))


if __name__=='__main__':
    main()
