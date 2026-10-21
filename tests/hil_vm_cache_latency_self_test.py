#!/usr/bin/env python3
"""Offline HIL parser/CRC/nonce checks, never open a physical port."""
import binascii
import struct
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
from hil_portable_apps import cobs_encode,ScreenPort
from hil_vm_cache_latency import checked_packet,parse_gaps,PingPort,FocalAcknowledger,fast_control,graphics_page,graphics,state_without_prompt_padding,require_launch_count


def packet(payload):
    raw=b'MS\x02\x15\0'+struct.pack('<HH',1,len(payload))+payload
    return cobs_encode(raw+struct.pack('<H',binascii.crc_hqx(raw,65535)))


names=['keyboard.poll','keyboard.sample',*[f'keyboard.row{i}' for i in range(5)],'usb.service']
flash='VMFLASH budget=32768 payload=32000 used=20000 lookups=110 hits=100 misses=10\n'
flash_data=dict(vm_cache_dropped=0,vm_cache=[],points={'vm.invoke':{'calls':32}})
assert require_launch_count(flash,flash_data,32)['engine']=='flash'
ram_data=dict(vm_cache_dropped=0,vm_cache=[dict(hits=16,misses=16)],points={})
assert require_launch_count('',ram_data,32)==dict(engine='ram',launches=32)
for raw,data,count in ((flash,flash_data,31),('',flash_data,32),
        (flash+flash,flash_data,32),(flash.replace('hits=100','hits=99'),flash_data,32),
        (flash.replace('used=20000','used=32001'),flash_data,32),
        (flash.replace('budget=32768','budget=65536'),flash_data,32),
        ('VMFLASH budget=32768 payload=32000 used=0 lookups=0 hits=0 misses=0\n',flash_data,32),
        (flash,{**flash_data,'points':{}},32),
        (flash,{**flash_data,'vm_cache_dropped':1},32),('',ram_data,31)):
    try:require_launch_count(raw,data,count)
    except AssertionError:pass
    else:raise AssertionError('invalid VM launch accounting accepted')
state='reg\r\nX = 0.000000 +00\r\n/>'
assert state_without_prompt_padding(state)==state_without_prompt_padding(state+' ')
for changed in (state.replace('0.000000','1.000000'),state.replace('+00','+01'),
                state.replace('X =','X  ='),state.replace('/>','/Games>')):
    assert state_without_prompt_padding(changed)!=state_without_prompt_padding(state)
for invalid in ('',state+'  ',state+'\r\n',state+' unexpected',state[:-1]):
    try:state_without_prompt_padding(invalid)
    except AssertionError:pass
    else:raise AssertionError('non-prompt state suffix ignored')
