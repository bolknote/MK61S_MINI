#!/usr/bin/env python3
"""Qualify Classic URQ graphics, arrows, handoff and a saved Russian draft.

Uses the real board/display/storage with USB matrix events. This does not
claim manual physical-button testing. Writes only /URQTEST.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png
from hil_c6_system_bootstrap import write_file,read_file
from hil_urq import saved,taps,OK,ESC,USER,RIGHT,F
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.apps.urq.qst2urq import make_package

LEFT,UP,DOWN=38,27,28


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--public-id',required=True)
    p.add_argument('--apps-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--installed',action='store_true')
    a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    source=(':s\npln Вы вошли в подземелье.\npln На двери древняя надпись.\nbtn ask, '+
            'Осмотреть старую дверь, внимательно изучить надпись и попытаться прочитать её. '*4+
            '\nbtn done, Выйти во двор\nend\n:ask\nproc name\nend\n:name\ninput имя\npln #имя$\nend\n:done\nquit\n')
    files,_=make_package(source.encode(),'urqw','UTF-8')
    report={'physical_key_test':False,'input_source':'USB Screen matrix events','screens':{},'apps':{}}
    with ScreenPort(a.port) as port:
        identity=port.command('identity');assert 'public='+a.public_id.upper() in identity;report['identity']=identity
        port.command('mkdir /URQTEST');port.command('mkdir /URQTEST/ui')
        for name in ('URQ.APP','URQUI.APP'):
            print('Uploading '+name,flush=True);data=(a.apps_dir/name).read_bytes()
            if not a.installed:write_file(port,'/URQTEST/'+name,data)
            read_file(port,'/URQTEST/'+name,data)
            report['apps'][name]=hashlib.sha256(data).hexdigest()
        for name,data in files.items():
            if not a.installed:write_file(port,'/URQTEST/ui/'+name,data)
        port.attach();port.open('/URQTEST/ui/game.urq')

        def wait(after,predicate,timeout=15):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                if len(port.frames)>after and predicate(port.frames[-1]):return port.frames[-1]
                port.pump(.05)
            raise TimeoutError('Expected a new URQ screen')
        def canonical(frame):
            # disk_activity::Overlay covers 16x16 pixels over two pages.
            return frame[:176]+bytes(16)+frame[192:368]+bytes(16)+frame[384:]
        def changed(key):
            port.pump(.1)
            before=len(port.frames);old=port.frames[-1];port.key(key)
            wait(before,lambda frame:canonical(frame)!=canonical(old));port.pump(.2)
            return port.frames[-1]
        def shot(name):
            port.pump(.6)
            png(port.frames[-1],a.output_dir/(name+'.png'))
            report['screens'][name]=hashlib.sha256(port.frames[-1]).hexdigest()
        wait(0,lambda frame:any(frame));port.pump(.4);shot('story')
        first=changed(OK);shot('actions')
        assert canonical(changed(RIGHT))!=canonical(first);shot('long-action')
        assert canonical(changed(LEFT))==canonical(first)
        for _ in range(18):port.key(RIGHT)
        shot('second-action');changed(LEFT)
        menu=changed(USER);shot('menu')
        assert canonical(changed(RIGHT))!=canonical(menu);shot('save-selected')
        changed(DOWN);changed(UP);assert canonical(changed(LEFT))==canonical(menu)
        # The confirming OK gesture must not select a game action as well.
        before=len(port.frames);port.send(0x30,bytes((OK,1)));port.pump(.7)
        wait(before,lambda frame:canonical(frame)==canonical(first));port.pump(.3)
        assert canonical(port.frames[-1])==canonical(first)
        port.send(0x30,bytes((OK,0)));port.pump(.1)
        changed(OK);shot('empty-input')
        taps(port,'333');port.key(F);taps(port,'3333');port.key(RIGHT);port.pump(.2)
        draft=port.frames[-1];shot('russian-input')
        changed(USER);changed(RIGHT);changed(OK);changed(OK);port.key(RIGHT)
        wait(0,lambda frame:canonical(frame)==canonical(draft))
        taps(port,'2');changed(USER);changed(RIGHT);changed(RIGHT);changed(OK);changed(OK);port.key(RIGHT)
        wait(0,lambda frame:canonical(frame)==canonical(draft));shot('restored-input')
        changed(ESC);changed(ESC);assert canonical(port.frames[-1])==canonical(draft)
        changed(USER)
        for _ in range(5):port.key(RIGHT)
        changed(OK);changed(OK);port.pump(.2)
        image,text=saved(port,'/URQTEST/ui/slot1.urs');assert text=='Ёж',text
        (a.output_dir/'input.urs').write_bytes(image)
        report['health']={c:port.command(c,timeout=15) for c in ('df','crash show')}
        assert 'CRASH none' in report['health']['crash show']
        port.send(0x13);port.attached=False;port.pump(.15)
    report['result']='PASS';(a.output_dir/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Classic URQ UI: story/actions/menu distinction, top arrows + step keys, long captions, held OK, Russian draft save/restore PASS')


if __name__=='__main__':main()
