#!/usr/bin/env python3
"""Execute Rust and C++ APP entry points on Cortex-M0 and Cortex-M4 models.

Requires unicorn, ARM GCC and the Rust thumbv6m/thumbv7em target libraries.
Checks the actual packed/relocated code, not just object-file compilation.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from run_portable_app_arm_tests import Machine, CALLBACKS, BASE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_CPU_ARM_CORTEX_M0, UC_CPU_ARM_CORTEX_M4)

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin


class ExampleMachine(Machine):
    def hook(self,uc,address,size,context):
        name=self.callbacks.get(address)
        if name not in ('key_wait','display_write_m8','display_rows','display_columns','led_blink','beep'):
            return super().hook(uc,address,size,context)
        result=0
        if name=='key_wait':
            self.waits+=1;result=39  # A key is not an APP error status.
        elif name=='display_rows':result=8
        elif name=='display_columns':result=32
        elif name=='display_write_m8':
            x,y,pointer,length=[uc.reg_read(r) for r in
                (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
            assert x==0 and y<8 and 0<length<=63
            assert self.base<=pointer<=self.base+self.memory_size-length
            self.text.append(bytes(uc.mem_read(pointer,length)).decode());result=1
        uc.reg_write(UC_ARM_REG_R0,result)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-toolchain-bin',type=Path)
    parser.add_argument('--rustc',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();toolchain=compiler_bin(args.arm_toolchain_bin)
    cases=[]
    with tempfile.TemporaryDirectory(prefix='mk61-rust-arm-') as raw:
        work=Path(raw)
        for target,model in (('picocalc-pico-h',UC_CPU_ARM_CORTEX_M0),('stm32',UC_CPU_ARM_CORTEX_M4)):
            reader=work/('reader-'+target)
            flags=['-DMK61_CORE_STANDALONE=1'] if target=='picocalc-pico-h' else []
            subprocess.run(['c++','-std=c++17','-O2',*flags,'-I'+str(ROOT/'code'),
                str(ROOT/'tests/portable_app_format_self_test.cpp'),str(ROOT/'code/loadable_module_format.cpp'),
                str(ROOT/'code/zx0.cpp'),'-o',str(reader)],check=True)
            for name,source,expected in (
                ('HELLO_RS','examples/portable-apps/HELLO-RUST/main.rs',['HELLO, MK61S!']),
                ('HELLO_CPP','examples/loadable-apps/HELLO/hello_app.cpp',['HELLO APP','KEY TO EXIT'])):
                out=work/target/name
                command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target',target,
                    '--name',name,'--source',str(ROOT/source),'--arm-toolchain-bin',str(toolchain),
                    '--output-dir',str(out)]
                if args.rustc:command+=['--rustc',str(args.rustc)]
                built=subprocess.run(command,capture_output=True,text=True)
                assert built.returncode==0,built.stdout+built.stderr
                packed=(out/(name+'.APP')).read_bytes()
                assert bool(struct.unpack_from('<I',packed,16)[0]&8)==(target=='picocalc-pico-h')
                image_size,_,entry=struct.unpack_from('<III',packed,28)
                image_crc=struct.unpack_from('<I',packed,52)[0]
                # Public ABI layout; deliberately unrelated callback addresses.
                api_address=0x08010000
                api=struct.pack('<IHHI',0x31505041,1,108,31)
                api+=struct.pack('<23I',*(0x08020001+4*i for i in range(len(CALLBACKS))))
                api+=struct.pack('<I',0)
                for address in (BASE,BASE+0x100,BASE+0x10000):
                    memory=work/'decoded.bin'
                    subprocess.run([str(reader),str(out/(name+'.APP')),str(memory),hex(address)],check=True)
                    machine=ExampleMachine(api_address,api,cpu_model=model)
                    for _ in range(2):
                        machine.load(memory.read_bytes(),image_size,entry,address);machine.waits=0
                        assert machine.call(0,api_address,image_crc,4)==0
                        assert machine.call(1)==0,(target,name,machine.text)
                        assert machine.text==expected,(target,name,machine.text)
                        assert machine.waits==1,(target,name,machine.waits)
                cases.append({'target':target,'app':name,'load_addresses':3,'fresh_launches_per_address':2})
                print(f'PASS {target} {name}: real main, text, nonzero exit key, relocation and register/memory guards')
    if args.output:args.output.write_text(json.dumps({'passed':True,'cases':cases},indent=2)+'\n')


if __name__=='__main__':main()
