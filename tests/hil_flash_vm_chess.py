#!/usr/bin/env python3
"""Pinned Classic chess qualification: compile-cold, warm and reboot-cold runs.

Temporarily installs the candidate firmware and five language APPs. Preserves
all original files and the empty calculator state, restoring them on exit.
--keep-installed defers restoration during diagnostics; --session-base resumes
that owned session using its original saved snapshot. --no-firmware-write
requires identical pinned firmware images and never enters DFU.
--linked-image additionally compares the ordinary M61 launcher with an explicit
linked-program command, keeping the resident and LANGVM identical in all stages.
--baseline-resident instead compares generic/compact/generic linked residents,
keeping every APP, container byte and launcher identical in all three stages.
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
import zlib
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

def linked_chunks(image):
    assert 32<=len(image)<=64*4096
    assert image[:4]==b'LVP1' and len(image)==struct.unpack_from('<I',image,8)[0]
    assert zlib.crc32(image[:28])==struct.unpack_from('<I',image,28)[0]
    assert zlib.crc32(image[32:])==struct.unpack_from('<I',image,24)[0]
    return {f'LVP{i:02d}.bin':image[at:at+4096] for i,at in enumerate(range(0,len(image),4096))}

def linked_stage_script(name,baseline,all_linked=False):
    return b'reinit\nloadfont Turochamp\nvm-linked\n' if all_linked or name=='candidate' else baseline

def steady_comparison(stages):
    assert [s['name'] for s in stages]==['baseline','candidate','control']
    assert all(len(s['runs'])>=2 for s in stages)
    steady=[statistics.median(r['seconds'] for r in stage['runs'][1:]) for stage in stages]
    reference=(steady[0]+steady[2])/2
    return dict(steady_seconds=steady,reference_seconds=reference,
        candidate_seconds=steady[1],speedup=reference/steady[1],
        elapsed_reduction_percent=100*(1-steady[1]/reference),
        control_drift_percent=100*(steady[2]/steady[0]-1))

def qualification_apps(linked=False):
    ordinary=('BASIC.APP','FOCAL.APP','LANGVM.APP','LANGIN.APP','SRCEDIT.APP')
    return ordinary+('VMCache/VMSTORE.APP',) if linked else ordinary

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
    stage=dict(name=name,build=build,runs=[],profiling=profiling)
    if getattr(ARGS,'linked_image',None):
        all_linked=bool(getattr(ARGS,'baseline_resident',None))
        linked=all_linked or name=='candidate'
        script=linked_stage_script(name,package(ROOT/'programs/games/Turochamp')['autoexec.m61'],all_linked)
        with connect(PORT,build) as port:
            # Do not make the ordinary compiler compete with an unused
            # 45-KiB package in C9's bounded journal. Each variant owns only
            # its own executable artifact; BASIC sources remain identical.
            present={line.split('\t')[-1].casefold():line.split('\t')[-1]
                for line in storage.listing_entries(port.command(f'ls "{REMOTE}"')) if line.startswith('f\t')}
            for filename,payload in linked_chunks(ARGS.linked_image.read_bytes()).items():
                existing=present.get(filename.casefold());remote=REMOTE+'/'+(existing or filename)
                if linked:
                    if not existing or read_file(port,remote)!=payload:
                        write_file(port,remote,payload);assert read_file(port,remote)==payload
                elif existing:
                    assert 'Removed 1 entry.' in port.command(f'rm "{remote}"',30)
            remote=REMOTE+'/autoexec.m61'
            if read_file(port,remote)!=script:
                write_file(port,remote,script);assert read_file(port,remote)==script
        stage['linked_program']=linked
    report['stages'].append(stage)
    with TimedScreenPort(PORT) as port:
        identity=parse_identity(port.command('identity'))
        assert (identity.public,identity.build,identity.profile)==(PUBLIC,build,'classic-v3-uc1609')
        options=SimpleNamespace(game_dir=REMOTE,build_id=build,timeout=ARGS.timeout,reset_before=not profiling,no_profile=not profiling)
        options.headless_window=getattr(ARGS,'headless_window',45)
        try:
            port.attach();port.pump(.2)
            stage['cache_before']=cache_statistics(port,destination/'cache-before.txt')
            save(OUT/'report.json',report)
            for i in range(count):
                run_out=destination/f'run-{i}';run_out.mkdir()
                if getattr(ARGS,'keywait_benchmark',False):
                    from hil_chess_screen_mode import search as timed_search
                else:timed_search=search
                stage['runs'].append(timed_search(port,font,options,i,run_out))
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
    ap.add_argument('--baseline-vm',type=Path,help='Same-resident LANGVM A/B/A; each stage starts with empty owned file cache; requires --no-firmware-write unless --linked-image is selected')
    ap.add_argument('--baseline-resident',type=Path,help='Linked resident A/B/A with byte-identical APPs and linked image in all three stages; requires --linked-image and --baseline-vm')
    ap.add_argument('--linked-image',type=Path,help='Experimental same-kernel M61/OPEN -> linked -> M61/OPEN A/B/A; requires --baseline-vm, owns LVPxx.bin chunks')
    ap.add_argument('--linked-smoke',action='store_true',help='Linked candidate only, before the full A/B/A; no speedup claim')
    ap.add_argument('--fast-transfer',action='store_true',help='Use the existing SourcePort 3-ms polling for setup/recovery only; TimedScreenPort timing is unchanged')
    ap.add_argument('--keywait-benchmark',action='store_true',help='Diagnostic accepted-key to next-wait USB-on/off/on; six runs per stage, unchanged game')
    ap.add_argument('--headless-window',type=float,default=45,help='Untimed detached wait before reattaching to validate the board; MCU result is captured earlier')
    ap.add_argument('--save-derived-images',action='store_true',help='Capture bytes during the existing between-stage hash scans for offline VM analysis')
    ap.add_argument('--runs',type=int,default=4)
    ap.add_argument('--ready-runs',type=int,default=2)
    ap.add_argument('--timeout',type=float,default=600)
    ap.add_argument('--menu-timeout',type=float,default=240)
    ARGS=ap.parse_args();OUT=ARGS.output_dir.resolve()
    if ARGS.fast_transfer:
        from hil_language_sources import SourcePort
        memory.ExclusiveScreenPort.command=SourcePort.command
    assert 2<=ARGS.runs<=8 and 1<=ARGS.ready_runs<=8
    assert not ARGS.source_commit or re.fullmatch(r'[0-9a-fA-F]{40}',ARGS.source_commit)
    assert not ARGS.baseline_vm or ((ARGS.no_firmware_write or ARGS.linked_image) and not ARGS.profile_repeat and not ARGS.profile_first_compile)
    assert not ARGS.linked_image or ARGS.baseline_vm
    assert not ARGS.linked_smoke or ARGS.linked_image
    assert not ARGS.baseline_resident or (ARGS.linked_image and ARGS.baseline_vm and
        not any((ARGS.no_firmware_write,ARGS.linked_smoke,ARGS.session_base,ARGS.keep_installed,
                 ARGS.keywait_benchmark,ARGS.profile_repeat,ARGS.profile_first_compile)))
    assert not ARGS.keywait_benchmark or (ARGS.runs==6 and ARGS.baseline_vm and not ARGS.profile_repeat and not ARGS.profile_first_compile)
    assert 30<=ARGS.headless_window<=120
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
    baseline_resident=None
    if ARGS.baseline_resident:
        baseline_resident=capture_image(ARGS.baseline_resident,OUT/'images/baseline.bin')
        assert not same_firmware(baseline_resident,target),'resident A/B/A requires distinct variants'
        assert struct.unpack_from('<I',(OUT/'images/baseline.bin').read_bytes(),baseline_resident['footer']+28)==struct.unpack_from('<I',(OUT/'images/current.bin').read_bytes(),target['footer']+28)
    if ARGS.no_firmware_write:
        require_no_firmware_write(original,target,original['build'])
    payloads={}
    for app in qualification_apps(bool(ARGS.linked_image)):
        app_memory_size(ARGS.candidate_system/app)
        payloads[app]=(ARGS.candidate_system/app).read_bytes()
    baseline_vm=None
    if ARGS.baseline_vm:
        app_memory_size(ARGS.baseline_vm)
        baseline_vm=ARGS.baseline_vm.read_bytes()
        assert baseline_vm[14]==10 and payloads['LANGVM.APP'][14]==10,'Expected LANGVM APPs'
    game=package(ROOT/'programs/games/Turochamp')
    if ARGS.keywait_benchmark:
        from hil_chess_screen_mode import PROBE_FILES
        assert not set(game).intersection(PROBE_FILES)
        game.update(PROBE_FILES)
    linked_image=None
    if ARGS.linked_image:
        linked_image=ARGS.linked_image.read_bytes()
        linked_chunks(linked_image) # Validate before any device write.
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
        fast_transfer=ARGS.fast_transfer,
        keywait_benchmark=ARGS.keywait_benchmark,
        timing='USB complete eight-rank board wall clock, level 2, depth 8, book off, 420 nodes',
        filesystem=('Candidate and owned chess/derived-page fixtures retained; original snapshot saved'
                    if ARGS.keep_installed else
                    'Compiler may create derived LBV2 pages; restore original bytes and directories on exit'),
        apps={apps[a]:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for a,b in payloads.items()},
        package={n:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in game.items()})
    if baseline_vm is not None:
        report['vm_variants']={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            for name,data in vm_stage_plan(baseline_vm,payloads['LANGVM.APP'])}
    if linked_image is not None:
        assert baseline_vm==payloads['LANGVM.APP'],'linked experiment must use byte-identical LANGVM kernels'
        report['linked_poc']=dict(package_bytes=len(linked_image),package_sha256=hashlib.sha256(linked_image).hexdigest(),
            same_resident=True,same_LANGVM=True,artifact_storage='LVP chunks only in linked stage; ordinary derived pages only in ordinary stages',
            stages=['linked smoke'] if ARGS.linked_smoke else ['M61/OPEN','linked','M61/OPEN'])
    if baseline_resident is not None:
        report['baseline_resident']=baseline_resident
        report['linked_poc'].update(same_resident=False,same_VMSTORE=True,
            artifact_storage='Identical LVP chunks and no ordinary game compiler path in all stages',
            stages=['linked generic','linked compact','linked generic'])
    save(OUT/'report.json',report)
    args=SimpleNamespace(port=PORT,dfu_util=Path('/Users/bolk/Library/Arduino15/packages/arduino/tools/dfu-util/0.11.0-arduino5/dfu-util'))
    touched=False;passed=False
    try:
        initial=baseline_resident or target
        touched=True;report['firmware_writes']+=1
        if running_build!=initial['build']:
            assert not ARGS.no_firmware_write
            memory.flash(args,initial,OUT/'current-flash.json')
        else:report['firmware_writes']-=1
        with connect(PORT,initial['build']) as port:
            for app,remote in apps.items():
                data=baseline_vm if app=='LANGVM.APP' and baseline_vm is not None else payloads[app]
                if read_file(port,remote)!=data:
                    write_file(port,remote,data);assert read_file(port,remote)==data
            if not ARGS.session_base:memory.require_empty(memory.health(port,initial['build']))
            elif CACHE in current['directories']:
                port.command(f'rm -r "{CACHE}"',60)
            port.command(f'mkdir "{REMOTE}"',20)
            for name,data in game.items():
                path=REMOTE+'/'+name
                if not ARGS.session_base or path not in current['files'] or read_file(port,path)!=data:
                    write_file(port,path,data);assert read_file(port,path)==data
            reset(port,initial['build'])
        print('Candidate installed;',len(game),'game/package files verified;',
              'cold container validation + warm searches' if baseline_resident is not None else 'first compile + warm searches',flush=True)
        font=Font(game['Turochamp.FMK'])
        if baseline_resident is not None:
            active=initial['build']
            for name,variant in vm_stage_plan(baseline_resident,target):
                if active!=variant['build']:
                    report['firmware_writes']+=1
                    memory.flash(args,variant,OUT/(name+'-flash.json'))
                    active=variant['build']
                with connect(PORT,active) as port:
                    remove_owned_pages(port,files,storage.fingerprint(port))
                    reset(port,active)
                print('Linked resident A/B/A:',name,active,flush=True)
                run_stage(name,ARGS.runs,active,font,report)
            report['resident_aba']=steady_comparison(report['stages'])
        elif ARGS.linked_smoke:
            run_stage('candidate',ARGS.runs,target['build'],font,report)
            report['linked_smoke']=True
        elif baseline_vm is not None:
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
            if not ARGS.keywait_benchmark:
                report['vm_aba']=steady_comparison(report['stages'])
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
        if baseline_resident is not None:
            report['first_search_seconds']=report.pop('first_compile_seconds')
        if ARGS.keywait_benchmark:
            from hil_chess_screen_mode import summary
            report['screen_comparison']=summary(report['stages'])
            report.pop('warm_median_seconds') # Never mix USB-on and USB-off samples.
            report['timing']='MCU micros: accepted OK -> next blocking key wait, before any validation reattachment; unchanged 420-node game and golden board'
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
