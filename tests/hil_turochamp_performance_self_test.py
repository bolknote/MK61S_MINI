#!/usr/bin/env python3
"""Pure pixel/profile tests for the chess HIL benchmark, without devices."""
from hil_turochamp_performance import Font, ROOT, profile, completed_board, board_pixels
from m8_codec import encode
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import hil_turochamp_performance as benchmark

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
for block_name in ('vm.block.integer','vm.block.fused'):
    block=profile('PROF state=stopped clock=96000000\n'
                  f'PROF {block_name} n=3 min=0 avg=32 max=0 total=96 self=96\n'
                  'VMOP op=256 n=3 integers=0 cycles=96\n')
    assert block['vm_opcodes']==[{'opcode':256,'instructions':3,'integer_pairs':0,
                                  'cycles':96,'seconds':.000001}]
detail=profile('PROF state=stopped clock=96000000\n'
               'PROF app.entry.vm n=2 min=10 avg=20 max=50 total=96000000 self=48000000\n'
               'VMCACHE dropped=0\n'
               'VMCACHE id=12 bytes=2189 hits=50 misses=2 name=search\r\n')
assert detail['points']['app.entry.vm']['self_seconds']==.5
assert detail['vm_cache_dropped']==0 and detail['vm_cache']==[
    {'id':12,'bytes':2189,'hits':50,'misses':2,'name':'search'}]
signature=('PROF state=stopped clock=96000000\nVMCACHE dropped=0\n'
           'VMCACHE_ORDER count=2 fnv64=10178788028133461333\n'
           'VMCACHE id=42 bytes=128 hits=1 misses=1 name=test\n')
assert profile(signature)['vm_cache_order']=={'count':2,'fnv64':10178788028133461333}
for invalid in (signature.replace('count=2','count=1'), signature.replace('count=2','count=4294967295'),
                signature+'VMCACHE_ORDER count=2 fnv64=1\n'):
    try:profile(invalid)
    except AssertionError:pass
    else:raise AssertionError('incomplete/saturated/duplicate cache signature accepted')
frame=bytearray(1536)
put('ВАШ ХОД',2,10);put('e2-e3',6,10)
for rank in range(1,7):put(str(rank),rank,0)
assert not completed_board(font,frame), 'partial six-rank board accepted'
put('7',7,0);put('С/П МЕНЮ',7,10)
assert not completed_board(font,frame), 'partial seven-rank board accepted'
put('8',8,0);put('ОК ВЫБОР',8,10)
assert completed_board(font,frame)
stable=board_pixels(frame)
for x,y in ((176,0),(191,0),(176,15),(191,15)):
    changed=bytearray(frame);changed[y//8*192+x]^=1<<(y%8)
    assert board_pixels(changed)==stable, 'disk animation changed board comparison'
for x,y in ((175,0),(176,16),(191,16),(0,7)):
    changed=bytearray(frame);changed[y//8*192+x]^=1<<(y%8)
    assert board_pixels(changed)!=stable, 'non-disk pixel ignored'
try:profile('invalid')
except AssertionError:pass
else:raise AssertionError('missing profile clock accepted')

class DetachedPort:
    attached=True
    frames=[bytes(1536)]
    frame_times=[0]
    text=bytearray()
    open_text_start=0
    def open(self,path):pass
    def key(self,key):pass
    def command(self,command):return 'PROF started'
    def pump(self,duration):self.attached=False
class NoBookFont:
    def has(self,frame,text):return False
with tempfile.TemporaryDirectory(prefix='mk61-chess-detach-') as temp:
    options=SimpleNamespace(game_dir='/game',timeout=1,build_id='TEST')
    with patch.object(benchmark,'wait_screen'),patch.object(benchmark,'png'):
        try:benchmark.search(DetachedPort(),NoBookFont(),options,0,Path(temp))
        except AssertionError as error:
            assert 'USB Screen detached during search' in str(error)
        else:raise AssertionError('detached stale frame accepted as a live search')
print('Turochamp performance oracle: M8, eight ranks, bounded disk mask and DWT timing PASS')
