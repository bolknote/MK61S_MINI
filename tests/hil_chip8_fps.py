#!/usr/bin/env python3
"""Prepare/run one finite stock-clock Classic CHIP8 FPS phase. No flashing.

--prepare only freezes local payloads. --run requires a separate coordinator
grant for that phase SHA/identity and an idle calculator. No other board is
opened. The phase owns only /C8Bench1108 and removes it before releasing CDC.
"""
import argparse,hashlib,json,re,time
from pathlib import Path
from hil_classic_cdc_guard import current_binding,require_no_holders
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
from hil_rtc_alarm import PROMPT,canonical_state_reply
from hil_c6_system_bootstrap import write_file,read_file
from hil_usb_disk_transaction import require_file_contents
from hil_portable_system_apps import png
from chip8_fps_fixtures import stress_rom

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY='/C8Bench1108'
STATE=('calcreg','stk','dump','pwd','ls')
def sha(data):return hashlib.sha256(data).hexdigest()
def fields(payload):
    text=payload.decode('ascii')
    assert text.startswith('CHIP8_FPS V=1 ') and text.endswith('\n'),text
    value={key:int(number) for key,number in re.findall(r'(\w+)=(\d+)',text)}
    assert value['RESULT']==0 and 10_000_000<=value['US']<=11_000_000,value
    assert value['PAUSE_US']==0,value
    value['fps']=value['FRAME']*1e6/value['US']
    value['ips']=value['CPU']*1e6/value['US']
    return value
def receive_file(port,path):
    reply=port.command(f'fsget "{path}"',timeout=15)
    chunks=re.findall(r'^@MKC:DATA (\d+) ([0-9A-Fa-f]+)\r?$',reply,re.M)
    payload=bytearray()
    for at,text in chunks:
        assert int(at)==len(payload);payload.extend(bytes.fromhex(text))
    require_file_contents(reply,bytes(payload))
    return bytes(payload)
def prepare(args):
    args.directory.mkdir(parents=True,exist_ok=False)
    payloads={'C8FPS.APP':args.app.read_bytes(),'stress.ch8':stress_rom(),
        'echo8.ch8':(ROOT/'programs/CHIP8/echo8.ch8').read_bytes()}
    for name,data in payloads.items():(args.directory/name).write_bytes(data)
    (args.directory/'proof.log').write_bytes(args.proof.read_bytes())
    phase={'schema':1,'id':'C8FPS-001','public':'AEB505B6E0067623','build':'13A2194A',
        'usb':'2068336B4731','directory':DIRECTORY,'compute_request':False,
        'firmware_changes':False,'duration_ms':10000,'repeats':3,
        'workloads':['stress.ch8','echo8.ch8'],'runtime_budget_s':240,'cleanup_budget_s':60,
        'files':{name:{'bytes':len(data),'sha256':sha(data)} for name,data in payloads.items()},
        'driver_sha256':sha(Path(__file__).read_bytes()),
        'host_arm_proof':'proof.log','host_arm_proof_sha256':sha(args.proof.read_bytes())}
    data=(json.dumps(phase,ensure_ascii=False,indent=2)+'\n').encode()
    (args.directory/'phase.json').write_bytes(data)
    print(json.dumps({'phase':str(args.directory/'phase.json'),'sha256':sha(data)},ensure_ascii=False))
