"""Frame-only campaign driver shared by HOST and an authorized Classic HIL.

The caller supplies an owned port; importing this module opens no device.
"""
import time
from functools import lru_cache
from runner_frame_player import Player,Action,observe,won,lost
from hil_runner_classic import DIGITS
from runner_screen_oracle import board,indicator,cell_signature
from runner_frame_player import screen


@lru_cache(None)
def banner_signature(text):
    rendered=indicator(screen(text))
    return tuple(cell_signature(rendered,i) for i in range(12))


def decode(frame,level):
    signature=tuple(cell_signature(frame,i) for i in range(12))
    for text in ('CAUGHt  0','ALL CLEAr' if level==3 else f'L{level} CLEAr'):
        if signature==banner_signature(text):
            return list(screen(text))
    view=board(frame)
    return view['masks'] if view else None


def play_level(port,level,timeout=120,*,initial_stage=None,reset_start=True):
    assert level in (2,3)
    player=Player(level);floor=1;hole=36;rows=[]
    if initial_stage is not None:player.stage=initial_stage
    deadline=time.monotonic()+timeout

    def send(key):
        port.send(0x30,bytes((DIGITS[key],1)))
        port.send(0x30,bytes((DIGITS[key],0)))

    def wait_candidate(index,predicate):
        while time.monotonic()<deadline:
            for raw in port.frames[index:]:
                masks=decode(raw,level)
                if masks is None:continue
                assert not lost(masks),'visible defeat'
                if won(level,masks) or predicate(masks):return masks
            index=len(port.frames)
            port.pump(.02)
        raise AssertionError('frame campaign timeout')

    masks=decode(port.frames[-1],level)
    assert masks is not None
    # A move then reset guarantees a changed, fresh start frame without a
    # blocking register query. Both ordinary gestures are in the HOST replay.
    for reset_key in ((6,0) if reset_start else ()):
        view=observe(level,masks,floor);action=Action(level,view,reset_key,hole)
        port.pump(.1);index=len(port.frames);sent=time.monotonic();send(reset_key)
        masks=wait_candidate(index,action.candidate);floor=action.floor_hint
        rows.append(dict(key=reset_key,prelude=True,sent=sent,masks=masks))
    hole=36
    for _ in range(100):
        if won(level,masks):return dict(level=level,won=True,rows=rows,CLI_queries_during_play=0)
        view=observe(level,masks,floor);stage=player.stage;key=player.choose(view)
        if key is None:
            prior=list(masks);index=len(port.frames)
            masks=wait_candidate(index,lambda candidate:candidate!=prior)
            rows.append(dict(stage=stage,key=None,masks=masks))
            continue
        if key=='hold4_to_gold':
            port.pump(.1)
            current=decode(port.frames[-1],level)
            fresh=observe(level,current,1) if current else None
            assert fresh and fresh['hero']==view['hero'], 'held corridor frame changed'
            if not (len(fresh['guards'])==2 and all(g-fresh['hero']>=3 for g in fresh['guards'])):
                # Selection may be followed by another guard frame during
                # pump(). Keep the held-start margin; reselect one ordinary
                # step from this newer safe view instead of using old masks.
                assert len(fresh['guards'])==2 and all(g-fresh['hero']>=2 for g in fresh['guards']), 'unsafe held corridor start'
                masks=current;floor=fresh['floor']
                rows.append(dict(stage=stage,key=None,fresh_replan=True,masks=masks))
                continue
            index=len(port.frames);sent=time.monotonic()
            port.send(0x30,bytes((DIGITS[4],1)))
            try:
                masks=wait_candidate(index,lambda candidate: observe(level,candidate,1)['hero']==12)
            finally:
                port.send(0x30,bytes((DIGITS[4],0)))
            floor=1
            rows.append(dict(stage=stage,key=4,held=True,sent=sent,masks=masks,
                             guard_margin_at_DOWN=min(g-fresh['hero'] for g in fresh['guards'])))
            continue
        action=Action(level,view,key,hole)
        port.pump(.1)
        if level==2 and ((view['hero']==12 and key==6) or (view['hero']==13 and key==2)):
            current=decode(port.frames[-1],level)
            fresh=observe(level,current,view['floor']) if current else None
            assert fresh and fresh['hero']==view['hero'], 'critical turn frame changed'
            if key==6:
                assert not any(abs(g-13)<=2 for g in fresh['guards']), 'unsafe fresh gold turnaround'
            else:
                assert not any(abs(g-13)<=1 for g in fresh['guards']), 'unsafe fresh ladder descent'
        index=len(port.frames);sent=time.monotonic();send(key)
        masks=wait_candidate(index,action.candidate)
        candidate=None if won(level,masks) else action.candidate(masks)
        # A guard can cover a newly burned tile. This is a visible candidate,
        # not an independent proof of the hidden R7/RD phase; log it honestly.
        rows.append(dict(stage=stage,key=key,sent=sent,masks=masks,
                         covered_burn_candidate=bool(candidate and candidate['burn_covered'])))
        floor=action.floor_hint
        if key in (7,9):hole=action.burn_target
    raise AssertionError('too many frame decisions')
