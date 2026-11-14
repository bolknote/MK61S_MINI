"""Exact PicoCalc cu/tty ownership, using macOS libproc and no CDC opens.

Holder query derived from tests/hil_classic_cdc_guard.py:path_holders.
No Classic identity, enumeration or port-control code is imported.
"""
import ctypes
import os
from pathlib import Path
import re
import stat

UID='E6657CD423721C35'
class HolderError(RuntimeError):pass
def need(ok,reason):
    if not ok:raise HolderError(reason)
def query_function():
    lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
    query=lib.proc_listpidspath
    query.argtypes=[ctypes.c_uint32,ctypes.c_uint32,ctypes.c_char_p,
                    ctypes.c_uint32,ctypes.c_void_p,ctypes.c_int]
    query.restype=ctypes.c_int
    return query
def path_holders(query,path):
    encoded=os.fsencode(path);word=ctypes.sizeof(ctypes.c_int)
    size=query(1,0,encoded,0,None,0)
    need(0<size<=1024*1024 and size%word==0,
         ('proc_listpidspath size/error',size,ctypes.get_errno()))
    buffer=(ctypes.c_int*(size//word+32))()
    count=query(1,0,encoded,0,buffer,ctypes.sizeof(buffer))
    need(0<=count<ctypes.sizeof(buffer) and count%word==0,
         ('proc_listpidspath error/truncation',count,ctypes.get_errno()))
    pids=list(buffer)[:count//word]
    need(all(pid>0 for pid in pids),('Invalid holder PID',pids))
    return sorted(set(pids))
def require_no_holders(binding,allow_self=False,query=None):
    need(binding.get('uid')==UID,'Foreign PicoCalc UID')
    cu=binding.get('cu','');tty=binding.get('tty','')
    need(re.fullmatch(r'/dev/cu\.usbmodem[0-9A-Za-z]+',cu) and tty==cu.replace('/dev/cu.','/dev/tty.',1),
         'Expected exact PicoCalc cu/tty pair')
    if query is None:query=query_function()
    allowed={os.getpid()} if allow_self else set();rows=[]
    for key in ('cu','tty'):
        path=binding[key];status=os.stat(path)
        need(Path(path).parent==Path('/dev') and stat.S_ISCHR(status.st_mode) and
             status.st_rdev==binding[key+'_rdev'],'PicoCalc endpoint type/device changed')
        pids=path_holders(query,path);rows.append(dict(path=path,pids=pids,rdev=status.st_rdev))
        need(set(pids)<=allowed,('Foreign PicoCalc CDC holder',path,pids))
    return dict(method='macOS libproc proc_listpidspath',allow_self=allow_self,paths=rows)
