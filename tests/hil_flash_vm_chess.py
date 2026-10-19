#!/usr/bin/env python3
"""Pinned Classic chess qualification: compile-cold, warm and reboot-cold runs.

Temporarily installs the candidate firmware and five language APPs. Preserves
all original files and the empty calculator state, restoring them on exit.
--keep-installed defers restoration during diagnostics; --session-base resumes
that owned session using its original saved snapshot. --no-firmware-write
requires identical pinned firmware images and never enters DFU.
"""
import argparse
import time
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import statistics
import shutil
import struct
import sys
from types import SimpleNamespace

import hil_system_memory as memory
import hil_packbits_firmware as storage
from hil_vm_compiled_blocks import PORT,PUBLIC,connect,snapshot_files,read_file,alarms_off,capture_image
from hil_c6_system_bootstrap import write_file
from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import canonical_state_reply,warm_reset
from hil_turochamp_merge import package
from hil_turochamp_performance import Font,TimedScreenPort,search,stop_game
from hil_language_flash import manifests
from check_app_memory_elf import app_memory_size

ROOT=Path(__file__).resolve().parents[1]
REMOTE='/FLASHCHESS'
CACHE='/System/VMCache/Pages'
OUT=None
ARGS=None

def save(path,data):path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

def same_firmware(left,right):
    return all(left[key]==right[key] for key in ('sha256','bytes','build'))

def require_no_firmware_write(original,target,running_build):
    assert same_firmware(original,target),'no-firmware-write requires identical images'
    assert running_build==original['build'],'no-firmware-write requires the pinned running build'

def vm_stage_plan(baseline,candidate):
    return [('baseline',baseline),('candidate',candidate),('control',baseline)]

def remove_owned_pages(port,original,current):
    if CACHE not in current['directories']:return
    assert CACHE not in original['directories']
    assert not any(p.startswith(CACHE+'/') for p in original['files'])
    assert not any(p.startswith(CACHE+'/') for p in original['directories'])
    print(port.command(f'rm -r "{CACHE}"',60),flush=True)

def reset(port,build):
    fresh,path,_=warm_reset(port,PORT,PUBLIC)
    try:
        assert path==PORT
        assert parse_identity(fresh.command('identity')).build==build
    finally:fresh.close()

