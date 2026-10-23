#!/usr/bin/env python3
"""Offline checks for per-stage cache restoration; never opens a serial port."""
import hashlib
import struct
import zlib
from pathlib import Path
import tempfile
from unittest.mock import patch
import hil_vm_compiled_blocks as h

def legacy(payload):
 header=bytearray(64);header[:8]=b'MK61APP\0'
 struct.pack_into('<HHHBB',header,8,1,64,6,10,0)
 struct.pack_into('<IIII',header,24,len(payload),len(payload),len(payload),0)
 struct.pack_into('<I',header,48,zlib.crc32(payload))
 struct.pack_into('<I',header,60,zlib.crc32(header[:60]))
 return bytes(header)+payload

OLD='/System/VMCache/VMC-000f.app'
NEW='/System/VMCache/VMC-0018.app'
OTHER='/games/search.tbi'
def fingerprint(files):
 return dict(files={k:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for k,v in files.items()},directories=[])
class Port:
 def __init__(self,files):self.files=files;self.operations=[]
 def command(self,command,timeout):
  assert timeout==30 and command.startswith('rm "') and command.endswith('"')
  path=command[4:-1];self.operations.append(('remove',path));del self.files[path]
  return 'Removed 1 entry.'
def exercise(files,snapshot,backup):
 p=Port(files)
 def write(port,path,data):port.operations.append(('write',path));port.files[path]=data
 with patch.object(h.storage_hil,'fingerprint',lambda port:fingerprint(port.files)),patch.object(h,'write_file',write),patch.object(h,'read_file',lambda port,path:port.files[path]):
  return p,h.restore_cache(p,snapshot,backup)
def main():
 original={OLD:legacy(b'original cache'),OTHER:b'original source'};snapshot=fingerprint(original)
 with tempfile.TemporaryDirectory() as directory:
  backup=Path(directory);path=backup/OLD.lstrip('/');path.parent.mkdir(parents=True);path.write_bytes(original[OLD])
  p,result=exercise({**original,OLD:legacy(b'new wire version'),NEW:legacy(b'created')},snapshot,backup)
  assert result==([NEW],[OLD]) and p.files==original and p.operations==[('remove',NEW),('write',OLD)]
  p,result=exercise(dict(original),snapshot,backup);assert result==([],[]) and not p.operations
  p,result=exercise({OTHER:original[OTHER]},snapshot,backup);assert result==([],[OLD]) and p.files==original
  try:exercise({**original,OTHER:b'foreign change'},snapshot,backup)
  except AssertionError:pass
  else:raise AssertionError('foreign change not refused')
  for added in ('/user.txt','/System/VMCache/VMC-user.app','/System/VMCache/VMC-0018.app.extra'):
   files={**original,NEW:legacy(b'created'),added:b'foreign'};p=Port(files)
   with patch.object(h.storage_hil,'fingerprint',lambda port:fingerprint(port.files)):
    try:h.restore_cache(p,snapshot,backup)
    except AssertionError:pass
    else:raise AssertionError(added)
   assert not p.operations and files[NEW]==legacy(b'created')
  path.write_bytes(b'bad backup')
  try:exercise({**original,OLD:legacy(b'new')},snapshot,backup)
  except AssertionError:pass
  else:raise AssertionError('bad backup accepted')
 a,b,c = 'raw24.bin','mixed24.bin','raw32.bin'
 common=Path('System');other=Path('other-System')
 planned=h.stage_plan(a,b,common,other,raw32=c)
 assert [name for name,_,_ in planned]==['baseline','candidate','raw32','control']
 assert [image for _,image,_ in planned]==[a,b,c,a]
 assert h.stage_plan(a,b,common,other)==[planned[0],planned[1],planned[3]]
 assert h.stage_plan(a,b,common,other,single=True)==[('qualification',b,other)]
 h.require_common_apps(planned,{common:{'LANGVM.APP':b'wire9'},other:{'LANGVM.APP':b'wire9'}})
 try:h.require_common_apps(planned,{common:{'LANGVM.APP':b'wire9'},other:{'LANGVM.APP':b'other'}})
 except AssertionError:pass
 else:raise AssertionError('mixed System accepted')
 try:h.stage_plan(a,b,common,other,raw32=c,single=True)
 except AssertionError:pass
 else:raise AssertionError('single raw32 accepted')
 expected=object()
 banner=AssertionError('not a canonical MK61 identity response: MK61s-Classic-V3 ver. boot banner')
 with patch.object(h,'original_connect',side_effect=[banner,expected]) as connect,patch.object(h.time,'sleep'):
  assert h.connect('/unused','GOOD',wait=2) is expected
  assert connect.call_count==2
 for error in (AssertionError('wrong UID/profile/build'),AssertionError('not a canonical MK61 identity response: other data')):
  with patch.object(h,'original_connect',side_effect=error) as connect,patch.object(h.time,'sleep'):
   try:h.connect('/unused','GOOD',wait=2)
   except AssertionError as caught:assert caught is error
   else:raise AssertionError('unverified identity accepted')
   assert connect.call_count==1
 assert h.is_vm_cache('/system/vmcache/vmc-abcd.APP')
 print('Versioned VM HIL: cache-only restoration, original SHA checks, foreign-file rejection and no-op PASS')
if __name__=='__main__':main()
