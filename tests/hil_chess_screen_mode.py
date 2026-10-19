"""Diagnostic Classic timing with unchanged chess and no timed screen traffic.

Requires MK61_KEY_WAIT_BENCHMARK: accepted OK -> next blocking APP key wait.
The headless path arms a diagnostic detach immediately after accepting OK,
BEFORE the timer or game resumes. It stays detached for a fixed observation
window, then reattaches solely to validate the complete golden board. The MCU
sample is frozen at the next wait; read it after STOP so linked VM's blocked
terminal cannot affect either endpoint.
"""
import hashlib
import json
import re
import statistics
import time
from hil_turochamp_performance import prepare_search,completed_board,board_pixels,require_launcher_ok,stop_game
from hil_portable_system_apps import png

MODES=('continuous','continuous','continuous','headless','headless','continuous')
PROBE_FILES={'__bench.tbi':b'10 .R0=@(146);END\n','__bench.m61':b'open __bench.tbi\n'}

def sample(text):
    assert 'PROF state=stopped' in text,'timing requires a stopped profiler'
    m=re.search(r'^KEYWAIT sequence=(\d+) us=(\d+) key=(-?\d+) screen_begin=([01]) screen_end=([01])\r?$',text,re.M)
    assert m,'missing KEYWAIT diagnostic'
    return dict(zip(('sequence','us','key','screen_begin','screen_end'),map(int,m.groups())))

def checked(before,after,mode,sequence_delta=1):
    assert (after['sequence']-before['sequence'])&0xFFFFFFFF==sequence_delta,(before,after)
    assert after['key']==37 and 0<after['us']<120000000,after
    assert after['screen_begin']==after['screen_end']==int(mode=='continuous'),after
    return after['us']/1000000

def r0(text):
    m=re.search(r'^R0\s*=\s*([+-]?\s*\d\.\d+)\s+([+-]?\d+)\s*\r?$',text,re.M)
    assert m,text
    return float(m[1].replace(' ',''))*10**int(m[2])

def node_probe(port,game_dir,out):
    # The owned probe runs only after the timed search and STOP; no chess
    # source or algorithm changes. Run 1 also warms any probe-induced miss.
    before=port.command('reg',timeout=15)
    assert r0(before)==0,'R0 must be freshly reset by the unchanged autoexec'
    port.open(game_dir+'/__bench.m61')
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        port.pump(.1);require_launcher_ok(port)
        after=port.command('reg',timeout=15)
        if r0(after)==420:
            (out/'node-probe-reg.txt').write_text(after);return 420
    raise AssertionError(('node probe did not read retained @(146)=420',after))

def search(port,font,args,index,out):
    mode=MODES[index]
    before=sample(port.command('prof',timeout=15))
    prepare_search(port,font,args,out)
    cursor=len(port.frames)
    if mode=='headless':
        port.send(0x14,b'KW');port.pump(.1)
        assert port.attached
        detached_frames=len(port.frames)
        started=time.monotonic();port.key(37)
        assert not port.attached,'diagnostic detach did not precede game execution'
        while time.monotonic()-started<args.headless_window:
            port.pump(.04);require_launcher_ok(port)
            assert not port.attached and len(port.frames)==detached_frames,'screen traffic during headless search'
        cursor=len(port.frames);port.attach_waiting()
    else:
        started=time.monotonic();port.key(37)
    progress=[];seen=set();finished=None
    deadline=time.monotonic()+args.timeout
    while time.monotonic()<deadline:
        port.pump(.04);require_launcher_ok(port)
        assert port.attached
        for frame,stamp in zip(port.frames[cursor:],port.frame_times[cursor:]):
            if font.has(frame,'ДУМАЕТ...'):
                nodes=font.number_after(frame,'ПОЗ ')
                if nodes is not None and nodes not in seen:
                    seen.add(nodes);progress.append(dict(nodes=nodes,seconds=stamp-started))
            elif completed_board(font,frame):
                finished=stamp;golden=frame;break
        cursor=len(port.frames)
        if finished is not None:break
    assert finished is not None,'missing complete eight-rank board'
    if mode=='continuous':
        assert progress and progress[-1]['nodes']==420,progress
        port.pump(.1)
    digest=hashlib.sha256(board_pixels(golden)).hexdigest()
    assert digest=='ef261082a0230600d21d7c4ae116e7cfc226f0fb9ce43a22fbbc26bcbe580460',digest
    png(golden,out/'move-e2-e3.png');(out/'move.frame').write_bytes(golden)
    stop_game(port)
    after=sample(port.command('prof',timeout=15))
    # Seven menu keys, then OK; after a prior run ESC's return is also closed
    # by the next menu wait. No unexpected extra wait may replace the sample.
    elapsed=checked(before,after,mode,8 if index==0 else 9)
    if mode=='continuous':
        assert abs((finished-started)-elapsed)<.5,'MCU interval disagrees with the complete-board wall clock'
    else:
        assert elapsed<args.headless_window,'observation window did not cover completion'
    (out/'keywait.json').write_text(json.dumps(dict(before=before,after=after),indent=2)+'\n')
    nodes=node_probe(port,args.game_dir,out)
    result=dict(repeat=index,temperature='warmup' if index<2 else 'repeat',
        seconds=elapsed,screen_mode=mode,keywait=after,host_complete_seconds=finished-started,
        nodes=nodes,move='e2e3',complete_eight_rank_board=True,board_frame_sha256=digest,
        final_frame_sha256=hashlib.sha256(golden).hexdigest(),progress=progress,profile=None)
    (out/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'{args.build_id} run {index} {mode}: {elapsed:.6f}s MCU / {nodes} nodes PASS',flush=True)
    return result

def summary(stages):
    rows=[]
    for stage in stages:
        groups={mode:[r['seconds'] for r in stage['runs'][2:] if r['screen_mode']==mode]
                for mode in ('continuous','headless')}
        assert all(len(v)==2 for v in groups.values()),groups
        on,off=(statistics.median(groups[m]) for m in ('continuous','headless'))
        rows.append(dict(name=stage['name'],samples=groups,continuous_seconds=on,
            headless_seconds=off,saved_seconds=on-off,elapsed_reduction_percent=100*(1-off/on)))
    return rows
