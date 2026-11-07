#!/usr/bin/env python3
"""Build permanent M3 recovery loader, relocated Southbridge and Pico SD updater.

Produces a one-time ROM bootstrap image (pages 0..61 only) and BIOS.M3U for
later updates through Pico. Does not open devices or write option bytes.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,struct,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(Path(__file__).resolve().parent),str(ROOT/'sdk/coproc')]
from build_picocalc import compiler_bin
from bios_boot import stage
from elf32 import ELF
APP=0x08002000;META=0x0800f400;SETTINGS=0x0800f800

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def package(image):
    if len(image)<8 or len(image)>META-APP:raise ValueError('BIOS image size')
    image+=b'\xff'*((-len(image))%4)
    import zlib
    h=struct.pack('<7I',0x3155334d,1,0x410,APP,len(image),zlib.crc32(image),int.from_bytes(hashlib.sha256(image).digest()[:4],'little'))
    return h+struct.pack('<I',zlib.crc32(h))+image

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-dir',type=Path,default=ROOT/'.build/picocalc-m3-boot')
    ap.add_argument('--drivers',type=Path,default=ROOT/'.build/stm32-module-runtime-20261107/community-southbridge/Drivers')
    ap.add_argument('--toolchain');ap.add_argument('--jobs',type=int,default=2)
    args=ap.parse_args();out=args.output_dir.resolve();tool=compiler_bin(args.toolchain)
    if not out.is_relative_to(ROOT/'.build') or out==ROOT/'.build':ap.error('Use an isolated .build directory')
    out.mkdir(parents=True,exist_ok=True)
    with (out/'base-build.json').open('w') as log:
        subprocess.run([sys.executable,str(ROOT/'tools/firmware/picocalc/build_async_bios.py'),'--output-dir',str(out/'base'),
                    '--drivers',str(args.drivers),'--toolchain',str(tool),'--jobs',str(args.jobs)],check=True,stdout=log)
    source=out/'base/source';stage(source)
    subprocess.run(['make','-C',str(source),'clean'],check=True,stdout=subprocess.DEVNULL)
    with (out/'app-build.log').open('w') as log:
        subprocess.run(['make','-C',str(source),'-j'+str(args.jobs),'GCC_PATH='+str(tool),'OPT=-Os -flto'],check=True,stdout=log,stderr=subprocess.STDOUT)
    app_elf=source/'build/picocalc_BIOS_jcs.elf';elf=ELF(app_elf);app=source/'build/picocalc_BIOS_jcs.bin'
    data=app.read_bytes();sp,entry=struct.unpack_from('<2I',data)
    if sp!=0x20004fe0 or not entry&1 or not APP<=(entry&~1)<APP+len(data):raise ValueError('Relocated BIOS vectors invalid')
    globals_bytes=elf.symbols['_ebss']['value']-0x20000000
    if globals_bytes+4096+2048>20*1024-32:raise ValueError('BIOS stack safety margin')
    boot=ROOT/'ports/picocalc/bios/boot';bootelf=out/'boot.elf'
    drivers=(source/'Drivers').resolve()
    cmd=[str(tool/'arm-none-eabi-gcc'),'-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-Os','-flto','-ffreestanding','-fno-builtin',
         '-fdata-sections','-ffunction-sections','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror',
         '-Wno-misleading-indentation','-DSTM32F103xB','-I'+str(drivers/'CMSIS/Include'),'-I'+str(drivers/'CMSIS_Device_ST_STM32F1xx/Include'),
         '-nostdlib','-Wl,--gc-sections,-Map='+str(out/'boot.map'),'-Wl,-T,'+str(boot/'boot.ld'),
         *map(str,[boot/'start.S',boot/'hardware.c',boot/'wire.c',boot/'update.c']),'-o',str(bootelf)]
    with (out/'boot-build.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
    binary=out/'boot.bin';subprocess.run([str(tool/'arm-none-eabi-objcopy'),'-O','binary',str(bootelf),str(binary)],check=True)
    bootdata=binary.read_bytes()
    if len(bootdata)>8192:raise ValueError('Boot exceeds reserved 8 KiB')
    packed=package(data);(out/'BIOS.M3U').write_bytes(packed)
    relocated=packed[32:];(out/'bios.bin').write_bytes(relocated)
    image=bootdata+b'\xff'*(8192-len(bootdata))+relocated
    image+=b'\xff'*(META-0x08000000-len(image))+packed[:32]+struct.pack('<I',0xc001cafe)
    if len(image)>SETTINGS-0x08000000:raise ValueError('Bootstrap overlaps settings')
    (out/'bootstrap.bin').write_bytes(image)
    sd=out/'sd/Apps/BIOS';sd.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(out/'BIOS.M3U',sd/'BIOS.M3U')
    shutil.copyfile(ROOT/'doc/explorer-icons/system.wbmp',sd/'autoexec.wbmp')
    appbuild=out/'updater'
    command=[sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),'--target','picocalc-pico-h',
      '--shared-runtime','--name','BIOSUPD','--handled-magic','M3','--arm-toolchain-bin',str(tool),
      '--include',str(boot),'--include',str(ROOT/'sdk/coproc'),'--output-dir',str(appbuild)]
    for source_file in [ROOT/'examples/portable-apps/BIOSUPD/main.c',boot/'wire.c',boot/'update.c',ROOT/'sdk/coproc/pico_uart1.c']:
        command+=['--source',str(source_file)]
    with (out/'updater-build.log').open('w') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    shutil.copyfile(appbuild/'BIOSUPD.APP',sd/'BIOSUPD.APP')
    belf=ELF(bootelf)
    result=dict(schema=1,status='BUILT_NOT_INSTALLED',target='PicoCalc STM32F103R8',flash_start='0x08000000',
      boot_bytes=len(bootdata),boot_reserved=8192,boot_ram_bytes=belf.symbols['_ebss']['value']-0x20000000,
      app_start=hex(APP),app_limit=META-APP,app_bytes=len(relocated),app_global_ram_bytes=globals_bytes,app_stack_bytes=4096,
      metadata_start=hex(META),settings_start=hex(SETTINGS),erase_pages=62,option_byte_writes=False,physical_io=False,
      files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p))for p in [binary,out/'bios.bin',out/'BIOS.M3U',out/'bootstrap.bin']},
      updater=json.loads((appbuild/'BIOSUPD.json').read_text()),
      base=json.loads((out/'base/manifest.json').read_text()),
      source_pins={str(p.relative_to(ROOT)):sha(p)for p in [*boot.iterdir(),Path(__file__),ROOT/'tools/firmware/picocalc/bios_boot.py',ROOT/'examples/portable-apps/BIOSUPD/main.c',ROOT/'sdk/coproc/pico_uart1.c']if p.is_file()})
    # Archive the fully staged source, including the current coprocessor
    # extension. Rebuilding it does not rely on an old .build work directory.
    entries={}
    for path in [*sorted((source/'Core').rglob('*')),source/'Makefile',source/'STM32F103XX_FLASH.ld',source/'startup_stm32f103xb.s',source/'LICENSE']:
        if path.is_file():entries['source/'+str(path.relative_to(source))]=path.read_bytes()
    for path in sorted(boot.iterdir()):
        if path.is_file():entries['boot/'+path.name]=path.read_bytes()
    entries['rebuild.py']=(ROOT/'tools/firmware/picocalc/rebuild_m3_boot.py').read_bytes()
    expected={'upstream':result['base']['upstream'],'sources':{name:hashlib.sha256(data).hexdigest()for name,data in entries.items()},
              'images':{name:info['sha256']for name,info in result['files'].items()}}
    entries['expected.json']=(json.dumps(expected,indent=2)+'\n').encode()
    with zipfile.ZipFile(out/'source.zip','w',compression=zipfile.ZIP_DEFLATED) as package_file:
        for name,data in sorted(entries.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,11,8,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            package_file.writestr(info,data)
    result['files']['source.zip']={'bytes':(out/'source.zip').stat().st_size,'sha256':sha(out/'source.zip')}
    result['files']['BIOSUPD.APP']={'bytes':(sd/'BIOSUPD.APP').stat().st_size,'sha256':sha(sd/'BIOSUPD.APP')}
    result['source_archive_entries']={name:hashlib.sha256(data).hexdigest()for name,data in entries.items()}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
