#!/usr/bin/env python3
"""Build finite retained-state probes from exact M3 ELF data addresses."""
from pathlib import Path
import argparse,json,hashlib,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sdk/coproc'))
from elf32 import ELF
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--m3',type=Path,required=True)
p.add_argument('--probes',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
elf=a.m3/'base/source/build/picocalc_BIOS_jcs.elf';e=ELF(elf);stats=e.symbols['bios_sleep_stats']
assert stats['size']==12 and 0x20000000<=stats['value']<0x20005000
result={'physical_io':False,'M3_ELF_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'stats_address':hex(stats['value']),'apps':{}}
for name,hold in [('SLEEPCAN',0),('SLEEPHLD',1)]:
    out=a.output/name;out.mkdir()
    (out/'sleep_probe_config.h').write_text(f'#define SLEEP_STATS_ADDRESS {stats["value"]}u\n#define SLEEP_KEEP_MODULE {hold}\n')
    cmd=[sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),'--target','picocalc-pico-h','--name',name,
        '--output-dir',str(out/'app'),'--arm-toolchain-bin',str(a.toolchain)]
    for inc in [ROOT/'sdk/coproc',a.probes,out]:cmd+=['--include',str(inc)]
    for source in [ROOT/'tests/picocalc_m3_sleep_canary_app.c',ROOT/'sdk/coproc/stm3_client.c',ROOT/'sdk/coproc/pico_uart1.c']:cmd+=['--source',str(source)]
    with (out/'build.log').open('w')as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
    app=out/'app'/f'{name}.APP';assert app.stat().st_size<32768
    linked=app.with_suffix('.bin').read_bytes();assert b'SLEEPCAN READY' in linked and b'SLEEPCAN RESUME' in linked
    result['apps'][name]={'path':str(app.resolve()),'bytes':app.stat().st_size,'sha256':hashlib.sha256(app.read_bytes()).hexdigest()}
(a.output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
