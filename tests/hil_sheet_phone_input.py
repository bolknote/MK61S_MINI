#!/usr/bin/env python3
"""Verify Russian phone input on a preinstalled SHEET.APP using USB Screen.

The chosen sheet must be saved and have one free cell in D1:P1. The test types
into that cell, saves and verifies M8/CRC, clears only that cell and verifies
that the original document bytes were restored. It then leaves the sheet open.
"""
import argparse
import binascii
import json
from pathlib import Path
import re
import struct
import time

from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort, PROMPT
from hil_portable_system_apps import png
from hil_usb_disk_transaction import require_file_contents

DIGITS = [4,9,8,7,14,13,12,19,18,17]
OK, ESC, USER, LEFT, RIGHT, UP, DOWN, K, F = 37,39,35,38,36,27,28,24,29
WORD = 'РОСТ ё ABC 123'

def document(report):
    data=bytearray()
    for offset, encoded in re.findall(r'(?m)^@MKC:DATA (\d+) ([0-9A-Fa-f]+)\r?$',report):
        assert int(offset)==len(data)
        data.extend(bytes.fromhex(encoded))
    require_file_contents(report,bytes(data))
    assert data[:4]==b'MKSH' and data[4]==1
    assert struct.unpack_from('<I',data,16)[0]==binascii.crc32(data[:16]+data[20:])
    cells={};at=20
    for _ in range(data[9]):
        position,kind,length=struct.unpack_from('<HBB',data,at);at+=4
        cells[position]=(kind,data[at:at+length].decode('cp1251'));at+=length
    assert at==len(data)
    return bytes(data),cells

def keys(port, sequence):
    for key in sequence:port.key(key)

def taps(port, digits):
    keys(port,[DIGITS[int(digit)] for digit in digits])

def open_sheet(port,path):
    start=len(port.frames);port.open(path)
    deadline=time.monotonic()+8
    while len(port.frames)==start and time.monotonic()<deadline:port.pump(.1)
    assert len(port.frames)>start,port.text[-1000:]

def move(port,position,current=0):
    delta_col=position%16-current%16;delta_row=position//16-current//16
    keys(port,[RIGHT if delta_col>0 else LEFT]*abs(delta_col))
    keys(port,[DOWN if delta_row>0 else UP]*abs(delta_row))

def save_exit(port):
    keys(port,[ESC,OK])
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        port.pump(.1)
        response=port.text[port.open_text_start:]
        if PROMPT.search(response):
            assert b'Open failed!' not in response,response
            return
    raise TimeoutError('SHEET did not save and exit')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--public-id',required=True)
    parser.add_argument('--build-id',required=True)
    parser.add_argument('--sheet',required=True)
    parser.add_argument('--selection',default='A1')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    assert '"' not in args.sheet and re.fullmatch(r'[A-P](?:[1-9]|[12][0-9]|3[0-2])',args.selection)
    selected=(ord(args.selection[0])-65)+(int(args.selection[1:])-1)*16
    args.output_dir.mkdir(parents=True,exist_ok=True)
    with ScreenPort(args.port) as port:
        try:
            identity=parse_identity(port.command('identity'))
            assert identity.public==args.public_id.upper() and identity.build==args.build_id.upper(),identity
            original,baseline=document(port.command('fsget "'+args.sheet+'"',timeout=45))
            (args.output_dir/'original.mks').write_bytes(original)
            position=next(p for p in range(3,16) if p not in baseline)
            assert len(baseline)<64
            port.attach();open_sheet(port,args.sheet);move(port,position)
            keys(port,[USER]+[RIGHT]*4+[OK,RIGHT,OK])
            # РОСТ, including С and Т on one button, then ё, Latin and digits.
            taps(port,'655566');port.key(RIGHT);taps(port,'6660')
            port.key(F);taps(port,'3330');port.pump(.15)
            png(port.frames[-1],args.output_dir/'russian-editor.png')
            port.key(K);port.key(F)
            taps(port,'2');port.key(RIGHT);taps(port,'22');port.key(RIGHT);taps(port,'2220')
            port.key(K);taps(port,'123');port.pump(.15)
            png(port.frames[-1],args.output_dir/'mixed-editor.png')
            port.key(OK);save_exit(port)
            saved,cells=document(port.command('fsget "'+args.sheet+'"',timeout=45))
            assert cells=={**baseline,position:(2,WORD)},cells
            (args.output_dir/'phone-input.mks').write_bytes(saved)
            print('Russian/ё/Latin/digits typed on device and saved as M8 with valid CRC PASS',flush=True)
            open_sheet(port,args.sheet);move(port,position)
            keys(port,[USER,RIGHT,RIGHT,RIGHT,OK]);save_exit(port)
            restored,_=document(port.command('fsget "'+args.sheet+'"',timeout=45))
            assert restored==original,'original sheet was not restored byte for byte'
            health={c:port.command(c,timeout=15) for c in ('df','crash show')}
            assert 'FIRMWARE CRC state=valid' in health['df'] and 'CRASH none' in health['crash show']
            open_sheet(port,args.sheet);move(port,selected)
            port.key(USER);port.pump(.15);assert port.frames[-1][191]==255
            port.key(ESC);port.pump(.15)
            png(port.frames[-1],args.output_dir/'sheet-open.png')
            port.send(0x13);port.attached=False;port.pump(.25)
            start=len(port.frames);port.attach_waiting()
            deadline=time.monotonic()+5
            while len(port.frames)==start and time.monotonic()<deadline:port.pump(.1)
            assert len(port.frames)>start
            png(port.frames[-1],args.output_dir/'sheet-open.png')
            port.send(0x13);port.attached=False;port.pump(.25)
            (args.output_dir/'result.json').write_text(json.dumps({'result':'PASS','sheet':args.sheet,
                'word':WORD,'original_restored':True,'left_open':True,'selection':args.selection,
                'identity':identity.__dict__,'health':health},ensure_ascii=False,indent=2)+'\n')
            print('Reopen, original sheet restoration, USER and physical display left open PASS',flush=True)
        finally:
            (args.output_dir/'terminal.txt').write_bytes(port.text)
            if port.frames:png(port.frames[-1],args.output_dir/'last-frame.png')

if __name__=='__main__':main()
