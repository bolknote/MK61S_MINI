#!/usr/bin/env python3
"""Package a verified Pico H UF2 and the current native APP collection."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import zipfile
import zlib

from build_picocalc_apps import APPS, ASSETS, ROOT
from seal_picocalc import verify as verify_firmware

README='''MK61S / PicoCalc / Pico H

Copy mk61s-picocalc-pico-h.uf2 to the RPI-RP2 ROM bootloader volume.
Use the native Micro-USB connector on Pico H. The case USB-C is UART.
Copy apps/ and games/ to microSD; copy Fonts/ to the card root.
APP images in this bundle target Cortex-M0+ and cannot replace STM32 APPs.
See README.md for controls, supported formats, clock and power limitations.
'''


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_app(path, record):
    data=path.read_bytes()
    if record['target']!='picocalc-pico-h' or record['abi']!=6:
        raise ValueError(f'{path.name}: not a Pico H ABI 6 build')
    if len(data)<64 or data[:8]!=b'MK61APP\0' or struct.unpack_from('<HHHBB',data,8)!=(1,64,6,4,1):
        raise ValueError(f'{path.name}: invalid user APP header')
    flags,base,stored,image,memory,entry=struct.unpack_from('<6I',data,16)
    if flags&13!=13 or flags&~31 or base!=0x20000000:
        raise ValueError(f'{path.name}: incompatible CPU/relocation flags')
    if 'native_display' in record and bool(flags&16)!=record['native_display']:
        raise ValueError(f'{path.name}: display flag/build manifest mismatch')
    if not 0<image<=memory<=49152 or entry>=image or len(data)!=64+stored:
        raise ValueError(f'{path.name}: invalid APP bounds')
    if zlib.crc32(data[:60])!=struct.unpack_from('<I',data,60)[0] or zlib.crc32(data[64:])!=struct.unpack_from('<I',data,48)[0]:
        raise ValueError(f'{path.name}: APP checksum mismatch')
    if len(data)!=record['app_bytes'] or sha256(path)!=record['app_sha256']:
        raise ValueError(f'{path.name}: build manifest mismatch')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=ROOT/'binary/picocalc-pico-h')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();directory=args.directory.resolve()
    build=json.loads((directory/'manifest.json').read_text())
    version=build['prototype_version']
    if build['profile']!='picocalc-pico-h' or not re.fullmatch(r'\d+\.\d+\.\d+',version):
        raise ValueError('not a Pico H firmware manifest')
    firmware=directory/'mk61s-picocalc-pico-h.uf2'
    if sha256(firmware)!=build['uf2_sha256']:
        raise ValueError('UF2/build manifest mismatch')
    sys_path=str(ROOT/'ports/picocalc')
    spec=importlib.util.spec_from_file_location('pico_uf2',Path(sys_path)/'uf2.py')
    uf2=importlib.util.module_from_spec(spec);spec.loader.exec_module(uf2)
    transport=firmware.read_bytes()
    image=b''.join(transport[i+32:i+288] for i in range(0,len(transport),512))[:build['flash_bytes']]
    uf2.validate(transport,image)
    integrity=verify_firmware(image,build['firmware_integrity']['footer_offset'])
    if integrity!=build['firmware_integrity'] or hashlib.sha256(image).hexdigest()!=build['bin_sha256']:
        raise ValueError('sealed firmware/build manifest mismatch')
    apps=directory/'apps';records=json.loads((apps/'manifest.json').read_text())
    if [record['name'] for record in records]!=list(APPS):
        raise ValueError('APP manifest must contain the complete current collection')
    for record in records:verify_app(apps/(record['name']+'.APP'),record)
    (directory/'README.txt').write_text(README)
    shutil.copy2(ROOT/'ports/picocalc/README.md',directory/'README.md')
    (directory/'Fonts').mkdir(exist_ok=True)
    font_files=[]
    for source in sorted((ROOT/'programs/Fonts').glob('*.FMK')):
        target=directory/'Fonts'/source.name;shutil.copy2(source,target);font_files.append(target)
    game_files=[]
    for game in sorted((ROOT/'programs/games').iterdir()):
        if not game.is_dir() or not any((game/name).exists() for name in ('autoexec.m61','autoexec.tbi')):continue
        for source in sorted(game.iterdir()):
            if not source.is_file():continue
            target=directory/'games'/game.name/source.name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target);game_files.append(target)
    for name in ('README.markdown','SOURCES.markdown'):
        target=directory/'games'/name;shutil.copy2(ROOT/'programs/games'/name,target);game_files.append(target)
    target=directory/'games/native-artwork.json'
    shutil.copy2(ROOT/'doc/game-artwork/native/manifest.json',target);game_files.append(target)
    for name in ('Graphics.tbi','Graphics.foc','Graph.tbi'):
        target=directory/'examples'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/'programs/examples'/name,target);game_files.append(target)
    spec=importlib.util.spec_from_file_location('pico_font_licenses',ROOT/'tools/.fmk-font/package_ui_font_licenses.py')
    licenses=importlib.util.module_from_spec(spec);spec.loader.exec_module(licenses)
    licenses.package(bundle=directory)
    shutil.copy2(ROOT/'tools/sync_picocalc_clock.py',directory/'sync_picocalc_clock.py')
    files=[firmware,directory/'manifest.json',directory/'README.txt',directory/'README.md',directory/'sync_picocalc_clock.py',
        *font_files,*game_files,*(directory/name for name in licenses.FILES),
        apps/'manifest.json',*[apps/(name+'.APP') for name in APPS],*[apps/name for name in ASSETS]]
    for report_name in ('hardware-parity-summary.json','hardware-apps-summary.json',
                        'hardware-software-summary.json','hardware-power-summary.json',
                        'hardware-contract-summary.json','hardware-integrity-summary.json','hardware-mkc-summary.json',
                        'hardware-usb-disk-summary.json','hardware-full-parity-summary.json',
                        'hardware-performance-summary.json','hardware-font-summary.json',
                        'hardware-display-summary.json','hardware-high-noon-summary.json',
                        'hardware-eliza-summary.json','hardware-sheet-summary.json','hardware-native-complete-summary.json'):
        report=directory/report_name
        if not report.exists():continue
        evidence=json.loads(report.read_text())
        verified=evidence.get('uf2_sha256') or evidence.get('hardware',{}).get('verified_uf2_sha256')
        if verified!=build['uf2_sha256']:raise ValueError(f'{report_name}: report belongs to another UF2')
        if evidence.get('passed') is False:raise ValueError(f'{report_name}: hardware verification failed')
        if report_name=='hardware-apps-summary.json':
            if not evidence.get('passed'):raise ValueError('APP hardware verification failed')
            expected={r['name']+'.APP':r['app_sha256'] for r in records}
            if any(evidence['files'].get(name)!=digest for name,digest in expected.items()):
                raise ValueError('APP hardware verification belongs to another collection')
        if report_name in ('hardware-eliza-summary.json','hardware-sheet-summary.json'):
            name='ELIZA' if report_name=='hardware-eliza-summary.json' else 'SHEET'
            expected=next(r['app_sha256'] for r in records if r['name']==name)
            if not evidence.get('passed') or evidence.get('app_sha256')!=expected:
                raise ValueError(name+' hardware verification belongs to another APP')
        if report_name=='hardware-native-complete-summary.json':
            expected=next(r['app_sha256'] for r in records if r['name']=='WBMP')
            if not evidence.get('passed') or evidence.get('app_sha256')!=expected:
                raise ValueError('native display hardware verification belongs to another WBMP APP')
            if evidence.get('native_artwork_manifest_sha256')!=sha256(ROOT/'doc/game-artwork/native/manifest.json'):
                raise ValueError('native display hardware verification belongs to another artwork manifest')
            for name,digest in evidence.get('uploaded_files_sha256',{}).items():
                if name.startswith('Bumblebee/') and sha256(ROOT/'programs/games'/name)!=digest:
                    raise ValueError('Bumblebee hardware verification belongs to another game file')
        files.append(report)
    checksum_file=directory/f'bundle-sha256-{version}.json'
    hashes={str(path.relative_to(directory)):sha256(path) for path in files}
    checksum_file.write_text(json.dumps(hashes,indent=2)+'\n');files.append(checksum_file)
    output=args.output or directory/f'mk61s-picocalc-pico-h-{version}.zip'
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in files:archive.write(path,'mk61s-picocalc-pico-h/'+str(path.relative_to(directory)))
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:raise ValueError('archive CRC mismatch')
            for name,digest in hashes.items():
                if hashlib.sha256(archive.read('mk61s-picocalc-pico-h/'+name)).hexdigest()!=digest:
                    raise ValueError(f'archive hash mismatch: {name}')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'{output}: {len(records)} native APPs, {output.stat().st_size} bytes')


if __name__=='__main__':main()
