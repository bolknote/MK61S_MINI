#!/usr/bin/env python3
"""Freeze the qualified offline suite for independent review; never use hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BUILD=ROOT/'.build/rp2040-interpolator-20261023'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=BUILD/'packet-v1')
 p.add_argument('--apps',type=Path,default=BUILD/'app/app-manifest.json')
 p.add_argument('--protocol-prefix',default='protocol-')
 p.add_argument('--firmware-proof',type=Path,default=BUILD/'firmware-proof');a=p.parse_args()
 out=a.output.resolve()
 if out.exists():raise SystemExit('Use a new packet directory; frozen packets are never overwritten')
 manifest=json.loads(a.apps.read_text())
 proof=json.loads((a.firmware_proof/'report.json').read_text())
 certificate=json.loads((HERE/'seed-certificate.json').read_text())
 assert proof['status']=='PASS_OFFLINE' and certificate['status']=='PASS'
 evidence={};calls=0
 for variant,app in manifest['apps'].items():
  assert sha(Path(app['app']))==app['app_sha256']
  validation=Path(app['app']).parent/'arm-validation.json'
  v=json.loads(validation.read_text());protocol=BUILD/(a.protocol_prefix+variant)/'report.json';r=json.loads(protocol.read_text())
  assert v['status']==r['status']=='PASS' and not v['hardware_verified'] and not r['hardware_verified']
  assert v['elf_sha256']==sha(Path(app['elf']))
  assert r['benchmark_sha256']==sha(HERE/'benchmark.c')
  assert r.get('full4096_checksum_perturbation_checked'), 'Require the nonlinear full-batch checksum regression'
  assert len(r['cases'])==4 and all(c['peripheral_state_restored'] for c in r['cases'])
  calls+=v['actual_arm_calls']
  evidence[variant]=dict(app_sha256=app['app_sha256'],elf_sha256=v['elf_sha256'],memory_bytes=app['memory_bytes'],
    actual_arm_calls=v['actual_arm_calls'],kernel_validation_sha256=sha(validation),protocol_report_sha256=sha(protocol),
    instruction_profiles={k:[x['instructions'] for x in rows] for k,rows in v['profiles'].items()})
 out.mkdir(parents=True)
 def copy(source,dest):
  target=out/dest;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
 for source in sorted(HERE.iterdir()):
  if source.is_file() and source.name not in ('HANDOFF.json','offline-result.json'):
   copy(source,'source/'+source.name)
 for variant,app in manifest['apps'].items():
  parent=Path(app['app']).parent
  for suffix in ('.APP','.elf','.json','.map'):
   copy(parent/(app['name']+suffix),'apps/'+variant+'/'+app['name']+suffix)
  copy(parent/'arm-validation.json','apps/'+variant+'/arm-validation.json')
  for name in ('report.json','fixture.elf','synthetic-result.bin'):
   copy(BUILD/(a.protocol_prefix+variant)/name,'protocol/'+variant+'/'+name)
 for name in ('report.json','frozen.bin','current.bin'):
  copy(a.firmware_proof/name,'firmware-proof/'+name)
 deps=[ROOT/'tools/build_portable_app.py',ROOT/'tools/build_picocalc.py',ROOT/'tools/.mk61-app/app_relocations.py',
  ROOT/'tests/native_eabi_m0_arm_self_test.py',ROOT/'tests/check_stm32_vectors.py',ROOT/'tests/m0_math_compare_app_self_test.py',
  ROOT/'code/native_eabi_m0.cpp',ROOT/'code/native_eabi_m0.S',ROOT/'code/native_eabi_m0_rp2040.S',ROOT/'code/native_eabi_m0_pow_fast.inc',
  ROOT/'code/native_eabi_m0_log70_center.inc',ROOT/'code/native_eabi_m0_log70_table.inc',ROOT/'code/native_eabi_m0_rsqrt_table.inc',
  ROOT/'code/native_eabi_m0_sqrt64_table.inc',ROOT/'sdk/portable/start.c',ROOT/'sdk/portable/memory.c']
 pins={str(f.relative_to(ROOT)):sha(f) for f in deps}
 summary=dict(status='OFFLINE_PASS_HARDWARE_PENDING',hardware_verified=False,physical_timing=False,
  actual_arm_calls=calls,protocol_cases=16,decoder_negative_cases=20,seed_certificate='PASS_ALL_131072_CELLS',
  variants=evidence,firmware_source_sha256=proof['source_sha256'],firmware_proof_sha256=sha(out/'firmware-proof/report.json'),
  conclusion='Wide32/Q62 and seed pipelines use more ARM instructions than the current CPU controls. Prepared table-address formation saves 1-3 instructions. No physical speed or production result is claimed.')
 (out/'offline-result.json').write_text(json.dumps(summary,indent=2)+'\n')
 plan=dict(schema=1,status='AWAITING_INDEPENDENT_REVIEW_AND_HARDWARE_LEASE',hardware_authorized_by_this_file=False,
  coordinator_thread='01a164b7-9caa-7011-90d1-807e9630921c',target=dict(uid='E6657CD423721C35',build='A7483AE6',profile='picocalc-pico-h',core=0),
  filesystem=dict(directory='/INTRP01',must_not_preexist=True,created_objects=manifest['created_objects'],
   app_order=['alu','rsqrt','sqrt','address'],result='RESULT.bin',marker_bytes_hex='00',
   cleanup='Only exact objects created by this packet; canonical case and bytes/hash recorded. Never remove unknown objects or use recursive cleanup.'),
  firmware_actions=[],timing=dict(rows=60,rounds=7,calls_per_batch=4096,order='ABBA/BAAB rotation',
   units='Raw TIMERAWL microseconds only;125MHz derived from register readback and12MHz Pico H crystal',interrupts='enabled'),
  preflight=['Explicit exclusive operator handoff after Cold/recovery queues; exact UID/build/accepted source',
   'Use the coordinator-supplied reviewed framed CDC/file/state/RTC/ALL-SD primitives; no legacy-runner substitution',
   'Fresh calculator/program/IP/CWD/RTC/filesystem preservation packet and original file bytes as required by that operator',
   'Read-only host checks and sufficient live heap for the largest20396B image plus alignment/loader live allocations',
   'No other foreground APP; core0 Thread privileged with PRIMASK0; both INTERP banks exclusively owned for each short measured batch; SIO divider initially idle'],
  preservation=['Snapshot/restore ACCUM/BASE/CTRL for both core0 interpolators, never POP; state compared after batches and at completion',
   'Initially idle divider operands/quotient/remainder restored and checked',
   'No reset, bootloader, Flash, firmware or production-source mutation',
   'Retrieve and retain raw RESULT.bin after every APP, validate exact variant, save raw failures before cleanup',
   'Final exact SD tree/file-byte audit plus calculator/IP/CWD/RTC restoration/readback and serial close'],
  transport_binding=None,lease_binding=None,external_dependency_sha256=pins)
 (out/'execution-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 files={str(p.relative_to(out)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(out.rglob('*')) if p.is_file()}
 package=dict(schema=1,status=summary['status'],hardware_verified=False,files=files)
 package_path=out/'packet-manifest.json';package_path.write_text(json.dumps(package,indent=2)+'\n')
 handoff=dict(status=summary['status'],hardware_verified=False,packet=str(out),manifest=str(package_path),manifest_sha256=sha(package_path),
  actual_arm_calls=calls,apps={k:{x:v[x] for x in ('app_sha256','memory_bytes')} for k,v in evidence.items()},
  next='Independent review, reviewed transport/restore binding, then coordinator hardware lease. This packet grants neither hardware access nor production adoption.')
 (HERE/'HANDOFF.json').write_text(json.dumps(handoff,indent=2)+'\n')
 (HERE/'offline-result.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(handoff,indent=2))
if __name__=='__main__':main()
