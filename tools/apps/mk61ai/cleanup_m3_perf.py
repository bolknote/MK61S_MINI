#!/usr/bin/env python3
"""Bounded cleanup of one proved returned AI diagnostic; never replays inference."""
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
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,why):
    if not ok: raise ValueError(why)

def validate(path,grant_path):
    p=json.loads(path.read_text());g=json.loads(grant_path.read_text());now=time.time()
    need(p['action']=='owned-returned-ai-cleanup' and p['deadline_seconds']==120 and
         p['controller_sha256']==sha(__file__) and p['save_or_restore'] is False,'cleanup scope')
    need(g['decision']=='GO' and g['coordinator_thread']==COORDINATOR and g['phase_sha256']==sha(path) and
         g['not_before']<=now<=g['start_before']<g['finish_before'] and 0<g['finish_before']-now<=300,'fresh ROOT cleanup grant')
    for item in p['payloads'].values():
        f=Path(item['path']);need(f.is_absolute() and f.stat().st_size==item['bytes'] and sha(f)==item['sha256'],'cleanup payload changed')
    original=json.loads(Path(p['payloads']['original_phase']['path']).read_text())
    receipt=json.loads(Path(p['payloads']['receipt']['path']).read_text())
    supervisor=json.loads(Path(p['payloads']['supervisor']['path']).read_text())
    need(original['action']=='perf' and original['config']['cores']==3 and receipt['status']=='HOLD' and
         receipt['cdc_closed'] and supervisor['reaped'] and supervisor['phase_sha256']==sha(p['payloads']['original_phase']['path']),
         'original phase not returned/closed/reaped')
    need(json.loads(Path(p['payloads']['owned']['path']).read_text())==
         ['/AI/'+original['nonce'],'/Apps/MK61AI/'+original['nonce']],'owned paths mismatch')
    foreground=set(json.loads(Path(p['payloads']['foreground']['path']).read_text()))
    folder='/Apps/MK61AI/'+original['nonce']
    need(folder+'/AIBENCH.APP' in foreground and foreground <= {folder+'/AIBENCH.APP',folder+'/AIHASH.APP'},
         'foreign foreground proof')
    return p,g,original

