#!/usr/bin/env python3
"""Preserve the user-selected 8-QUEEN algorithm while reducing ROM work."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PROGRAM=ROOT/'programs/examples/8 Queens optimized.m61'
# Unchanged opcode payloads of the two user-supplied baseline files.
BASELINES={
    '8-queen_anv (1).m61': bytes.fromhex(
        '0D495E14690110490911574608B969400160115C02D9D011'
        '57342221691160105E16D90111B95E14690111495C3450514000'),
    '8-QUEEN.m61': bytes.fromhex(
        '0D4B09400DB0605E044C6C01104C08BC6B01104B6C4D6D01'
        '11575659564DDCDD115742316C6D11115E22004BDC0111BC'
        '5E226C01114C51446B01115E166C08115E105000'),
}

def reference_model():
    # The flag-based algorithm of the supplied 8-QUEEN.m61, not Pascal qbench.
    a=[0]*9
    x=0;flag=0
    events=[]
    while True:
        x+=1;a[x]=8
        events.append(['write',x,a[x]])
        while True:
            flag+=1
            events.append(['flag',flag])
            y=x
            events.append(['reset_y',x,y])
            while True:
                events.append(['while_y',x,y,y>1])
                if y<=1:break
                y-=1;t=a[x]-a[y]
                events.append(['pair',x,y,a[x],a[y]])
                if t==0 or x-y==abs(t):
                    flag=0
                    events.append(['flag',flag])
                    a[x]-=1
                    events.append(['write',x,a[x]])
                    while True:
                        events.append(['while_a',x,a[x],a[x]==0])
                        if a[x]!=0:break
                        x-=1;a[x]-=1
                        events.append(['write',x,a[x]])
            events.append(['until_flag',flag,flag==1])
            if flag==1:break
        events.append(['until_x',x,x==8])
        if x==8:break
    assert a[1:]==[8,4,1,3,6,2,7,5]
    return events,a[1:]

def run(runner,path,mode=None):
    output=subprocess.check_output([str(runner),str(path)]+([mode] if mode else []),text=True)
    lines=output.splitlines()
    report=json.loads(lines[-1])
    assert not report['running'] and not report['error'],report
    return report,[json.loads(line[2:]) for line in lines[:-1]]

def assert_trace(expected,actual):
    for index,(wanted,got) in enumerate(zip(expected,actual)):
        assert wanted==got,('trace mismatch',index,wanted,got)
    assert len(expected)==len(actual),(len(expected),len(actual))

def main():
    runner=Path(sys.argv[1])
    code=b''.join(bytes.fromhex(line.split()[2]) for line in PROGRAM.read_text().splitlines()
                  if line.startswith('hin '))
    assert code[:21]==BASELINES['8-QUEEN.m61'][:21], 'Initialization was changed'
    actual,events=run(runner,PROGRAM,'trace')
    expected,board=reference_model()
    assert_trace(expected,events)
    counts=dict(Counter(event[0] for event in events))
    assert counts['pair']==1436 and counts['write']==540,counts
    nonzero=sum(event[0]=='write' and event[2]!=0 for event in events)
    assert nonzero==484,nonzero
    assert actual['regs'][1:9]==board and actual['x']==0,actual
    results={'optimized':actual}
    with tempfile.TemporaryDirectory(prefix='mk61-qbench-') as directory:
        for name,code in BASELINES.items():
            path=Path(directory)/name
            path.write_text('reinit\n'+''.join(
                f'hin {at:04} {code[at:at+24].hex().upper()}\n'
                for at in range(0,len(code),24))+'run\n')
            baseline,baseline_events=run(runner,path,'reference' if name=='8-QUEEN.m61' else None)
            assert baseline['regs'][1:9]==board,baseline
            assert actual['core_steps']<baseline['core_steps'],(name,actual,baseline)
            if name=='8-QUEEN.m61':
                assert_trace(expected,baseline_events)
                assert_trace(baseline_events,events)
                assert actual['regs']==baseline['regs'] and actual['x']==baseline['x']
                assert actual['ip']==baseline['ip']==67
            results[name]=baseline
    report={
        'method':'Stock 105-step MK-61 ROM execution; core.step counts, not physical milliseconds',
        'program_sha256':hashlib.sha256(PROGRAM.read_bytes()).hexdigest(),
        'reference':'Unchanged user-supplied 8-QUEEN.m61; flag-based search',
        'trace_counts':counts,'trace_matches_reference_and_model':True,
        'trace_sha256':hashlib.sha256(json.dumps(events,separators=(',',':')).encode()).hexdigest(),
        'board':board,'nonzero_candidates':nonzero,'results':results,
    }
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
