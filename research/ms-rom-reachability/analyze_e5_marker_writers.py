#!/usr/bin/env python3
"""Exact emitters of the E5 marker-test field M22 in the three original ROMs.

Inspection of all 768 control words selects physical order-24 emitters at
tick 22. The following symbolic checks classify their complete ALU outputs.
Arbitrary-state F production is not a keyboard-reachability claim.
"""
import json
from pathlib import Path
import runpy
import subprocess
from z3 import sat, unsat

ROOT=Path(__file__).resolve().parent
EXPECTED={
    'ИК1302':{0x32:'R21',0xA8:'R21',0xBC:'R19',0xC7:'R21',0xE7:'R21',0xE9:'R21'},
    'ИК1303':{0x2A:'R21',0x3A:'ST21',0x4E:'R21',0xD8:'R21',0xDE:'R21'},
    'ИК1306':{0xFF:'R21'},
}


def analyze():
    first=runpy.run_path(str(ROOT/'ik1302_symbolic.py'))
    roms=json.loads(subprocess.check_output(['node','-e',
        'console.log(JSON.stringify(require(process.argv[1])))',str(first['ROM_PATH'])],text=True))
    results={}
    for chip in ('ИК1302','ИК1303','ИК1306'):
        q=runpy.run_path(str(ROOT/'ik1302_symbolic.py'))
        tables=roms[chip]
        q['execute_command'].__globals__.update(COMMANDS=tables['команды'],
            SYNCS=tables['синхропрограммы'],MICROS=tables['микрокоманды'])
        emitters=[]
        for ip,word in enumerate(tables['команды']):
            # Tick 22 uses the FIRST sync program, j=22 mod 9=4.
            micro=tables['синхропрограммы'][(word&127)*9+4]&63
            choices=[micro] if micro<60 else [2*(micro-60)+60,2*(micro-60)+61]
            if any(tables['микрокоманды'][i]&(1<<20) for i in choices):
                emitters.append(ip)
        rows={}
        assert set(emitters)==set(EXPECTED[chip]),('complete M22 writer inventory',chip)
        print(chip,'M22 emitters:',','.join(f'{ip:02X}' for ip in emitters),flush=True)
        for ip in emitters:
            a=q['State'](f'e5_writer_{chip}_{ip}');out=[]
            b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'e5_writer_keys_{chip}_{ip}'),
                                   emitted_outputs=out)
            p=q['base_solver'](a,ip);assert p.check()==sat
            inputs=[(prefix+str(i),x) for prefix,values in [('R',a.r),('M',a.m),('ST',a.st)]
                    for i,x in enumerate(values)]+[('S',a.s),('S1',a.s1)]
            source=None
            for label,value in inputs:
                p.push();p.add(out[22]!=value);same=p.check()==unsat;p.pop()
                if same:source=label;break
            p.push();p.add(out[22]==15,a.m[22]!=15);creates_f=p.check()==sat;p.pop()
            p.push();values=q['possible_values'](out[22],p,17);p.pop()
            assert source==EXPECTED[chip][ip],('exact entry-tetra source',chip,ip,source)
            assert creates_f and set(values)==set(range(16)),('arbitrary-state output range',chip,ip)
            rows[ip]={'a':a,'b':b,'out':out,'model':q,'source':source,'creates_f':creates_f,
                      'values':values}
            print(f'  {ip:02X}: {source or "computed"}; values '+','.join(f'{v:X}' for v in values)
                  +('; can create F' if creates_f else '; cannot create F'),flush=True)
        results[chip]=rows
    return results


if __name__=='__main__':
    analyze()
