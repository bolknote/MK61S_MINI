#!/usr/bin/env python3
"""Rebuild the M3 images from an extracted, pinned source.zip (no devices)."""
from pathlib import Path
import argparse,hashlib,json,os,struct,subprocess,zlib

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--drivers',type=Path,required=True);ap.add_argument('--toolchain',type=Path,required=True)
    args=ap.parse_args();root=Path(__file__).resolve().parent;drivers=args.drivers.resolve();tool=args.toolchain.resolve()
    expected=json.loads((root/'expected.json').read_text())
    for name,digest in expected['sources'].items():
        if sha(root/name)!=digest:raise ValueError('Source changed: '+name)
    for name,revision in expected['upstream'].items():
        checkout=drivers.parent if name=='.' else drivers.parent/name
        if subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()!=revision:raise ValueError('Dependency changed: '+name)
        if name!='.' and subprocess.check_output(['git','-C',str(checkout),'status','--porcelain','--untracked-files=no'],text=True):raise ValueError('Dirty dependency: '+name)
    source=root/'source'
    if not (source/'Drivers').exists():(source/'Drivers').symlink_to(drivers,target_is_directory=True)
    subprocess.run(['make','-C',str(source),'clean'],check=True)
    subprocess.run(['make','-C',str(source),'-j2','GCC_PATH='+str(tool),'OPT=-Os -flto'],check=True)
    out=root/'rebuilt';out.mkdir(exist_ok=True);boot=root/'boot'
    cmd=[str(tool/'arm-none-eabi-gcc'),'-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-Os','-flto','-ffreestanding','-fno-builtin',
         '-fdata-sections','-ffunction-sections','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror',
         '-Wno-misleading-indentation','-DSTM32F103xB','-I'+str(drivers/'CMSIS/Include'),'-I'+str(drivers/'CMSIS_Device_ST_STM32F1xx/Include'),
         '-nostdlib','-Wl,--gc-sections,-Map='+str(out/'boot.map'),'-Wl,-T,'+str(boot/'boot.ld'),
         *map(str,[boot/'start.S',boot/'hardware.c',boot/'wire.c',boot/'update.c']),'-o',str(out/'boot.elf')]
    subprocess.run(cmd,check=True);subprocess.run([str(tool/'arm-none-eabi-objcopy'),'-O','binary',str(out/'boot.elf'),str(out/'boot.bin')],check=True)
    data=(source/'build/picocalc_BIOS_jcs.bin').read_bytes();data+=b'\xff'*((-len(data))%4)
    if len(data)>0xd400:raise ValueError('BIOS overlaps metadata')
    h=struct.pack('<7I',0x3155334d,1,0x410,0x08002000,len(data),zlib.crc32(data),int.from_bytes(hashlib.sha256(data).digest()[:4],'little'))
    h+=struct.pack('<I',zlib.crc32(h));(out/'bios.bin').write_bytes(data);(out/'BIOS.M3U').write_bytes(h+data)
    b=(out/'boot.bin').read_bytes()
    if len(b)>8192:raise ValueError('Boot region overflow')
    combined=b+b'\xff'*(8192-len(b))+data
    combined+=b'\xff'*(0xf400-len(combined))+h+struct.pack('<I',0xc001cafe)
    (out/'bootstrap.bin').write_bytes(combined)
    for name,digest in expected['images'].items():
        if sha(out/name)!=digest:raise ValueError('Rebuilt image differs: '+name)
    print('M3 loader/BIOS/M3U/bootstrap byte-exact rebuild PASS')
if __name__=='__main__':main()
