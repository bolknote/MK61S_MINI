#!/usr/bin/env python3
"""Qualify native ELIZA pixels, editing and pagination on an exact Pico UID.

--install replaces only the selected ELIZA.APP after backing it up. On failure
the previous APP is restored. Calculator data and USB Screen mode are restored.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

from hil_c5_stack import read_file,write_file
from hil_picocalc_apps import AppsPort
from hil_picocalc_software import calculator,restore
from hil_picocalc_turochamp import healthy,stop
from hil_picocalc_display import lcd_crc
from hil_portable_system_apps import png

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from generate_ui_fonts import load_atlases


class ElizaFont:
    """Reference composition from reviewed Ark JSON, independent of APP code."""
    def __init__(self):self.atlas=load_atlases()[0][2]
    def width(self,text):return sum(self.atlas['by_codepoint'][ord(c)]['advance'] for c in text)
    def paint(self,frame,text,x,baseline):
        for char in text:
            g=self.atlas['by_codepoint'][ord(char)]
            for dy,row in enumerate(g['rows']):
                for dx,bit in enumerate(row):
                    if bit=='1':
                        px=x+g['safe_bearing_x']+dx;py=baseline-g['bearing_y']+dy
                        assert 0<=px<320 and 0<=py<320
                        frame[py//8*320+px]|=1<<(py%8)
            x+=g['advance']
    def matches(self,frame,text,x,baseline):
        expected=bytearray(12800);self.paint(expected,text,x,baseline)
        width=self.width(text)
        return all(bool(frame[y//8*320+px]&(1<<(y%8)))==bool(expected[y//8*320+px]&(1<<(y%8)))
                   for y in range(baseline-14,baseline+3) for px in range(x,x+width))
    def header(self,frame,label):return self.matches(frame,label,316-self.width(label),20)
    def wrap(self,text):
        lines=[];line=''
        for word in text.split():
            if line and self.width(line+' '+word)<=304:line+=' '+word;continue
            if line:lines.append(line);line=''
            while self.width(word)>304:
                at=1
                while self.width(word[:at+1])<=304:at+=1
                lines.append(word[:at]);word=word[at:]
            line=word
        if line:lines.append(line)
        return lines
    def page(self,frame,lines):
        if not self.header(frame,'REPLY'):return False
        expected=bytearray(12800)
        for row,line in enumerate(lines):self.paint(expected,line,8,54+24*row)
        return frame[5*320:38*320]==expected[5*320:38*320]
    def editor(self,frame,text,cursor=None):
        if not self.header(frame,'YOU'):return False
        if cursor is None:cursor=len(text)
        positions=[];x=row=0
        for char in text+' ':
            advance=self.width(char)
            if x+advance>304:x=0;row+=1
            positions.append((x,row,advance));x+=advance
        cx,cy,cw=positions[cursor];first=max(0,cy-10)
        expected=bytearray(12800)
        for char,(x,row,advance) in zip(text,positions):
            if first<=row<first+11:self.paint(expected,char,8+x,54+24*(row-first))
        y=40+24*(cy-first)+19
        for x in range(8+cx,8+cx+cw):expected[y//8*320+x]|=1<<(y%8)
        return frame[5*320:38*320]==expected[5*320:38*320]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid','build-id'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--app',type=Path,required=True)
    ap.add_argument('--directory',default='/MK61S-PicoCalc-0.8')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--install',action='store_true',required=True)
    args=ap.parse_args();assert re.fullmatch(r'[0-9A-Fa-f]{16}',args.uid)
    assert re.fullmatch(r'[0-9A-Fa-f]{8}',args.build_id)
    assert args.directory.startswith('/') and '"' not in args.directory and '..' not in args.directory.split('/')
    args.output.mkdir(parents=True,exist_ok=False);path=args.directory+'/ELIZA.APP'
    font=ElizaFont();data=args.app.read_bytes();old=None;before=None
    result=dict(passed=False,uid=args.uid.upper(),build=args.build_id.upper(),directory=args.directory,
                app_sha256=hashlib.sha256(data).hexdigest(),font='Ark Pixel 16 native',
                recorded_at_utc=datetime.now(timezone.utc).isoformat(),cases=[],screens={},firmware_writes=0)
    with AppsPort(args.port,keyboard_layout=0) as p:
        p.native_display=True;p.commands();assert 'UID='+args.uid.upper() in p.command('identity')
        calculator(p);initial=p.status();healthy(initial,args.build_id.upper())
        p.expect('SERVICE=CLOSED','DIRTY=0','M61_ACTIVE=0','RUN=0 BUSY=0')
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        (args.output/'before.json').write_text(json.dumps(before,indent=2)+'\n')
        def shot(name,predicate):
            start=len(p.frames);p.pump(.2);p.send(0x16);deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                p.pump(.04)
                if len(p.frames)>start and predicate(p.frames[-1]):break
            else:
                if p.frames:png(p.frames[-1],args.output/'failure.png')
                raise AssertionError('Missing ELIZA frame: '+name)
            frame=p.frames[-1];png(frame,args.output/(name+'.png'))
            (args.output/(name+'.bin')).write_bytes(frame)
            result['screens'][name]=hashlib.sha256(frame).hexdigest();return frame
        def passed(name):result['cases'].append(name);print('PASS '+name,flush=True)
        def type_text(text):
            os.write(p.fd,b'\x1e')
            for at in range(0,len(text),8):
                os.write(p.fd,text[at:at+8].encode('ascii'));p.pump(.16)
        def intro():
            start=len(p.text);p.open(path);p.expect('RUNTIME=APP')
            shot('intro-keys',lambda f:font.matches(f,'QWERTY OR SMS NUMBER KEYS',
                 (320-font.width('QWERTY OR SMS NUMBER KEYS'))//2,60))
            p.key(29)
            shot('intro-start',lambda f:font.matches(f,'HOW DO YOU DO?',
                 (320-font.width('HOW DO YOU DO?'))//2,65))
            p.key(29);shot('editor-empty',lambda f:font.editor(f,''));return start
        def ended(start):
            p.wait_text(b'APP_FLOW_RESULT=0',start,timeout=20);calculator(p)
            p.expect('RUNTIME=NONE','SERVICE=CLOSED');healthy(p.status(),args.build_id.upper())
        try:
            old=read_file(p,path);(args.output/'previous-ELIZA.APP').write_bytes(old)
            write_file(p,path,data);assert read_file(p,path)==data
            p.command('uscreen on');p.attach_waiting()
            start=intro();type_text('hellp');p.key(0);type_text('o')
            shot('editor-hello',lambda f:font.editor(f,'hello'))
            p.key(34);shot('cursor-left',lambda f:font.editor(f,'hello',4))
            p.key(24);shot('cursor-right',lambda f:font.editor(f,'hello',5))
            p.key(29)
            reply='HOW DO YOU DO. PLEASE STATE YOUR PROBLEM'
            shot('reply-hello',lambda f:font.page(f,font.wrap(reply)))
            passed('native help, QWERTY edit/backspace/arrows and complete HELLO response')
            p.key(29);shot('editor-next',lambda f:font.editor(f,''))
            text='I WANT '+'W'*504;assert len(text)==511
            type_text(text);shot('editor-511',lambda f:font.editor(f,text))
            p.key(29)
            lines=font.wrap('WHAT WOULD IT MEAN TO YOU IF YOU GOT '+'W'*504)
            pages=[lines[i:i+11] for i in range(0,len(lines),11)]
            assert len(pages)>1;result['reply_pages']=len(pages);result['input_bytes']=len(text)
            for index,lines in enumerate(pages):
                frame=shot('reply-long-'+str(index+1),lambda f,lines=lines:font.page(f,lines))
                wanted=lcd_crc(frame);deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    status=p.status()
                    if 'LCD_PENDING=0 ' in status and 'LCD_FRAME_CRC='+wanted in status:break
                else:raise AssertionError('LCD source snapshot differs from ELIZA page')
                p.key(29)
            passed('511-byte wide-letter input, cursor scrolling and every reply page matched native pixels')
            shot('editor-before-bye',lambda f:font.editor(f,''));type_text('bye');p.key(29)
            shot('goodbye',lambda f:font.page(f,font.wrap('GOODBYE. IT WAS NICE TALKING TO YOU.')))
            p.key(29);ended(start)
            passed('goodbye and clean return with graphics/workspace released')
            start=intro();type_text('cancel');p.key(39);ended(start)
            passed('second launch and Escape during text input')
            assert read_file(p,path)==data;result['passed']=True
        finally:
            try:
                stop(p)
                if not result['passed'] and old is not None:write_file(p,path,old);result['original_app_restored']=True
                p.command('cd "'+re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]+'"');restore(p,before)
                program=re.findall(r'(?m)^\d{4} [0-9A-F]{2}\r?$',before['dump'])
                assert program and re.findall(r'(?m)^\d{4} [0-9A-F]{2}\r?$',p.command('dump'))==program
                result['calculator_state_restored']=True
                if p.attached:p.send(0x13);p.attached=False;p.pump(.2)
                p.command('uscreen off' if 'USB_SCREEN=OFF ' in initial else 'uscreen on')
                result['final']=p.status();healthy(result['final'],args.build_id.upper())
                for label in ('UI_FONT_FAMILY','UI_FONT_SIZE','UI_FONT_KEY'):
                    assert re.search(label+r'=\w+',initial)[0]==re.search(label+r'=\w+',result['final'])[0]
            except BaseException as error:result.update(passed=False,cleanup_error=repr(error))
            result['frames_crc_verified']=len(p.frames)
            (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            (args.output/'terminal.bin').write_bytes(p.text)
    assert result['passed'],result
    print('ELIZA PicoCalc PASS',flush=True)


if __name__=='__main__':main()
