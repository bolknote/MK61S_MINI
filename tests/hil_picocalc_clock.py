#!/usr/bin/env python3
"""Set local RTC through a RAM-only M61 editor and verify alarm wake on Pico H."""
import argparse
from datetime import datetime
import json
import hashlib
from pathlib import Path
import re
import time
from hil_picocalc_runtime import Pico

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with Pico(args.port) as p:
        p.log_output=args.output
        initial=p.expect('SERVICE=CLOSED','UI=CALCULATOR','X_RAW=[')
        if 'SLEEP=1' in initial: p.step(b' ','SLEEP=0')
        expected_x=re.search(r'X_RAW=\[([^\]]+)\]',initial).group(1)
        p.menu(3);p.step(b'\x82','SERVICE=PROMPT')
        name='CLOCK-TEST-'+time.strftime('%H%M%S')+'.m61'
        p.step(b'\x08'*7+name.encode()+b'\r','SERVICE=EDITOR','SOURCE=0','DIRTY=1')
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        source=f'date {now}\nalarm a in 10\nret\n'
        p.step(source.encode(),f'SOURCE={len(source)}','DIRTY=1');p.raw(b'\x83');p.pump(.5)
        p.expect('M61_ACTIVE=0','SERVICE=EDITOR','RTC_SET=1')
        assert b'ALARM OK' in p.text and b'Unknown command' not in p.text
        # Discard only this newly created unsaved RAM document.
        p.step(b'\x1b','SERVICE=CONFIRM');p.step(b'\r','DIRTY=0')
        for _ in range(3):
            if 'SERVICE=CLOSED' in p.status(): break
            p.raw(b'\x1b');p.pump(.2)
        p.expect('SERVICE=CLOSED','DIRTY=0')
        # Running a script selects the calculator page itself.
        if 'UI=CALCULATOR' not in p.status(): p.step(b'\t','UI=CALCULATOR')
        p.system(7,'SLEEP=1');asleep=p.expect('SLEEP=1','LCD_BKL=0','X_RAW=[')
        start=len(p.text);p.pump(10.5)
        final=p.expect('SLEEP=0','LCD_BKL=240','KBD_BKL=40','RTC_SET=1','X_RAW=[')
        assert b'RTC_ALARM=A' in p.text[start:]
        assert re.search(r'X_RAW=\[([^\]]+)\]',asleep).group(1)==expected_x
        assert re.search(r'X_RAW=\[([^\]]+)\]',final).group(1)==expected_x
        (args.output/'result.json').write_text(json.dumps({'uf2_sha256':hashlib.sha256((Path(__file__).resolve().parents[1]/'binary/picocalc-pico-h/mk61s-picocalc-pico-h.uf2').read_bytes()).hexdigest(),'source':source,'asleep':asleep,'final':final,
            'initial':initial,'preserved_x':expected_x,
            'cases':['M61 date sets local RTC','M61 alarm A in 10 seconds','unsaved editor discarded without SD write',
                     'alarm wakes display and both backlights from sleep','arbitrary initial X preserved through the script and alarm wake']},indent=2)+'\n')
        print('PASS RTC date/alarm M61 commands, RAM editor restore, alarm sleep/wake',flush=True)
if __name__=='__main__':main()
