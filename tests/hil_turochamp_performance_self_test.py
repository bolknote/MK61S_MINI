#!/usr/bin/env python3
"""Pure pixel/profile tests for the chess HIL benchmark, without devices."""
from hil_turochamp_performance import Font, ROOT, profile
from m8_codec import encode

font=Font((ROOT/'programs/games/Turochamp/Turochamp.FMK').read_bytes())
frame=bytearray(1536)
def put(text,row,col):
    for code in encode(text):
        glyph=font.glyphs[code]
        for y,bits in enumerate(glyph):
            for x in range(7):
                if bits&(1<<(6-x)):
                    px,py=2+col*7+x,row*7+y
                    frame[py//8*192+px]|=1<<(py%8)
        col+=1

put('ДУМАЕТ...',2,10);put('ПОЗ 420',3,10);put('e2-e3',6,10)
assert font.has(frame,'ДУМАЕТ...') and font.number_after(frame,'ПОЗ ')==420
assert font.has(frame,'e2-e3') and not font.has(frame,'ВАШ ХОД')
assert font.number_after(frame,'КНИГА ') is None
data=profile('PROF state=stopped clock=96000000 overhead=1\n'
             'PROF flash.read n=23 min=10 avg=20 max=50 total=96000000\n'
             'PROF zx0.decode n=3 min=1 avg=2 max=3 total=192000000\n')
assert data['points']['flash.read']['calls']==23
assert data['points']['flash.read']['total_seconds']==1
assert data['points']['zx0.decode']['total_seconds']==2
try:profile('invalid')
except AssertionError:pass
else:raise AssertionError('missing profile clock accepted')
print('Turochamp performance oracle: M8 pixels, progress, move and DWT timing PASS')
