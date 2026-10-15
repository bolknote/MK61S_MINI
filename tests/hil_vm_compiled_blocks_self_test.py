#!/usr/bin/env python3
"""Offline checks for per-stage cache restoration; never opens a serial port."""
import hashlib
from pathlib import Path
import tempfile
from unittest.mock import patch
import hil_vm_compiled_blocks as h

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
 original={OLD:b'original cache',OTHER:b'original source'};snapshot=fingerprint(original)
 with tempfile.TemporaryDirectory() as directory:
  backup=Path(directory);path=backup/OLD.lstrip('/');path.parent.mkdir(parents=True);path.write_bytes(original[OLD])
  p,result=exercise({**original,OLD:b'new wire version',NEW:b'created'},snapshot,backup)
  assert result==([NEW],[OLD]) and p.files==original and p.operations==[('remove',NEW),('write',OLD)]
  p,result=exercise(dict(original),snapshot,backup);assert result==([],[]) and not p.operations
  p,result=exercise({OTHER:original[OTHER]},snapshot,backup);assert result==([],[OLD]) and p.files==original
  p,result=exercise({**original,OTHER:b'foreign change'},snapshot,backup);assert result==([],[]) and p.files[OTHER]==b'foreign change'
  for added in ('/user.txt','/System/VMCache/VMC-user.app','/System/VMCache/VMC-0018.app.extra'):
   files={**original,NEW:b'created',added:b'foreign'};p=Port(files)
   with patch.object(h.storage_hil,'fingerprint',lambda port:fingerprint(port.files)):
    try:h.restore_cache(p,snapshot,backup)
    except AssertionError:pass
    else:raise AssertionError(added)
   assert not p.operations and files[NEW]==b'created'
  path.write_bytes(b'bad backup')
  try:exercise({**original,OLD:b'new'},snapshot,backup)
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
 assert h.is_vm_cache('/system/vmcache/vmc-abcd.APP')
 print('Versioned VM HIL: cache-only restoration, original SHA checks, foreign-file rejection and no-op PASS')
if __name__=='__main__':main()
