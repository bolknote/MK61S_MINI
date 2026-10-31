"""Frame-directed route policy, independent of calculator registers and clocks.

Decisions receive only decoded masks and the level. No phase/RD/RE, hidden
guards, native-step timing or timer values are exposed to this policy.
"""
from pathlib import Path
import sys
from runner_game_test import BOARDS,move,ROOT
sys.path.insert(0,str(ROOT/'tools/elite'))
from assembler import screen


def won(level,masks):
    return list(masks)==list(screen('ALL CLEAr' if level==3 else f'L{level} CLEAr'))


def lost(masks):
    return list(masks)==list(screen('CAUGHt  0'))


class Action:
    def __init__(self,level,view,key,hole=36):
        self.level,self.before,self.key=level,view,key
        hero=view['hero']
        self.target=hero
        self.hole=hole
        self.burn_target=None
        if key in (2,4,6,8):
            self.target=move(BOARDS[level-1],hero,key)
            if self.target==hole:self.target-=12
        elif key==0:
            self.target=BOARDS[level-1]['start']
        elif key in (7,9):
            self.burn_target=hero+(-1 if key==7 else 1)
        self.floor_hint=self.target//12

    def candidate(self,masks):
        if masks==self.before['masks']:return None
        actual=observe(self.level,masks,self.floor_hint)
        if not actual:return None
        if self.key in (7,9):
            target_mask=masks[self.burn_target%12]
            if actual['hero']==self.before['hero'] and target_mask in (0,119):
                return dict(view=actual,burn_covered=(target_mask==119))
        elif actual['hero']==self.target:
            return dict(view=actual,burn_covered=False)
        return None


def observe(level,masks,floor_hint=None):
    if masks.count(107)!=1:return None
    board=BOARDS[level-1]
    floors=[]
    for floor in range(3):
        links=(board['links'][floor-1] if floor else set()) | (board['links'][floor] if floor<2 else set())
        if all((value not in (8,126) or value==(126 if col+1 in links else 8)) and
               (value!=201 or board['gold'][floor]%12==col)
               for col,value in enumerate(masks)):
            floors.append(floor)
    if len(floors)==1:floor=floors[0]
    else:
        # Sprites may cover every ladder distinguishing two floors. Retain
        # the floor implied by the last confirmed move instead of reading R4.
        assert floor_hint in floors,('ambiguous floor without history',floors,masks)
        floor=floor_hint
    return dict(hero=floor*12+masks.index(107),floor=floor,
        guards=[floor*12+c for c,value in enumerate(masks) if value==119],
        holes=[floor*12+c for c,value in enumerate(masks) if value==0],
        gold=[floor*12+c for c,value in enumerate(masks) if value==201],masks=list(masks))


class Player:
    def __init__(self,level):
        assert level in (2,3)
        self.level,self.stage=level,'approach'

    def choose(self,view):
        h=view['hero']
        while True:
            if self.level==2:
                if self.stage=='approach':
                    if h<19:return 6
                    if h==19:return 8
                    assert h==31
                    self.stage='burn'
                elif self.stage=='burn':
                    assert h==31
                    self.stage='top-gold';return 9
                elif self.stage=='top-gold':
                    if h==31:return 4
                    assert h==30;self.stage='return-ladder'
                elif self.stage=='return-ladder':
                    if h==30:return 6
                    assert h==31;self.stage='lure'
                elif self.stage=='lure':
                    # Wait for the pursuing left guard to CLIMB to the top.
                    # It then follows us from behind after the descent.
                    if any(30<=g<h for g in view['guards']):
                        self.stage='middle-left';return 2
                    if view['masks'][8]==8:return 9
                    return None
                elif self.stage=='middle-left':
                    if h>12:
                        if len(view['guards'])==2 and all(g-h>=3 for g in view['guards']):return 'hold4_to_gold'
                        return 4
                    assert h==12
                    # Returning12->13 and then descending needs two guard
                    # updates of clearance. A visible guard at14/15 is unsafe.
                    assert not any(abs(g-13)<=2 for g in view['guards']), 'unsafe gold turnaround'
                    self.stage='lower-ladder';return 6
                elif self.stage=='lower-ladder':
                    assert h==13
                    assert not any(abs(g-h)<=1 for g in view['guards']), 'unsafe ladder descent'
                    self.stage='bottom-right';return 2
                elif self.stage=='bottom-right':
                    if h==11:return None
                    assert 1<=h<11;return 6
                else:raise AssertionError(self.stage)
            else:
                if self.stage=='approach':
                    if h>16 and h<24:return 4
                    if h==16:return 8
                    assert h==28;self.stage='top-gold'
                elif self.stage=='top-gold':
                    if h>24:return 4
                    assert h==24;self.stage='burn-position';return 6
                elif self.stage=='burn-position':
                    assert h==25;self.stage='lure';return 7
                elif self.stage=='lure':
                    # The upper pursuer visibly reaches27. This also lets
                    # the lower guard leave the landing route before falling.
                    if view['masks'][0]==8:return 7
                    if not any(25<g<=27 for g in view['guards']):return None
                    self.stage='descend';return 4
                elif self.stage=='descend':
                    assert h==12;self.stage='bottom-right';return 2
                elif self.stage=='bottom-right':
                    if h<11:return 6
                    assert h==11;self.stage='middle-gold';return 8
                elif self.stage=='middle-gold':
                    if h==22:return None
                    assert h==23;return 4
                else:raise AssertionError(self.stage)
