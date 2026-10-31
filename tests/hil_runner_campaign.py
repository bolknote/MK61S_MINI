#!/usr/bin/env python3
"""Qualify the complete Runner through real Classic USB Screen events.

Only run after an explicit hardware handoff. No firmware/file/register patching;
the caller installs and verifies the matching image/files beforehand. Latency
uses arrival of a complete decoded framebuffer, without register-poll padding.
"""
import argparse
import binascii
import struct
import json
import os
from pathlib import Path
import statistics
import sys
import time
from datetime import datetime, timezone

from hil_multi_device_identity import parse_identity
from hil_runner_classic import GamePort, registers, DIGITS
from hil_portable_apps import cobs_decode
from hil_portable_system_apps import png
from runner_game_test import BOARDS, move
from runner_screen_oracle import board, expected
from runner_frame_campaign import play_level

ROUTES = ('66244668666666666484444444444',
          '669666644444444448668667644474484',
          '44844446964426666666666684')


class TimedPort(GamePort):
    def __init__(self, path):
        self.timeline = []
        self.detach_watch=False;self.detach_offer=None;self.server_detach=None
        super().__init__(path)

    def receive_packet(self, encoded):
        count = len(self.frames)
        super().receive_packet(encoded)
        try:
            raw=cobs_decode(encoded)
            valid=(len(raw)>=11 and raw[:3]==b'MS\x02' and len(raw)==11+struct.unpack_from('<H',raw,7)[0] and
                   binascii.crc_hqx(raw[:-2],65535)==struct.unpack_from('<H',raw,len(raw)-2)[0])
            if valid and raw[3]==0x12:self.server_detach=None
            if valid and raw[3]==0x13:self.server_detach=raw.hex()
            if valid and raw[3]==0x10 and self.detach_watch and raw[9:13]==bytes((192,0,64,8)):
                self.detach_offer=raw.hex();self.attached=False
        except AssertionError:pass
        if len(self.frames) > count:
            self.timeline.append((time.monotonic(), board(self.frames[-1])))

    def close(self):
        super().close()
        if hasattr(self,'closure_path'):
            self.closure_path.write_text(json.dumps(dict(pid=os.getpid(),pgid=os.getpgrp(),
                closed=True,fd=self.fd,lock_fd=self.lock_fd),indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--directory', default='/games/Runner')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prototype-benchmark', action='store_true')
    parser.add_argument('--benchmark-only', action='store_true')
    parser.add_argument('--campaign-only',action='store_true',help='complete campaign and levels2/3 benchmarks after a separately recorded level1 functional pass')
    parser.add_argument('--start-level',type=int,choices=(1,2,3),default=1)
    parser.add_argument('--long-cx', action='store_true')
    parser.add_argument('--max-step-seconds', type=float, default=.75)
    parser.add_argument('--min-held-cells', type=int, default=4)
    parser.add_argument('--max-hole-seconds', type=float, default=5.0)
    parser.add_argument('--confirm-game-reset', action='store_true', required=True)
    args = parser.parse_args()
    if args.start_level!=1 and (not args.benchmark_only or args.prototype_benchmark):
        parser.error('--start-level 2/3 requires --benchmark-only and the complete game')
    if args.campaign_only and (args.start_level!=1 or args.benchmark_only or args.prototype_benchmark):
        parser.error('--campaign-only requires the ordinary complete campaign')
    args.output.mkdir(parents=True, exist_ok=True)
    results, start = [], time.monotonic()
    (args.output/'actor-start.json').write_text(json.dumps(dict(pid=os.getpid(),pgid=os.getpgrp(),
        utc=datetime.now(timezone.utc).isoformat(),port=args.port,build=args.build_id),indent=2)+'\n')
    passed, cleanup = False, {}
    with TimedPort(args.port) as p:
        p.closure_path=args.output/'actor-closed.json'
        identity = parse_identity(p.command('identity'))
        assert identity.public == args.public_id.upper() and identity.build == args.build_id.upper(), identity
        assert identity.profile.startswith('classic-'), identity

        def key(digit, down=True):
            p.send(0x30, bytes((DIGITS[digit], int(down))))

        def tap(digit):
            begin, index = time.monotonic(), len(p.timeline)
            key(digit); key(digit, False)
            return begin, index

        def wait_visual(predicate, index=0, timeout=15):
            deadline = time.monotonic()+timeout
            while time.monotonic() < deadline:
                for at, decoded in p.timeline[index:]:
                    if decoded and predicate(decoded):
                        return at, decoded
                index = len(p.timeline)
                p.pump(.02)
            raise AssertionError(('visual timeout', p.timeline[-3:], p.text[-250:]))

        def save(name, at=None, **extra):
            png(p.frames[-1], args.output/(name+'.png'))
            row = dict(case=name, at=round((at or time.monotonic())-start, 4), **extra)
            results.append(row); print(json.dumps(row), flush=True)
            return row

        def state_match(predicate, level=1, timeout=20):
            deadline = time.monotonic()+timeout
            last = None
            while time.monotonic() < deadline:
                last = registers(p)
                if predicate(last) and last[3] == 1:
                    if last[4] < 0:
                        return last
                    masks = expected(last, BOARDS[level-1])
                    # The matching framebuffer can arrive just after the
                    # register reply. Let it finish without another CLI query:
                    # that query can span the next guard turn and discard an
                    # otherwise complete action from the saved snapshot.
                    frame_deadline = min(deadline, time.monotonic()+.15)
                    while True:
                        if p.timeline and p.timeline[-1][1] and p.timeline[-1][1]['masks'] == masks:
                            return last
                        if time.monotonic() >= frame_deadline:
                            break
                        p.pump(min(.02, frame_deadline-time.monotonic()))
                p.pump(.02)
            raise AssertionError(('state timeout', level, last, p.timeline[-2:]))

        def reset(level=1):
            config=BOARDS[level-1]
            origin=config['start']%12
            sent, index = tap(0)
            p.pump(.2)
            wait_visual(lambda b: b['hero'] == origin, index)
            if not args.prototype_benchmark:
                state_match(lambda r: r[4:9] == [config['start'],config['enemies'][0],0,36,config['enemies'][1]],level)
            else:
                deadline=time.monotonic()+10
                while registers(p)[3]!=1:
                    assert time.monotonic()<deadline,'prototype restart stalled'
                    p.pump(.02)
            p.pump(.1)
            return sent

        def action(digit, level=1, target=None, win=False):
            before = registers(p)
            assert before[4] >= 0, ('action after defeat', level, digit, before)
            hole = None
            if digit in (7,9):
                floor, column = divmod(before[4],12)
                column += -1 if digit==7 else 1
                links = (BOARDS[level-1]['links'][floor-1] if floor else set()) | (BOARDS[level-1]['links'][floor] if floor<2 else set())
                hole = floor*12+column if before[7]==36 and floor and 0<=column<12 and column+1 not in links else before[7]
                target = before[4]
            if target is None and digit in (4,6,8,2):
                target = move(BOARDS[level-1], before[4], digit)
                if target == before[7]: target -= 12
            sent, index = tap(digit)
            if win:
                state = state_match(lambda r: r[4] == -2 and r[6] == 252, level)
            else:
                state = state_match(lambda r: (target is None or r[4]==target) and
                                    (hole is None or r[7]==hole) and r[13]==0, level)
                assert state[4] >= 0, ('lost', level, digit, state)
            p.pump(.1)  # let post-frame clock arming finish; not part of latency
            return state, sent, index

        benchmarks={}
        def benchmark(level=1):
            origin=BOARDS[level-1]['start']%12
            prefix='' if level==1 else f'level{level}-'
            reset(level)
            latencies=[]
            for column in range(origin+1,origin+5):
                sent,index=tap(6)
                at,decoded=wait_visual(lambda b,c=column:b['hero']==c,index)
                latencies.append(at-sent)
                save(prefix+'walk-'+str(column),at,seconds=round(at-sent,4),board=decoded)
            reset(level)
            begin,first=time.monotonic(),len(p.timeline)
            key(6);p.pump(3);release=time.monotonic();key(6,False)
            p.pump(1.5)
            seen=[(at,b['hero']) for at,b in p.timeline[first:] if b]
            positions=[col for at,col in seen if at<=release]
            settled=seen[-1][1]
            p.pump(1)
            assert p.timeline[-1][1] and p.timeline[-1][1]['hero']==settled,'movement stuck after release'
            held=max(positions,default=origin)-origin
            save(prefix+'hold-release',held_seconds=release-begin,cells_during_hold=held,settled_column=settled)
            reset(level)
            sent,index=tap(9)
            opened,_=wait_visual(lambda b:b['holes']==[origin+1],index)
            closed,decoded=wait_visual(lambda b:not b['holes'],len(p.timeline),timeout=10)
            median=statistics.median(latencies);duration=closed-opened
            save(prefix+'hole-restored',closed,seconds=duration,board=decoded)
            row=save(prefix+'responsiveness',median_walk_seconds=median,max_walk_seconds=max(latencies),
                     held_cells=held,hole_seconds=duration)
            benchmarks[level]=row
            assert median<=args.max_step_seconds,('slow step',level,median,args.max_step_seconds)
            assert held>=args.min_held_cells,('slow hold',level,held,args.min_held_cells)
            assert duration<=args.max_hole_seconds,('late restoration',level,duration,args.max_hole_seconds)
            reset(level)

        try:
            assert 'Calculator reinitialized.' in p.command('reinit')
            name='autoexec.m61' if args.start_level==1 else f'level{args.start_level}.m61'
            p.attach();p.open(args.directory.rstrip('/')+'/'+name);p.pump(.6)
            if args.start_level==1:
                png(p.frames[-1], args.output/'manual.png');p.key(39)
            wait_visual(lambda b:b['hero']==BOARDS[args.start_level-1]['start']%12,timeout=20)
            save('start', registers=registers(p))
            if not args.campaign_only:
                benchmark(args.start_level)
                if args.prototype_benchmark or args.benchmark_only:
                    save('benchmark-summary',benchmarks=benchmarks)
                    passed=True
                    return
                reset()
                sent,index=tap(9)
                wait_visual(lambda b:b['holes']==[1],index)
                p.key(37);p.pump(5);save('paused-hole-help')
                index=len(p.timeline);p.key(39)
                resumed,_=wait_visual(lambda b:b['holes']==[1],index)
                closed,_=wait_visual(lambda b:not b['holes'],len(p.timeline),timeout=8)
                assert 2.5<=closed-resumed<=5.0, ('manual did not preserve timer',closed-resumed)
                save('paused-hole-restored',closed,seconds_after_resume=closed-resumed)
                reset(); action(9, target=12); action(6, target=1)
                save('fall', registers=registers(p))
                reset()
                for digit in (6,6,2,4,4): action(digit)
                state=state_match(lambda r: r[4]==0 and r[6]==36)
                save('gold-collected', registers=state)
                tap(5);p.pump(.7);save('score')
                state_match(lambda r:r[4]==0 and r[6]==36)
                p.key(37);p.pump(.5);save('help');p.key(39)
                state_match(lambda r:r[4]==0 and r[6]==36)
                reset();action(6);action(6)
                state_match(lambda r:r[5]==16, timeout=35)
                action(9, target=14)
                state=state_match(lambda r:r[5]==r[7]==15)
                save('trapped-guard', registers=state)
                state=state_match(lambda r:r[7]==36 and r[5]!=15)
                save('guard-respawned', registers=state)
                reset()
                state=state_match(lambda r:r[4]==-1, timeout=40)
                save('lost', registers=state)
                tap(6);p.pump(2)
                assert registers(p)[4:9] == state[4:9], 'loss did not stop the game'
                reset()
                p.key(39);p.pump(.2)
                state=registers(p)
                assert state==[0]*len(state), 'ESC did not finish the campaign'
                save('escape-cancelled')
                p.open(args.directory.rstrip('/')+'/autoexec.m61');p.pump(.6);p.key(39)
                state_match(lambda r:r[4:9]==[12,35,0,36,36] and r[14]==2000)

            phase=registers(p)[14]
            for level, route in enumerate(ROUTES,1):
                if level>1:
                    config=BOARDS[level-1]
                    state=state_match(lambda r:r[4:9]==[config['start'],config['enemies'][0],0,36,config['enemies'][1]] and
                                      r[14]==4000-config['period'],level)
                    benchmark(level)
                    phase=registers(p)[14]
                    report=play_level(p,level)
                    save('level-'+str(level)+'-clear',frame_campaign=report)
                    continue
                for index,digit in enumerate(route):
                    deadline=time.monotonic()+10
                    while True:
                        state=registers(p)
                        assert state[4]>=0, ('campaign lost before key',level,index,digit,state)
                        if state[14]>=0 and state[14]!=phase:
                            phase=state[14];break
                        assert time.monotonic()<deadline, ('guard clock stalled',level,index,state)
                        p.pump(.02)
                    state,_,_=action(int(digit),level,win=index==len(route)-1)
                    if digit in '79': phase=state[14]
                    print(json.dumps(dict(level=level,move=index+1,key=digit,hero=state[4],guards=[state[5],state[8]],gold=state[6]//36)),flush=True)
                save('level-'+str(level)+'-clear', registers=state)
            p.pump(1.7);reset()
            save('campaign-restarted', registers=registers(p))
            if args.long_cx:
                action(9,target=12)
                p.send(0x30,bytes((0,1)));p.pump(1.8);p.send(0x30,bytes((0,0)));p.pump(.2)
                after=registers(p);tap(6);p.pump(5)
                assert registers(p)[4:15] == after[4:15], 'background activity survived long Cx'
                assert not p.timeline[-1][1], 'ordinary display was not restored'
                save('long-cx-cancelled', registers=after)
            save('summary',benchmarks=benchmarks)
            passed=True
        finally:
            failure=repr(sys.exc_info()[1]) if sys.exc_info()[1] else None
            # Restoring the ordinary calculator also cancels every M61 frame.
            try:
                cleanup['reinit_reply']=p.command('reinit')
                assert 'Calculator reinitialized.' in cleanup['reinit_reply'],cleanup
                if p.attached:
                    p.detach_watch=True;p.send(0x13);p.pump(1.1)
                    cleanup['detach_proof']=dict(kind='server OFFER after host DETACH',packet=p.detach_offer)
                else:
                    cleanup['detach_proof']=dict(kind='server DETACH',packet=p.server_detach)
                cleanup['detach_proof_verified']=bool(cleanup['detach_proof']['packet'])
                cleanup['detached']=not p.attached
                p.accept_frames=False
            finally:
                result=dict(identity=identity.__dict__,cases=results,passed=passed,failure=failure,
                    cleanup=cleanup,seconds=round(time.monotonic()-start,3))
                (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
