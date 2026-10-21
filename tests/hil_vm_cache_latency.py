#!/usr/bin/env python3
"""Identity-pinned Classic cache A/B/A: real matrix gaps, USB PING, exact recovery.

Requires the explicitly reserved device, immutable recovery BIN and matching
System APPs. Adds only /VMLAT plus owned VMC, then restores original bytes/state.
Does not grant M61 any additional terminal permissions or touch Mini.
"""
from dataclasses import asdict
from collections import deque
import argparse
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
from types import SimpleNamespace
from types import MethodType

import hil_vm_compiled_blocks as base
from hil_portable_apps import ScreenPort,cobs_encode
from hil_rtc_alarm import PROMPT,canonical_state_reply as state_without_prompt_padding
from hil_multi_device_identity import parse_identity
from hil_portable_system_apps import png
from hil_turochamp_performance import Font,profile

VER=b'MK61s-Classic-V3 ver.'
APPS=('LANGVM.APP','LANGIN.APP','BASIC.APP','FOCAL.APP','VMCache/VMSTORE.APP')


def save(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')


def fast_control(port):
    # Keep the exact prompt/ACK/offset/CRC protocol, but do not sleep 50 ms
    # after each 48-byte upload chunk. No pipelining or unacknowledged writes.
    def command(self,command,timeout=5):
        self.pump(.002);start=len(self.text);self.write_line(command)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.pump(.005)
            if PROMPT.search(self.text[start:]):return self.text[start:].decode('cp1251','replace')
        raise TimeoutError((command,bytes(self.text[start:])))
    port.command=MethodType(command,port)
    return port


class PingPort(ScreenPort):
    def __init__(self,path):
        super().__init__(path)
        self.measuring=False;self.outstanding=None;self.pings=[];self.next_measured_ping=0
        self.nonce=0xA100;self.packets_crc_verified=0
        self.last_host_poll=None;self.maximum_host_poll_gap=0
        self.wire_events=deque(maxlen=256);self.measured_sent=0;self.automatic_pending=False

    def trace(self,direction,kind,payload):
        if not hasattr(self,'wire_events'):return
        self.wire_events.append(dict(at=time.monotonic(),direction=direction,kind=kind,
            payload=payload.hex(),measuring=self.measuring,
            outstanding=self.outstanding[0] if self.outstanding else None))

    def send(self,kind,payload=b''):
        if kind==0x14 and payload==b'\x61\0':
            assert self.outstanding is None,'automatic heartbeat would preempt measured PONG'
            assert not getattr(self,'automatic_pending',False),'automatic heartbeat still awaiting PONG'
            self.automatic_pending=True
        elif kind==0x14:
            assert not getattr(self,'automatic_pending',False),'measured PING would preempt automatic PONG'
        self.trace('tx',kind,payload)
        return super().send(kind,payload)

    def diagnostics(self):
        return dict(outstanding=self.outstanding,measuring=self.measuring,
            maximum_host_poll_gap_seconds=self.maximum_host_poll_gap,
            measured_sent=self.measured_sent,measured_replies=len(self.pings),automatic_pending=self.automatic_pending,
            packets_crc_verified=self.packets_crc_verified,frames=len(self.frames),
            last_control_packets=list(self.wire_events))

    def receive_packet(self,encoded):
        raw=checked_packet(encoded)
        if raw[3]<0x20:self.trace('rx',raw[3],raw[9:-2])
        super().receive_packet(encoded)  # Includes full frame CRC and geometry.
        self.packets_crc_verified+=1
        if raw[3]==0x12:self.next_ping=float('inf')
        if raw[3]==0x15 and raw[9:-2]==b'\x61\0':self.automatic_pending=False
        if raw[3]==0x15 and raw[9:-2]!=b'\x61\0' and self.outstanding is not None:
            nonce,started=self.outstanding
            assert raw[9:-2]==struct.pack('<H',nonce),('uncorrelated PONG',raw.hex(),nonce)
            elapsed=time.monotonic()-started
            assert elapsed<1.0,('late PONG >1s',elapsed)
            self.pings.append(elapsed);self.outstanding=None
            self.next_measured_ping=time.monotonic()+.02

    def pump(self,duration=.02):
        end=time.monotonic()+duration
        while time.monotonic()<end:
            now=time.monotonic()
            if self.measuring or self.outstanding is not None:
                if self.last_host_poll is not None:
                    self.maximum_host_poll_gap=max(self.maximum_host_poll_gap,now-self.last_host_poll)
                self.last_host_poll=now
            if self.attached:
                self.next_ping=float('inf')
                if self.measuring and self.outstanding is None and now>=self.next_measured_ping:
                    self.nonce=(self.nonce+1)&65535
                    if self.nonce==0x61:self.nonce=0x62  # Reserved idle heartbeat payload.
                    self.outstanding=(self.nonce,now)
                    self.measured_sent+=1
                    self.send(0x14,struct.pack('<H',self.nonce))
                # end_measurement() stops new samples before draining the
                # final one. Never put an automatic heartbeat behind that
                # PING: firmware readRx() has one last-wins response slot.
                elif not self.measuring and self.outstanding is None and not getattr(self,'automatic_pending',False) and now>=self.next_measured_ping:
                    self.send(0x14,b'\x61\0');self.next_measured_ping=now+.7
            if self.outstanding is not None:
                assert now-self.outstanding[1]<1.0,('PONG timeout >1s',
                    dict(host_poll_gap_seconds=self.maximum_host_poll_gap,
                         crc_verified_packets=self.packets_crc_verified,frames=len(self.frames)))
            super().pump(min(.005,max(0,end-time.monotonic())))

    def begin_measurement(self):
        assert not self.measuring and self.outstanding is None,'previous measurement is not drained'
        # Do not overlap a previous idle keepalive with the first sample either.
        self.next_measured_ping=float('inf');deadline=time.monotonic()+1
        while getattr(self,'automatic_pending',False):
            assert time.monotonic()<deadline,'automatic PONG absent before measurement'
            self.pump(.005)
        self.pings=[];self.outstanding=None;self.measuring=True;self.next_measured_ping=0
        self.last_host_poll=None;self.maximum_host_poll_gap=0
        self.measured_sent=0

    def end_measurement(self):
        assert self.measuring,'no active measurement to drain'
        self.measuring=False;self.next_measured_ping=time.monotonic()+.7
        deadline=time.monotonic()+1
        while self.outstanding is not None and time.monotonic()<deadline:self.pump(.005)
        assert self.outstanding is None,'last PONG absent'
        assert self.pings,'no measured PONG'
        assert self.measured_sent==len(self.pings),'measured PING/PONG accounting mismatch'


def checked_packet(encoded):
    # Reuse the existing COBS parser, independently keep packet CRC mandatory.
    from hil_portable_apps import cobs_decode
    raw=cobs_decode(encoded)
    assert len(raw)>=11 and raw[:3]==b'MS\x02'
    assert binascii.crc_hqx(raw[:-2],65535)==struct.unpack_from('<H',raw,len(raw)-2)[0]
    assert len(raw)==struct.unpack_from('<H',raw,7)[0]+11
    return raw


def percentile(values,fraction):
    ordered=sorted(values)
    return ordered[min(len(ordered)-1,int((len(ordered)-1)*fraction))]


class FocalAcknowledger:
    def __init__(self,font,requests):
        assert requests and requests%16==0
        self.font=font;self.expected=[f'LATF{i:02d}' for _ in range(requests//16) for i in range(8)]
        self.seen=[]

    def consume(self,frame):
        if len(self.seen)==len(self.expected):return False
        label=self.expected[len(self.seen)]
        if not self.font.matches(frame,label,0,0):return False
        self.seen.append(label);return True


def parse_gaps(text):
    matches=re.findall(r'^GAP (\S+) n=(\d+) max=(\d+) total=(\d+) over1=(\d+) over5=(\d+) over10=(\d+) over30=(\d+)\s*$',text,re.M)
    rows={name:dict(zip(('samples','max_cycles','total_cycles','over1','over5','over10','over30'),map(int,nums)))
          for name,*nums in matches}
    assert len(matches)==len(rows)==8 and all(row['samples'] for row in rows.values()),rows
    assert set(rows)=={'keyboard.poll','keyboard.sample','usb.service',*(f'keyboard.row{i}' for i in range(5))}
    for row in rows.values():
        assert row['over30']<=row['over10']<=row['over5']<=row['over1']<=row['samples']
        row['max_us']=row['max_cycles']/96
    return rows


def require_launch_count(text,data,expected):
    """Keep exact launch accounting for both the RAM and Flash VM engines."""
    assert expected>0 and data['vm_cache_dropped']==0
    if data['vm_cache']:
        actual=sum(row['hits']+row['misses'] for row in data['vm_cache'])
        assert actual==expected,data['vm_cache']
        return dict(engine='ram',launches=actual)
    # Flash page hits are not program launches. The resident's outer invoke
    # scope records exactly one launch, including a first compilation.
    matches=re.findall(r'^VMFLASH (.*)$',text,re.M)
    assert len(matches)==1,'missing Flash VM diagnostics; empty RAM rows are not sufficient'
    cache={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',matches[0])}
    assert cache['budget']==32768 and 0<cache['payload']<cache['budget'],cache
    assert 0<=cache['used']<=cache['payload'],cache
    assert cache['lookups']==cache['hits']+cache['misses'],cache
    assert cache['lookups'] or cache.get('loan_hits',0),cache
    actual=data['points'].get('vm.invoke',{}).get('calls')
    assert actual==expected,('Flash VM launch mismatch',actual,expected)
    return dict(engine='flash',launches=actual,page_cache=cache)


def batch(port,filename,out,expected_requests):
    assert 'PROF started' in port.command('prof start')
    start=len(port.text);frames=len(port.frames);packets=port.packets_crc_verified
    port.begin_measurement();started=time.monotonic()
    port.write_line('open "/VMLAT/'+filename+'"')
    deadline=started+180;notice=started;cursor=len(port.frames)
    acknowledger=FocalAcknowledger(port.latency_font,expected_requests)
    while time.monotonic()<deadline:
        port.pump(.01)
        # FOCAL deliberately waits after EXIT, even when called from M61.
        # Acknowledge only its expected end marker, not on a blind timer.
        for frame in port.frames[cursor:]:
            if acknowledger.consume(frame):
                port.send(0x30,bytes((37,1)));port.send(0x30,bytes((37,0)))
        cursor=len(port.frames)
        text=bytes(port.text[start:])
        assert port.attached,'screen detached'
        assert b'Open failed' not in text and b'not allowed' not in text and b'Unknown command' not in text,text[-1000:]
        if text.count(VER)>=2:break
        if time.monotonic()-notice>25:
            print(filename,'running',round(time.monotonic()-started,1),'s',flush=True);notice=time.monotonic()
    else:raise TimeoutError(('batch missing end VER',bytes(port.text[start:])[-1000:]))
    finished=time.monotonic();port.end_measurement()
    assert acknowledger.seen==acknowledger.expected,('missing FOCAL end markers',acknowledger.seen,acknowledger.expected)
    counters=port.command('prof stop',timeout=20)
    out.mkdir();(out/'prof.txt').write_text(counters)
    (out/'terminal.txt').write_bytes(port.text[start:])
    assert 'KBD overflow=0' in counters,counters
    data=profile(counters);assert data['clock_hz']==96000000 and data['vm_cache_dropped']==0
    launches=require_launch_count(counters,data,expected_requests) if expected_requests is not None else None
    points=data['points'];gaps=parse_gaps(counters)
    row=dict(filename=filename,wall_seconds=finished-started,gaps=gaps,profile=data,launch_accounting=launches,focal_acknowledgements=acknowledger.seen,
        maximum_host_poll_gap_seconds=port.maximum_host_poll_gap,
        keyboard_overflow=0,frames_crc_verified=len(port.frames)-frames,
        packets_crc_verified=port.packets_crc_verified-packets,
        ping=dict(count=len(port.pings),p50_seconds=percentile(port.pings,.5),
                  p95_seconds=percentile(port.pings,.95),p99_seconds=percentile(port.pings,.99),
                  max_seconds=max(port.pings),all_seconds=port.pings.copy()),
        transport=port.diagnostics())
    save(out/'report.json',row)
    print(filename,'PASS',round(row['wall_seconds'],3),'s',
          'kbd-row-max-us',round(max(gaps['keyboard.row'+str(i)]['max_us'] for i in range(5)),1),
          'usb-gap-us',round(gaps['usb.service']['max_us'],1),
          'ping-max-ms',round(max(port.pings)*1000,2),flush=True)
    return row


def quiesce(port):
    port.measuring=False;port.outstanding=None
    if not port.attached:return
    try:
        for _ in range(2):port.key(39)
    finally:
        port.send(0x13);port.attached=False;port.pump(.1)


def interactive(port,item,out):
    filename=item['filename'];kind=item['kind']
    assert 'PROF started' in port.command('prof start')
    start=len(port.text);port.begin_measurement()
    port.write_line('open "/VMLAT/'+item['launcher']+'"')
    label='LAT INPUT' if kind=='INPUT' else 'RUN ESC'+('B' if item['language']=='basic' else 'F')
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        port.pump(.01)
        if port.frames and port.latency_font.matches(port.frames[-1],label,0,0):break
        assert not PROMPT.search(port.text[start:]),('program ended before ready marker',filename,port.text[start:])
    else:raise TimeoutError(('missing interactive ready marker',filename,label))
    assert not PROMPT.search(port.text[start:]),('program ended before key',filename,port.text[start:])
    key_started=time.monotonic()
    if kind=='INPUT':port.key(9);port.key(37)  # Classic digit 1, OK.
    else:port.key(39)  # Short ESC; not the USB Screen detach hold.
    deadline=time.monotonic()+4
    acknowledged=False
    while time.monotonic()<deadline and not PROMPT.search(port.text[start:]):
        port.pump(.005)
        if not acknowledged and item['language']=='focal':
            finished=kind=='INPUT' and port.frames and port.latency_font.matches(port.frames[-1],item['tag'],0,0)
            stopped=kind=='ESC' and time.monotonic()-key_started>.4
            if finished or stopped:
                port.send(0x30,bytes((37,1)));port.send(0x30,bytes((37,0)));acknowledged=True
    assert PROMPT.search(port.text[start:]),('key not consumed',filename,port.text[start:])
    assert port.attached,'screen detached after a short key'
    elapsed=time.monotonic()-key_started;port.end_measurement()
    text=port.command('prof stop',timeout=20)
    assert 'KBD overflow=0' in text
    out.mkdir();(out/'prof.txt').write_text(text);(out/'terminal.txt').write_bytes(port.text[start:])
    row=dict(filename=filename,kind=kind,key_to_prompt_seconds=elapsed,
        maximum_host_poll_gap_seconds=port.maximum_host_poll_gap,
        gaps=parse_gaps(text),profile=profile(text),pings=len(port.pings),ping_max_seconds=max(port.pings),
        keyboard_overflow=0,screen_stayed_attached=True)
    row['transport']=port.diagnostics()
    save(out/'report.json',row);print(filename,kind,'PASS',round(elapsed*1000,2),'ms key-to-prompt',flush=True)
    return row


def graphics_page(frame,page):
    assert len(frame)==1536
    # Both example pages draw a full-screen BOX. Wait for the transient disk
    # overlay to restore its backing pixels, rather than comparing animation
    # phases or masking any part of the final, complete graphics frame.
    if frame[191]!=0xff or frame[192+191]!=0xff:return False
    def pixel(x,y):return bool(frame[y//8*192+x] & (1 << (y%8)))
    if page==0:
        return (pixel(0,30) and pixel(69,21) and not pixel(90,30)
                and pixel(160,27) and pixel(50,12))
    assert page==1
    return pixel(48,42) and pixel(144,42) and pixel(96,20) and pixel(30,53)


def graphics(port,out):
    """Actual wire10 graphics after cache churn, cold and warm, strict PONG.

    This separate phase does not contaminate the timed arithmetic workload.
    Save complete CRC-checked pages, not just a success marker from BASIC.
    """
    assert 'PROF started' in port.command('prof start')
    out.mkdir();start=len(port.text);first=frames_start=len(port.frames)
    port.begin_measurement();port.write_line('open "/VMLAT/GFXDEMO.tbi"')
    pages=[]
    for page in range(2):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            port.pump(.01)
            frame=next((f for f in reversed(port.frames[first:]) if graphics_page(f,page)),None)
            if frame is not None:break
            assert port.attached,'screen detached during graphics'
            assert not PROMPT.search(port.text[start:]),('graphics ended before page',page,port.text[start:])
        else:raise TimeoutError(('missing graphics page',page))
        stem='primitives' if page==0 else 'graph'
        (out/(stem+'.bin')).write_bytes(frame);png(frame,out/(stem+'.png'))
        pages.append(dict(name=stem,sha256=hashlib.sha256(frame).hexdigest()))
        first=len(port.frames)
        # SHOW publishes the frame just before PAUSE starts waiting. Keep
        # pumping USB while it enters the wait, so OK cannot precede PAUSE.
        port.pump(.2);port.key(37)
    deadline=time.monotonic()+5
    while time.monotonic()<deadline and not PROMPT.search(port.text[start:]):port.pump(.01)
    assert PROMPT.search(port.text[start:]),'graphics did not exit after its second PAUSE'
    port.end_measurement();text=port.command('prof stop',timeout=20)
    assert 'KBD overflow=0' in text
    data=profile(text);assert data['vm_cache_dropped']==0
    assert sum(r['hits']+r['misses'] for r in data['vm_cache'])==1
    (out/'prof.txt').write_text(text);(out/'terminal.txt').write_bytes(port.text[start:])
    row=dict(status='PASS',pages=pages,gaps=parse_gaps(text),profile=data,
        ping_max_seconds=max(port.pings),pings=len(port.pings),
        frames_crc_verified=len(port.frames)-frames_start,transport=port.diagnostics())
    save(out/'report.json',row);print('Graphics two pages PASS',out.name,flush=True)
    return row


def cleanup_files(port,original,created,out):
    current=base.storage_hil.fingerprint(port)
    for remote in set(current['files'])-set(original['files']):
        assert remote in created or base.is_vm_cache(remote),remote
        assert 'Removed 1 entry.' in port.command('rm "'+remote+'"',30),remote
    for remote,detail in original['files'].items():
        if current['files'].get(remote)==detail:continue
        assert remote.casefold().startswith('/system/') and (remote in out['changed_apps'] or base.is_vm_cache(remote)),remote
        payload=(out['original_files']/remote.lstrip('/')).read_bytes()
        assert hashlib.sha256(payload).hexdigest()==detail['sha256']
        base.write_file(port,remote,payload)
    added_dirs=set(current['directories'])-set(original['directories'])
    for remote in added_dirs:
        assert remote.casefold()=='/vmlat',remote
        port.command('rmdir "'+remote+'"',30)
    assert base.storage_hil.fingerprint(port)==original


def load_workload(directory):
    sources={p.name:p.read_bytes() for p in (directory/'sources').iterdir() if p.is_file()}
    capacities={'.m61':1536,'.foc':1536,'.tbi':3584}
    for filename,data in sources.items():
        assert 0<len(data)<=capacities[Path(filename).suffix.lower()],(filename,len(data))
    manifest_data=(directory/'manifest.json').read_bytes()
    manifest=json.loads(manifest_data)
    assert manifest['window_requests']==16*manifest['cycles']
    for module in manifest['modules']:
        assert hashlib.sha256(sources[module['filename']]).hexdigest()==module['source_sha256']
    return dict(sources=sources,manifest=manifest,directory=str(directory.resolve()),
                manifest_sha256=hashlib.sha256(manifest_data).hexdigest())


def install_sources(port,sources,created):
    for filename,data in sorted(sources.items()):
        remote='/VMLAT/'+filename
        if remote in created and base.read_file(port,remote)==data:continue
        created.add(remote)
        base.write_file(port,remote,data);assert base.read_file(port,remote)==data
        print('Installed/read back',remote,len(data),'bytes',flush=True)


def orphan_probe(port,directory):
    """Deliberately emulate the old forbidden two-PING burst, outside timing.

    One atomic OUT write fits one 64-byte CDC packet and readRx's 96-byte
    budget. A responsive firmware may replace the first PONG with the second;
    this is an expected negative control, never a normal latency PASS.
    """
    assert port.outstanding is None and not port.measuring
    assert 'PROF started' in port.command('prof start')
    directory.mkdir();started=time.monotonic();nonce=0xF001
    payloads=(struct.pack('<H',nonce),b'\x61\0');wire=bytearray()
    port.outstanding=(nonce,started);port.measured_sent=1;port.pings=[]
    port.maximum_host_poll_gap=0;port.last_host_poll=None
    for payload in payloads:
        raw=b'MS\x02\x14\0'+struct.pack('<HH',port.sequence,len(payload))+payload
        port.sequence=(port.sequence+1)&65535
        raw+=struct.pack('<H',binascii.crc_hqx(raw,65535))
        wire.extend(b'\0'+cobs_encode(raw)+b'\0')
        port.trace('deliberate-negative-tx',0x14,payload)
    assert len(wire)<=64
    timed_out=False
    try:
        assert os.write(port.fd,wire)==len(wire),'negative probe needs one complete atomic OUT'
        while port.outstanding is not None:port.pump(.005)
    except AssertionError as error:
        if error.args and isinstance(error.args[0],tuple) and error.args[0][0]=='PONG timeout >1s':timed_out=True
        else:raise
    finally:
        transport=port.diagnostics()
        port.outstanding=None;port.measuring=False;port.next_measured_ping=time.monotonic()+.7
    port.pump(.03)
    counters=port.command('prof stop',timeout=20)
    gaps=parse_gaps(counters)
    replies=[e['payload'] for e in transport['last_control_packets']
             if e['at']>=started and e['direction']=='rx' and e['kind']==0x15]
    reproduced=timed_out and replies==['6100']
    row=dict(status='EXPECTED_ORPHAN_REPRODUCED' if reproduced else 'INCONCLUSIVE_PACKET_COALESCING',
        deliberately_violated_single_outstanding_rule=True,expected_timeout=timed_out,
        response_payloads=replies,device_usb_gap_max_us=gaps['usb.service']['max_us'],
        gaps=gaps,transport=transport,not_a_latency_pass=True)
    (directory/'prof.txt').write_text(counters);save(directory/'report.json',row)
    print('PONG single-slot negative control:',row['status'],
          'device USB gap us',round(row['device_usb_gap_max_us'],1),flush=True)
    return row


def run_workload(target,workload,directory,font,probe=False):
    directory.mkdir();manifest=workload['manifest']
    with PingPort(base.PORT) as port:
        port.latency_font=font
        identity=parse_identity(port.command('identity'))
        assert identity.public==base.PUBLIC and identity.build==target['build']
        failed=False
        try:
            port.attach();port.pump(.1)
            negative=orphan_probe(port,directory/'orphan-probe') if probe else None
            prime=batch(port,'PRIME.m61',directory/'prime',32)
            runs=[batch(port,'STRESS.m61',directory/f'warm-{i}',manifest['window_requests']) for i in range(2)]
            keys=[interactive(port,m,directory/Path(m['filename']).stem) for m in manifest['auxiliary']]
            frames=[graphics(port,directory/f'graphics-{i}') for i in range(2)] if 'GFXDEMO.tbi' in workload['sources'] else []
            if frames:assert frames[0]['pages']==frames[1]['pages'],'cold/warm graphics changed'
        except BaseException:
            failed=True
            save(directory/'failure-transport.json',port.diagnostics())
            (directory/'failure-terminal.txt').write_bytes(port.text)
            if port.frames:
                (directory/'failure.frame').write_bytes(port.frames[-1])
                png(port.frames[-1],directory/'failure.png')
            raise
        finally:
            quiesce(port)
            if failed:
                try:(directory/'failure-prof.txt').write_text(port.command('prof stop',timeout=20))
                except (AssertionError,OSError,TimeoutError) as e:print('Failure profile unavailable:',repr(e),flush=True)
        health=base.memory_hil.health(port,target['build'])
        assert 'layout=ok' in health['mpu status']
    return dict(prime=prime,runs=runs,keys=keys,graphics=frames,health=health,
                workload=workload['directory'],manifest_sha256=workload['manifest_sha256'],
                orphan_probe=negative)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('original','baseline','candidate','system-dir','corpus-dir','output-dir'):
        ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--original-build',required=True);ap.add_argument('--original-sha256',required=True)
    ap.add_argument('--single-candidate',action='store_true',help='Diagnostic repetition only, not a matched A/B/A claim')
    ap.add_argument('--resource-corpus-dir',type=Path,help='Also qualify incompressible resources with the same owned source paths')
    ap.add_argument('--orphan-probe',action='store_true',help='First stage only: separately reproduce the old forbidden two-PING burst')
    ap.add_argument('--graphics-example',type=Path,help='Also run both pages of the matching main Graphics.tbi, cold/warm in every corpus/stage')
    a=ap.parse_args();out=a.output_dir.resolve();assert not out.exists();out.mkdir(parents=True);(out/'images').mkdir()
    driver_source=Path(__file__).read_bytes()
    (out/'driver-source.py').write_bytes(driver_source)
    source_patch=subprocess.check_output(['git','-C',str(base.ROOT),'diff','--binary','HEAD','--','code'])
    (out/'resident-source.patch').write_bytes(source_patch)
    images={name:base.capture_image(getattr(a,name),out/'images'/(name+'.bin')) for name in ('original','baseline','candidate')}
    assert images['original']['build']==a.original_build.upper() and images['original']['sha256']==a.original_sha256.lower()
    system={name:(a.system_dir/name).read_bytes() for name in APPS}
    # All fixture size/hash checks precede any device mutation.
    workload=load_workload(a.corpus_dir)
    pressure=load_workload(a.resource_corpus_dir) if a.resource_corpus_dir else None
    if a.graphics_example:
        example=a.graphics_example.read_bytes();assert 0<len(example)<=3584
        (out/'graphics-source.tbi').write_bytes(example)
        for w in (workload,pressure):
            if w:
                assert 'GFXDEMO.tbi' not in w['sources']
                w['sources']['GFXDEMO.tbi']=example
    if pressure:assert pressure['sources'].keys()==workload['sources'].keys()
    from check_app_memory_elf import app_memory_size
    for app in system:app_memory_size(a.system_dir/app)
    font_path=base.ROOT/'programs/games/Turochamp/Turochamp.FMK'
    font=Font(font_path.read_bytes())
    with base.connect(base.PORT,images['original']['build'],wait=0) as port:
        before=base.memory_hil.health(port,images['original']['build']);base.memory_hil.require_empty(before);base.alarms_off(port)
        files=base.snapshot_files(port,out/'original-files')
        installed_font=next(p for p in files['files'] if p.casefold()=='/games/turochamp/turochamp.fmk')
        assert files['files'][installed_font]['sha256']==hashlib.sha256(font_path.read_bytes()).hexdigest()
        assert all(p.casefold()!='/vmlat' for p in files['directories'])
        save(out/'snapshot.json',dict(health=before,files=files,identity=asdict(parse_identity(port.command('identity')))))
    args=SimpleNamespace(port=base.PORT,dfu_util=Path('/Users/bolk/Library/Arduino15/packages/arduino/tools/dfu-util/0.11.0-arduino5/dfu-util'))
    revision=subprocess.check_output(['git','-C',str(base.ROOT),'rev-parse','HEAD'],text=True).strip()
    result=dict(status='RUNNING',stages=[],restored=False,original=images['original'],base_sha=revision,
        scenario='single-candidate diagnostic' if a.single_candidate else 'matched A/B/A',
        driver_sha256=hashlib.sha256(driver_source).hexdigest(),
        resident_source_patch_sha256=hashlib.sha256(source_patch).hexdigest(),
        system_apps={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in system.items()})
    result['workloads']=[dict(directory=w['directory'],manifest_sha256=w['manifest_sha256'])
                         for w in (workload,pressure) if w]
    if a.graphics_example:result['graphics_source_sha256']=hashlib.sha256(example).hexdigest()
    touched=False;changed=set();created=set();passed=False;with_sources=None
    try:
        stages=[('candidate',images['candidate'])] if a.single_candidate else [
            ('baseline',images['baseline']),('candidate',images['candidate']),('control',images['baseline'])]
        for stage_index,(name,target) in enumerate(stages):
            print('Stage',name,target['build'],flush=True);touched=True
            base.memory_hil.flash(args,target,out/(name+'-flash.json'))
            with base.connect(base.PORT,target['build']) as port:
                fast_control(port)
                for app,data in system.items():
                    remote=next(p for p in files['files'] if p.casefold()==('/System/'+app).casefold())
                    if base.read_file(port,remote)!=data:
                        changed.add(remote);base.write_file(port,remote,data);assert base.read_file(port,remote)==data
                        print('Installed/read back',remote,len(data),'bytes',flush=True)
                if with_sources is None:
                    response=port.command('mkdir /VMLAT')
                    assert 'mkdir:' not in response and 'Usage:' not in response,response
                    assert '0 entries.' in port.command('ls /VMLAT')
                else:base.restore_cache(port,with_sources,out/'original-files')
                install_sources(port,workload['sources'],created)
                if with_sources is None:with_sources=base.storage_hil.fingerprint(port)
            stage= dict(name=name,firmware=target,status='RUNNING')
            result['stages'].append(stage)
            stage.update(run_workload(target,workload,out/name,font,a.orphan_probe and stage_index==0))
            save(out/'report.json',result)
            if pressure:
                # Match the ordinary corpus's fresh-resident setup. fsput
                # needs exclusive transfer/stage workspace; retained VM state
                # after INPUT/ESC may reject fixture replacement with PUT_BUSY.
                # This reset is outside all timing/profile windows, for A/B/A
                # alike. Working-set churn is exercised inside each corpus.
                base.reset()
                stage['reset_between_corpora']=True
                save(out/'report.json',result)
                with base.connect(base.PORT,target['build']) as port:
                    fast_control(port)
                    base.restore_cache(port,with_sources,out/'original-files')
                    install_sources(port,pressure['sources'],created)
                stage['resource']=run_workload(target,pressure,out/(name+'-resource'),font)
            stage['status']='PASS'
            if a.graphics_example:
                for w in (stage,stage.get('resource')):
                    if w:assert all(g['pages']==result['stages'][0]['graphics'][0]['pages'] for g in w['graphics']), 'A/B/A graphics mismatch'
            save(out/'report.json',result)
        passed=True
    except BaseException as error:
        result.update(status='FAIL',error=repr(error));save(out/'report.json',result)
        print('Latency check failed:',repr(error),flush=True)
        raise
    finally:
        try:
            if touched:
                print('Restoring exact original firmware/files/state',flush=True)
                try:base.reset()
                except (OSError,TimeoutError) as e:result['reset_transport_error']=repr(e)
                base.memory_hil.flash(args,images['original'],out/'restore-flash.json')
                with base.connect(base.PORT,images['original']['build']) as port:
                    fast_control(port)
                    cleanup_files(port,files,created,dict(changed_apps=changed,original_files=out/'original-files'))
                    final=base.memory_hil.health(port,images['original']['build']);base.memory_hil.require_empty(final);base.alarms_off(port)
                    for key in ('reg','stk','dump','pwd'):
                        assert state_without_prompt_padding(final[key])==state_without_prompt_padding(before[key]),(key,before[key],final[key])
                    assert base.storage_hil.fingerprint(port)==files
                result.update(restored=True,files_preserved=True,calculator_preserved=True,serial_closed=True,
                    mini_touched=False,read_retries=base.read_retries,health_after=final)
                print('Exact restoration PASS; CDC closed',flush=True)
            result['status']='PASS' if passed and result['restored'] else 'FAIL'
        except BaseException as error:
            result.update(status='FAIL',cleanup_error=repr(error));raise
        finally:save(out/'report.json',result)
    print('Latency',result['scenario'],result['status'],flush=True)


if __name__=='__main__':main()
