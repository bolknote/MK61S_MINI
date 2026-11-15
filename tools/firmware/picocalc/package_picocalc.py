#!/usr/bin/env python3
"""Package a verified Pico H UF2 and the current native APP collection."""

# Resolve shared host helpers independently of the current command directory.
import sys as _tool_sys
from pathlib import Path as _ToolPath
_tool_root = _ToolPath(__file__).resolve().parents[3]
_tool_sys.path[:0] = [str(_tool_root), str(_tool_root / "dev/lib"), str(_tool_root / "dev/tools")]
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from tools.apps.system.build_picocalc_apps import APPS, ROOT
from tools.apps.mp3.build_mp3_app import SD_FILES as MP3_SD_FILES
from tools.apps.packer.mk61_module_pack import PICO_APP_MAX_MEMORY_SIZE
from seal_picocalc import verify as verify_firmware
from program_collection import PICO_APP_FOLDERS, export, plan, validate_app
from explorer_icons import install_bundle_icons
from tools.apps.urq.library import copy_licenses

README='''MK61S / PicoCalc / Pico H

Copy mk61s-picocalc-pico-h.uf2 to the RPI-RP2 ROM bootloader volume.
Use the native Micro-USB connector on Pico H. The case USB-C is UART.
Copy the folders inside Disk/ to the microSD card root.
Open Explorer > Games and press Enter on a title to play.
APP images in this bundle target Cortex-M0+ and cannot replace STM32 APPs.
See README.md for controls, supported formats, clock and power limitations.
'''


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_app(path, record, memory_limit=PICO_APP_MAX_MEMORY_SIZE):
    cap=dict(platform='picocalc', profile='picocalc-pico-h', abi=6, app_memory_limit=memory_limit)
    validate_app(path,cap,build=record)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=ROOT/'.build/firmware/picocalc-pico-h')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();directory=args.directory.resolve()
    with tempfile.TemporaryDirectory(prefix='mk61-pico-disk-') as stage:
        package(directory, args.output, Path(stage)/'Disk')


def package(directory, output, disk):
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
    memory_limit=build.get('app_memory_limit', 48 * 1024)
    if not 0 < memory_limit <= PICO_APP_MAX_MEMORY_SIZE:
        raise ValueError('invalid Pico H APP memory limit')
    for record in records:verify_app(apps/(record['name']+'.APP'),record,memory_limit)
    selection=plan(directory, prefer_bundle=False)
    if selection['capabilities']['app_memory_limit'] != memory_limit:
        raise ValueError('Pico H APP memory limit does not match build manifest')
    if missing := set(PICO_APP_FOLDERS.values()) - set(selection['packages']):
        raise ValueError('incomplete Pico H APP collection: ' + ', '.join(sorted(missing)))
    assets={name:{Path(record['path']).relative_to(folder).as_posix() for record in selection['files']
                  if record['package']==folder} for name,folder in PICO_APP_FOLDERS.items()}
    if assets['MP3']!=set(MP3_SD_FILES):
        raise ValueError('incomplete MP3 asset manifest')
    if not {'48.rom','128-0.rom','128-1.rom','AY.S3M'}<=assets['SPECTRUM']:
        raise ValueError('incomplete Spectrum asset manifest')
    (directory/'README.txt').write_text(README)
    shutil.copy2(ROOT/'ports/picocalc/README.md',directory/'README.md')
    manifest=disk.parent/'programs-manifest.json'
    export(selection, disk, manifest=manifest)
    spec=importlib.util.spec_from_file_location('pico_font_licenses',ROOT/'tools/fonts/package_ui_font_licenses.py')
    licenses=importlib.util.module_from_spec(spec);spec.loader.exec_module(licenses)
    licenses.package(bundle=directory)
    ryu=directory/'licenses/ryu';ryu.mkdir(parents=True,exist_ok=True)
    for name in ('LICENSE-Apache2','LICENSE-Boost','README.md'):
        shutil.copy2(ROOT/'third_party/ryu'/name,ryu/name)
    menu_license=directory/'licenses/LUCIDE.txt'
    shutil.copy2(ROOT/'ports/picocalc/MENU_ICONS_LICENSE.txt',menu_license)
    shutil.copy2(ROOT/'tools/device/sync_picocalc_clock.py',directory/'sync_picocalc_clock.py')
    files=[firmware,directory/'manifest.json',directory/'README.txt',directory/'README.md',
           directory/'sync_picocalc_clock.py',directory/'program-capabilities.json',
           *(directory/name for name in licenses.FILES),menu_license,apps/'manifest.json',
           *(apps/name/'manifest.json' for name in PICO_APP_FOLDERS)]
    files += copy_licenses(directory/'licenses/urq')
    files += sorted(path for path in (directory/'licenses/ryu').rglob('*') if path.is_file())
    license_folders={parent.relative_to(directory).as_posix() for path in files
                     for parent in path.parents if parent.is_relative_to(directory/'licenses')}
    files += install_bundle_icons(directory,license_folders)
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
    payload={path.relative_to(directory).as_posix():path for path in files}
    payload[manifest.name]=manifest
    payload.update({path.relative_to(disk.parent).as_posix():path
                    for path in disk.rglob('*') if path.is_file()})
    hashes={name:sha256(path) for name,path in payload.items()}
    checksum_file.write_text(json.dumps(hashes,indent=2)+'\n')
    payload[checksum_file.name]=checksum_file
    output=output or directory/f'mk61s-picocalc-pico-h-{version}.zip'
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,path in sorted(payload.items(),key=lambda item:item[0].casefold()):
                archive.write(path,'mk61s-picocalc-pico-h/'+name)
            for path in disk.iterdir():
                if path.is_dir() and not any(path.iterdir()):
                    archive.write(path,'mk61s-picocalc-pico-h/'+path.relative_to(disk.parent).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:raise ValueError('archive CRC mismatch')
            for name,digest in hashes.items():
                if hashlib.sha256(archive.read('mk61s-picocalc-pico-h/'+name)).hexdigest()!=digest:
                    raise ValueError(f'archive hash mismatch: {name}')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'{output}: {len(records)+len(PICO_APP_FOLDERS)} native APPs, {output.stat().st_size} bytes')


if __name__=='__main__':main()
