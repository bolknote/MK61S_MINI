#!/usr/bin/env python3
"""Classic URQ acceptance through real USB Screen/keyboard/storage services.

Writes only /URQTEST; firmware flashing is a separate explicit action. Keys
are USB-injected matrix events, not a claim of human physical-key testing.
"""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import re
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from qst2urq import make_package
from hil_c6_system_bootstrap import write_file,read_file
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png
from hil_usb_disk_transaction import require_file_contents

DIGITS=[4,9,8,7,14,13,12,19,18,17]
OK,ESC,USER,RIGHT,DOWN,K,F,CX=37,39,35,36,28,24,29,0
WORD='Ёж ABC 123,!? ё'

def keys(p,sequence):
    for key in sequence:p.key(key)
def taps(p,digits):keys(p,[DIGITS[int(d)] for d in digits])
def wait_input(p,header,timeout=12):
    start=len(p.frames);deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        p.pump(.1)
        if len(p.frames)>start and p.frames[-1][:384]==header:return
    raise TimeoutError('URQ did not return to its input screen')
def menu(p,item,slot=None):
    p.key(USER);keys(p,[DOWN]*item+[OK])
    if slot is not None:keys(p,[DOWN]*slot+[OK])
    p.pump(.15)
def saved(p,path):
    reply=p.command('fsget "'+path+'"',timeout=45);data=bytearray()
    for offset,hexbytes in re.findall(r'(?m)^@MKC:DATA (\d+) ([0-9A-Fa-f]+)\r?$',reply):
        assert int(offset)==len(data);data.extend(bytes.fromhex(hexbytes))
    require_file_contents(reply,bytes(data))
    assert data[:6]==b'URQS\x04\0'
    assert int.from_bytes(data[28:32],'little')==binascii.crc32(data[32:])
    size=int.from_bytes(data[40:44],'little');length=int.from_bytes(data[34:36],'little')
    return bytes(data),bytes(data[48+size:48+size+length]).decode('cp1251')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--public-id',required=True)
    parser.add_argument('--apps-dir',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    root='/URQTEST';quest=root+'/input'
    source=':start\nproc внутри\nend\n:внутри\ninput имя\npln #имя$\nend\n'
    files,package=make_package(source.encode(),'dosurq','UTF-8',{'urqw_title':'Проверка ввода'})
    report={'input_source':'USB Screen virtual matrix events','physical_key_test':False,'profile':'classic-v3-uc1609'}
    with ScreenPort(args.port) as p:
        identity=p.command('identity');assert 'public='+args.public_id.upper() in identity
        report['identity']=identity;report['apps']={}
        p.command('mkdir '+root);p.command('mkdir '+quest)
        for name in ('URQ.APP','URQUI.APP'):
            data=(args.apps_dir/name).read_bytes();write_file(p,root+'/'+name,data);read_file(p,root+'/'+name,data)
            report['apps'][name]=hashlib.sha256(data).hexdigest()
        for name,data in files.items():write_file(p,quest+'/'+name,data);read_file(p,quest+'/'+name,data)
        p.attach();p.open(quest+'/game.urq');p.pump(.4)
        taps(p,'333');p.key(F);taps(p,'33330') # Ёж and space
        p.key(K);p.key(F);taps(p,'2');p.key(RIGHT);taps(p,'22');p.key(RIGHT);taps(p,'2220')
        p.key(K);taps(p,'123');p.key(K);taps(p,'11');p.key(RIGHT);taps(p,'1111');p.key(RIGHT);taps(p,'1110')
        p.key(F);taps(p,'333');p.key(RIGHT)
        # Correction must finish the active SMS character before deleting.
        taps(p,'2');p.key(CX)
        p.pump(.3);png(p.frames[-1],args.output_dir/'input.png');header=p.frames[-1][:384]
        menu(p,1,0);wait_input(p,header);png(p.frames[-1],args.output_dir/'after-save.png')
        taps(p,'2');menu(p,2,0) # discard the changed draft by restoring it
        wait_input(p,header)
        png(p.frames[-1],args.output_dir/'after-load.png')
        p.key(OK);p.pump(1);png(p.frames[-1],args.output_dir/'echo.png')
        menu(p,1,1);menu(p,5);p.key(OK);p.pump(.3)
        first,draft=saved(p,quest+'/slot1.urs');assert draft==WORD,(draft,WORD)
        assert first[48+7]==4 and int.from_bytes(first[48+32+20:48+32+22],'little')==1
        second,empty=saved(p,quest+'/slot2.urs');assert not empty and WORD.encode('cp1251') in second
        (args.output_dir/'input.urs').write_bytes(first);(args.output_dir/'echo.urs').write_bytes(second)
        report['health']={command:p.command(command,timeout=15) for command in ('df','crash show')}
        assert 'FIRMWARE CRC state=valid' in report['health']['df']
        assert 'CRASH none' in report['health']['crash show']
        p.send(0x13);p.attached=False;p.pump(.2)
    report.update(result='PASS',word=WORD,package=package)
    (args.output_dir/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Classic URQ: Ё/ё, RU/ABC/123, case, punctuation, correction, save in procedure/input, restore and echo PASS')

if __name__=='__main__':main()
