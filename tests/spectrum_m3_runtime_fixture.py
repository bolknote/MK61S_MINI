#!/usr/bin/env python3
"""Extract checked compact-loader fixtures from the versioned firmware archive."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES={
    'stm3_runtime.c':'source/Core/Src/stm3_runtime.c',
    'stm3_runtime.h':'source/Core/Inc/stm3_runtime.h',
    'stm3_module.h':'source/Core/Inc/stm3_module.h',
    'arm_harness.c':'recipe/repository/research/picocalc-stm32-runtime-20261107/tests/arm_harness.c',
    'harness.ld':'recipe/repository/research/picocalc-stm32-runtime-20261107/tests/harness.ld',
    'arm_execution.py':'recipe/repository/research/picocalc-stm32-runtime-20261107/tests/arm_execution.py',
}


def prepare(output):
    baseline=ROOT/'firmware/picocalc-southbridge'
    archive=baseline/'source.zip';manifest=json.loads((baseline/'manifest.json').read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['source_archive_sha256']:
        raise ValueError('Southbridge fixture archive differs from its manifest')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    pins={}
    with zipfile.ZipFile(archive) as z:
        for name,path in FILES.items():
            data=z.read(path);digest=hashlib.sha256(data).hexdigest()
            if digest!=manifest['source_archive_files'][path]:
                raise ValueError('Changed compact-loader fixture: '+path)
            (output/name).write_bytes(data);pins[path]=digest
    if (output/'stm3_module.h').read_bytes()!=(ROOT/'sdk/coproc/stm3_module.h').read_bytes():
        raise ValueError('SDK module ABI differs from the archived resident')
    return pins


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    prepare(ap.parse_args().output)
