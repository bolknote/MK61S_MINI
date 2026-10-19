#!/usr/bin/env python3
"""Install High Noon on an exact Pico UID and play its production M61 driver.

Back up replaced game files, read every installed byte back, exercise real RNG
duels through the reward receipt, and restore calculator data in finally.
No firmware flashing or RNG seeding. Requires explicit --install.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import re
import time
import zlib
from pathlib import Path

from hil_c5_stack import read_file,write_file
from hil_high_noon_vm import Game,GameFont,ROOT
from hil_picocalc_apps import AppsPort
from hil_picocalc_software import calculator,restore
from hil_picocalc_turochamp import healthy,stop
from hil_portable_system_apps import png


class PicoGame(Game):
    def save(self,name):
        super().save(name)
        if name!='reward-receipt':return
        frame=self.port.frames[-1];rows=bytearray(12800)
        for y in range(320):
            for x in range(320):
                if frame[y//8*320+x]&(1<<(y&7)):rows[y*40+x//8]|=0x80>>(x&7)
        wanted=f'{zlib.crc32(rows):08X}'
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            status=self.port.status()
            if 'LCD_PENDING=0 ' in status and 'LCD_FRAME_CRC='+wanted in status:
                self.result['receipt_lcd_source_crc']=wanted
                return
        raise AssertionError(('LCD source snapshot differs from receipt',wanted,status))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid','build-id'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--directory',default='/games/High Noon')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--attempts',type=int,default=12)
    ap.add_argument('--install',action='store_true',required=True)
    args=ap.parse_args()
    assert re.fullmatch(r'[0-9A-Fa-f]{16}',args.uid)
    assert re.fullmatch(r'[0-9A-Fa-f]{8}',args.build_id)
    assert args.directory.startswith('/') and '"' not in args.directory and '..' not in args.directory.split('/')
    assert 1<=args.attempts<=20
    args.output.mkdir(parents=True,exist_ok=False)
    local=ROOT/'programs/games/High Noon'
    payloads={p.name:p.read_bytes() for p in sorted(local.iterdir()) if p.is_file()}
    face=GameFont(payloads['HighNoon320.FMK'],frame_width=320,left=0,top=40,columns=40)
    result=dict(status='RUNNING',uid=args.uid.upper(),build=args.build_id.upper(),
                recorded_at_utc=datetime.now(timezone.utc).isoformat(),directory=args.directory,
                checks=[],screens=[],register_reports=[],native_geometry=[320,320],
                text_cell=[8,24],columns=40,firmware_writes=0,rng_seeded=False)
    before=None;installed=False;replaced={};new=[];created=[]
    with AppsPort(args.port,keyboard_layout=0) as p:
        p.native_display=True;p.commands()
        assert 'UID='+args.uid.upper() in p.command('identity')
        calculator(p);initial=p.status();healthy(initial,args.build_id.upper())
        p.expect('SERVICE=CLOSED','DIRTY=0','M61_ACTIVE=0','RUN=0 BUSY=0')
        if 'SLEEP=1' in initial:p.command('display on')
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        (args.output/'before.json').write_text(json.dumps(before,indent=2)+'\n')
        game=PicoGame(p,face,args.directory,args.output,result)
        try:
            parent='/'
            for component in args.directory.strip('/').split('/'):
                listing=p.command('ls "'+parent+'"')
                path=parent.rstrip('/')+'/'+component
                if not any(line.casefold()=='d\t'+component.casefold()+'/' for line in listing.splitlines()):
                    assert 'ERROR' not in p.command('mkdir "'+path+'"')
                    created.append(path)
                parent=path
            listing=p.command('ls "'+args.directory+'"')
            assert 'ERROR' not in listing and 'not found' not in listing.lower(),listing
            names={line.split('\t')[-1].strip().casefold() for line in listing.splitlines() if line.startswith('f\t')}
            backup=args.output/'previous-game';backup.mkdir()
            for name in payloads:
                path=args.directory+'/'+name
                if name.casefold() in names:
                    replaced[name]=read_file(p,path);(backup/name).write_bytes(replaced[name])
                else:new.append(name)
            # Publish the dispatcher last, after its font and all BASIC parts.
            for name in sorted(payloads,key=lambda n:n=='autoexec.m61'):
                path=args.directory+'/'+name
                if replaced.get(name)!=payloads[name]:write_file(p,path,payloads[name])
                assert read_file(p,path)==payloads[name],name
            installed=True
            result['files']={n:dict(bytes=len(d),sha256=hashlib.sha256(d).hexdigest()) for n,d in payloads.items()}
            result['checks'].append('complete-game-installed-and-read-back-byte-for-byte')
            print('Installed and verified all High Noon files',flush=True)
            p.command('uscreen on');p.attach_waiting()
            game.instructions_surrender();game.escape();game.victory(args.attempts)
            result['after']=p.status();healthy(result['after'],args.build_id.upper())
            assert 'FONT=0 ' in result['after'] and 'M61_ACTIVE=0 ' in result['after'],result['after']
            for name,data in payloads.items():assert read_file(p,args.directory+'/'+name)==data,name
            result['checks'].append('game-files-unchanged-after-play')
            result['status']='PASS'
        except BaseException as error:
            result.update(status='FAIL',error=repr(error))
            if p.frames:png(p.frames[-1],args.output/'failure.png')
            raise
        finally:
            try:
                stop(p)
                if result['status']!='PASS':
                    for name,data in replaced.items():write_file(p,args.directory+'/'+name,data)
                    for name in new:
                        listing=p.command('ls "'+args.directory+'"')
                        if any(line.casefold().endswith('\t'+name.casefold()) for line in listing.splitlines()):
                            assert 'ERROR' not in p.command('rm "'+args.directory+'/'+name+'"')
                    for path in reversed(created):assert 'ERROR' not in p.command('rm "'+path+'"')
                    result['original_game_restored']=True
                p.command('cd "'+re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]+'"')
                restore(p,before)
                program=re.findall(r'(?m)^\d{4} [0-9A-F]{2}\r?$',before['dump'])
                assert program and re.findall(r'(?m)^\d{4} [0-9A-F]{2}\r?$',p.command('dump'))==program
                result['calculator_state_restored']=True
                if p.attached:p.send(0x13);p.attached=False;p.pump(.2)
                p.command('uscreen off' if 'USB_SCREEN=OFF ' in initial else 'uscreen on')
                result['final']=p.status();healthy(result['final'],args.build_id.upper())
            except BaseException as error:result.update(status='FAIL',cleanup_error=repr(error))
            result['frames_crc_verified']=len(p.frames)
            result['updated_game_retained']=installed and result['status']=='PASS'
            (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            (args.output/'terminal.bin').write_bytes(p.text)
    assert result['status']=='PASS',result
    print('High Noon PicoCalc PASS: instructions, inputs, duel, exact receipt and data restoration',flush=True)


if __name__=='__main__':main()