def worker(p,g,original,out):
    sys.path.insert(0,str(Path(p['payloads']['ai_helper']['path']).parent))
    import hil_mk61_ai as ai
    lease_fd=None;port=None
    r=dict(status='HOLD',original_measurement_status='HOLD',physical_io=True,save_or_restore=False,
           inference_replayed=False,flash=False,reset=False,m3_unload_sent=False,temporary_removed=False)
    def health(s,closed=False):
        values={}
        for k in ('BUILD','ACTUAL','EXPECTED','FIRMWARE_CRC','BOOTS','CRASH','SYS_HZ','PERI_HZ','RUN','BUSY',
                  'USB_DISK','PHYSICAL_KEYS','SETTINGS_WRITES','RTC_SET','APP_BUFFERS','ERRORS','QPI_FALLBACKS',
                  'TAIL_TIMEOUTS','CRC_ERRORS','DMA_TIMEOUTS','LCD_ERRORS','SD_SPEED_FALLBACKS','SD_PROBE_FAILURES',
                  'I2C_TIMEOUTS','I2C_ABORTS','SCREEN_ERRORS'):
            m=re.search(r'(?<![A-Za-z0-9_])'+k+r'=([^ \r\n]+)',s);need(m is not None,'missing health '+k);values[k]=m[1]
        for k,v in dict(BUILD=original['new_build'],ACTUAL=original['new_crc'],EXPECTED=original['new_crc'],
                        FIRMWARE_CRC='valid',BOOTS='4',CRASH='NONE',SYS_HZ='125000000',PERI_HZ='48000000',
                        RUN='0',BUSY='0',USB_DISK='0',PHYSICAL_KEYS='0',SETTINGS_WRITES='0',RTC_SET='0').items():
            need(values[k]==v,'unexpected cleanup '+k)
        if closed: need(values['APP_BUFFERS']=='0','APP buffers retained after cleanup')
        for k in ('ERRORS','QPI_FALLBACKS','TAIL_TIMEOUTS','CRC_ERRORS','DMA_TIMEOUTS','LCD_ERRORS',
                  'SD_SPEED_FALLBACKS','SD_PROBE_FAILURES','SCREEN_ERRORS'): need(values[k]=='0','new error '+k)
        return values
    try:
        lease=Path(original['root_lease_path']);lease_fd=os.open(lease,os.O_RDONLY|os.O_NOFOLLOW)
        info=os.fstat(lease_fd);need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and
                                    info.st_ino==original['root_lease_inode'],'ROOT lease identity')
        fcntl.flock(lease_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        port=ai.Serial(time.monotonic()+min(120,g['finish_before']-time.time()-5));ai.usb_identity()
        s=port.status();r['admission']=health(s)
        foreground=set(json.loads(Path(p['payloads']['foreground']['path']).read_text()))
        need('RUNTIME=NONE' in s,'foreign/running APP');ai.cleanup_status(s,original,foreground)
        # Observe idle growth without accepting a new counter as a repair.
        time.sleep(1);r['idle_observation']=health(port.status())
        performance=json.loads(Path(p['payloads']['performance']['path']).read_text())
        m3=performance['results'][1]['m3']
        need(m3['jobs']>0 and not m3['error'] and not m3['unload_failures'],'no completed owned module-empty proof')
        r['module_empty_proof']='completed native backend UNLOAD + HELLO EMPTY; recorded zero unload failures'
        owned=json.loads(Path(p['payloads']['owned']['path']).read_text())
        r['native_final']=ai.cleanup(port,original,owned,foreground)
        r['temporary_removed']=True;r['after_cleanup']=health(port.status(),True)
        time.sleep(1);r['idle_after_cleanup']=health(port.status(),True)
        r['i2c_deltas']={k:{'admission':int(r['admission'][k]),
            'idle_before':int(r['idle_observation'][k])-int(r['admission'][k]),
            'cleanup':int(r['after_cleanup'][k])-int(r['idle_observation'][k]),
            'idle_after':int(r['idle_after_cleanup'][k])-int(r['after_cleanup'][k])}
            for k in ('I2C_TIMEOUTS','I2C_ABORTS')}
        r['status']='CLEANUP_COMPLETE_ORIGINAL_HOLD'
    except BaseException as e: r['error']=type(e).__name__+': '+str(e)
    finally:
        if port: port.close()
        r['cdc_closed']=port is None or port.fd==-1
        if lease_fd is not None: os.close(lease_fd)
        r['shared_lock_released']=True
        (out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
    need(r['status']=='CLEANUP_COMPLETE_ORIGINAL_HOLD',r.get('error','cleanup HOLD'))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('phase','grant','output'): ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--worker',action='store_true');a=ap.parse_args();p,g,original=validate(a.phase,a.grant)
    a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/('worker-attempt.json' if a.worker else 'attempt.json')).open('x')as f:json.dump({'phase_sha256':sha(a.phase)},f)
    if a.worker: worker(p,g,original,a.output);return
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'--phase',str(a.phase.resolve()),
             '--grant',str(a.grant.resolve()),'--output',str(a.output.resolve()),'--worker']
    with(a.output/'worker.log').open('w')as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        record=dict(pid=child.pid,reaped=False)
        try:child.wait(timeout=min(130,g['finish_before']-time.time()-2))
        finally:
            if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5);record['forced_stop']=True
            record.update(reaped=True,exit_code=child.returncode);(a.output/'supervisor.json').write_text(json.dumps(record,indent=2)+'\n')
        if child.returncode: raise SystemExit(child.returncode)
if __name__=='__main__':main()
