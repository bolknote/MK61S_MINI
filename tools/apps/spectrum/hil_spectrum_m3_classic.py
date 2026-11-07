#!/usr/bin/env python3
"""Finite Classic M4 comparison of unchanged M3 synth binaries. No flashing."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import termios
import time
import statistics

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tests'))
from hil_classic_cdc_guard import current_binding,require_no_holders
from hil_rtc_alarm import Port,canonical_state_reply
from hil_multi_device_identity import parse_identity
from hil_c6_system_bootstrap import write_file
from hil_c5_stack import read_file
from hil_usb_disk_transaction import listing_entries

PUBLIC='AEB505B6E0067623'
DEFAULT_PORT='/dev/cu.usbmodem2068336B47311'
STATE_COMMANDS=('reg','stk','dump','pwd')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

class ClassicPort(Port):
    def __init__(self,path):
        self.path=path;self.fd=self.lock_fd=-1;self.saved=None;self.require_echo=False
        self.restored=False
        canonical=os.path.realpath(path).replace('/dev/tty.','/dev/cu.')
        key=hashlib.sha256(canonical.encode()).hexdigest()[:20]
        self.lock_fd=os.open(f'/tmp/mk61-hil-cdc-{os.geteuid()}-{key}.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            fcntl.flock(self.lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.fd=os.open(path,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
            fcntl.ioctl(self.fd,termios.TIOCEXCL)
            self.saved=termios.tcgetattr(self.fd)
            attrs=termios.tcgetattr(self.fd);attrs[0]=attrs[1]=attrs[3]=0
            attrs[2]=(attrs[2]&~(termios.CSIZE|termios.PARENB|termios.CSTOPB))|termios.CS8|termios.CREAD|termios.CLOCAL
            attrs[4]=attrs[5]=termios.B115200;attrs[6][termios.VMIN]=attrs[6][termios.VTIME]=0
            termios.tcsetattr(self.fd,termios.TCSANOW,attrs)
        except BaseException:
            self.close();raise
    def close(self):
        error=None
        if self.fd>=0 and self.saved is not None:
            try:
                termios.tcsetattr(self.fd,termios.TCSANOW,self.saved)
                assert termios.tcgetattr(self.fd)==self.saved,'CDC attributes not restored'
                self.restored=True
            except BaseException as e:error=e
        super().close()
        if error:raise error

def save(path,data):path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

def root_names(port):
    return {row.split('\t')[-1].rstrip('/').casefold() for row in listing_entries(port.command('ls /',timeout=12))}

def cpu_hz(pll,cfgr):
    source=(cfgr>>2)&3
    if source==0:hz=16000000
    elif source==1:hz=25000000
    else:
        assert source==2
        m=pll&63;n=(pll>>6)&511;p=2*(1+((pll>>16)&3))
        hz=(25000000 if pll&(1<<22) else 16000000)*n//m//p
    return hz>>((0,0,0,0,0,0,0,0,1,2,3,4,6,7,8,9)[(cfgr>>4)&15])

def parse_benchmark(raw,manifest):
    text=raw.decode('ascii');assert 'S3BENCH END result=0' in text,text
    assert 'S3BENCH module_sha256='+manifest['module_sha256'] in text,text
    clocks=re.findall(r'S3BENCH RCC(?:_END)? cr=([0-9A-F]{8}) pll=([0-9A-F]{8}) cfgr=([0-9A-F]{8})',text)
    assert len(clocks)==2 and clocks[0]==clocks[1],clocks
    hz=cpu_hz(int(clocks[0][1],16),int(clocks[0][2],16));assert hz==96000000,(hz,clocks)
    rows=[]
    for name,samples,lo,hi,maximum,wall,crc in re.findall(
        r'S3BENCH mode=(\w+) samples=(\d+) cycles_lo=(\d+) cycles_hi=(\d+) max_block_cycles=(\d+) wall_ms=(\d+) pcm_crc=([0-9A-F]{8})',text):
        count=int(samples);cycles=int(lo)+(int(hi)<<32);assert count==6144 and cycles>0
        rows.append(dict(mode=name,samples=count,cycles=cycles,cycles_per_sample=cycles/count,
                         max_block_cycles=int(maximum),wall_ms=int(wall),pcm_crc=crc))
    assert [r['mode']for r in rows]==['TONE3','TURBO_ENV_NOISE','DAC_DENSE'],text
    return dict(clock_hz=hz,rcc=clocks[0],rows=rows)

def compare(port,out,manifests,admission,result):
    before=root_names(port);directory='/S3HIL20261107'
    expected_results={m['result_path'].lstrip('/').casefold()for m in manifests}
    assert directory[1:].casefold() not in before and not(expected_results&before),'Benchmark names occupied'
    owned=[];created=False;runs=[]
    original_state={c:canonical_state_reply(admission[c]).strip()for c in STATE_COMMANDS}
    try:
        port.command('mkdir "'+directory+'"',timeout=15)
        assert directory[1:].casefold() in root_names(port);created=True
        for m in manifests:
            target=directory+'/'+Path(m['app']).name
            payload=Path(m['app']).read_bytes();write_file(port,target,payload)
            assert read_file(port,target)==payload,'APP readback differs'
            owned.append((target,payload));print('Uploaded and verified '+Path(target).name,flush=True)
        # A/B/A/B/A/B/A: every optimized run has a baseline on each side.
        for index,variant in enumerate((0,1,0,1,0,1,0)):
            m=manifests[variant];target=owned[variant][0]
            assert not(expected_results&root_names(port)),'Previous result file remains'
            reply=port.command('open "'+target+'"',timeout=20)
            (out/f'run-{index}-open.txt').write_text(reply)
            assert 'Open failed!' not in reply,reply
            data=read_file(port,m['result_path']);(out/f'run-{index}-result.txt').write_bytes(data)
            measured=parse_benchmark(data,m);measured.update(variant='baseline'if variant==0 else'candidate',index=index)
            if runs:
                assert measured['rcc']==runs[0]['rcc'],'Clock changed between runs'
                assert [x['pcm_crc']for x in measured['rows']]==[x['pcm_crc']for x in runs[0]['rows']],'PCM CRC differs'
            runs.append(measured);result['runs']=runs;save(out/'progress.json',result)
            assert read_file(port,m['result_path'])==data
            port.command('rm "'+m['result_path']+'"',timeout=15)
            assert m['result_path'].lstrip('/').casefold()not in root_names(port)
            current=parse_identity(port.command('identity'));assert vars(current)==result['identity'],'Identity/build changed'
            print(json.dumps({'run':index,'variant':measured['variant'],'clock_hz':measured['clock_hz'],
                              'cycles_per_sample':{r['mode']:round(r['cycles_per_sample'],2)for r in measured['rows']}}),flush=True)
        summary=[]
        for mode in ('TONE3','TURBO_ENV_NOISE','DAC_DENSE'):
            a=[row['cycles_per_sample']for run in runs if run['variant']=='baseline'for row in run['rows']if row['mode']==mode]
            b=[row['cycles_per_sample']for run in runs if run['variant']=='candidate'for row in run['rows']if row['mode']==mode]
            av=statistics.median(a);bv=statistics.median(b)
            summary.append(dict(mode=mode,baseline_cycles_per_sample=av,candidate_cycles_per_sample=bv,
                                cycle_reduction_percent=100*(1-bv/av),speedup=av/bv,
                                baseline_range=[min(a),max(a)],candidate_range=[min(b),max(b)]))
        result['summary']=summary
    finally:
        # Delete only reserved new artifacts whose bytes are proved to be ours.
        names=root_names(port)
        for m in manifests:
            if m['result_path'].lstrip('/').casefold()in names:
                data=read_file(port,m['result_path'])
                assert ('S3BENCH module_sha256='+m['module_sha256']).encode()in data,'Foreign result file'
                port.command('rm "'+m['result_path']+'"',timeout=15)
        if created:
            for target,payload in owned:
                assert read_file(port,target)==payload,'Owned APP changed before cleanup'
                port.command('rm "'+target+'"',timeout=15)
            assert not listing_entries(port.command('ls "'+directory+'"'))
            port.command('rmdir "'+directory+'"',timeout=15)
        assert root_names(port)==before,'Root listing not restored'
        for command in STATE_COMMANDS:
            reply=port.command(command,timeout=12);(out/('after-'+command+'.txt')).write_text(reply)
            assert canonical_state_reply(reply).strip()==original_state[command],('Calculator state changed',command)
        final={c:port.command(c,timeout=12)for c in ('identity','df','crash show','mpu status')}
        save(out/'final-health.json',final)
        assert vars(parse_identity(final['identity']))==result['identity']
        assert 'FIRMWARE CRC state=valid' in final['df'] and 'CRASH none' in final['crash show']
        result.update(owned_files_removed=True,root_listing_restored=True,calculator_state_unchanged=True,final_health=final)
    result['status']='PASS'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--phase',choices=['admit','run'],required=True)
    ap.add_argument('--port',default=DEFAULT_PORT)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--baseline-manifest',type=Path,default=ROOT/'.build/spectrum-m3-audio-20261107/classic-stock-baseline/manifest.json')
    ap.add_argument('--candidate-manifest',type=Path,default=ROOT/'.build/spectrum-m3-audio-20261107/classic-stock-candidate/manifest.json')
    args=ap.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'status':'HOLD','physical_io':True,'phase':args.phase,'flash':False,'reset':False,'clock_changes':False}
    port=None
    try:
        manifests=[]
        for manifest in (args.baseline_manifest,args.candidate_manifest):
            meta=json.loads(manifest.read_text())
            assert sha(meta['app'])==meta['app_sha256']
            for p,h in meta['source_sha256'].items():assert sha(ROOT/p)==h,('Changed benchmark source',p)
            manifests.append(meta)
        result['benchmarks']=manifests
        binding=current_binding(args.port);require_no_holders(binding);result['binding']=binding
        port=ClassicPort(args.port)
        replies={}
        for command in ('identity','df','state','crash show','mpu status',*STATE_COMMANDS,'help'):
            replies[command]=port.command(command,timeout=12)
            (out/(command.replace(' ','-')+'.txt')).write_text(replies[command])
            if command=='identity':
                identity=parse_identity(replies[command]);assert identity.public==PUBLIC and identity.profile.startswith('classic-'),identity
                result['identity']=vars(identity)
        result['admission']=replies
        assert 'CRASH none' in replies['crash show'],replies['crash show']
        assert 'FIRMWARE CRC state=valid' in replies['df'],replies['df']
        if args.phase=='run':compare(port,out,manifests,replies,result)
        else:result['status']='ADMISSION_PASS'
    except BaseException as error:
        result['error']=str(error);raise
    finally:
        if port is not None:port.close();result['termios_restored']=port.restored
        result['cdc_closed']=port is None or port.fd<0;result['lease_released']=port is None or port.lock_fd<0
        save(out/'receipt.json',result)
        print(json.dumps({k:result[k]for k in ('status','phase','cdc_closed','lease_released')},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
