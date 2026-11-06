"""One-shot PicoCalc clock phases. Importing performs no device I/O."""
import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import secrets
import sys
import termios
import time

HERE=Path(__file__).resolve().parent
PACKAGE=HERE.parent
ROOT=PACKAGE.parents[1]
sys.path.insert(0,str(ROOT/'.build/spectrum-games-20261106/cosmic-display'))
import run_pipe as old
import local_holders
import device_guard as native
import clock_protocol as protocol
b=old.b
need,Hold,sha=b.need,b.Hold,b.sha
UID=b.UID
FOLDER=b.FOLDER
APP='SPCLK.APP'
TEMP={APP,'SPCF.Z80','SPCF.ULP'}

def pins():
    return {**old.source_pins(),**{str(Path(m.__file__).resolve()):sha(m.__file__)
            for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and str(m.__file__).endswith('.py')
            and Path(m.__file__).resolve().is_relative_to(ROOT)}}

class Gate(b.Gate):
    def __init__(self,phase,grant,out):
        self.phase=Path(phase);self.grant=Path(grant);self.out=Path(out)
        self.j=json.loads(self.phase.read_text());g=json.loads(self.grant.read_text())
        need(g['authority']=='direct human user' and g['user_quote']=='занимай устройство',
             'Missing direct authorization to occupy PicoCalc')
        need(g['uid']==self.j['uid']==UID and g['phase_sha256']==sha(self.phase),
             'Wrong device or changed phase')
        need(self.j['action'] in ('admit','flash','clock','step'), 'Unknown phase')
        need(pins().keys()<=g['source_pins'].keys(),'Unpinned controller module')
        for path,value in {**g['source_pins'],**self.j['pins']}.items():
            need(sha(path)==value,'Changed phase/controller input '+path)
        self.start=time.time();need(g['not_before']<=self.start<=g['start_before'],'Stale launch')
        self.deadline=g['finish_before'];need(0<self.deadline-self.start<=390,'Unbounded phase')
        self.continuous_start=b.continuous();self.wall_origin=time.time();self.last_wall=self.wall_origin
        self.continuous_budget=self.deadline-self.wall_origin
        self.events=[];self.counter=0;self.cleaning=False;self.cleanup_start=0
        self.final={'authorization_authority':'direct human user','root_review_claimed':False,
                    'lease':'held','classic_io':False,
                    'previous_flash_backup':False,'settings_writes_requested':False,
                    'rtc_writes_requested':False}
        self.out.mkdir(exist_ok=False)
        self.used=self.grant.with_name(self.grant.name+'.USED')
        fd=os.open(self.used,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        try:os.write(fd,str(os.getpid()).encode())
        finally:os.close(fd)
    def noholders(self,binding,allow_self=False):
        self.check()
        try:result=local_holders.require_no_holders(binding,allow_self)
        except (local_holders.HolderError,OSError) as error:raise Hold(str(error)) from error
        self.final.setdefault('holder_checks',[]).append(result);self.check()
    def cleanup(self):
        if not self.cleaning:
            self.cleanup_start=b.elapsed(self.continuous_start,b.continuous());self.cleaning=True
    def check(self):
        left=super().check();elapsed=b.elapsed(self.continuous_start,b.continuous())
        cap=min(390,self.cleanup_start+150) if self.cleaning else 240
        need(elapsed<cap,'Clock phase/cleanup cap exceeded');return min(left,cap-elapsed)

def admit(g):
    with b.Port(g) as p:
        before=ready_status(p,g.j['expected'],125) if g.j.get('diagnostic') else p.status()
        physical=b.guard_status(before,g.j['expected'])
        p.commands();need(b.field(p.command('identity'),'UID')==UID,'Identity mismatch')
        if g.j.get('cleanup_previous'):
            previous=Path(g.j['cleanup_previous']);old_phase=json.loads(previous.read_text())
            need(sha(previous)==g.j['pins'][str(previous)] and old_phase['uid']==UID and
                 old_phase['folder']==FOLDER and set(old_phase['files'])==TEMP,'Unowned cleanup predecessor')
            g.final['temporary_files_absent']=remove_own(p,TEMP)
        g.final['heap']=p.command('prof heap');after=p.status()
        b.guard_status(after,g.j['expected'],physical)
        g.final.update(status_before=before,status_after=after,native_binding=p.binding,
                       physical_keys=physical,read_only=not bool(g.j.get('cleanup_previous')))
        if g.j.get('verify_install_receipt'):
            source=Path(g.j['verify_install_receipt']);r=json.loads(source.read_text())
            need(sha(source)==g.j['pins'][str(source)] and r['new_program_readback_equal'] and
                 r['expected']==g.j['expected'] and r['target_bin_sha256']==g.j['target_bin_sha256'],
                 'Installation readback not proved')
            g.final['clock']=protocol.clock(p.command('prof cosmic status'),125,False,0)
            g.final.update(expected=g.j['expected'],installation_verified=True)
    g.noholders(g.final['native_binding']);g.final['lease']='reserved_ports_closed'

def clock_guard(status,expected,mhz,physical=None):
    values=dict(BUILD=expected['build'].upper(),FIRMWARE_CRC='valid',EXPECTED=expected['crc'].upper(),
        ACTUAL=expected['crc'].upper(),IMAGE=str(expected['bytes']),CRASH='NONE',MATH_TEST='OK',
        failures='0',SERVICE='CLOSED',RUNTIME='NONE',RUN='0',BUSY='0',USB_DISK='0',USB_SCREEN='OFF',
        DIRTY='0',APP_BUFFERS='0',APP_BUFFER_BYTES='0',APP_EXTERNAL_BYTES='0',APP_WINDOWS='0',
        KBD='OK',PANEL_INIT='1',PSRAM='OK',SD='OK',SYS_HZ=str(mhz*1000000),PERI_HZ='48000000')
    for key,value in values.items():need(b.field(status,key)==value,'Native clock guard differs '+key)
    banners=re.findall(r'(?<!\S)RP2040 ([0-9]+) MHz(?!\S)',status)
    need(banners==[str(mhz)],'Actual native CPU clock differs from target')
    raw=b.field(status,'PHYSICAL_KEYS');need(re.fullmatch('[0-9]+',raw),'Invalid physical key counter')
    keys=int(raw)
    if physical is not None:need(keys==physical,'Physical keyboard used during controlled test')
    return keys

def ready_status(p,expected,mhz):
    end=time.monotonic()+10
    while True:
        status=p.status()
        # Enumeration precedes keyboard/panel readiness. Permit only these
        # explicit startup WAIT states; identity, CRC and faults remain strict.
        for key,value in dict(BUILD=expected['build'],ACTUAL=expected['crc'],FIRMWARE_CRC='valid',
                              CRASH='NONE',MATH_TEST='OK',PSRAM='OK').items():
            need(b.field(status,key)==value,'Boot readiness differs '+key)
        kbd=b.field(status,'KBD');panel=b.field(status,'PANEL_INIT');sd=b.field(status,'SD')
        need(kbd in ('WAIT','OK') and panel in ('0','1') and sd in ('WAIT','OK'),'Boot peripheral failure')
        if (kbd,panel,sd)==('OK','1','OK'):
            clock_guard(status,expected,mhz);return status
        need(time.monotonic()<end,'Keyboard/panel/card startup did not complete')
        p.pump(.2)

def flash(g):
    j=g.j;target=Path(j['firmware']);manifest=target/'manifest.json'
    m=json.loads(manifest.read_text());binary=target/'mk61s-picocalc-pico-h.bin'
    need(sha(binary)==m['bin_sha256']==j['pins'][str(binary)],'Target image changed')
    n=binary.stat().st_size
    need(n==m['flash_bytes'] and 0<n and (n+4095)//4096*4096<=0x1c0000,
         'Image overlaps ROMCACHE/settings reserve')
    previous=Path(j['previous_receipt']);r=json.loads(previous.read_text())
    need(sha(previous)==j['pins'][str(previous)] and r['status']=='PASS' and
         r['lease']=='reserved_ports_closed','No successful current-image admission')
    with b.Port(g) as p:
        need(p.binding==r['native_binding'],'Device binding changed since admission')
        b.guard_status(p.status(),j['expected']);p.commands()
        need(b.field(p.command('identity'),'UID')==UID,'Native UID mismatch')
        binding=p.binding.copy();location=native.enter_rom(g,p,j['expected'])
    g.wait_rom(location);g.final['owned_rom_binding']=g.rom_identity(location)
    g.native_absent(binding)
    g.picotool(['load','-v',str(binary),'-t','bin','-o','0x10000000'])
    readback=g.out/'new-program-readback.bin'
    g.save_range(0x10000000,0x10000000+n,readback)
    need(readback.read_bytes()==binary.read_bytes(),'New firmware readback mismatch')
    g.final.update(flash_writes=1,new_program_readback_equal=True,target_bin_sha256=sha(binary),expected=j['target_expected'])
    g.picotool(['reboot']);g.wait_native(location)
    with b.Port(g) as p:
        s=ready_status(p,j['target_expected'],125)
        p.commands();need(b.field(p.command('identity'),'UID')==UID,'Reboot UID mismatch')
        g.final['clock']=protocol.clock(p.command('prof cosmic status'),125,False,0)
        g.final.update(status_after=s,native_binding=p.binding)
    g.noholders(g.final['native_binding']);g.final['lease']='reserved_ports_closed'

class Port(old.previous.GamesPort):
    def open_app(self,name):
        need(name==APP,'Foreign APP')
        self.opened=True;self.pump(.02);self.send(('open "'+FOLDER+'/'+name+'"\r').encode())
    def native_return(self,mhz,physical):
        browser=False
        for _ in range(5):
            status=self.status();service,path,result=b.foreground(status)
            if service=='CLOSED':
                clock_guard(status,self.g.j['expected'],mhz,physical);self.commands();return status
            if service=='BROWSER' and browser:
                need(b.field(status,'RUNTIME')=='NONE','Unexpected browser runtime')
                self.wire(27);self.pump(.2);continue
            need(getattr(self,'opened',False) and path==FOLDER+'/'+APP,'Foreign foreground; no escape sent')
            if b.field(status,'RUNTIME')=='APP':self.wire(27);self.pump(.3);continue
            need(b.field(status,'RUNTIME')=='NONE' and service in ('VIEWER','BROWSER'),'Unexpected owned foreground')
            if service=='VIEWER':need(result.startswith('APP finished;'),'APP did not finish normally')
            self.send(b'\x1e');self.wire(27);self.pump(.2);browser=True
        raise Hold('Native return exceeded finite escape cap')
    def detach(self,command):
        need(command in ('prof cosmic switch','prof cosmic end'),'Unowned detach command')
        self.pump(.02)
        termios.tcsetattr(self.fd,termios.TCSANOW,self.saved)
        need(native.stable_termios(termios.tcgetattr(self.fd))==native.stable_termios(self.saved),
             'Pre-detach termios restore differs')
        fcntl.ioctl(self.fd,native.TIOCNXCL);self.exclusive=False;self.restored_for_dfu=True
        before=time.monotonic();self.send(command.encode()+b'\r')
        # Do not close a macOS CDC descriptor immediately after write: it can
        # discard the final command. This finite wait observes owned removal.
        self.wait_owned_dfu_delivery()
        self.g.final.setdefault('planned_detaches',[]).append(dict(command=command,
            old_binding=self.binding,delivery_wait_seconds=time.monotonic()-before))
        self.close()

def reopen(g,before,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        g.check()
        try:binding=g.native()
        except (Hold,FileNotFoundError):time.sleep(.2);continue
        need(binding['location']==before['location'],'PicoCalc changed USB slot')
        if binding['session']==before['session'] or binding['usb_entry']==before['usb_entry']:
            time.sleep(.1);continue
        p=Port(g);p.__enter__()
        try:
            need(p.binding==binding,'Binding changed while reopening')
            p.commands();need(b.field(p.command('identity'),'UID')==UID,'Reconnected UID mismatch')
        except BaseException:
            p.close();raise
        return p
    raise Hold('USB did not re-enumerate within finite reconnect cap')

def probe(p,sequence):
    challenge=secrets.token_bytes(32)
    response=p.command(f'prof cosmic echo {sequence} {challenge.hex()}',timeout=8)
    try:result=protocol.usb(response,sequence,challenge)
    except protocol.EvidenceError as error:raise Hold(str(error)) from error
    p.g.final.setdefault('usb_probes',[]).append(dict(sequence=sequence,
        challenge=challenge.hex(),result=result,binding=p.binding))
    return result

def listing(report):
    return {line.rstrip('\r').split('\t')[-1].rstrip('/') for line in report.splitlines()
            if re.match(r'^[df]\t',line)}

def remove_own(p,attempted):
    need(attempted<=TEMP,'Foreign cleanup target')
    for name in sorted(attempted):p.command(f'rm "{FOLDER}/{name}"')
    names=listing(p.command(f'ls "{FOLDER}"'))
    need({'48.rom','SPECTRUM.APP'}<=names and not attempted.intersection(names),'Cleanup/namespace unproved')
    return sorted(attempted)

def error_counters(status):
    keys=('ERRORS','QPI_FALLBACKS','TAIL_TIMEOUTS','CRC_ERRORS','DMA_TIMEOUTS','LCD_ERRORS',
          'SD_SPEED_FALLBACKS','SD_PROBE_FAILURES','I2C_TIMEOUTS','I2C_ABORTS','SCREEN_ERRORS')
    return {key:int(b.field(status,key)) for key in keys}

def wait_for_fallback(g,binding,attempted,observe_deadline=False):
    deadline=g.final['lease_armed_monotonic']+protocol.LEASE_MS/1000+2
    observed=None
    while time.monotonic()<deadline:
        g.check()
        if observe_deadline:
            try:
                now=g.native()
                need(now['location']==binding['location'],'Fallback device moved USB slot')
                if now['session']!=binding['session'] and now['usb_entry']!=binding['usb_entry']:
                    observed=time.monotonic()-g.final['lease_armed_monotonic'];break
            except (Hold,FileNotFoundError):pass
            time.sleep(.5)
        else:time.sleep(.2)
    p=reopen(g,binding,timeout=20)
    try:
        status=ready_status(p,g.j['expected'],125);p.commands()
        protocol.clock(p.command('prof cosmic status'),125,False,0)
        g.final['temporary_files_absent']=remove_own(p,attempted)
        g.final.update(status_after=p.status(),native_binding=p.binding,
            automatic_125_fallback_verified=True,cleanup_native_verified=True)
        if observe_deadline:
            g.final['fallback_observed_seconds']=observed
            target=g.final['status_at_target']
            need(int(b.field(status,'BOOTS'))==int(b.field(target,'BOOTS'))+1,'Unexpected fallback boot count')
            need(observed is not None and 104<=observed<=110,'Fallback reset missed105s deadline')
    finally:p.close()

def clock_phase(g):
    j=g.j;mhz=j['mhz'];need(mhz in protocol.PLANS,'Unsupported target')
    g.final['expected']=j['expected']
    need(j['measurement']==dict(warmup_frames=100,window_frames=300,windows=10,timer_interval_uncertainty_us=1),
         'Changed complete-window contract')
    need(set(j['files'])==TEMP and j['folder']==FOLDER,'Foreign writable namespace')
    for name,item in j['files'].items():
        need(sha(item['local'])==item['sha256']==j['pins'][item['local']] and
             0<Path(item['local']).stat().st_size<=65535,'Unpinned/oversized '+name)
    previous=Path(j['previous_receipt']);r=json.loads(previous.read_text())
    need(sha(previous)==j['pins'][str(previous)] and r['status']=='PASS' and
         r['lease']=='reserved_ports_closed','Unreleased/unsuccessful predecessor')
    need(r['native_binding']==j['native_binding'],'Predecessor binding mismatch')
    p=None;attempted=set();armed=False;switched=False;failure=None;before_binding=None
    expected_boots=None;physical=None
    try:
        p=Port(g);p.__enter__();need(p.binding==j['native_binding'],'Stale device binding')
        status=p.status();physical=clock_guard(status,j['expected'],125)
        expected_boots=b.field(status,'BOOTS');g.final['status_before']=status
        errors=error_counters(status);g.final['errors_before']=errors
        need(all(v==0 for v in errors.values()),'Pre-existing memory/I/O errors')
        p.commands();need(b.field(p.command('identity'),'UID')==UID,'Wrong UID')
        protocol.clock(p.command('prof cosmic status'),125,False,0)
        g.final['heap_start']=p.command('prof heap')
        need(b.field(g.final['heap_start'],'HEAP_FREE_BLOCKS')=='1' and
             int(b.field(g.final['heap_start'],'HEAP_FREE'))>=90000,'Cold single-block heap required')
        names=listing(p.command(f'ls "{FOLDER}"'))
        need({'48.rom','SPECTRUM.APP'}<=names and not names.intersection(TEMP),'Namespace absent/temporary names occupied')
        def write(name):
            attempted.add(name);b.write_file(p,FOLDER+'/'+name,Path(j['files'][name]['local']).read_bytes())
        write(APP);start=len(p.text);p.open_app(APP);p.menu(start);b.validate_root(p.text[start:],initial=True)
        status=p.status();need(b.field(status,'RUNTIME')=='APP' and b.field(status,'APP_EXTERNAL_BYTES')=='1892352',
                               'APP SRAM/PSRAM/ROMCACHE preflight failed')
        p.save('preflight');p.native_return(125,physical)
        for name in ('SPCF.Z80','SPCF.ULP'):write(name)
        reply=p.command(f'prof cosmic begin {mhz}')
        arm=protocol.fields(reply,'CCARM',('mhz','lease_ms','usb_hz'))
        need(arm==dict(mhz=mhz,lease_ms=105000,usb_hz=48000000),'Native lease not armed')
        armed=True;g.final['lease_armed_monotonic']=time.monotonic();before_binding=p.binding
        p.detach('prof cosmic switch');p=None
        p=reopen(g,before_binding);switched=True
        status=p.status();clock_guard(status,j['expected'],mhz,physical)
        need(b.field(status,'BOOTS')==expected_boots,'Unexpected reset during switch')
        g.final['clock_before']=protocol.clock(p.command('prof cosmic status'),mhz,True,1)
        for sequence in (mhz*10,mhz*10+1):probe(p,sequence)
        g.final['load_binding']=p.binding
        start=len(p.text);p.open_app(APP);p.menu(start);b.validate_root(p.text[start:],initial=True);p.save('initial')
        game=j['game'];start=len(p.text);p.open_fixture(game);p.pump(2)
        for _ in range(10):p.wire(ord('p'));p.pump(.2)
        # No queries/probes/log messages are sent during the measured interval.
        p.match(rb'SPPACING_DONE\r?\n',start,timeout=85);p.pause()
        record=bytes(p.text);frame=old.previous.framebuffer(record)
        signature=old.previous.scene_signature(frame,game)
        result=old.measurements(record);result.update(old.pipeline_details(record));result.update(old.sound_details(record))
        result.update(mhz=mhz,hud_signature=signature,app_sha256=j['files'][APP]['sha256'],
            frame_sha256=hashlib.sha256(frame).hexdigest(),bus_clocks_fixed=True,xip_hz=mhz*1000000//4,
            comparison='same image and payload; CPU plus XIP clock change; PIO/peripheral/PCM clocks fixed')
        (g.out/'frame.bin').write_bytes(frame);p.save('game');g.final['result']=result
        p.native_return(mhz,physical)
        for sequence in (mhz*10+2,mhz*10+3):probe(p,sequence)
        need(p.binding==g.final['load_binding'],'USB binding changed under load')
        status=p.status();clock_guard(status,j['expected'],mhz,physical)
        need(b.field(status,'BOOTS')==expected_boots,'Unexpected reset under load')
        g.final['clock_after']=protocol.clock(p.command('prof cosmic status'),mhz,True,1)
        g.final['errors_after']=error_counters(status)
        need(g.final['errors_after']==errors,'New memory/I/O errors during clock test')
        g.final['status_at_target']=status
    except BaseException as error:failure=error;g.final['primary_error']=repr(error)
    finally:
        g.cleanup()
        try:
            if p is not None and p.fd is not None:
                # Only escape the APP this phase explicitly opened.
                if switched:p.native_return(mhz,physical)
                else:p.native_return(125,physical)
                p.command('fsput cancel')
                if armed and j.get('cleanup_mode')=='lease-timeout':
                    need(mhz==250,'Timeout validation is scoped to final250MHz mode')
                    before_binding=p.binding;p.close();p=None
                    wait_for_fallback(g,before_binding,attempted,observe_deadline=True);armed=False
                elif armed:
                    before_binding=p.binding;p.detach('prof cosmic end');p=None
                    p=reopen(g,before_binding);armed=False
                if p is not None:
                    status=ready_status(p,j['expected'],125)
                    protocol.clock(p.command('prof cosmic status'),125,False,0)
                    g.final['temporary_files_absent']=remove_own(p,attempted)
                    g.final.update(status_after=p.status(),native_binding=p.binding,heap_end=p.command('prof heap'))
                    clock_guard(g.final['status_after'],j['expected'],125)
                    g.final['cleanup_native_verified']=True
            elif armed:
                # The device owns a105s independent reset deadline. Wait only
                # for a fresh native binding; never resend a failed switch.
                wait_for_fallback(g,before_binding,attempted)
        except BaseException as error:
            g.final['cleanup_error']=repr(error)
            if failure is None:failure=error
        finally:
            if p is not None:p.close()
        if armed and not g.final.get('cleanup_native_verified'):
            try:wait_for_fallback(g,before_binding,attempted)
            except BaseException as error:g.final['fallback_error']=repr(error)
        try:
            sessions=g.final.get('cdc_sessions',[])
            need(sessions and all(s['closed'] and not s.get('errors') for s in sessions),'Unclosed/failed CDC session')
            need(g.final.get('cleanup_native_verified'),'125MHz native cleanup unproved')
            g.noholders(g.final['native_binding']);g.final['lease']='reserved_ports_closed'
        except BaseException as error:
            g.final['handoff_error']=repr(error)
            if failure is None:failure=error
    if failure is not None:raise failure

def step_phase(g):
    j=g.j;mhz=j['mhz'];reset_probe=mhz==125 and j.get('role')=='reset-probe'
    need(mhz in protocol.PLANS and (mhz not in (125,200,250) or reset_probe),'Not an intermediate step')
    previous=Path(j['previous_receipt']);r=json.loads(previous.read_text())
    need(sha(previous)==j['pins'][str(previous)] and r['status']=='PASS' and r['lease']=='reserved_ports_closed',
         'Incomplete previous frequency')
    need(r['native_binding']==j['native_binding'] and r['expected']==j['expected'],'Changed device/image')
    if reset_probe:need(r['action']=='flash' and r['new_program_readback_equal'],'Reset probe requires verified install')
    p=None;armed=False;binding=None;failure=None
    g.final['expected']=j['expected']
    try:
        p=Port(g);p.__enter__();need(p.binding==j['native_binding'],'Stale intermediate-step binding')
        status=ready_status(p,j['expected'],125);physical=clock_guard(status,j['expected'],125)
        boots=b.field(status,'BOOTS');p.commands()
        protocol.clock(p.command('prof cosmic status'),125,False,0)
        need(all(v==0 for v in error_counters(status).values()),'Pre-existing I/O errors')
        arm=protocol.fields(p.command(f'prof cosmic begin {mhz}'),'CCARM',('mhz','lease_ms','usb_hz'))
        need(arm==dict(mhz=mhz,lease_ms=105000,usb_hz=48000000),'Intermediate lease not armed')
        armed=True;g.final['lease_armed_monotonic']=time.monotonic();binding=p.binding
        p.detach('prof cosmic switch');p=None;p=reopen(g,binding)
        status=p.status();clock_guard(status,j['expected'],mhz,physical)
        need(b.field(status,'BOOTS')==boots,'Unexpected intermediate reset')
        clock=protocol.clock(p.command('prof cosmic status'),mhz,True,1)
        probe(p,mhz*10);probe(p,mhz*10+1)
        p.send(b'\x1e');p.pump(.05);start=len(p.text);p.wire(ord('m'))
        p.match(rb'(?m)^MSC_SD_READ_US=[^\r\n]*\r?\n',start,timeout=15)
        math=native.c5_frame(bytes(p.text[start:]));clock_guard(math,j['expected'],mhz,physical)
        need(b.field(math,'BOOTS')==boots,'Reset during intermediate math check')
        p.commands();probe(p,mhz*10+2)
        errors=error_counters(p.status());need(all(v==0 for v in errors.values()),'Intermediate I/O fault')
        g.final['result']=dict(mhz=mhz,clock=clock,math_test='OK',errors=errors,
            kind='short USB/clock/native-M0-math check; full Cosmic latency unmeasured')
    except BaseException as error:failure=error;g.final['primary_error']=repr(error)
    finally:
        g.cleanup()
        try:
            if p is not None and p.fd is not None:
                status=p.status()
                need(b.field(status,'BUILD')==j['expected']['build'] and b.field(status,'SERVICE')=='CLOSED' and
                     b.field(status,'RUNTIME')=='NONE','Foreign foreground at intermediate cleanup')
                p.commands()
                if armed:
                    binding=p.binding;p.detach('prof cosmic end');p=None;p=reopen(g,binding);armed=False
                status=ready_status(p,j['expected'],125)
                protocol.clock(p.command('prof cosmic status'),125,False,0)
                g.final.update(status_after=status,native_binding=p.binding,cleanup_native_verified=True)
            elif armed:wait_for_fallback(g,binding,set())
        except BaseException as error:
            g.final['cleanup_error']=repr(error)
            if failure is None:failure=error
        finally:
            if p is not None:p.close()
        if armed and not g.final.get('cleanup_native_verified'):
            try:wait_for_fallback(g,binding,set())
            except BaseException as error:g.final['fallback_error']=repr(error)
        try:
            need(g.final.get('cleanup_native_verified'),'Intermediate125MHz release unproved')
            need(all(s['closed'] and not s['errors'] for s in g.final['cdc_sessions']),'Intermediate CDC not closed')
            g.noholders(g.final['native_binding']);g.final['lease']='reserved_ports_closed'
            if reset_probe:g.final['installation_verified']=True
        except BaseException as error:
            g.final['handoff_error']=repr(error)
            if failure is None:failure=error
    if failure is not None:raise failure

def run(g):
    if g.j['action']=='admit':return admit(g)
    if g.j['action']=='flash':return flash(g)
    if g.j['action']=='clock':return clock_phase(g)
    if g.j['action']=='step':return step_phase(g)
    raise Hold('Hardware mutation/controller is not ready')

def main():
    parser=argparse.ArgumentParser()
    for name in ('phase','grant','out'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();g=Gate(args.phase,args.grant,args.out)
    try:run(g)
    except BaseException as error:g.finish(False,repr(error));raise
    else:g.finish(True)
if __name__=='__main__':main()