def cache_statistics(port,destination):
    raw=port.command('prof',timeout=15)
    destination.write_text(raw)
    assert 'PROF state=stopped' in raw,'timing requires a stopped profiler'
    line=re.search(r'^VMFLASH (.*)$',raw,re.M)
    assert line,raw
    values={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',line[1])}
    assert values['budget']==32768 and 0<values['payload']<values['budget'],values
    assert values['used']<=values['payload'],values
    assert values['lookups']==values['hits']+values['misses'],values
    return values

def require_cache_activity(values):
    # A ready contiguous loan intentionally skips page get()/copy entirely.
    # Keep its hits separate instead of silently changing page hit-rate units.
    assert values['hits']>0 or values.get('loan_hits',0)>0,values

def run_stage(name,count,build,font,report,profiling=False):
    destination=OUT/name;destination.mkdir()
    stage=dict(name=name,runs=[],profiling=profiling)
    report['stages'].append(stage)
    with TimedScreenPort(PORT) as port:
        identity=parse_identity(port.command('identity'))
        assert (identity.public,identity.build,identity.profile)==(PUBLIC,build,'classic-v3-uc1609')
        options=SimpleNamespace(game_dir=REMOTE,build_id=build,timeout=ARGS.timeout,reset_before=not profiling,no_profile=not profiling)
        try:
            port.attach();port.pump(.2)
            stage['cache_before']=cache_statistics(port,destination/'cache-before.txt')
            save(OUT/'report.json',report)
            for i in range(count):
                run_out=destination/f'run-{i}';run_out.mkdir()
                stage['runs'].append(search(port,font,options,i,run_out))
                counters=cache_statistics(port,run_out/'cache-after.txt')
                require_cache_activity(counters)
                stage['runs'][-1]['flash_cache']=counters
                save(OUT/'report.json',report)
        except BaseException as error:
            stage['error']=repr(error)
            save(OUT/'report.json',report)
            if port.frames:
                from hil_portable_system_apps import png
                png(port.frames[-1],destination/'failure-screen.png')
                (destination/'failure.frame').write_bytes(port.frames[-1])
            raise
        finally:
            try:
                if port.attached:
                    stop_game(port)
                    stage['cache_after']=cache_statistics(port,destination/'cache-after.txt')
                    save(OUT/'report.json',report)
                    port.send(0x13);port.attached=False;port.pump(.2)
            finally:(destination/'terminal.txt').write_bytes(port.text)
        stage['health']=memory.health(port,build)
        assert 'layout=ok' in stage['health']['mpu status']
        stage['manifests']=manifests(port)
        stage['frames_crc_checked']=len(port.frames)
    assert len({r['board_frame_sha256'] for r in stage['runs']})==1
    save(OUT/'report.json',report)

def main():
    global OUT,ARGS
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate-bin',type=Path,required=True)
    ap.add_argument('--candidate-system',type=Path,required=True)
    ap.add_argument('--restore-bin',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--session-base',type=Path,help='Continue an earlier --keep-installed run using its original snapshot')
    ap.add_argument('--keep-installed',action='store_true',help='Leave the candidate and owned fixtures for another diagnostic run')
    ap.add_argument('--no-firmware-write',action='store_true',help='Refuse DFU; candidate and recovery BIN must be identical to the pinned running build')
    ap.add_argument('--profile-repeat',action='store_true',help='One separate warm search with the existing profiler, excluded from ordinary timing statistics')
    ap.add_argument('--profile-first-compile',action='store_true',help='One separate search after clearing only the owned derived cache, excluded from ordinary timing statistics')
    ap.add_argument('--source-commit',help='Explicit source SHA for this qualification, not a claim of binary equivalence')
    ap.add_argument('--baseline-vm',type=Path,help='Same-resident LANGVM A/B/A; each stage starts with empty owned file cache; requires --no-firmware-write')
    ap.add_argument('--save-derived-images',action='store_true',help='Capture bytes during the existing between-stage hash scans for offline VM analysis')
    ap.add_argument('--runs',type=int,default=4)
    ap.add_argument('--ready-runs',type=int,default=2)
    ap.add_argument('--timeout',type=float,default=600)
    ap.add_argument('--menu-timeout',type=float,default=240)
    ARGS=ap.parse_args();OUT=ARGS.output_dir.resolve()
    assert 2<=ARGS.runs<=8 and 1<=ARGS.ready_runs<=8
    assert not ARGS.source_commit or re.fullmatch(r'[0-9a-fA-F]{40}',ARGS.source_commit)
    assert not ARGS.baseline_vm or (ARGS.no_firmware_write and not ARGS.profile_repeat and not ARGS.profile_first_compile)
    assert not OUT.exists(),'Preserve earlier reports'
    import hil_turochamp_performance as benchmark
    original_wait=benchmark.wait_screen
    waits=[]
    def wait_screen(port,font,*labels,timeout=ARGS.menu_timeout):
        started=time.monotonic()
        result=original_wait(port,font,*labels,timeout=timeout)
        waits.append(dict(labels=labels,seconds=time.monotonic()-started,result=result))
        save(OUT/'menu-waits.json',waits)
        print('Menu:',result,f'{time.monotonic()-started:.3f}s',flush=True)
        return result
    benchmark.wait_screen=wait_screen
    (OUT/'images').mkdir(parents=True)
    original=capture_image(ARGS.restore_bin,OUT/'images/original.bin')
    target=capture_image(ARGS.candidate_bin,OUT/'images/current.bin')
    assert struct.unpack_from('<I',(OUT/'images/original.bin').read_bytes(),original['footer']+28)==struct.unpack_from('<I',(OUT/'images/current.bin').read_bytes(),target['footer']+28)
    if ARGS.no_firmware_write:
        require_no_firmware_write(original,target,original['build'])
    payloads={}
    for app in ('BASIC.APP','FOCAL.APP','LANGVM.APP','LANGIN.APP','SRCEDIT.APP'):
        app_memory_size(ARGS.candidate_system/app)
        payloads[app]=(ARGS.candidate_system/app).read_bytes()
    baseline_vm=None
    if ARGS.baseline_vm:
        app_memory_size(ARGS.baseline_vm)
        baseline_vm=ARGS.baseline_vm.read_bytes()
        assert baseline_vm[14]==10 and payloads['LANGVM.APP'][14]==10,'Expected LANGVM APPs'
    game=package(ROOT/'programs/games/Turochamp')
    if ARGS.session_base:
        previous=json.loads((ARGS.session_base/'report.json').read_text())
        saved=json.loads((ARGS.session_base/'snapshot.json').read_text())
        assert previous.get('candidate_kept') and not previous['restored'],previous['status']
        assert previous['original']['sha256']==original['sha256']
        before=saved['health'];files=saved['files'];identity=saved['identity']
        from hil_multi_device_identity import Identity
        identity=Identity(**identity)
        running_build=previous['current']['build']
        shutil.copytree(ARGS.session_base/'original-files',OUT/'original-files')
        with connect(PORT,running_build,wait=0) as port:
            memory.health(port,running_build)
            current=storage.fingerprint(port)
            assert all(p in files['files'] or p.startswith(REMOTE+'/') or p.startswith(CACHE+'/') for p in current['files'])
            assert all(p in files['directories'] or p in (REMOTE,CACHE) or p.startswith(REMOTE+'/') or p.startswith(CACHE+'/') for p in current['directories'])
            for path,detail in files['files'].items():
                if not path.casefold() in {('/System/'+a).casefold() for a in payloads}:
                    assert current['files'].get(path)==detail,path
    else:
        with connect(PORT,original['build'],wait=0) as port:
            before=memory.health(port,original['build']);memory.require_empty(before);alarms_off(port)
            files=snapshot_files(port,OUT/'original-files')
            for root in (REMOTE,CACHE):
                assert root not in files['directories'] and not any(p.startswith(root+'/') for p in files['files'])
            identity=parse_identity(port.command('identity'))
        running_build=original['build']
    if ARGS.no_firmware_write:require_no_firmware_write(original,target,running_build)
    apps={app:next(p for p in files['files'] if p.casefold()==('/System/'+app).casefold()) for app in payloads}
    save(OUT/'snapshot.json',dict(identity=asdict(identity),health=before,files=files,firmware=original))
    report=dict(status='RUNNING',source_base=ARGS.source_commit or '36ff01c60d3edf4b8fd350fb0c84a827907755de',
        original=original,current=target,device=asdict(identity),stages=[],restored=False,
        firmware_writes=0,profiling=False,profile_repeat=ARGS.profile_repeat,profile_first_compile=ARGS.profile_first_compile,
        no_firmware_write=ARGS.no_firmware_write,limits_weakened=False,
        timing='USB complete eight-rank board wall clock, level 2, depth 8, book off, 420 nodes',
        filesystem=('Candidate and owned chess/derived-page fixtures retained; original snapshot saved'
                    if ARGS.keep_installed else
                    'Compiler may create derived LBV2 pages; restore original bytes and directories on exit'),
        apps={apps[a]:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for a,b in payloads.items()},
        package={n:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in game.items()})
    if baseline_vm is not None:
        report['vm_variants']={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            for name,data in vm_stage_plan(baseline_vm,payloads['LANGVM.APP'])}
    save(OUT/'report.json',report)
    args=SimpleNamespace(port=PORT,dfu_util=Path('/Users/bolk/Library/Arduino15/packages/arduino/tools/dfu-util/0.11.0-arduino5/dfu-util'))
    touched=False;passed=False
    try:
        touched=True;report['firmware_writes']+=1
        if running_build!=target['build']:
            assert not ARGS.no_firmware_write
            memory.flash(args,target,OUT/'current-flash.json')
        else:report['firmware_writes']-=1
        with connect(PORT,target['build']) as port:
            for app,remote in apps.items():
                data=baseline_vm if app=='LANGVM.APP' and baseline_vm is not None else payloads[app]
                if read_file(port,remote)!=data:
                    write_file(port,remote,data);assert read_file(port,remote)==data
            if not ARGS.session_base:memory.require_empty(memory.health(port,target['build']))
            elif CACHE in current['directories']:
                port.command(f'rm -r "{CACHE}"',60)
            port.command(f'mkdir "{REMOTE}"',20)
            for name,data in game.items():
                path=REMOTE+'/'+name
                if not ARGS.session_base or read_file(port,path)!=data:
                    write_file(port,path,data);assert read_file(port,path)==data
            reset(port,target['build'])
        print('Candidate installed; 29-file game verified; first compile + warm searches',flush=True)
        font=Font(game['Turochamp.FMK'])
        if baseline_vm is not None:
            for name,data in vm_stage_plan(baseline_vm,payloads['LANGVM.APP']):
                with connect(PORT,target['build']) as port:
                    current=(snapshot_files(port,OUT/(name+'-cache-before-files'))
                        if ARGS.save_derived_images else storage.fingerprint(port))
                    remove_owned_pages(port,files,current)
                    remote=apps['LANGVM.APP']
                    if read_file(port,remote)!=data:
                        write_file(port,remote,data);assert read_file(port,remote)==data
                    reset(port,target['build'])
                print('LANGVM A/B/A:',name,flush=True)
                run_stage(name,ARGS.runs,target['build'],font,report)
            steady=[statistics.median(r['seconds'] for r in stage['runs'][1:]) for stage in report['stages']]
            reference=(steady[0]+steady[2])/2
            report['vm_aba']=dict(steady_seconds=steady,reference_seconds=reference,
                candidate_seconds=steady[1],speedup=reference/steady[1],
                elapsed_reduction_percent=100*(1-steady[1]/reference),
                control_drift_percent=100*(steady[2]/steady[0]-1))
        else:
            run_stage('first-compile',ARGS.runs,target['build'],font,report)
            with connect(PORT,target['build']) as port:reset(port,target['build'])
            print('Reboot with ready Flash pages; measuring RAM-cold search',flush=True)
            run_stage('ready-file-cache',ARGS.ready_runs,target['build'],font,report)
        rows=[r for stage in report['stages'] for r in stage['runs']]
        assert len({r['board_frame_sha256'] for r in rows})==1
        assert rows[0]['board_frame_sha256']=='ef261082a0230600d21d7c4ae116e7cfc226f0fb9ce43a22fbbc26bcbe580460'
        report.update(first_compile_seconds=rows[0]['seconds'],
            warm_median_seconds=statistics.median(r['seconds'] for r in report['stages'][0]['runs'][1:]))
        if baseline_vm is None:report['ready_cache_reboot_seconds']=report['stages'][1]['runs'][0]['seconds']
        if ARGS.profile_repeat:
            run_stage('profile-repeat',1,target['build'],font,report,profiling=True)
            assert report['stages'][-1]['runs'][0]['board_frame_sha256']==rows[0]['board_frame_sha256']
        if ARGS.profile_first_compile:
            with connect(PORT,target['build']) as port:
                remove_owned_pages(port,files,storage.fingerprint(port))
                reset(port,target['build'])
            run_stage('profile-first-compile',1,target['build'],font,report,profiling=True)
            assert report['stages'][-1]['runs'][0]['board_frame_sha256']==rows[0]['board_frame_sha256']
        passed=True
    except BaseException as error:
        report.update(status='FAIL',error=repr(error));raise
    finally:
        try:
            if touched and ARGS.keep_installed:
                with connect(PORT,target['build']) as port:
                    report.update(candidate_kept=True,health_kept=memory.health(port,target['build']))
                print('Candidate and owned fixtures kept for the next run; CDC closed',flush=True)
            elif touched:
                print('Restoring original firmware, System, caches and calculator',flush=True)
                if report['firmware_writes'] or not same_firmware(original,target):
                    assert not ARGS.no_firmware_write
                    report['firmware_writes']+=1
                    memory.flash(args,original,OUT/'restore-flash.json')
                else:
                    report['restoration_firmware_write_skipped']=True
                with connect(PORT,original['build']) as port:
                    port.command('fsput cancel');port.command('reinit')
                    current=storage.fingerprint(port)
                    added=set(current['files'])-set(files['files'])
                    assert all(p.startswith(REMOTE+'/') or p.startswith(CACHE+'/') for p in added),added
                    for path,detail in files['files'].items():
                        if current['files'].get(path)!=detail:
                            assert path in apps.values() or path.startswith('/System/VMCache/'),path
                    for root in (REMOTE,CACHE):
                        if root in current['directories']:
                            assert not any(p.startswith(root+'/') for p in files['files'])
                            print(port.command(f'rm -r "{root}"',60),flush=True)
                    for directory in sorted(set(files['directories'])-set(current['directories']),key=len):
                        assert directory.startswith('/System/VMCache/'),directory
                        port.command(f'mkdir "{directory}"',20)
                    for path,detail in files['files'].items():
                        if current['files'].get(path)==detail:continue
                        payload=(OUT/'original-files'/path.lstrip('/')).read_bytes()
                        assert hashlib.sha256(payload).hexdigest()==detail['sha256']
                        write_file(port,path,payload);assert read_file(port,path)==payload
                    assert storage.fingerprint(port)==files
                    reset(port,original['build'])
                with connect(PORT,original['build']) as port:
                    final=memory.health(port,original['build']);memory.require_empty(final);alarms_off(port)
                    for key in ('reg','stk','dump','pwd'):
                        assert canonical_state_reply(final[key])==canonical_state_reply(before[key]),key
                    report.update(restored=True,files_preserved=True,calculator_preserved=True,
                        original_files=len(files['files']),original_directories=len(files['directories']),
                        health_after=final,mini_touched=False,pico_touched=False)
                print('Exact restoration PASS; Classic released at '+original['build'],flush=True)
            if passed and (report['restored'] or report.get('candidate_kept')):report['status']='PASS'
        except BaseException as error:
            report.update(status='FAIL',cleanup_error=repr(error));raise
        finally:save(OUT/'report.json',report)

if __name__=='__main__':main()
