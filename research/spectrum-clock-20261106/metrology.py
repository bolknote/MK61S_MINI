"""Frozen complete-window metrology; no device I/O."""
import re
from types import SimpleNamespace

class Hold(ValueError):pass
def need(ok,reason):
    if not ok:raise Hold(reason)

def measured_timing(record):
 total=re.findall(rb'SPTIME frames=(\d+) cycles=(\d+) wall=(\d+) xip=(\d) starved=(\d+)',record)
 need(len(total)==1,'Missing/ambiguous whole-interval timing')
 frames,cycles,wall,xip,starved=map(int,total[0])
 need(wall>0 and cycles>0 and xip==1,'Invalid whole-interval timing')
 whole={'frames':frames,'cycles':cycles,'wall_us':wall,'mhz':cycles/wall,'xip':xip,'starved':starved}
 rows=re.findall(rb'SPSTEADY frames=(\d+) cycles=(\d+) wall=(\d+) phase=(\d+)/(\d+) starved=(\d+)',record)
 need(len(rows)==1,'Missing/ambiguous steady frame timing')
 frames,cycles,wall,first_phase,last_phase,steady_starved=map(int,rows[0])
 need(frames>=2 and wall>=5000000 and first_phase<4096 and last_phase<4096,'Steady interval too short or not at frame boundaries')
 need(cycles==frames*71680+last_phase-first_phase,'Steady cycles disagree with frame/phase counters')
 need(cycles<=whole['cycles'] and wall<=whole['wall_us'] and steady_starved<=starved,'Steady counters outside whole interval')
 mhz=cycles/wall;need(0<mhz<=3.55,'Steady measurement exceeds target pacing')
 return whole,{'frames':frames,'cycles':cycles,'wall_us':wall,'mhz':mhz,'xip':xip,'starved':steady_starved,'first_phase':first_phase,'last_phase':last_phase,'kind':'complete-frame interval inside active execution'}

b=SimpleNamespace(measured_timing=measured_timing)

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

def sound_details(record):
    rows=re.findall(rb'SPSOUND late=(\d+) wholemaxlate=(\d+) wholemaxdeficit=(\d+)',record)
    need(len(rows)==1,'Sound event timing absent or duplicated')
    late,maximum,deficit=map(int,rows[0])
    need(maximum<0x80000000 and deficit<0x80000000,'Invalid sound timing counters')
    return dict(sound=dict(late_events=late,whole_max_late_tstates=maximum,whole_max_deficit_tstates=deficit))
