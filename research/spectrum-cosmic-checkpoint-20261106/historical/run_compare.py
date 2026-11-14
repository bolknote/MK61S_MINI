"""Fixed long Spectrum pacing measurement. No previous-state backup/restore."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
sys.path.insert(0,str(HERE))
import run_games as previous
import local_holders
b=previous.base
need,Hold,sha=b.need,b.Hold,b.sha
FOLDER=b.FOLDER
IDS=('SP2C',)
APPS=('SPWAIT.APP',)
TEMP={*APPS,*(n+s for n in IDS for s in ('.Z80','.ULP'))}
WRITABLE=TEMP

def source_pins():return {**previous.source_pins(),str(Path(__file__).resolve()):sha(__file__),str(Path(local_holders.__file__).resolve()):sha(local_holders.__file__)}
def validate_plan(p):
    need(p.get("readiness")=="fresh_handoff_verified","Draft/stale handoff: no device access")
    need(p['role']=='spectrum-wait-v2' and p['folder']==FOLDER and p['uid']==b.UID,'Changed device/namespace')
    need(p['indexes']==[0] and set(p['files'])==WRITABLE,'Changed workload or writable set')
    need([g['id'] for g in p['games']]==list(IDS),'Changed game count')
    need(p['variants']==[{'label':'WAIT','app':APPS[0]}],'Changed A/B order or APPs')
    need(p['measurement']=={'warmup_frames':100,'window_frames':300,'windows':10,'timer_interval_uncertainty_us':1},'Changed fixed measurement')
    need(p['expected']=={'build':'2483E8A7','crc':'22F8ED32','bytes':1537040},'Changed reviewed native firmware')
    item=p['platform'];need(sha(item['local'])==item['sha256']==p['pins'][item['local']],'Changed platform equivalence')
    eq=json.loads(Path(item['local']).read_text());need(eq['all_identical'],'Platform services differ')
    for row in eq['files']:
        need(row['identical'] and row['old_sha256']==row['new_sha256'],'Platform source mismatch')
        for key in ('old_source','new_source'):
            path=str(Path(eq[key])/row['file']);need(sha(path)==row['new_sha256']==p['pins'][path],'Platform source changed')
    for name,item in p['files'].items():
        need(sha(item['local'])==item['sha256']==p['pins'][item['local']],'Changed binary: '+name)
        need(0<Path(item['local']).stat().st_size<=65535,'File exceeds fsput scope')
    h=p['handoff'];need(sha(h['local'])==h['sha256']==p['pins'][h['local']],'Changed native handoff')
    handoff=json.loads(Path(h['local']).read_text())
    need(handoff['uid']==b.UID and handoff['expected']==p['expected'] and handoff['lease']=='released','Supplier identity/release differs')
    need(sha(handoff['source_receipt'])==handoff['source_receipt_sha256'],'Supplier receipt changed')
    baseline=p['baseline']
    need(baseline['comparison']=='sequential clean-start old717 BASE/AY descriptive;2483 WAITv2','Changed comparison conditions')
    for key in ('receipt','record','app'):
        item=baseline[key];need(sha(item['local'])==item['sha256']==p['pins'][item['local']],'Changed full BASE evidence')
    before=json.loads(Path(baseline['receipt']['local']).read_text())
    need(before['uid']==b.UID and before['lease']=='released' and before['cleanup_native_verified'],'BASE native release differs')
    need(len(before['variants'])==1 and before['variants'][0]['variant']=='BASE','BASE was not measured completely')
    reference=before['variants'][0]
    need(reference['app_sha256']==baseline['app']['sha256'],'BASE image differs')
    need('HEAP_FREE=104368 ' in before['heap_start'] and 'HEAP_FREE_BLOCKS=1 ' in before['heap_start'],'BASE clean-start conditions differ')
    raw=Path(baseline['record']['local']).read_bytes();parsed=measurements(raw)
    need(all(reference[k]==v for k,v in parsed.items()),'Full BASE windows/report differ')
    need(reference['audio']==details(raw)['audio'],'BASE audio evidence differs')
    prior=p['prior_ay']
    for item in prior.values():need(sha(item['local'])==item['sha256']==p['pins'][item['local']],'Changed AY evidence')
    ay=json.loads(Path(prior['receipt']['local']).read_text())
    need(ay['status']=='PASS' and ay['lease']=='released' and ay['uid']==b.UID,'AY clean-start result/release differs')
    need(len(ay['variants'])==1 and ay['variants'][0]['variant']=='AY','AY interval differs')
    raw=Path(prior['record']['local']).read_bytes();reference=ay['variants'][0]
    need(all(reference[k]==v for k,v in measurements(raw).items()) and reference['audio']==details(raw)['audio'],'Complete AY windows/audio differ')
    for game in p['games']:
        x0,x1,y0,y1=game['hud_roi_bytes']
        need(0<=x0<x1<=32 and 0<=y0<y1<=192 and game['ulaplus'] in (0,1),'Invalid scene predicate')

def measurements(record):
    whole,steady=b.measured_timing(record)
    need(whole['frames']>=3100 and steady['frames']==3000,'Fixed long interval incomplete')
    rows=re.findall(rb'SPWIN n=(\d+) frames=(\d+) cycles=(\d+) wall=(\d+) phase=(\d+)/(\d+) late=(\d+)/(\d+)',record)
    need(len(rows)==10,'Missing/extra predeclared window')
    windows=[]
    for i,row in enumerate(rows):
        index,frames,cycles,wall,first,last,firstlate,lastlate=map(int,row)
        need(index==i and frames==300 and wall>1 and max(first,last)<4096,'Window order/length differs')
        need(cycles==frames*71680+last-first,'Window cycle/frame/phase mismatch')
        if windows:need(first==windows[-1]['last_phase'] and firstlate==windows[-1]['last_late_us'],'Non-adjacent windows')
        windows.append(dict(index=index,frames=frames,cycles=cycles,wall_us=wall,first_phase=first,last_phase=last,
            first_late_us=firstlate,last_late_us=lastlate,mhz=cycles/wall,
            timer_lower_mhz=cycles/(wall+1),timer_upper_mhz=cycles/(wall-1)))
    need(sum(w['cycles'] for w in windows)==steady['cycles'] and sum(w['wall_us'] for w in windows)==steady['wall_us'],'Dropped or duplicated measured time')
    need(windows[0]['first_phase']==steady['first_phase'] and windows[-1]['last_phase']==steady['last_phase'],'Overall endpoints differ')
    rows=re.findall(rb'SPPACING count=(\d+) firstlate=(\d+) maxlate=(\d+) wait=(\d+) minwait=(\d+) lateframes=(\d+) resets=(\d+) done=(\d+)',record)
    need(len(rows)==1,'Pacing summary absent or duplicated')
    count,firstlate,maxlate,wait,minwait,lateframes,resets,done=map(int,rows[0])
    need(count==10 and done==1 and firstlate==windows[0]['first_late_us'],'Pacing interval incomplete')
    need(max(max(w['first_late_us'],w['last_late_us']) for w in windows)<=maxlate,'Unbounded endpoint lateness')
    need(wait<=steady['wall_us'] and minwait*3000<=wait and lateframes<=3000,'Invalid pacing headroom counters')
    pacing=dict(max_late_us=maxlate,wait_us=wait,min_wait_us=minwait,late_frames=lateframes,resyncs=resets)
    steady.update(timer_lower_mhz=steady['cycles']/(steady['wall_us']+1),
                  timer_upper_mhz=steady['cycles']/(steady['wall_us']-1))
    strict=resets==0 and steady['cycles']*2>=(steady['wall_us']+1)*7
    return dict(whole=whole,steady=steady,windows=windows,pacing=pacing,
                strict_3_5_lower_bound_reached=strict,timer_interval_uncertainty_us=1)

def stages(record):
    rows=re.findall(rb'SPSTAGE id=(\d+) count=(\d+) total=(\d+) max=(\d+) frame=(\d+) phase=(\d+) pc=([0-9A-F]{4})',record)
    need(len(rows)==8,'Stage profile missing/duplicated')
    result=[]
    for i,row in enumerate(rows):
        id,count,total,maximum,frame,phase=map(int,row[:6]);pc=int(row[6],16)
        need(id==i and maximum<=total and (count>0 or total==maximum==0),'Invalid stage summary')
        if count:need(100<=frame<=3100 and phase<71680,'Stage outside fixed interval')
        result.append(dict(id=id,name=('CPU','SERVICE','KEYS','PALETTE','PRESENT','BUFFER','OTHER','VIDEO')[id],count=count,total_us=total,max_us=maximum,frame=frame,phase=phase,pc=f'{pc:04X}'))
    return result
def details(record):
    rows=re.findall(rb'SPAUDIO count=(\d+) busy=(\d+) max=(\d+) starved=(\d+) minlead=(-?\d+) maxlead=(-?\d+)',record)
    need(len(rows)==1,'Audio detail absent or duplicated')
    count,busy,maximum,starved,minlead,maxlead=map(int,rows[0])
    need(count>0 and maximum<=busy and starved<=count and minlead<=maxlead,'Invalid audio details')
    return dict(audio=dict(samples=count,busy_us=busy,max_us=maximum,starved=starved,min_lead_tstates=minlead,max_lead_tstates=maxlead))
def sound_details(record):
    rows=re.findall(rb'SPSOUND late=(\d+) wholemaxlate=(\d+) wholemaxdeficit=(\d+)',record)
    need(len(rows)==1,'Sound event timing absent or duplicated')
    late,maximum,deficit=map(int,rows[0])
    need(maximum<0x80000000 and deficit<0x80000000,'Invalid sound timing counters')
    return dict(sound=dict(late_events=late,whole_max_late_tstates=maximum,whole_max_deficit_tstates=deficit))
def pipeline_details(record):
    # Frozen display clocks and actual executed CPU clocks are distinct.
    rows=re.findall(rb'SPWORK n=(\d+) phase=(\d+)/(\d+)',record)
    need(len(rows)==10,'Missing/extra actual-work window')
    work=[]
    for i,row in enumerate(rows):
        index,first,last=map(int,row);need(index==i and max(first,last)<=14044,'Invalid actual-work phase')
        if work:need(first==work[-1]['last_phase'],'Non-adjacent actual-work windows')
        work.append(dict(index=i,first_phase=first,last_phase=last,cycles=300*71680+last-first))
    rows=re.findall(rb'SPEXEC (\d+) (\d+) (\d+)/(\d+) (\d+)',record);need(len(rows)==1,'Actual execution summary absent/duplicated')
    frames,cycles,first,last,ahead=map(int,rows[0])
    need(frames==3000 and cycles==sum(w['cycles'] for w in work) and first==work[0]['first_phase'] and last==work[-1]['last_phase'],'Actual execution endpoints disagree')
    need(ahead<=14044,'Prefetch exceeds predeclared normal-instruction cap')
    rows=re.findall(rb'SPPRES (\d+) (\d+) (\d+) (\d+)/(\d+) (\d+)/(\d+) (\d+)/(\d+) (\d+)',record)
    need(len(rows)==10,'API presentation windows absent/duplicated')
    presents=[]
    for i,row in enumerate(rows):
        index,count,busy,first_frame,last_frame,first_us,last_us,min_us,max_us,late=map(int,row)
        need(index==i and count+busy==(301 if i==9 else 300),'Presentation attempts omitted')
        if count:
            need(100+300*i<=first_frame<=last_frame<=(3100 if i==9 else 399+300*i),'Accepted frame identity outside window')
            need(count<=last_frame-first_frame+1 and ((last_us-first_us)&0xffffffff)<0x80000000,'Invalid accepted span/timer')
            need(0<min_us<=max_us<0x80000000,'Invalid API accepted intervals')
        presents.append(dict(index=i,accepted=count,busy=busy,first_frame=first_frame,last_frame=last_frame,
            first_us=first_us,last_us=last_us,min_interval_us=min_us,max_interval_us=max_us,max_late_us=late))
    rows=re.findall(rb'SPDISPLAY (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)',record);need(len(rows)==1,'Presentation totals absent/duplicated')
    records,accepted,busy,repeated,skipped,early,faults=map(int,rows[0])
    need(records==3001 and accepted+busy+faults==records and accepted==sum(w['accepted'] for w in presents) and busy==sum(w['busy'] for w in presents),'Presentation totals disagree')
    need(repeated<=accepted and early<=accepted and skipped<=3100,'Invalid presentation failures')
    accepted_wall=None
    if accepted==3001 and not (busy or repeated or skipped or early or faults):
        accepted_wall=(presents[-1]['last_us']-presents[0]['first_us'])&0xffffffff
        need(accepted_wall>1 and presents[0]['first_frame']==100 and presents[-1]['last_frame']==3100,'Accepted endpoints missing')
    return dict(executed=dict(frames=frames,cycles=cycles,first_phase=first,last_phase=last,max_ahead_tstates=ahead,windows=work),
        display=dict(measurement='API accepted submissions after native call; physical LCD scanout unmeasured',records=records,accepted=accepted,busy=busy,
            repeated=repeated,skipped=skipped,early=early,faults=faults,accepted_wall_us=accepted_wall,windows=presents),
        audio_observer='No per-sample core1 timing observer; consumer SPSOUND counters retained')
class ProfileGate(b.SpectrumGate):
    def noholders(self,binding,allow_self=False):
        self.check()
        try:proof=local_holders.require_no_holders(binding,allow_self)
        except (local_holders.HolderError,OSError) as error:raise Hold(str(error)) from error
        self.final.setdefault('holder_checks',[]).append(proof)
        self.check()
    def check(self):
        left=super().check();duration=b.elapsed(self.continuous_start,b.continuous())
        cap=min(300,self.cleanup_start+60) if self.cleaning else 240
        need(duration<cap,'Profile/cleanup time cap exceeded');return min(left,cap-duration)

class Port(previous.GamesPort):
    def open_app(self,name):
        need(name in APPS,'Foreign APP')
        self.pump(.02);self.send(('open "'+FOLDER+'/'+name+'"\r').encode())
    def native_return(self,physical):
        browser=False
        for _ in range(5):
            status=self.status();service,path,result=b.foreground(status)
            if service=='CLOSED':b.guard_status(status,b.EXPECTED,physical);self.commands();return status
            if service=='BROWSER' and browser:
                need(b.field(status,'RUNTIME')=='NONE','Unexpected browser runtime');self.wire(27);self.pump(.2);continue
            own={FOLDER+'/'+name for name in APPS}
            # Only the diagnostic APP is in this profile scope.
            need(path in own,'Foreign foreground; no escape sent')
            if b.field(status,'RUNTIME')=='APP':self.wire(27);self.pump(.3);continue
            need(b.field(status,'RUNTIME')=='NONE' and service in ('VIEWER','BROWSER'),'Unexpected owned foreground')
            if service=='VIEWER':need(result.startswith('APP finished;'),'APP did not finish normally')
            self.send(b'\x1e');self.wire(27);self.pump(.2);browser=True
        raise Hold('Native return exceeded finite cap')

def cleanup_files(p,attempted):
    need(attempted<=TEMP,'Cleanup contains an unowned target')
    for name in sorted(attempted):
        p.command(f'rm "{FOLDER}/{name}"')
    report=p.command(f'ls "{FOLDER}"')
    names={line.rstrip('\r').split('\t')[-1].rstrip('/') for line in report.splitlines() if re.match(r'^[df]\t',line)}
    need({'48.rom','SPECTRUM.APP'}<=names,'Owned-folder response not recognized')
    need(not names.intersection(attempted),'Temporary file was not removed: '+str(names.intersection(attempted)))
    return sorted(attempted)

def run_port(g):
    validate_plan(g.j);b.EXPECTED=g.j['expected'];attempted=set();changed={};clean=False
    with Port(g) as p:
        physical=b.guard_status(p.status(),b.EXPECTED)
        h=json.loads(Path(g.j['handoff']['local']).read_text())
        need(p.binding==h['native_binding'],'Native USB binding changed since handoff')
        p.commands();need(b.field(p.command('identity'),'UID')==b.UID,'Wrong PicoCalc UID')
        try:
            g.final['heap_start']=p.command('prof heap')
            need(b.field(g.final['heap_start'],'HEAP_FREE_BLOCKS')=='1' and
                 int(b.field(g.final['heap_start'],'HEAP_FREE'))>=104368,
                 'Clean single-block heap required before any upload; separate reset review needed')
            def write(name):
                item=g.j['files'][name]
                if name in TEMP:attempted.add(name)
                b.write_file(p,FOLDER+'/'+name,Path(item['local']).read_bytes());changed[name]=item['sha256']
            fixtures_written=False
            g.final['variants']=[]
            for variant in g.j['variants']:
                name=variant['app'];write(name)
                start=len(p.text);p.open_app(name);p.menu(start);b.validate_root(p.text[start:],initial=True)
                status=p.status();need(b.field(status,'RUNTIME')=='APP' and b.field(status,'APP_EXTERNAL_BYTES')=='1892352','SRAM preflight failed')
                p.save('preflight-'+variant['label']);p.native_return(physical)
                if not fixtures_written:
                    for fixture in sorted(TEMP-set(APPS)):write(fixture)
                    fixtures_written=True
                start=len(p.text);p.open_app(name);p.menu(start);b.validate_root(p.text[start:],initial=True);p.save('initial-'+variant['label'])
                game=g.j['games'][0];start=len(p.text);p.open_fixture(game);p.pump(2)
                for _ in range(10):p.wire(ord('p'));p.pump(.2)
                p.match(rb'SPPACING_DONE\r?\n',start,timeout=95)
                p.pause();record=bytes(p.text)
                data=previous.framebuffer(record);signature=previous.scene_signature(data,game)
                result=measurements(record);result.update(pipeline_details(record));result.update(sound_details(record));result.update(title=game['title'],fixture=game['id'],hud_signature=signature,
                    variant=variant['label'],app_sha256=g.j['files'][name]['sha256'],frame_sha256=hashlib.sha256(data).hexdigest())
                (g.out/(variant['label']+'-frame.bin')).write_bytes(data);p.save('game-'+variant['label']);g.final['variants'].append(result)
                p.native_return(physical)
            g.final['profiling_overhead_present']=True
        except BaseException as error:
            g.final['primary_error']=repr(error)
            raise
        finally:
            try:
                g.cleanup()
                p.native_return(physical);p.command('fsput cancel')
                g.final['temporary_files_absent']=cleanup_files(p,attempted)
                g.final['heap_end']=p.command('prof heap')
                status=p.status();b.guard_status(status,b.EXPECTED,physical)
                g.final.update(status_after=status,previous_state_backup=False,previous_state_restoration=False)
                clean=True
            except BaseException as error:
                g.final['cleanup_error']=repr(error)
                raise
            finally:g.final.update(changed_sd_files=changed,cleanup_native_verified=clean)

def run(g):
    failure=None
    try:run_port(g)
    except BaseException as error:failure=error
    try:
        need(g.final.get('cdc_descriptor_closed') and not g.final.get('port_close_errors'),'CDC close unproven')
        g.noholders(g.final['native_binding']);need(g.final.get('cleanup_native_verified'),'Native/temporary cleanup unproven');g.final['lease']='released'
    except BaseException as error:
        g.final['handoff_error']=repr(error)
        if failure is None:failure=error
    if failure is not None:raise failure

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pins',action='store_true');ap.add_argument('--phase',type=Path);ap.add_argument('--grant',type=Path);ap.add_argument('--out',type=Path);args=ap.parse_args()
    if args.pins:print(json.dumps(source_pins(),indent=2));return
    need(args.phase and args.grant and args.out,'Exact phase/grant/output required');validate_plan(json.loads(args.phase.read_text()))
    g=ProfileGate(args.phase,args.grant,args.out);g.final['lease']='closed_port_needs_attention'
    try:run(g)
    except BaseException as error:g.finish(False,repr(error));raise
    else:g.finish(True)
if __name__=='__main__':main()
