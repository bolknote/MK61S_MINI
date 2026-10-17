#!/usr/bin/env python3
"""Run the real Flash-cache preparation before a cold USB Screen session.

Only millis is stubbed. Real allocator/USB start/heap limits and cache accessor
execute on ARM. --expect-unprepared reproduces the missing Flash-cache hook.
"""
import argparse
from pathlib import Path
from unicorn.arm_const import UC_ARM_REG_IPSR
from run_usb_screen_cold_buffers_arm_tests import Buffers

START='_ZN10usb_screen5startEv'
LOOKUP='_ZN11language_vm12_GLOBAL__N_116flash_page_cacheEb'

def pointer(m):
    names=[n for n in m.elf.symbols if 'flash_page_cache' in n and n.endswith('E5cache')]
    assert len(names)==1,names
    return m.word(m.elf.symbols[names[0]])

def lookup(m):
    # LTO inlines the public diagnostics/preparation. Exercise the exact
    # shared accessor they use; observing it must not allocate anything.
    before=m.heap()
    result=m.call(LOOKUP,0)
    assert m.heap()==before,'read-only lookup allocated the cache'
    assert result==pointer(m)
    return result

def prepare(m):
    return m.call(LOOKUP,1)!=0

def cold(path,expected):
    m=Buffers(path)
    assert not pointer(m)
    if not expected:
        assert not lookup(m)
    assert m.call(START)==1
    if expected:
        assert pointer(m)==0,'negative oracle already prepares Flash cache'
        print('Flash ARM cold USB: missing early page-cache preparation REPRODUCED')
        return
    cache=pointer(m);heap=m.heap()
    assert lookup(m)==cache
    budget=m.elf.symbols['mk61_lazy_vm_cache_bytes']
    assert budget==32768 and cache and cache<heap<=cache+budget+64,(cache,heap,budget)
    assert prepare(m) and m.heap()==heap and pointer(m)==cache
    assert m.call(START)==1 and m.heap()==heap
    m.invariant()
    print('Flash ARM cold USB: cache allocated before pinning; read-only lookup and idempotence PASS')

def refusal(path):
    m=Buffers(path)
    m.uc.reg_write(UC_ARM_REG_IPSR,16);heap=m.heap()
    assert not prepare(m) and m.heap()==heap and not pointer(m)
    m.uc.reg_write(UC_ARM_REG_IPSR,0)
    assert m.call('24prepare_retained_buffers')==1
    capacity=m.call('_ZN13shared_memory8capacity',3)
    block=m.acquire(0,3,'USB_SCREEN',capacity);assert block
    sentinel=b'\xB7'*capacity;m.uc.mem_write(block,sentinel);heap=m.heap()
    assert not prepare(m) and m.heap()==heap and not pointer(m)
    assert m.uc.mem_read(block,capacity)==sentinel
    assert not lookup(m)
    m.release(0)
    assert prepare(m) and pointer(m)
    print('Flash ARM cache: IRQ/OOM fallback preserves live buffers; retry after release PASS')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resident-elf',type=Path,required=True)
    p.add_argument('--expect-unprepared',action='store_true')
    a=p.parse_args()
    cold(a.resident_elf,a.expect_unprepared)
    if not a.expect_unprepared:refusal(a.resident_elf)
if __name__=='__main__':main()