for page,points in enumerate((((0,30),(69,21),(160,27),(50,12)),((48,42),(144,42),(96,20),(30,53)))):
    frame=bytearray(1536)
    assert not graphics_page(frame,page)
    for x,y in points:frame[y//8*192+x]|=1 << (y%8)
    assert not graphics_page(frame,page)  # Full BOX border is still missing.
    frame[191]=frame[192+191]=0xff
    assert graphics_page(frame,page) and not graphics_page(frame,1-page)
    for animation in (0,0x0c):
        overlaid=bytearray(frame);overlaid[191]=0;overlaid[192+191]=animation
        assert not graphics_page(overlaid,page)  # Neither disk phase is artwork.
    if page==0:
        frame[30//8*192+90]|=1 << (30%8)
        assert not graphics_page(frame,page)
text='\n'.join(f'GAP {name} n=5 max=2976000 total=4848000 over1=4 over5=3 over10=2 over30=1' for name in names)+'\n'
rows=parse_gaps(text);assert len(rows)==8 and rows['keyboard.row4']['max_us']==31000
for invalid in (text+text.splitlines()[0]+'\n',text.replace('keyboard.row4','bad'),
                text.replace('over30=1','over30=3'),text.replace('n=5','n=0')):
    try:parse_gaps(invalid)
    except AssertionError:pass
    else:raise AssertionError('invalid gap report accepted')
p=PingPort.__new__(PingPort)
p.packets_crc_verified=0;p.outstanding=(0xA101,time.monotonic()-.01);p.pings=[]
p.receive_packet(packet(b'\x61\0'))  # Previous automatic heartbeat is not our sample.
assert p.outstanding and not p.pings
p.receive_packet(packet(struct.pack('<H',0xA101)))
assert p.outstanding is None and len(p.pings)==1 and p.pings[0]>=.01
p.outstanding=(0xA102,time.monotonic())
try:p.receive_packet(packet(struct.pack('<H',0xA103)))
except AssertionError:pass
else:raise AssertionError('wrong PONG nonce accepted')
p.outstanding=(0xA104,time.monotonic()-1.1)
try:p.receive_packet(packet(struct.pack('<H',0xA104)))
except AssertionError:pass
else:raise AssertionError('late PONG accepted after a delayed host poll')
encoded=bytearray(packet(b'ab'));encoded[-1]^=1
try:checked_packet(encoded)
except AssertionError:pass
else:raise AssertionError('bad packet CRC accepted')
class FakeFont:
    def matches(self,frame,label,row,col):
        assert row==col==0
        return frame==label
ack=FocalAcknowledger(FakeFont(),32)
assert not ack.consume('LATF07') and not ack.consume('LATB00')
for label in ack.expected:
    assert ack.consume(label)
    assert not ack.consume(label)  # An old completed frame is not another key.
assert ack.seen==ack.expected and not ack.consume('LATF00')
class FakePort:
    def __init__(self):self.text=bytearray();self.pumps=[]
    def pump(self,duration):self.pumps.append(duration)
    def write_line(self,line):self.text.extend((line+'\r\n@MKC:ACK 48\r\n/> ').encode())
port=fast_control(FakePort())
assert '@MKC:ACK 48' in port.command('fsput data 0 1234')
assert port.pumps==[.002,.005]


def final_pong_survives_keepalive(service_at,expect_timeout=False):
    """Real one-response-slot policy, a device gap below the unchanged 1 s cap.

    VER may arrive before M61's scoped-font cleanup. The final measured PING
    remains in RX while the host drains at end_measurement(). An untracked
    keepalive queued behind it would overwrite its PONG in firmware readRx().
    """
    class Clock:
        now=.1
        def __call__(self):return self.now
    clock=Clock();nonce=0xA101;payload=struct.pack('<H',nonce)
    queued=[payload];sent=[];serviced=[]
    port=PingPort.__new__(PingPort)
    port.attached=True;port.measuring=True;port.outstanding=(nonce,0)
    port.pings=[];port.packets_crc_verified=0;port.frames=[]
    port.last_host_poll=None;port.maximum_host_poll_gap=0
    port.measured_sent=1
    port.next_measured_ping=0;port.next_ping=0
    def send(kind,body):
        assert kind==0x14
        sent.append((clock.now,body));queued.append(body)
    port.send=send
    def pump_transport(self,duration):
        assert self is port
        clock.now+=duration
        if clock.now>=service_at and not serviced:
            # queueResponse overwrites the single pending response for every
            # PING consumed by one bounded readRx(), before scheduleTx().
            serviced.extend(queued);reply=queued[-1];queued.clear()
            port.receive_packet(packet(reply))
    with patch('hil_vm_cache_latency.time.monotonic',clock),patch.object(ScreenPort,'pump',pump_transport):
        if expect_timeout:
            try:port.end_measurement()
            except AssertionError as error:assert error.args[0][0]=='PONG timeout >1s',error
            else:raise AssertionError('actual late device response did not fail')
            assert sent==[] and serviced==[]
            return
        try:port.end_measurement()
        except AssertionError as error:
            raise AssertionError(('final PONG preempted by host keepalive',sent,serviced,str(error))) from error
    assert sent==[],sent
    assert serviced==[payload] and port.outstanding is None
    assert len(port.pings)==1 and service_at<=port.pings[0]<service_at+.006


for delay in (.2,.7,.85,.99):final_pong_survives_keepalive(delay)
final_pong_survives_keepalive(1.05,expect_timeout=True)
port=PingPort.__new__(PingPort);port.outstanding=(0xA101,0)
with patch.object(ScreenPort,'send') as transport:
    try:port.send(0x14,b'\x61\0')
    except AssertionError:pass
    else:raise AssertionError('untracked PING reached the physical transport while draining')
    transport.assert_not_called()
port=PingPort.__new__(PingPort);port.outstanding=None;port.automatic_pending=True
with patch.object(ScreenPort,'send') as transport:
    for payload in (b'\x61\0',struct.pack('<H',0xA101)):
        try:port.send(0x14,payload)
        except AssertionError:pass
        else:raise AssertionError('another PING preempted a pending automatic PONG')
    transport.assert_not_called()
port.measuring=False;port.pings=[];drained=[]
def drain_automatic(duration):
    assert duration==.005 and port.next_measured_ping==float('inf')
    assert not port.measuring
    drained.append(True);port.receive_packet(packet(b'\x61\0'))
port.pump=drain_automatic;port.packets_crc_verified=0
port.begin_measurement()
assert drained==[True] and port.measuring and not port.automatic_pending
port=PingPort.__new__(PingPort)
port.attached=True;port.measuring=True;port.outstanding=None;port.nonce=0x60
port.automatic_pending=False;port.next_measured_ping=0;port.measured_sent=0
port.last_host_poll=None;port.maximum_host_poll_gap=0;sent=[]
def record_sample(kind,payload):
    assert kind==0x14;sent.append(payload)
port.send=record_sample
nonce_clock=[0.0]
def advance_nonce_clock(self,duration):nonce_clock[0]+=duration
with patch('hil_vm_cache_latency.time.monotonic',lambda:nonce_clock[0]),patch.object(ScreenPort,'pump',advance_nonce_clock):
    port.pump(.001)
assert sent==[b'\x62\0'] and port.outstanding[0]==0x62

# Exercise both page waits and SHOW -> PAUSE pacing without a real device.
# A stale initial page must not be mistaken for the newly launched program.
class GraphicsClock:
    now=0.
    def __call__(self):return self.now
graphics_clock=GraphicsClock()
class GraphicsPort:
    def __init__(self):
        self.text=bytearray(b'/> ');self.frames=[self.page(0)];self.attached=True
        self.phase=0;self.published=None;self.pings=[.005];self.measuring=False
        self.overlay_started=None
    @staticmethod
    def page(index):
        frame=bytearray(1536)
        frame[191]=frame[192+191]=0xff
        points=(((0,30),(69,21),(160,27),(50,12)),((48,42),(144,42),(96,20),(30,53)))[index]
        for x,y in points:frame[y//8*192+x]|=1 << (y%8)
        return bytes(frame)
    def command(self,command,timeout=5):
        if command=='prof start':return 'PROF started'
        assert command=='prof stop' and not self.measuring
        return 'KBD overflow=0\n'+text+flash
    def write_line(self,line):assert line=='open "/VMLAT/GFXDEMO.tbi"'
    def begin_measurement(self):self.measuring=True
    def end_measurement(self):self.measuring=False
    def pump(self,duration):
        graphics_clock.now+=duration
        if self.overlay_started is None:
            frame=bytearray(self.page(self.phase));frame[191]=0;frame[192+191]=0x0c
            self.frames.append(bytes(frame));self.overlay_started=graphics_clock.now
        elif self.published is None and graphics_clock.now-self.overlay_started>=.17:
            self.frames.append(self.page(self.phase));self.published=graphics_clock.now
    def key(self,key):
        assert key==37 and graphics_clock.now-self.published>=.199
        self.phase+=1
        if self.phase==1:self.published=None;self.overlay_started=None
        else:self.text.extend(b'/> ')
    def diagnostics(self):return dict(measured_sent=1,measured_replies=1)
with tempfile.TemporaryDirectory(prefix='mk61-graphics-hil-offline-') as temporary:
    port=GraphicsPort()
    with patch('hil_vm_cache_latency.time.monotonic',graphics_clock), \
         patch('hil_vm_cache_latency.png'), \
         patch('hil_vm_cache_latency.profile',return_value=dict(vm_cache_dropped=0,vm_cache=[dict(hits=1,misses=0)])):
        result=graphics(port,Path(temporary)/'pages')
    assert result['status']=='PASS' and result['frames_crc_verified']==4
    assert [p['name'] for p in result['pages']]==['primitives','graph']
    assert len(list(Path(temporary).rglob('*.bin')))==2
    for index,name in enumerate(('primitives','graph')):
        assert (Path(temporary)/'pages'/(name+'.bin')).read_bytes()==port.page(index)
    graphics_clock.now=0
    port=GraphicsPort()
    with patch('hil_vm_cache_latency.time.monotonic',graphics_clock), \
         patch('hil_vm_cache_latency.png'), \
         patch('hil_vm_cache_latency.profile',return_value=dict(vm_cache_dropped=0,vm_cache=[],points={'vm.invoke':{'calls':1}})):
        result=graphics(port,Path(temporary)/'flash-pages')
    assert result['launch_accounting']['engine']=='flash' and result['launch_accounting']['launches']==1
print('Cache latency HIL: RAM/Flash launch accounting, gaps, CRC/nonce, single-slot race, 1s deadline, complete graphics after disk overlay PASS')
