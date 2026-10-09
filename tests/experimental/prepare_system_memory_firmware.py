#!/usr/bin/env python3
"""Build matched normal residents differing only in global memory helpers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from hil_packbits_firmware import firmware_info


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--source-dir',type=Path,required=True)
    p.add_argument('--flags',type=Path,required=True)
    p.add_argument('--variant',choices=('baseline','candidate'),required=True)
    p.add_argument('--baseline-scope',choices=('copy_compare','fill_move'),default='copy_compare',
                   help='which global replacements to omit in the baseline')
    args=p.parse_args()
    out=args.output_dir.resolve()/args.variant
    sketch=out/'mk61s-M'
    assert not sketch.exists(),'use a fresh snapshot'
    shutil.copytree(args.source_dir,sketch)
    if args.variant=='baseline':
        if args.baseline_scope=='copy_compare':
            (sketch/'system_memory.c').unlink(missing_ok=True)
        else:
            (sketch/'system_memory_fill_move.c').unlink()
    flags=args.flags.read_text().strip()
    env=dict(os.environ,SOURCE_DATE_EPOCH='1791504000')
    # Keep the qualified Classic F411 -Os policy for both images.
    fqbn='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=osstd'
    properties=subprocess.check_output(['arduino-cli','compile','--fqbn',fqbn,
        '--show-properties=expanded','--build-path',str(out/'properties'),str(sketch)],env=env,text=True)
    properties=dict(line.split('=',1) for line in properties.splitlines() if '=' in line)
    linker=out/'portable.ld'
    subprocess.run([sys.executable,ROOT/'tools/.mk61-gcc/portable-layout.py',
        Path(properties['build.variant.path'])/properties['build.ldscript'],linker],env=env,check=True)
    link='-Wl,--wrap=USBD_CDC_ClearBuffer,--wrap=USBD_LL_SetupStage,--wrap=USBD_LL_Reset,--wrap=USBD_LL_Suspend,--wrap=USBD_LL_Resume,--wrap=USBD_LL_DevConnected,--wrap=USBD_LL_DevDisconnected'
    command=['arduino-cli','compile','--fqbn',fqbn,'--jobs','8',
        '--build-path',str(out/'build'),'--build-property','compiler.cpp.extra_flags='+flags,
        '--build-property','compiler.c.extra_flags=-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0',
        '--build-property','compiler.c.elf.extra_flags='+link+' -Wl,--default-script='+str(linker),str(sketch)]
    (out/'build-command.json').write_text(json.dumps(command,indent=2)+'\n')
    print('Building',args.variant,'resident',flush=True)
    with (out/'build.log').open('w') as log:
        subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    binary=out/'build/mk61s-M.ino.bin';elf=out/'build/mk61s-M.ino.elf'
    subprocess.run(['bash',ROOT/'tools/seal-firmware.sh','seal','--max-size','524288',binary],env=env,check=True)
    subprocess.run(['bash',ROOT/'tools/seal-firmware.sh','check','--max-size','524288',binary],env=env,check=True)
    subprocess.run([sys.executable,ROOT/'tools/seal-firmware-elf.py','--bin',binary,'--elf',elf,
        '--compile-commands',out/'build/compile_commands.json'],env=env,check=True)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sketch.iterdir() if p.is_file()}
    result={'variant':args.variant,'baseline_scope':args.baseline_scope,'firmware':firmware_info(binary),'source_hashes':hashes,'flags':flags}
    (out/'evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(args.variant,result['firmware']['build'],result['firmware']['bytes'],'bytes',flush=True)


if __name__=='__main__':main()
