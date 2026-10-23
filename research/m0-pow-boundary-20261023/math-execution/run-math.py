"""Math-only execution stage. Default is offline verification; never flashes/resets.

The transaction owner supplies a fresh post-install full-Flash readback and
owns snapshot/rollback. Import run(port, ...) to reuse its already open port.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics
import struct
import sys
import time

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]

# Authenticate every project helper byte before executing any project import.
# The parent pins this runner and execution manifest before invoking it.
_bootstrap=json.loads((PACKAGE/'execution-manifest.json').read_text())
_helper=PACKAGE/'frozen_helpers.py'
_binding=next(a for a in _bootstrap['artifacts'] if Path(a['path'])==_helper)
assert hashlib.sha256(_helper.read_bytes()).hexdigest()==_binding['sha256'],'Frozen helper closure changed'
_spec=importlib.util.spec_from_file_location('_mk61_v138_frozen_helpers',_helper)
_helpers=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_helpers)
MathPort,decode,read_file,write_file=(_helpers.MathPort,_helpers.decode,_helpers.read_file,_helpers.write_file)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)


def verify_package():
    manifest=json.loads((PACKAGE/'execution-manifest.json').read_text())
    for artifact in manifest['artifacts']:
        path=Path(artifact['path'])
        assert path.is_file() and sha(path)==artifact['sha256'],path
    cfg=json.loads((PACKAGE/'benchmark.json').read_text())
    assert cfg['elf_sha256']==manifest['target']['elf_sha256']
    assert cfg['firmware_manifest']['build_id'].upper()==manifest['target']['build']=='83CF4AC4'
    assert len(cfg['chunks'])==119 and cfg['streams']==117 and cfg['cases']==23352
    assert len(cfg['verification_canaries'])==1 and cfg['verification_canaries'][0]['cases']==30
    assert manifest['ownedtemporarySDdirectories']==[cfg['directory']]
    mutation_directory(cfg['directory'])
    return manifest,cfg


def mutation_directory(path):
    assert isinstance(path,str) and re.fullmatch(r'/MK61S-M0-V138-[0-9]{8}',path),path
    assert path==json.loads((PACKAGE/'benchmark.json').read_text())['directory'],path
    assert len(Path(path).parts)==2 and path not in ('/','.','..'),path
    return path


def parse_listing(report):
    """Parse only the versioned terminal row grammar and complete row count."""
    entries=[];counts=[]
    for line in report.splitlines():
        if re.match(r'^[df]\t',line):
            fields=line.split('\t');kind=fields[0]
            if kind=='d':
                assert len(fields)==2 and fields[1].endswith('/'),line
                name=fields[1][:-1]
            else:
                assert len(fields)==3 and re.fullmatch(r'[0-9]+ B',fields[1]),line
                name=fields[2]
            assert name and name not in ('.','..') and not any(c in name for c in '/\\\x00\r\n\t"'),line
            entries.append(dict(kind=kind,name=name))
        elif re.fullmatch(r'[0-9]+ entries\.',line):counts.append(int(line.split()[0]))
    assert counts==[len(entries)],'Incomplete or unparseable ls response'
    assert len({e['name'].casefold() for e in entries})==len(entries),'FAT casefold collision in listing'
    return entries


def require_absent_directory(report,directory):
    mutation_directory(directory)
    name=directory[1:].casefold()
    assert all(e['name'].casefold()!=name for e in parse_listing(report)),'Private FAT path already exists, including another spelling or file kind'


def child(directory,leaf):
    mutation_directory(directory)
    assert leaf in ('TIMING.APP','INPUT.bin','RESULT.bin','GUARD.bin'),leaf
    return directory+'/'+leaf


def installed_readback(path,cfg):
    data=Path(path).read_bytes()
    assert len(data)==2*1024*1024,'Require a full fresh post-install Flash readback'
    base=Path(cfg['firmware_elf']).with_suffix('.bin').read_bytes()
    assert data[:len(base)]==base,'Readback differs from exact V138 BIN'
    addon=(PACKAGE/'reference/reference-sectors.bin').read_bytes()
    offset=cfg['reference_address']-0x10000000
    assert data[offset:offset+len(addon)]==addon,'Reference addon readback differs'
    return dict(path=str(Path(path).resolve()),sha256=sha(path),base_bytes=len(base),
                reference_bytes=len(addon),verified=True)


def require_idle(text,build):
    for token in ('BUILD='+build,'RP2040 125 MHz','MATH_TEST=OK','FIRMWARE_CRC=valid',
                  'CRASH=NONE','RUN=0 BUSY=0','USB_DISK=0','RUNTIME=NONE','SERVICE=CLOSED','DIRTY=0'):
        assert token in text,(token,text)
    assert 'SLEEP=1' not in text,'Parent must establish awake125MHz before the math stage'


def guard(raw,cfg):
    assert struct.unpack('<8I',raw)==(0x56313338,1,cfg['runtime_table_address'],26,
        cfg['reference_fnv'],125000000,125000000,cfg['footer_crc']),'APP guard receipt mismatch'


def summarize(rows,cfg):
    groups=[]
    for index in sorted({r['stream_index'] for r in rows}):
        parts=[r for r in rows if r['stream_index']==index];cases=sum(r['cases'] for r in parts)
        estimate={side:sum(r['order_balanced']['us_per_call'][side]*r['cases'] for r in parts)/cases
                  for side in ('own','qfplib')}
        groups.append(dict(stream_index=index,operation=parts[0]['operation'],stream=parts[0]['stream'],
            cases=cases,us_per_call=estimate,cycle_equivalents_per_call={k:v*125 for k,v in estimate.items()},
            own_over_qfplib=estimate['own']/estimate['qfplib'] if estimate['qfplib']>0 else None,
            slower_observed=estimate['own']>estimate['qfplib'],
            empirical_ranges_us=[r['order_balanced']['empirical_delta_range_us'] for r in parts]))
    return groups


def run(port, *, uid, output, verified_flash, stop_file=None, resume=False, settle_ms=1000,phase='all'):
    """Use an already open command-mode port; return finite math result dict.

    No identity/mode retry, keys, reset, recovery or flash writes. A device
    failure preserves evidence and leaves all recovery to the transaction.
    """
    manifest,cfg=verify_package()
    assert phase in ('matrix','canary','all')
    selected=(cfg['chunks'] if phase!='canary' else [])+(cfg['verification_canaries'] if phase!='matrix' else [])
    primary_indexes={c['index'] for c in cfg['chunks']}
    assert uid=='E6657CD423721C35' and 0<=settle_ms<=10000
    readback=installed_readback(verified_flash,cfg)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    checkpoint=output/'checkpoint.json';packet=sha(PACKAGE/'execution-manifest.json')
    rows=[];created=False;before=None;initial=None;error=None;removed=False;cancelled=False;current=None
    if checkpoint.exists():
        assert resume,'Output already contains a checkpoint; use explicit resume'
        old=json.loads(checkpoint.read_text())
        assert old['package_sha256']==packet and old['uid']==uid
        assert old['phase']==phase
        for chunk in selected:
            if chunk['index'] not in old['completed']:continue
            stem=output/f"{chunk['index']:03d}"
            guard(stem.with_suffix('.guard.bin').read_bytes(),cfg)
            rows.append(decode(stem.with_suffix('.bin').read_bytes(),chunk,Path(chunk['input']).read_bytes()))
    elif resume:
        raise AssertionError('No host checkpoint to resume')
    completed={r['index'] for r in rows}
    if len(completed)==len(selected):
        raise AssertionError('Already complete; retain the original physical receipt')
    directory=cfg['directory']
    started=time.monotonic()
    def progress(event):
        state=dict(phase=phase,event=event,package_sha256=packet,uid=uid,completed=sorted(completed),
            total=len(selected),current=current,elapsed_seconds=time.monotonic()-started,
            timestamp=datetime.now(timezone.utc).isoformat())
        atomic_json(output/'progress.json',state);atomic_json(checkpoint,state)
        print(json.dumps(state),flush=True)
        if hasattr(port,'text'):(output/'transcript.bin').write_bytes(port.text)
    try:
        identity=port.command('identity');assert 'UID='+uid in identity,identity
        initial=port.status();require_idle(initial,'83CF4AC4')
        assert 'TERMINAL=COMMAND' in initial,'Parent must enter command mode first'
        initial_ip=re.search(r'\bIP=([0-9]+)',initial)
        assert initial_ip,'Missing calculator IP in initial status'
        before={c:_helpers.canonical_state_reply(port.command(c)) for c in ('reg','stk','hout','dump','pwd')}
        (output/'initial-status.txt').write_text(initial)
        atomic_json(output/'before.json',before)
        require_absent_directory(port.command('ls /'),directory)
        answer=port.command('mkdir '+directory);assert 'ERROR' not in answer,answer;created=True
        write_file(port,child(directory,'TIMING.APP'),Path(cfg['app']).read_bytes())
        progress('ready')
        for chunk in selected:
            current=chunk['index']
            if current in completed:continue
            if stop_file and Path(stop_file).exists():cancelled=True;break
            progress('uploading')
            data=Path(chunk['input']).read_bytes();assert hashlib.sha256(data).hexdigest()==chunk['input_sha256']
            require_idle(port.status(),'83CF4AC4')
            write_file(port,child(directory,'INPUT.bin'),data)
            port.pump(settle_ms/1000)
            progress('app-running')
            answer=port.command('open "'+child(directory,'TIMING.APP')+'"',timeout=30)
            (output/f'{current:03d}.app-response.txt').write_text(answer)
            assert 'APP_FLOW_RESULT=0' in answer and 'APP returned an error' not in answer,answer
            raw=read_file(port,child(directory,'RESULT.bin'))
            audit=read_file(port,child(directory,'GUARD.bin'))
            (output/f'{current:03d}.bin').write_bytes(raw)
            (output/f'{current:03d}.guard.bin').write_bytes(audit)
            guard(audit,cfg)
            row=decode(raw,chunk,data)
            assert row['rounds']==12 and row['app_warmup_us']>=1000000
            row['cycle_equivalents_per_call']={side:[v*125 for v in values['paired_us']] for side,values in row['timings'].items()}
            atomic_json(output/f'{current:03d}.json',row)
            require_idle(port.status(),'83CF4AC4')
            rows.append(row);completed.add(current);progress('chunk-complete')
        progress('cancelling' if cancelled else 'cleaning')
        answer=port.command('rm -r '+mutation_directory(directory),timeout=30);assert 'ERROR' not in answer,answer;removed=True
        after={c:_helpers.canonical_state_reply(port.command(c)) for c in before}
        atomic_json(output/'after.json',after)
        assert before==after,'Calculator registers/program/output/cwd changed'
        final=port.status();require_idle(final,'83CF4AC4')
        final_ip=re.search(r'\bIP=([0-9]+)',final)
        assert final_ip and final_ip[1]==initial_ip[1],'Calculator IP changed'
        (output/'final-status.txt').write_text(final)
    except BaseException as failure:
        error=repr(failure)
        # Capture raw state before any cleanup/retry/reset. A missing CDC is
        # passed to the parent unchanged; this runner performs no recovery.
        capture={}
        for command in ('status','crash show','identity'):
            try:capture[command]=port.status() if command=='status' else port.command(command,timeout=2)
            except BaseException as secondary:capture[command]={'error':repr(secondary)}
        atomic_json(output/'failure-observation.json',capture)
    finally:
        if hasattr(port,'text'):(output/'transcript.bin').write_bytes(port.text)
        result=dict(status='FAIL' if error else 'PARTIAL_STOPPED' if cancelled else 'PASS',
            uid=uid,package_sha256=packet,build='83CF4AC4',fresh_readback=readback,
            phase=phase,failure=error,current_chunk=current,completed_chunks=len(completed),expected_chunks=len(selected),
            completed_matrix_chunks=len(completed&primary_indexes),expected_matrix_chunks=0 if phase=='canary' else 119,
            completed_verification_chunks=len(completed-primary_indexes),expected_verification_chunks=0 if phase=='matrix' else 1,
            completed_cases=sum(r['cases'] for r in rows if r['index'] in primary_indexes),expected_cases=0 if phase=='canary' else 23352,
            supplementary_cases=sum(r['cases'] for r in rows if r['index'] not in primary_indexes),
            groups=summarize([r for r in rows if r['index'] in primary_indexes],cfg),raw_rounds=12,opposite_order_pairs=6,
            sd_directory=directory,sd_directory_created=created,temporary_directory_removed=removed,
            calculator_data_preserved=not error,stop_requested=cancelled,
            elapsed_seconds=time.monotonic()-started,physical_cycle_counter=False,
            cycle_scope=cfg['cycle_reporting'],goal_complete=False)
        atomic_json(output/'result.json',result);progress(result['status'])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--port');p.add_argument('--uid')
    p.add_argument('--output',type=Path);p.add_argument('--verified-flash',type=Path)
    p.add_argument('--stop-file',type=Path);p.add_argument('--resume',action='store_true')
    p.add_argument('--phase',choices=('matrix','canary','all'),default='all')
    a=p.parse_args()
    if not a.execute:
        manifest,cfg=verify_package();print(json.dumps(dict(status='PASS_OFFLINE_PACKAGE',chunks=119,cases=23352,
            target=manifest['target'],device_accessed=False)));return
    if not all((a.port,a.uid,a.output,a.verified_flash)):
        p.error('--execute requires --port --uid --output --verified-flash')
    # Only this explicit branch opens a port; never called by preparation.
    with MathPort(a.port,keyboard_layout=0) as port:
        result=run(port,uid=a.uid,output=a.output,verified_flash=a.verified_flash,
                   stop_file=a.stop_file,resume=a.resume,phase=a.phase)
    raise SystemExit(0 if result['status']=='PASS' else 2 if result['status']=='PARTIAL_STOPPED' else 1)


if __name__=='__main__':main()
