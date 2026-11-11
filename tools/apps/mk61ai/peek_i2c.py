#!/usr/bin/env python3
"""One bounded read-only I2C-register APP; no resets, inference or STM32 traffic."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

COORDINATOR='01a164b7-9caa-7011-90d1-807e9630921c'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,why):
    if not ok:raise ValueError(why)
def validate(path,gpath):
    p=json.loads(path.read_text());g=json.loads(gpath.read_text());now=time.time()
    need(p['action']=='read-only-i2c-peek' and p['deadline_seconds']==90 and p['controller_sha256']==sha(__file__), 'scope changed')
    need(g['decision']=='GO' and g['coordinator_thread']==COORDINATOR and g['phase_sha256']==sha(path) and
         g['not_before']<=now<=g['start_before']<g['finish_before'] and 0<g['finish_before']-now<=240,'no fresh ROOT grant')
    need(re.fullmatch('HILV3-I2C-[A-F0-9]{12}',p['nonce']),'unsafe nonce')
    for v in p['payloads'].values():
        f=Path(v['path']);need(f.is_absolute() and f.stat().st_size==v['bytes'] and sha(f)==v['sha256'],'payload changed')
    return p,g
def worker(p,g,out):
    sys.path.insert(0,str(Path(p['payloads']['helper']['path']).parent))
    import hil_mk61_ai as a
    fd=None;port=None;owned=[]
    r=dict(status='HOLD',original_measurement_status='HOLD',physical_io=True,flash=False,reset=False,
           mmio_writes=False,inference=False,stm32_commands=False,save_or_restore=False,temporary_removed=False)
    def health(s,closed=False):
        d={}
        for k in ('BUILD','ACTUAL','EXPECTED','FIRMWARE_CRC','BOOTS','CRASH','SYS_HZ','PERI_HZ','PHYSICAL_KEYS',
                  'SETTINGS_WRITES','RTC_SET','APP_BUFFERS','RUN','BUSY','USB_DISK','KBD','I2C_TIMEOUTS','I2C_ABORTS',
                  'I2C_IRQS','I2C_TRANSACTIONS','I2C_BUSY_US','I2C_SLEEP_HOLDS','SLEEP_CLOCK0','SLEEP_CLOCK1',
                  'ERRORS','QPI_FALLBACKS','TAIL_TIMEOUTS','CRC_ERRORS','DMA_TIMEOUTS','LCD_ERRORS','SCREEN_ERRORS'):
            m=re.search(r'(?<![A-Za-z0-9_])'+k+r'=([^ \r\n]+)',s);need(m is not None,'missing '+k);d[k]=m[1]
        for k,v in dict(BUILD=p['build'],ACTUAL=p['crc'],EXPECTED=p['crc'],FIRMWARE_CRC='valid',BOOTS='4',CRASH='NONE',
                        SYS_HZ='125000000',PERI_HZ='48000000',PHYSICAL_KEYS='0',SETTINGS_WRITES='0',RTC_SET='0',RUN='0',BUSY='0',USB_DISK='0',
                        ERRORS='0',QPI_FALLBACKS='0',TAIL_TIMEOUTS='0',CRC_ERRORS='0',DMA_TIMEOUTS='0',LCD_ERRORS='0',SCREEN_ERRORS='0').items():
            need(d[k]==v,'unexpected '+k)
        need('RUNTIME=NONE' in s,'running/unknown owner')
        if closed:need('SERVICE=CLOSED' in s and 'UI=CALCULATOR' in s and d['APP_BUFFERS']=='0','native not closed')
        return d
    def present(parent,leaf):
        cmd='ls "'+parent+'"';rows=a.listing_rows(port.command(cmd),cmd)
        return any(row.split(b'\t')[-1].rstrip(b'/').lower()==leaf.lower().encode()for row in rows)
    try:
        fd=os.open(p['lease'],os.O_RDONLY|os.O_NOFOLLOW);info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_ino==p['lease_inode'],'ROOT lease changed')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        a.usb_identity();port=a.Serial(time.monotonic()+min(90,g['finish_before']-time.time()-5))
        s=port.status();r['entry']=health(s)
        if 'SERVICE=CLOSED' not in s:
            need('PATH=['+p['previous_probe_path']+']' in s,'unknown previous foreground')
        a.leave_app(port);a.identity(port)
        previous=p['previous_probe_path']
        if present(*previous.rsplit('/',1)):
            need(sha(Path(p['payloads']['previous_app']['path']))==hashlib.sha256(a.download(port,previous)).hexdigest(),
                 'old probe file changed')
            port.command('rm -r "'+previous.rsplit('/',1)[0]+'"',20)
        r['previous_probe_removed']=not present('/Apps/MK61AI',previous.split('/')[-2])
        r['old_owned_absent']={x:not present(*x.rsplit('/',1))for x in p['old_owned_paths']}
        folder='/Apps/MK61AI/'+p['nonce'];a.create_owned(port,folder,owned,out)
        app=folder+'/I2CPEEK.APP';a.upload(port,app,Path(p['payloads']['app']['path']).read_bytes(),out/'upload-fault.bin')
        port.data.clear();port.send(('run "'+app+'"\r').encode());raw=port.wait(lambda b:a.PROMPT.search(b),15)
        (out/'probe-output.txt').write_bytes(raw)
        rows=re.findall(rb'(?m)^AI_I2C_PEEK ([^\r\n]+)',raw)
        need(len(rows)==16 and b'ERROR' not in raw,'probe did not return sixteen successful samples')
        samples=[]
        for i,row in enumerate(rows):
            d=dict(x.split('=')for x in row.decode().split());need(int(d['i'])==i,'sample ordering')
            need(set(d)==set('i CON EN ES ST RAW MASK TX RX ABRT HC LC PINS F6 F7 S0 S1 RD'.split()),'sample fields')
            samples.append({k:int(v,10 if k in ('i','TX','RX','HC','LC')else 16)for k,v in d.items()})
        r['samples']=samples;s=port.status();r['after_probe']=health(s)
        a.cleanup_status(s,dict(new_build=p['build'],new_crc=p['crc']),{app});a.leave_app(port)
        port.command('rm -r "'+folder+'"',20);need(not present('/Apps/MK61AI',p['nonce']),'probe directory retained')
        r['temporary_removed']=True;port.send(b'\x1e');r['final']=health(port.status(),True)
        r['status']='DIAGNOSTIC_COMPLETE_ORIGINAL_HOLD'
    except BaseException as e:r['error']=type(e).__name__+': '+str(e)
    finally:
        if port:port.close()
        r['cdc_closed']=port is None or port.fd==-1
        if fd is not None:os.close(fd)
        r['shared_lock_released']=True;(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
    need(r['status']=='DIAGNOSTIC_COMPLETE_ORIGINAL_HOLD',r.get('error','HOLD'))
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('phase','grant','output'):ap.add_argument('--'+k,type=Path,required=True)
    ap.add_argument('--worker',action='store_true');q=ap.parse_args();p,g=validate(q.phase,q.grant);q.output.mkdir(parents=True,exist_ok=True)
    with(q.output/('worker-attempt.json'if q.worker else'attempt.json')).open('x')as f:json.dump({'phase_sha256':sha(q.phase)},f)
    if q.worker:worker(p,g,q.output);return
    cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'--phase',str(q.phase.resolve()),'--grant',str(q.grant.resolve()),'--output',str(q.output.resolve()),'--worker']
    with(q.output/'worker.log').open('w')as log:
        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);record=dict(pid=child.pid,reaped=False)
        try:child.wait(timeout=min(100,g['finish_before']-time.time()-2))
        finally:
            if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5);record['forced_stop']=True
            record.update(reaped=True,exit_code=child.returncode);(q.output/'supervisor.json').write_text(json.dumps(record,indent=2)+'\n')
        if child.returncode:raise SystemExit(child.returncode)
if __name__=='__main__':main()
