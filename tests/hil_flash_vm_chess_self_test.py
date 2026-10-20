#!/usr/bin/env python3
"""Offline guards for no-DFU qualification and separate profiled searches."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import struct
import zlib

import hil_flash_vm_chess as hil

original=dict(sha256='a'*64,bytes=370064,build='3AB3DD45')
assert hil.same_firmware(original,dict(original))
assert hil.vm_stage_plan(b'old',b'new')==[('baseline',b'old'),('candidate',b'new'),('control',b'old')]
assert hil.qualification_apps()==('BASIC.APP','FOCAL.APP','LANGVM.APP','LANGIN.APP','SRCEDIT.APP')
assert hil.qualification_apps(True)==hil.qualification_apps()+('VMCache/VMSTORE.APP',)
assert [hil.linked_stage_script(name,b'ordinary') for name in ('baseline','candidate','control')]==[
    b'ordinary',b'reinit\nloadfont Turochamp\nvm-linked\n',b'ordinary']
assert [hil.linked_stage_script(name,b'ordinary',True) for name in ('baseline','candidate','control')]==[
    b'reinit\nloadfont Turochamp\nvm-linked\n']*3
stages=[dict(name=n,runs=[dict(seconds=t) for t in times]) for n,times in (
    ('baseline',(99,25,25.2)),('candidate',(88,23,23.2)),('control',(77,25.2,25.4)))]
comparison=hil.steady_comparison(stages)
assert all(abs(a-b)<1e-12 for a,b in zip(comparison['steady_seconds'],(25.1,23.1,25.3)))
assert abs(comparison['reference_seconds']-25.2)<1e-12
assert comparison['candidate_seconds']==23.1
try:hil.steady_comparison(stages[:2])
except AssertionError:pass
else:raise AssertionError('accepted an incomplete resident A/B/A')
image=bytearray(32+9000);image[:4]=b'LVP1';struct.pack_into('<I',image,8,len(image))
struct.pack_into('<I',image,24,zlib.crc32(image[32:]));struct.pack_into('<I',image,28,zlib.crc32(image[:28]))
chunks=hil.linked_chunks(bytes(image))
assert list(chunks)==['LVP00.bin','LVP01.bin','LVP02.bin']
assert b''.join(chunks.values())==image and all(0<len(data)<=4096 for data in chunks.values())
bad=bytearray(image);bad[-1]^=1
for damaged in (b'',bytes(image[:31]),bytes(image[:-1]),bytes(bad)):
    try:hil.linked_chunks(damaged)
    except AssertionError:pass
    else:raise AssertionError('accepted corrupt/truncated linked transport')
hil.require_no_firmware_write(original,dict(original),original['build'])
hil.require_cache_activity({'hits':1})
hil.require_cache_activity({'hits':0,'loan_hits':1})
for counters in ({'hits':0},{'hits':0,'loan_hits':0}):
    try:hil.require_cache_activity(counters)
    except AssertionError:pass
    else:raise AssertionError('accepted an unused page/image cache')
for field,value in (('sha256','b'*64),('bytes',370068),('build','3DF44CE4')):
    different=dict(original);different[field]=value
    assert not hil.same_firmware(original,different)
    try:hil.require_no_firmware_write(original,different,original['build'])
    except AssertionError:pass
    else:raise AssertionError('no-DFU accepted a changed '+field)
try:hil.require_no_firmware_write(original,original,'3DF44CE4')
except AssertionError:pass
else:raise AssertionError('no-DFU accepted a different running firmware')

class Port:
    frames=[b'frame'];text=b'';attached=False
    def __init__(self,path):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def command(self,command):return 'identity'
    def attach(self):self.attached=True
    def pump(self,*args):pass
    def send(self,*args):pass

empty=dict(files={},directories=[])
with patch.object(hil,'print'),patch.object(Port,'command',return_value='Removed 1 entry.') as remove:
    hil.remove_owned_pages(Port(None),empty,dict(directories=[]))
    remove.assert_not_called()
    hil.remove_owned_pages(Port(None),empty,dict(directories=[hil.CACHE]))
    remove.assert_called_once_with('rm -r "'+hil.CACHE+'"',60)
    for original_tree in (dict(files={},directories=[hil.CACHE]),
                          dict(files={hil.CACHE+'/user.bin':{}},directories=[]),
                          dict(files={},directories=[hil.CACHE+'/user'])):
        remove.reset_mock()
        try:hil.remove_owned_pages(Port(None),original_tree,dict(directories=[hil.CACHE]))
        except AssertionError:pass
        else:raise AssertionError('accepted a pre-existing cache tree')
        remove.assert_not_called()

calls=[]
def search(port,font,options,index,out):
    calls.append((options.no_profile,options.reset_before))
    return dict(seconds=60.0,board_frame_sha256='golden')

with TemporaryDirectory(prefix='flash-chess-guard-') as directory:
    report=dict(stages=[])
    with patch.object(hil,'OUT',Path(directory)), \
         patch.object(hil,'ARGS',SimpleNamespace(timeout=600)), \
         patch.object(hil,'TimedScreenPort',Port), \
         patch.object(hil,'parse_identity',return_value=SimpleNamespace(
             public=hil.PUBLIC,build=original['build'],profile='classic-v3-uc1609')), \
         patch.object(hil,'cache_statistics',return_value={'hits':100}), \
         patch.object(hil,'search',side_effect=search), \
         patch.object(hil,'stop_game'), \
         patch.object(hil.memory,'health',return_value={'mpu status':'layout=ok'}), \
         patch.object(hil,'manifests',return_value=[]):
        hil.run_stage('ordinary',2,original['build'],None,report)
        hil.run_stage('profile-repeat',1,original['build'],None,report,profiling=True)
    assert calls==[(True,True),(True,True),(False,False)]
    assert [s['profiling'] for s in report['stages']]==[False,True]
    assert len(report['stages'][0]['runs'])==2 and len(report['stages'][1]['runs'])==1

print('Flash chess HIL: identical firmware/no-DFU guards and separate profiler stage PASS')