def run_phase(args):
    manifest=args.directory/'phase.json';raw=manifest.read_bytes();phase=json.loads(raw)
    assert sha(raw)==args.phase_sha and phase['driver_sha256']==sha(Path(__file__).read_bytes())
    assert phase['id']=='C8FPS-001' and phase['directory']==DIRECTORY and not phase['compute_request']
    for name,entry in phase['files'].items():assert sha((args.directory/name).read_bytes())==entry['sha256']
    assert sha((args.directory/phase['host_arm_proof']).read_bytes())==phase['host_arm_proof_sha256']
    binding=current_binding(args.port);require_no_holders(binding)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'os-binding.json').write_text(json.dumps(binding,indent=2))
    deadline=time.monotonic()+phase['runtime_budget_s']
    before={};owned=False;foreground=False;created=set();rows=[]
    def bounded():assert time.monotonic()<deadline,'finite phase deadline reached'
    with ScreenPort(args.port) as port:
        original_command=port.command
        def command(text,timeout=5):
            bounded()
            return original_command(text,timeout=min(timeout,max(.05,deadline-time.monotonic())))
        port.command=command
        try:
            bounded();identity_reply=port.command('identity');identity=parse_identity(identity_reply)
            assert (identity.public,identity.build,identity.usb)==(phase['public'],phase['build'],phase['usb'])
            (args.output/'identity-before.txt').write_text(identity_reply)
            for command in STATE:
                bounded();reply=port.command(command,timeout=15)
                before[command]=canonical_state_reply(reply)
                (args.output/('before-'+command+'.txt')).write_text(reply)
            assert DIRECTORY[1:] not in before['ls'],'phase directory already exists; no overwrite'
            reply=port.command(f'mkdir "{DIRECTORY}"');assert 'error' not in reply.lower(),reply
            owned=True
            app_path=DIRECTORY+'/C8FPS.APP'
            created.add(app_path);write_file(port,app_path,(args.directory/'C8FPS.APP').read_bytes())
            read_file(port,app_path,(args.directory/'C8FPS.APP').read_bytes())
            port.attach()
            active=DIRECTORY+'/active.ch8';report_path=DIRECTORY+'/result.txt'
            for workload in phase['workloads']:
                bounded()
                if active in created:
                    port.command(f'rm "{active}"');created.remove(active)
                data=(args.directory/workload).read_bytes()
                created.add(active);write_file(port,active,data);read_file(port,active,data)
                for repeat in range(phase['repeats']):
                    bounded();cursor=len(port.frames);created.add(report_path);port.open(app_path);foreground=True
                    stop_at=min(deadline,time.monotonic()+16)
                    while time.monotonic()<stop_at:
                        port.pump(.05)
                        if PROMPT.search(port.text[port.open_text_start:]):break
                    else:raise TimeoutError('finite FPS APP did not return')
                    foreground=False
                    payload=receive_file(port,report_path);sample=fields(payload)
                    label=f'{Path(workload).stem}-{repeat+1}'
                    (args.output/(label+'.txt')).write_bytes(payload)
                    frames=port.frames[cursor:]
                    if frames:png(frames[len(frames)//2],args.output/(label+'.png'))
                    sample.update(workload=workload,repeat=repeat+1,usb_frames=len(frames));rows.append(sample)
                    port.command(f'rm "{report_path}"');created.remove(report_path)
            (args.output/'samples.json').write_text(json.dumps(rows,indent=2))
        finally:
            cleanup_end=time.monotonic()+phase['cleanup_budget_s']
            deadline=cleanup_end
            if foreground and port.attached:
                port.key(39);port.pump(.5)
            for path in sorted(created):
                assert time.monotonic()<cleanup_end
                port.command(f'rm "{path}"',timeout=10)
            if owned:port.command(f'rmdir "{DIRECTORY}"',timeout=10)
            if port.attached:port.send(0x13);port.pump(.3)
            after={}
            for command in before:
                reply=port.command(command,timeout=10);after[command]=canonical_state_reply(reply)
                (args.output/('after-'+command+'.txt')).write_text(reply)
            (args.output/'terminal.bin').write_bytes(port.text)
            assert after==before,'calculator/cwd/root listing changed; do not restore an old snapshot'
            if before:
                fresh=parse_identity(port.command('identity'));assert fresh==identity
    print(json.dumps(rows,indent=2))
def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true')
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--app',type=Path)
    p.add_argument('--proof',type=Path);p.add_argument('--port');p.add_argument('--phase-sha');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.prepare:
        if not a.app or not a.proof:p.error('--prepare needs --app and --proof')
        assert b'ownership and graphics cleanup PASS' in a.proof.read_bytes();prepare(a)
    else:
        if not a.port or not a.phase_sha or not a.output:p.error('--run needs --port, --phase-sha and --output')
        run_phase(a)
if __name__=='__main__':main()
