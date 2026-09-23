#!/usr/bin/env python3
"""Measure an installed ELITE on Classic V3, including every USB screen frame.

Resets the game, buys one unit of food, jumps, then returns to the title.
Uploads and removes one temporary loader; never flashes firmware or replaces
the installed game. Requires explicit --confirm-game-reset and a pinned ID.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from hil_c6_system_bootstrap import write_file, read_file
from hil_c6_programs_deploy import payload_for
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png
from hil_usb_disk_transaction import listing_entries

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/elite'))
from assembler import pack_number


class TimedScreenPort(ScreenPort):
    def __init__(self,path):
        super().__init__(path)
        self.frame_times=[]

    def receive_packet(self,encoded):
        count=len(self.frames)
        super().receive_packet(encoded)
        if len(self.frames)>count:self.frame_times.append(time.monotonic())


def indicator(frame):
    # UC1609 calculator cells occupy these four pages; RUN is above them.
    return frame[3*192:7*192]


def check_state(port,state,timeout=40):
    masks=state['frame']
    words=[sum(masks[i+j]<<(8*j) for j in range(3)) for i in range(0,12,3)]
    expected=b''.join(pack_number(v) for v in words)
    kernel=re.search(r'^hin 0000 ([0-9A-F]{48})\s*$',
                     port.command('hout 0000 24'),re.M)
    assert kernel,'cannot read ELITE kernel bank'
    def registers_match(report):
        values={int(index,16):Decimal(value).scaleb(int(exponent))
                for index,value,exponent in re.findall(
                    r'^R([0-9A-E]) =\s*([+-]?[0-9.]+)\s+([+-]?[0-9]{2})\s*$',
                    report,re.M)}
        return (len(values)==15 and
                all(values[i]==state['regs'][i] for i in range(15)) and
                re.search(r'^IP: '+str(state['pc'])+r'\s*$',report,re.M))
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        report=port.command('hout 3248 28')
        actual=b''.join(bytes.fromhex(line.split()[2]) for line in report.splitlines()
                        if re.fullmatch(r'hin \d{4} [0-9A-F]+',line))
        if actual==expected:
            report=port.command('reg')
            if registers_match(report):
                # IP is local and may match in another bank while RUN is on.
                # Argumentless hout reads the active ROM page: ELITE stops in B0.
                active=port.command('hout')
                if re.search(r'^0000 '+kernel.group(1)+r'\s*$',active,re.M):
                    port.pump(.4)
                    if registers_match(port.command('reg')):return
        port.pump(.1)
    raise AssertionError('ELITE did not reach expected frame, registers and kernel stop')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',required=True)
    ap.add_argument('--public-id',required=True)
    ap.add_argument('--build-id',required=True)
    ap.add_argument('--runner',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--confirm-game-reset',action='store_true')
    args=ap.parse_args()
    if not args.confirm_game_reset:ap.error('pass --confirm-game-reset')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    actions=[('new-game','0'),('credits','1'),('buy-food','30'),('cargo','20'),
             ('destination','71'),('distance','9'),('jump','60')]
    commands=['run']+['input '+code for _,code in actions]
    result=subprocess.run([str(args.runner),str(ROOT/'programs/games/ELITE')],
                          input='\n'.join(commands)+'\n',text=True,capture_output=True,
                          check=True,timeout=30)
    states=[json.loads(line) for line in result.stdout.splitlines()]
    temporary='/games/ELITE/_bench.m61'
    loader=(ROOT/'programs/games/ELITE/autoexec.m61').read_text().replace('open? manual.md\n','')
    measurements=[]
    with TimedScreenPort(args.port) as port:
        ident=parse_identity(port.command('identity'))
        assert ident.public==args.public_id.upper() and ident.build==args.build_id.upper(),ident
        assert ident.profile=='classic-v3-uc1609',ident
        entries=listing_entries(port.command('ls /games/ELITE'))
        assert not any(e.split('\t')[-1].casefold()=='_bench.m61' for e in entries)
        for path in sorted((ROOT/'programs/games/ELITE').iterdir()):
            if path.is_file():read_file(port,'/games/ELITE/'+path.name,payload_for(path))
        print('Installed files match local sources.',flush=True)
        write_file(port,temporary,loader.encode('ascii'))
        loader_exists=True
        try:
            port.command('open '+temporary)
            check_state(port,states[0])
            # DETACH keeps the USB Screen session waiting for reconnection.
            # Its overlay lease prevents C6 from acquiring the staging index
            # for a catalog mutation. Remove our loader before attaching.
            removed=port.command('rm "'+temporary+'"')
            assert 'Removed 1 entry.' in removed,removed
            assert not any('_bench.m61' in e for e in listing_entries(port.command('ls /games/ELITE')))
            loader_exists=False
            port.attach();port.pump(.5)
            assert port.frames,'USB screen returned no frames'
            png(port.frames[-1],args.output_dir/'title.png')
            for (name,code),state in zip(actions,states[1:]):
                before=indicator(port.frames[-1])
                port.command('cmd 0D')
                for digit in code:port.command('cmd 0'+digit)
                port.pump(.2)
                assert indicator(port.frames[-1])==before,'input changed the held display'
                start_frame=len(port.frames);started=time.monotonic()
                port.command('cmd 50')
                check_state(port,state)
                frames=port.frames[start_frame:]
                changes=[before]
                for frame in frames:
                    if indicator(frame)!=changes[-1]:changes.append(indicator(frame))
                png(port.frames[-1],args.output_dir/(name+'.png'))
                expected_change=state['frame']!=states[len(measurements)]['frame']
                assert len(changes)==1+int(expected_change),(name,len(changes)-1)
                appeared=next((t for f,t in zip(frames,port.frame_times[start_frame:])
                               if indicator(f)==changes[-1]),time.monotonic())
                measurement={'action':name,'seconds_to_frame':round(appeared-started,3),
                             'indicator_changes':len(changes)-1,'core_steps':state['steps']}
                measurements.append(measurement)
                print(json.dumps(measurement),flush=True)
            health=port.command('df')
            assert 'FIRMWARE CRC state=valid' in health,health
            assert 'CRASH none' in port.command('crash show')
            # Exercise the normal loader and dismiss its opening manual.
            port.open('/games/ELITE/autoexec.m61')
            port.pump(.5)
            port.close_app()
            check_state(port,states[0])
        finally:
            if port.attached:port.send(0x13);port.pump(.3)
            if loader_exists:
                port.command('rm "'+temporary+'"')
                assert not any('_bench.m61' in e for e in listing_entries(port.command('ls /games/ELITE')))
    (args.output_dir/'measurements.json').write_text(json.dumps(measurements,indent=2)+'\n')
    print('ELITE HIL passed; returned to title, temporary loader removed.',flush=True)


if __name__=='__main__':main()
