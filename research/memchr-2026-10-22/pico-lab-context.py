"""Memchr-specific adapter for the existing raw Pico SD/CDC transport.

Importing it opens no device. Original and diagnostic identities are supplied
by the independently verified BIN/ELF proof, never inferred from CRC == BUILD.
"""
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
RAW=ROOT/'.build/picocalc-fresh-sd-verifier-20261023/sd-only-v2'
sys.path.insert(0,str(RAW/'lib'));sys.path.insert(0,str(ROOT/'tests'))
from transaction_core import assert_health, field, parse_listing, require
import status_frames
from hil_rtc_alarm import Port
from session import Hold

spec=importlib.util.spec_from_file_location('memchr_existing_raw_transport',RAW/'transport.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
RawPort=transport.port_class(Port,status_frames,require)


def canonical(command,reply):
    require(reply.startswith(command+'\r\n') and reply.endswith('\r\nmk61> '),
            'Uncorrelated Pico command envelope')
    return reply[len(command)+2:-len('\r\nmk61> ')]


def settings(status):
    result={}
    for prefix in ('UI_FONT_FAMILY=','UI='):
        rows=[line.rstrip('\r') for line in status.splitlines() if line.startswith(prefix)]
        require(len(rows)==1,'Missing/duplicate settings row');result[prefix]=rows[0]
    for name in ('SETTINGS_WRITES','SETTINGS_ERASES','SETTINGS_SEQUENCE','RTC_SET','RTC_PPM'):
        values=re.findall(r'\b'+name+r'=(-?\d+)\b',status)
        require(len(values)==1,'Missing/duplicate setting '+name);result[name]=int(values[0])
    return result


class Context:
    def __init__(self,build,crc,image_bytes,guard,expected_settings=None):
        self.build=build;self.crc=crc;self.image_bytes=image_bytes;self.guard=guard
        self.expected_settings=expected_settings;self.boot=None;self.reset=None
        self.directory='/MCHR-Q01';self.app_path=self.directory+'/CHRBEN.APP'
        self.state={};self.observed_first=None

    def observe_status(self,frame):self.observed_first=frame

    def health(self,status,candidate=False,service='CLOSED'):
        self.guard();assert_health(status,self.build,self.crc,self.image_bytes)
        for token in ('RUN=0 BUSY=0','DIRTY=0','RUNTIME=NONE','USB_DISK=0',
                      'USB_SCREEN=OFF','M61_ACTIVE=0 SUSPENDED=0','SERVICE='+service+' '):
            require(token in status,'Unexpected memchr foreground: '+token)
        require(field(status,'SYS_HZ')==125000000,'Physical system clock is not125MHz')
        if self.boot is None:self.boot=field(status,'BOOTS');self.reset=field(status,'RESET_REASON',16)
        require(field(status,'BOOTS')==self.boot and field(status,'RESET_REASON',16)==self.reset,
                'Unexpected reboot within this memchr CDC session')
        current=settings(status)
        if self.expected_settings is not None:require(current==self.expected_settings,'Pico settings changed')

    def heap(self,port):
        reply=port.command('profile heap');body=canonical('profile heap',reply)
        keys=('HEAP_BYTES','HEAP_USED','HEAP_FREE','HEAP_ARENA','HEAP_FREE_BLOCKS','HEAP_TOP')
        return {name:field(body,name) for name in keys}

    def listing(self,port,directory):
        command='ls /' if directory=='/' else 'ls "'+directory+'"'
        reply=port.command(command,timeout=30)
        canonical(command,reply)
        return parse_listing(reply,directory)

    def capture(self,port,label,output):
        self.health(port.status())
        result={}
        for command in ('reg','stk','hout','pwd','alarm'):
            result[command]=canonical(command,port.command(command))
        alarm=result['alarm'].split('\r\n')
        require(len(alarm)==2 and all(re.fullmatch('ALARM '+slot+r' OFF ONCE 20\d\d-\d\d-\d\d \d\d:\d\d:\d\d',line)
                                     for slot,line in zip(('A','B'),alarm)),'Memchr requires unarmed alarms')
        begin=time.monotonic_ns();reply=port.command('date');end=time.monotonic_ns()
        date=canonical('date',reply)
        require(re.fullmatch(r'20\d\d-\d\d-\d\d \d\d:\d\d:\d\d',date),'Unrecognized current RTC')
        result['clock']=dict(rtc=date,monotonic_before_ns=begin,monotonic_after_ns=end,wall=time.time())
        result['settings']=settings(port.status())
        (Path(output)/(label+'.json')).write_text(json.dumps(result,indent=2)+'\n')
        return result

    @staticmethod
    def compare(before,after):
        for name in ('reg','stk','hout','pwd','alarm','settings'):
            require(before[name]==after[name],'Pico matrix changed '+name)
        first,last=before['clock'],after['clock'];ppm=before['settings']['RTC_PPM']
        require(-500<=ppm<=500,'Unknown RTC correction')
        rate=46875/((46875*(1000000-ppm)+500000)//1000000)
        lo=(last['monotonic_before_ns']-first['monotonic_after_ns'])/1e9
        hi=(last['monotonic_after_ns']-first['monotonic_before_ns'])/1e9
        elapsed=(datetime.fromisoformat(last['rtc'])-datetime.fromisoformat(first['rtc'])).total_seconds()
        require(0<=lo<=hi and lo*rate-3-hi/93750<=elapsed<=hi*rate+3+hi/93750,
                'Pico matrix changed current RTC trajectory')


class MatrixPort(RawPort):
    def send_bytes(self,value,purpose):
        self.t.guard();return super().send_bytes(value,purpose)

    def allowed_command(self,command):
        self.t.guard()
        if command=='profile heap' or command=='ls "'+self.t.directory+'"':
            require(not self.app_inflight,'Command into running APP');return
        return super().allowed_command(command)

    def open(self,path):
        self.t.guard();return super().open(path)

    def command(self,command,timeout=8):
        reply=super().command(command,timeout)
        canonical(command,reply)
        return reply


def physical_usb(output,port,location=18022400):
    """Only the caller under its active lease may invoke this read-only gate."""
    import subprocess
    result=subprocess.run(['/usr/sbin/ioreg','-a','-l','-r','-c','IOUSBHostDevice'],capture_output=True,check=True)
    require(not result.stderr,'ioreg failed');(Path(output)/'usb-before.plist').write_bytes(result.stdout)
    transport.usb_admission(result.stdout,'E6657CD423721C35',location,port)
    result=subprocess.run(['/usr/sbin/lsof','-nP','-t','--',port],capture_output=True)
    (Path(output)/'lsof-before.json').write_text(json.dumps(dict(returncode=result.returncode,
        stdout=result.stdout.decode(errors='replace'),stderr=result.stderr.decode(errors='replace')),indent=2)+'\n')
    require(result.returncode==1 and not result.stdout and not result.stderr,'Pico CDC is held/unknown')
