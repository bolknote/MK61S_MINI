#!/usr/bin/env python3
"""Prepare one short, pinned RP2 vs RP2+M3 phase. HOST only; no flash/ports."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tests'))
import hil_mk61_ai_perf as perf
from build_m3_linear import DEFAULT_TOOL

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def item(p):
    p=Path(p).resolve()
    return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware-manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',type=Path,default=ROOT/'.build/mk61ai/bundle/sd/AI/MODEL.MKA')
    parser.add_argument('--module-dir',type=Path,default=ROOT/'.build/mk61ai/m3-linear/module')
    parser.add_argument('--int8',action='store_true')
    parser.add_argument('--arm-toolchain-bin',type=Path,default=DEFAULT_TOOL)
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    controller=out/'controller';controller.mkdir()
    for name in ('hil_mk61_ai_perf.py','hil_mk61_ai.py','hil_mk61_ai_finish.py'):
        shutil.copy2(ROOT/'tests'/name,controller/name)
    firmware=json.loads(args.firmware_manifest.read_text())
    model=item(args.model)
    model_sha='67aae98d9ffbd332bbea6e9a7dde9ec003f8213b99d92c555b523c794256d01b' if args.int8 else '45ebc482d2247d36d386c9563becb89d3ca08868db66aad001afa977703b0166'
    if model['bytes']!=2093896 or model['sha256']!=model_sha:
        raise ValueError('This short phase requires the frozen model for its arithmetic')
    module=args.module_dir/'M3LINE.S3M'
    module_manifest=json.loads((args.module_dir/'manifest.json').read_text())
    arm=json.loads((args.module_dir/'arm-verification.json').read_text())
    expected_status='M3_INT8_RELOCATED_ARM_PASS' if args.int8 else 'M3_LINEAR_ARM_PASS'
    if arm['status']!=expected_status or arm['package_sha256']!=sha(module) or module_manifest['sha256']!=sha(module):
        raise ValueError('Exact native module build/ARM evidence required')
    config=dict(kernel=2,arithmetic=1 if args.int8 else 3,cores=3,freeze=1,filter=0,mhz=125,
                prefill=1,decode=1,repeat=1,stress_ms=0,control=1,constrained=0,prefetch=1)
    cfg=out/'PERF.CFG';cfg.write_text('AIPERF2\n'+''.join(f'{k}={v}\n' for k,v in config.items()))
    assert perf.parse_config(cfg.read_bytes())==config
    nonce='HILV3-M3-'+secrets.token_hex(6).upper()
    directory='/AI/'+nonce
    wrapper=out/'benchmark.c'
    wrapper.write_text('#define MK61_AI_DIAGNOSTIC_DIRECTORY '+json.dumps(directory)+'\n#include '+
                       json.dumps(str(ROOT/'examples/portable-apps/MK61AI/bench.c'))+'\n')
    hash_wrapper=out/'hash.c'
    hash_wrapper.write_text('#define MK61_AI_HASH_PATH '+json.dumps(directory+'/MODEL.MKA' if args.int8 else '/AI/MODEL.MKA')+'\n#include '+json.dumps(str(ROOT/'tests/mk61_ai_file_hash_probe.c'))+'\n')
    for name,source in (('AIBENCH',wrapper),('AIHASH',hash_wrapper)):
        subprocess.run([sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),
            '--target','picocalc-pico-h','--shared-runtime','--name',name,'--source',str(source),
            '--arm-toolchain-bin',str(args.arm_toolchain_bin),'--output-dir',str(out/name)],
            check=True,stdout=subprocess.DEVNULL)
    sources=[p for folder in ('code','ports/picocalc','sdk/coproc','sdk/portable','third_party/fatfs','third_party/core_math')
             for p in (ROOT/folder).rglob('*') if p.is_file() and
             (p.suffix in ('.c','.cpp','.h','.hpp','.S','.inc','.ld','.pio','.py') or p.name=='CMakeLists.txt')]
    sources += [Path(__file__).resolve(),ROOT/'tools/apps/portable/build_portable_app.py',
                ROOT/'tools/firmware/picocalc/build_picocalc.py',ROOT/'dev/lib/seal_picocalc.py',
                ROOT/'tests/mk61_ai_file_hash_probe.c',ROOT/'examples/portable-apps/MK61AI/bench.c',wrapper,hash_wrapper,
                ROOT/'examples/portable-apps/MK61AI'/('m3_int8_module.c' if args.int8 else 'm3_linear_module.c'),
                ROOT/'examples/portable-apps/MK61AI/m3_linear_protocol.h',
                *controller.glob('*.py'),args.module_dir/'manifest.json',args.module_dir/'arm-verification.json']
    phase=dict(schema=3,uid=perf.ai.UID,port=perf.ai.PORT,save_or_restore=False,deadline_seconds=850,
        action='perf',nonce=nonce,new_build=firmware['build_id'].upper(),
        new_crc=firmware['firmware_integrity']['crc32'].upper(),
        script_sha256=sha(controller/'hil_mk61_ai_perf.py'),helper_sha256=sha(controller/'hil_mk61_ai.py'),
        finish_helper_sha256=sha(controller/'hil_mk61_ai_finish.py'),
        source_pins={str(p.resolve()):sha(p) for p in sources},
        payloads=dict(firmware_manifest=item(args.firmware_manifest),model=model,m3_module=item(module),
            config=item(cfg),benchmark=item(out/'AIBENCH/AIBENCH.APP'),hashprobe=item(out/'AIHASH/AIHASH.APP')),
        config=config,alternate_model=args.int8,expected_usb_reenumerations=0,cancel_at=None,
        startup_error_limits={'QPI_FALLBACKS':1,'I2C_ABORTS':64})
    lease=ROOT/'.build/m0-libc-batch-20261107-v1/ROOT-PICO-LEASE-001.json'
    phase.update(root_lease_path=str(lease),root_lease_inode=lease.lstat().st_ino)
    path=out/'PHASE.json';path.write_text(json.dumps(phase,indent=2)+'\n')
    review=dict(status='HOST_PREPARED_NOT_RUN',physical_io=False,phase=str(path),phase_sha256=sha(path),
        build=phase['new_build'],crc=phase['new_crc'],full_forwards=4,uart_in_forward_timing=True,
        native_module_sha256=sha(module),source_pin_count=len(phase['source_pins']),
        needs_actual_spectrum_release=True,needs_exact_root_grant=True,flash=False,save_or_restore=False)
    (out/'REVIEW.json').write_text(json.dumps(review,indent=2)+'\n')
    print(json.dumps(review,indent=2))

if __name__=='__main__': main()
