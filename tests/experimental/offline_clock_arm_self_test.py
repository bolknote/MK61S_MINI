#!/usr/bin/env python3
import sys,runpy
from pathlib import Path
elf=Path(sys.argv[1]);sys.argv=['stm32-runtime',str(elf),'--mcu','f411']
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=runpy.run_path(str(Path(__file__).resolve().parents[1]/'stm32f4_runtime_arm_self_test.py'))
call,get=m['call'],m['get'];rcc=m['RCC'];clock=m['core_clock']
for mhz in (96,120,132,138,144,96):
 assert call('offline_clock_set',mhz)==1
 assert get(clock)==mhz*1000000
 pll=get(rcc+4);cfgr=get(rcc+8)
 assert pll&63==25 and (pll>>6)&511==mhz*2 and (pll>>16)&3==0 and (pll>>24)&15==6
 assert (cfgr>>4)&15==0 and (cfgr>>10)&7==5 and (cfgr>>13)&7==4
 assert call('offline_clock_set',0)==1 and get(clock)==96000000
 assert ((get(rcc+4)>>6)&511)//((get(rcc+4)>>24)&15)==48
 print('OfflinePLL',mhz,'USB off plan and USB48 return ARM PASS')
assert call('offline_clock_set',131)==0
