#!/usr/bin/env python3
"""Test changed finite operator paths against inert files and a fake CDC peer.

Never instantiate the physical Gate/Port or create a device lease. Real
streamed reports come from the packed ARM HOST model, not invented times.
"""
import argparse,copy,hashlib,json,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'research/m0-libc-batch-2026-11-07';O=R/'operator'
sys.path[:0]=[str(O),str(R),str(ROOT/'tests')]
import controller as c
import campaign
from device_guard import Hold
from prepare import pin,save,NAMESPACE
import wire
class Peer:
    def __init__(self,t,build,model,corrupt=False,physical=False):
        self.t,self.build,self.model=t,build,model;self.files={};self.foreground='CLOSED';self.fs='';self.keys=0;self.list=False;self.events=[];self.corrupt=corrupt;self.physical=physical;self.opens=0
class FakePort:
    peer=None
    def __init__(self,g):self.g=g;self.binding=g.j['usb_binding'];self.closed=False
    def __enter__(self):self.g.final['native_binding']=self.binding;return self
    def __exit__(self,*unused):self.closed=True;self.g.final.setdefault('cdc_sessions',[]).append(dict(closed=True,errors=[]))
    def status(self):
        p=self.peer;j=self.g.j;e=j['expected']
        values=dict(BUILD=e['build'],FIRMWARE_CRC='valid',EXPECTED=e['crc'],ACTUAL=e['crc'],IMAGE=e['bytes'],CRASH='NONE',MATH_TEST='OK',failures=0,SERVICE=p.foreground,RUNTIME='NONE',RUN=0,BUSY=0,USB_DISK=0,USB_SCREEN='OFF',DIRTY=0,APP_BUFFERS=0,APP_BUFFER_BYTES=0,APP_EXTERNAL_BYTES=0,APP_WINDOWS=0,KBD='OK',PANEL_INIT=1,SYS_HZ='125000000',PERI_HZ='48000000',PLL_MASK=3,SD='OK',POWER_MODE='RUN',PHYSICAL_KEYS=p.keys)
        values.update(j['boot_fields']);values.update(j['context_fields'])
        return 'RP2040 125 MHz '+' '.join(str(k)+'='+str(v) for k,v in values.items())+' FS_ERROR=['+p.fs+'] PATH=['+NAMESPACE+'/BATCH0.APP]'
    def commands(self):self.peer.events.append('command-mode')
    def pump(self,*unused):pass
    def send(self,data):
        p=self.peer;p.events.append(('send',data.hex()))
        if data==b'\x1b':
            if p.foreground=='VIEWER':p.foreground='BROWSER';p.fs='' if p.list else 'File or directory not found (4)'
            elif p.foreground=='BROWSER':p.foreground='CLOSED'
        if data==b'\x88':assert p.foreground=='BROWSER';p.list=True;p.fs=''
    def command(self,line,timeout=8):
        p=self.peer;p.events.append(line)
        if line=='identity':return 'UID='+c.UID
        if line=='ls /':return ''
        if line=='mkdir '+NAMESPACE:return 'OK'
        if line=='ls '+NAMESPACE:return ''.join('f\t11\t'+name+'\n' for name in p.files)
        if line.startswith('rm '):del p.files['RESULT.bin'];return 'OK'
        if line.startswith('open '):
            p.opens+=1;request=p.files['INPUT.bin'];q=wire.parse_request(request,p.t)
            app=p.build['products'][q['route']];assert p.files['BATCH0.APP']==Path(app['APP']['path']).read_bytes()
            suffix='qual' if q['batch'] is None else 'strlen';assert q['batch'] in (None,0)
            raw=(p.model/(app['route']+'-'+suffix+'.bin')).read_bytes()
            if p.corrupt:raw=raw[:1020]+bytes(4)+raw[1024:]
            p.files['RESULT.bin']=raw;p.foreground='VIEWER';return 'APP_FLOW_RESULT=0\nmk61> '
        raise AssertionError(('unreviewed command',line))
class FakeGate:
    def __init__(self,j,out):
        self.j,self.out,self.phase=j,out,out/'host-phase.json';out.mkdir();self.phase.write_text('{}')
        self.final={};self.grant_data=dict(one_time_owned_browser_list_switch_authorized=True)
    def check(self):return 900
    def noholders(self,binding):self.final['host_no_real_holder_check']=True
    def command(self,argv,timeout=10):return subprocess.run(argv,capture_output=True)
