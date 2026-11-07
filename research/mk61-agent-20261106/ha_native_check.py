"""Cross-check the bounded C++ frontend against every frozen task."""
import ctypes as C
import json
from pathlib import Path
import subprocess

from ha_common import ROOT,HERE,read,write,sha
from ha_protocol import constants,encode,assemble,parse_call,write_call,patch_call


def library(out):
    out.mkdir(exist_ok=True,parents=True);path=out/'ha-native.dylib'
    subprocess.run(['clang++','-std=c++17','-O2','-fPIC','-shared',str(HERE/'ha_native_probe.cpp'),'-o',str(path)],check=True)
    lib=C.CDLL(str(path));byteptr=C.POINTER(C.c_ubyte);nptr=C.POINTER(C.c_uint);poolptr=C.POINTER(C.c_char_p)
    lib.ha_pool.argtypes=[C.c_char_p,C.c_void_p,C.c_uint,nptr]
    lib.ha_assemble.argtypes=[byteptr,C.c_uint,poolptr,C.c_uint,C.c_int,byteptr,nptr]
    lib.ha_patch.argtypes=[byteptr,nptr,byteptr,C.c_uint]
    lib.ha_reply.argtypes=[C.c_char_p,byteptr,nptr,poolptr,C.c_uint,C.c_int,C.POINTER(C.c_int),nptr,byteptr,nptr]
    return lib


def cpp_pool(lib,text):
    data=C.create_string_buffer(256*20);used=C.c_uint()
    assert lib.ha_pool(text.encode(),data,len(data),C.byref(used))==0,text
    return [data.raw[i*20:(i+1)*20].split(b'\0')[0].decode()for i in range(used.value)]


def cpp_assemble(lib,body,pool,arm):
    values=(C.c_char_p*len(pool))(*(x.encode()for x in pool));encoded=(C.c_ubyte*len(body))(*body);out=(C.c_ubyte*105)();used=C.c_uint()
    result=lib.ha_assemble(encoded,len(body),values,len(pool),arm=='asm',out,C.byref(used))
    if result:raise ValueError('Native assembler rejected body: '+str(result))
    return list(out[:used.value])


def verify_all(root,out):
    lib=library(out);pool_checks=0;program_checks=0
    for filename in ['train.jsonl','validation.jsonl','fresh.jsonl','isa-audit.jsonl']:
        for task in read(root/filename):
            pool=constants(task['task']);actual=cpp_pool(lib,task['task']);assert actual==pool,(task['id'],actual,pool)
            pool_checks+=1
            for arm in ['direct','asm']:
                body=encode(task['reference_code'],pool,arm);actual=cpp_assemble(lib,body,pool,arm)
                assert actual==task['reference_code'],task['id'];program_checks+=1
    for byte in range(256):
        code=[byte,0x50];body=encode(code,[],'asm');assert cpp_assemble(lib,body,[],'asm')==code
    for arm in ['direct','asm']:
        pool=constants('Подсчитай синус -.125.');target=encode([0x0E,0x0D,0,0x0A,1,2,5,0x0B,0x1C,0x50],pool,arm)
        current=encode([0x60,0x50],pool,arm)
        for reply in [write_call(target),patch_call(current,target),'<trace/>','<run>01</run>','<done/>']:
            expected_kind,expected=parse_call(reply,current)
            body=(C.c_ubyte*512)(*current);size=C.c_uint(len(current));action=C.c_int();test=C.c_uint();output=(C.c_ubyte*105)();used=C.c_uint()
            values=(C.c_char_p*len(pool))(*(x.encode()for x in pool))
            assert lib.ha_reply(reply.encode(),body,C.byref(size),values,len(pool),arm=='asm',C.byref(action),C.byref(test),output,C.byref(used))==0
            if expected_kind in ['write','patch']:assert list(body[:size.value])==expected
            elif expected_kind=='run':assert test.value==expected
    result={'pool_extractions_matched':pool_checks,'program_expansions_matched':program_checks,'all_256_raw_bytes_verified':True,
      'tool_reply_calls_matched':10,'native_state_bytes':lib.ha_state_bytes(),'native_assembler_workspace_bytes':lib.ha_workspace_bytes(),
      'bounded_allocation_free_cpp':True,'physical_picocalc_measured':False,
      'sources':{name:sha(HERE/name)for name in ['ha_native.hpp','ha_native_probe.cpp']}}
    write(out/'frontend-verification.json',result);print(json.dumps(result),flush=True)
    return result


if __name__=='__main__':verify_all(ROOT,ROOT/'native-frontend')
