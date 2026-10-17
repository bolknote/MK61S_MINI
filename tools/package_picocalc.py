#!/usr/bin/env python3
"""Package a verified Pico H UF2 and the current native APP collection."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import zipfile
import zlib

from build_picocalc_apps import APPS, ASSETS, ROOT


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_app(path, record):
    data=path.read_bytes()
    if record['target']!='picocalc-pico-h' or record['abi']!=6:
        raise ValueError(f'{path.name}: not a Pico H ABI 6 build')
    if len(data)<64 or data[:8]!=b'MK61APP\0' or struct.unpack_from('<HHHBB',data,8)!=(1,64,6,4,1):
        raise ValueError(f'{path.name}: invalid user APP header')
    flags,base,stored,image,memory,entry=struct.unpack_from('<6I',data,16)
    if flags&13!=13 or flags&~15 or base!=0x20000000:
        raise ValueError(f'{path.name}: incompatible CPU/relocation flags')
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
    apps=directory/'apps';records=json.loads((apps/'manifest.json').read_text())
    if [record['name'] for record in records]!=list(APPS):
        raise ValueError('APP manifest must contain the complete current collection')
    for record in records:verify_app(apps/(record['name']+'.APP'),record)
    shutil.copy2(ROOT/'tools/sync_picocalc_clock.py',directory/'sync_picocalc_clock.py')
    files=[firmware,directory/'manifest.json',directory/'README.txt',directory/'sync_picocalc_clock.py',
        apps/'manifest.json',*[apps/(name+'.APP') for name in APPS],*[apps/name for name in ASSETS]]
    for report_name in ('hardware-parity-summary.json','hardware-apps-summary.json'):
        report=directory/report_name
        if not report.exists():continue
        evidence=json.loads(report.read_text())
        verified=evidence.get('uf2_sha256') or evidence.get('hardware',{}).get('verified_uf2_sha256')
        if verified!=build['uf2_sha256']:raise ValueError(f'{report_name}: report belongs to another UF2')
        if report_name=='hardware-apps-summary.json':
            if not evidence.get('passed'):raise ValueError('APP hardware verification failed')
            expected={r['name']+'.APP':r['app_sha256'] for r in records}
            if any(evidence['files'].get(name)!=digest for name,digest in expected.items()):
                raise ValueError('APP hardware verification belongs to another collection')
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