def fake_read(p,path):assert path.startswith(NAMESPACE+'/');return bytes(p.peer.files[path.rsplit('/',1)[1]])
def fake_write(p,path,data):assert path.startswith(NAMESPACE+'/');p.peer.files[path.rsplit('/',1)[1]]=bytes(data)
def main():
    p=argparse.ArgumentParser();p.add_argument('--template',type=Path,required=True);p.add_argument('--apps',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    t=json.loads(a.template.read_text());build=json.loads(a.apps.read_text());model_result=json.loads((a.model/'RESULT.json').read_text());assert model_result['status']=='PASS_ALL_EIGHT_PACKED_ROUTES_STREAMING_AND_FIRST_FAULT'
    original=(c.Port,c.read_file,c.write_file,c.D)
    c.Port,c.read_file,c.write_file=FakePort,fake_read,fake_write;c.D=a.output/'no-physical-claims';c.D.mkdir()
    expected=dict(build=t['candidate_build'].upper(),crc=t['candidate_crc'].upper(),bytes=t['candidate_firmware']['bytes'],crash='NONE')
    j=dict(expected=expected,boot_fields=dict(BOOTS='5',RESET_REASON='1000001',BOOT_WATCHDOG='0'),context_fields=dict(SYS_HZ='125000000',PERI_HZ='48000000',PLL_MASK='3'),usb_binding=dict(uid=c.UID,fake_HOST_peer=True),identity_wake_authorized=True,scope='m0-libc-batch-qualification',action='timing',create_namespace=True,initialize_list_browser=True,indexes=[0,1,2,3],decoder=str(a.model/'decode-app'))
    try:
        peer=Peer(t,build,a.model);FakePort.peer=peer;g=FakeGate(j,a.output/'qualification');c.execute(g,t,build,{})
        qualification=g.out/'QUALIFICATION.json';q=json.loads(qualification.read_text());assert len(q['routes'])==4 and peer.opens==4
        assert sum(e==('send','88') for e in peer.events)==1
        previous=dict(owned_files=g.final['owned_files'],completed_jobs=[])
        timing=dict(j,scope='m0-libc-batch-timing',create_namespace=False,initialize_list_browser=False,indexes=[0],qualification=str(qualification))
        h=FakeGate(timing,a.output/'timing');c.execute(h,t,build,previous);assert h.final['completed_jobs']==[0] and peer.opens==5
        assert (h.out/'job-000.bin').read_bytes()==(a.model/'standalone-sram-strlen.bin').read_bytes()
        # An invalid first report must be exported verbatim before rejecting it;
        # no UI-return keys, next job, cleared error or retry may follow.
        c.D=a.output/'fault-no-physical-claims';c.D.mkdir();peer.corrupt=True;before=len(peer.events)
        previous=dict(owned_files=h.final['owned_files'],completed_jobs=[]);bad=dict(timing,indexes=[0,1]);f=FakeGate(bad,a.output/'first-fault')
        try:c.execute(f,t,build,previous)
        except ValueError:pass
        else:raise AssertionError('Bad header accepted')
        assert (f.out/'job-000.bin').exists() and not (c.D/'journal/job-/001').exists() and peer.opens==6
        assert not any(isinstance(e,tuple) and e[0]=='send' for e in peer.events[before:])
        negatives=0
        good_status=FakePort(h).status();peer.foreground='CLOSED';peer.fs=''
        good_status=FakePort(h).status();assert c.status_guard(good_status,j)==0
        for old,new in [('BUILD='+expected['build'],'BUILD=DEADBEEF'),('CRASH=NONE','CRASH=AVAILABLE'),('SYS_HZ=125000000','SYS_HZ=200000000'),('PERI_HZ=48000000','PERI_HZ=125000000'),('PHYSICAL_KEYS=0','PHYSICAL_KEYS=1'),('FS_ERROR=[]','FS_ERROR=[Disk error (1)]'),('RUNTIME=NONE','RUNTIME=APP'),('SERVICE=CLOSED','SERVICE=VIEWER')]:
            try:c.status_guard(good_status.replace(old,new),j,0)
            except Hold:negatives+=1
            else:raise AssertionError(('C5 guard accepted',old))
        plan=campaign.phase_plan();assert len(plan['phases'])==45 and [i for p in plan['phases'] if p['scope']=='timing' for i in p['indexes']]==list(range(672))
        # Precheck fixtures live only under this inert HOST peer directory.
        # They are never passed to Gate/Port or a campaign launcher.
        accept=a.output/'HOST-only-fixture-acceptance.json'
        save(accept,dict(status='ROOT_ACCEPTED_M0_LIBC_IMAGE_AND_FIXTURE',uid=c.UID,template_sha256=c.sha(a.template),**{k:j[k] for k in ('expected','boot_fields','context_fields','usb_binding')},HOST_TEST_ONLY=True))
        pred=a.output/'HOST-only-predecessor.json';save(pred,dict(status='PASS',HOST_TEST_ONLY=True))
        proc=a.output/'HOST-only-process.json';save(proc,dict(status='PASS_PROCESS_EXIT',EXIT=0,reaped=True,group_gone=True,parent_fds_before=[0,1,2],parent_fds_after=[0,1,2],HOST_TEST_ONLY=True))
        paths=[a.template,a.apps,accept,pred,proc,a.model/'decode-app',Path(sys.executable).resolve()]+[Path(t[k]['path']) for k in ('candidate_firmware','candidate_ELF','candidate_manifest','fixture')]+[Path(v[k]['path']) for v in build['products'] for k in ('APP','ELF')]
        pins={str(p):c.sha(p) for p in paths};source_pins={p:c.sha(p) for p in c.source_closure()}
        for change in ('valid','reset','RTC','owner','stale-source','wrong-argv','unknown-image','Go-SHA'):
            phase=a.output/('HOST-only-precheck-'+change+'.json');grant=phase.with_suffix('.grant.json');out=a.output/('not-opened-'+change)
            argv=[str(Path(sys.executable).resolve()),str(Path(c.__file__).resolve()),'--phase',str(phase),'--grant',str(grant),'--output',str(out)]
            test=dict(j,schema=1,uid=c.UID,owner=c.OWNER,scope='m0-libc-batch-qualification',action='timing',Flash_writes=0,reset_commands=0,RTC_setters=0,argv=argv,cwd=str(ROOT),template=str(a.template),build=str(a.apps),fixture_acceptance=str(accept),previous_receipt=str(pred),previous_supervisor=str(proc),pins=pins)
            if change=='reset':test['reset_commands']=1
            if change=='RTC':test['RTC_setters']=1
            if change=='owner':test['owner']='wrong'
            if change=='wrong-argv':test['argv']=argv+['--unreviewed']
            if change=='unknown-image':test['expected']=dict(test['expected'],build='DEADBEEF')
            save(phase,test)
            gr=dict(status='ROOT_EXPLICIT_PHASE_GO',executor=c.OWNER,uid=c.UID,phase_sha256=c.sha(phase),source_pins=dict(source_pins),fixture_receipt_sha256=c.sha(accept),HOST_TEST_ONLY=True)
            if change=='stale-source':gr['source_pins'][str(Path(c.__file__).resolve())]='0'*64
            if change=='Go-SHA':gr['phase_sha256']='0'*64
            save(grant,gr)
            try:c.precheck(phase,grant,out)
            except Hold:
                assert change!='valid';negatives+=1
            else:assert change=='valid'
            assert not out.exists()
        supervisor=O/'supervisor.py';prior=Path('/Users/bolk/Projects/MK61S_MINI/.build/strchr-m0-hil-20261107-v1/measurement-source/supervisor.py');assert supervisor.read_bytes()==prior.read_bytes()
        save(a.output/'RESULT.json',dict(status='PASS_CHANGED_GROUPED_OPERATOR_HOST_ONLY',physical_IO=0,real_gate_or_port_instantiated=False,device_lease_created=False,qualified_source_pinning=pin(supervisor),previous_supervisor_qualification_reused_by_byte_identity=True,qualification_routes=4,raw_export_before_first_fault=True,no_fault_replay=True,no_later_job_after_fault=True,finite_phase_count=45,finite_jobs=672,C5_and_precheck_negative_controls=negatives,source_pins=[pin(Path(__file__)),pin(O/'controller.py'),pin(O/'campaign.py')],model=pin(a.model/'RESULT.json')))
        print('4 route qualification, complete job, first-fault export/stop, C5 guards and finite672job coverage PASS; device IO0')
    finally:c.Port,c.read_file,c.write_file,c.D=original
if __name__=='__main__':main()
