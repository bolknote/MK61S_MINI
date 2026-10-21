#!/usr/bin/env python3
"""Time the identified diagnostic M0 image, preserving calculator data.

Never flashes or resets. It checks the exact UID and diagnostic build before
creating one temporary directory, then removes it in finally. Both libraries
execute from the same flash image. The input vectors contain MPFR references.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import struct
import time

from hil_picocalc_apps import AppsPort
from hil_c5_stack import read_file,write_file


class MathPort(AppsPort):
    """Wait for every terminal acknowledgement without a fixed 70-ms delay."""
    def commands(self):
        # A mode-change banner can be lost during USB startup. Check the
        # acknowledged mode instead of waiting for that one banner.
        for _ in range(4):
            if 'TERMINAL=COMMAND' in self.status():return
            os.write(self.fd,b'\x1f');self.pump(.3)
        raise AssertionError('PicoCalc terminal did not enter command mode')

    def command(self,command,timeout=5):
        if command.startswith('fsget '):timeout=max(timeout,120)
        self.pump(.002);start=len(self.text);self.write_line(command)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.pump(.002)
            if re.search(rb'(?:^|[\r\n])mk61> ',self.text[start:]):
                return self.text[start:].decode('cp1251','replace')
        raise TimeoutError((command,bytes(self.text[start:])))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def rtc_after_wall_elapsed(rtc_before, sampled_at_utc, now_utc=None):
    """Preserve the RTC trajectory across host sleep using UTC wall time."""
    rtc=datetime.fromisoformat(rtc_before)
    sampled=datetime.fromisoformat(sampled_at_utc)
    now=now_utc or datetime.now(timezone.utc)
    if rtc.tzinfo is not None or sampled.utcoffset() is None or now.utcoffset() is None:
        raise ValueError('RTC must be local naive time; host samples must include a timezone')
    elapsed=now-sampled
    if elapsed.total_seconds()<0:
        raise ValueError('Host wall clock precedes the saved RTC sample')
    return rtc+elapsed


def cleanup_session(port,output,before,directory,created,identity,initial,failure):
    """Save the received transcript even when disconnect also breaks cleanup."""
    after=final=None
    removed=preserved=False
    cleanup_error=None
    try:
        port.command('fsput cancel')
        os.write(port.fd,b'\x1e\x1b\x1b\x1f');port.pump(.3)
        if created:
            answer=port.command('rm -r '+directory,timeout=30)
            assert 'ERROR' not in answer,answer
            removed=True
        after={command:port.command(command) for command in before}
        final=port.status()
        assert before==after,('Calculator data changed',before,after)
        preserved=True
    except BaseException as error:
        cleanup_error=error
    result=dict(status='FAIL' if failure or cleanup_error else 'PASS',failure=failure,
        cleanup_failure=repr(cleanup_error) if cleanup_error else None,
        identity=identity,initial=initial,final=final,before=before,after=after,
        temporary_directory_removed=removed,calculator_data_preserved=preserved)
    (output/'transcript.bin').write_bytes(port.text)
    (output/'session.json').write_text(json.dumps(result,indent=2)+'\n')
    if cleanup_error is not None and failure is None:
        raise cleanup_error
    return result


def ordered(x,width):
    sign=1<<(width-1);mask=(1<<width)-1
    return (~x&mask) if x&sign else x|sign


def order_balanced(timings):
    rounds=len(timings['own']['paired_us'])
    assert rounds==len(timings['qfplib']['paired_us']) and rounds>=2
    paired={}
    for name in ('own','qfplib'):
        values=timings[name]['paired_us']
        paired[name]=[(values[i]+values[i+1])/2 for i in range(0,rounds-1,2)]
    medians={name:statistics.median(v) for name,v in paired.items()}
    differences=[x-y for x,y in zip(paired['own'],paired['qfplib'])]
    return dict(rounds_used=2*(rounds//2),rounds_excluded=rounds%2,
        pair_means_us=paired,us_per_call=medians,
        own_over_qfplib=medians['own']/medians['qfplib'] if medians['qfplib']>0 else None,
        paired_differences_us=differences,median_paired_delta_us=statistics.median(differences),
        mean_paired_delta_us=statistics.mean(differences),
        empirical_delta_range_us=[min(differences),max(differences)],
        method='Average each adjacent pair of rounds with opposite library order, then take the median of those pair averages. The empirical range is not a confidence interval.')


def decode(raw,chunk,inputs):
    h=struct.unpack_from('<10I',raw)
    cases,loops=chunk['cases'],chunk['loops'];kind=chunk['kind']
    assert h[0]==0x4D305250 and h[1] in (1,2,3,4),h
    rounds=9 if h[1] in (1,2) else 12
    cached=h[1] in (2,4)
    assert h[2:7]==(chunk['index'],kind,cases,loops,rounds),h
    assert not h[7] and h[8]==0xFFFFFFFF,('Owned result mismatch',h)
    counter_offset=40+16*rounds
    result_offset=counter_offset+(32*rounds if cached else 0)
    assert len(raw)==result_offset+16*cases
    timings=struct.unpack_from('<'+'I'*(4*rounds),raw,40);n=cases*loops
    series={}
    for index,name in enumerate(('own','qfplib')):
        start=index*rounds
        elapsed=timings[start:start+rounds];control=timings[2*rounds+start:3*rounds+start]
        paired=[(x-y)/n for x,y in zip(elapsed,control)]
        series[name]=dict(median_us=statistics.median(paired),mean_us=statistics.mean(paired),
            min_us=min(paired),max_us=max(paired),raw_batch_us=list(elapsed),control_batch_us=list(control),paired_us=paired)
        if cached:
            counters=struct.unpack_from('<'+'I'*(8*rounds),raw,counter_offset)
            hits=counters[start:start+rounds];accesses=counters[2*rounds+start:3*rounds+start]
            control_hits=counters[4*rounds+start:5*rounds+start];control_accesses=counters[6*rounds+start:7*rounds+start]
            assert all(0<=x<=y<0xFFFFFFFF for x,y in zip(hits+control_hits,accesses+control_accesses))
            misses=[((acc-hit)-(ca-ch))/n for acc,hit,ca,ch in zip(accesses,hits,control_accesses,control_hits)]
            series[name]['cache']=dict(hits=list(hits),accesses=list(accesses),control_hits=list(control_hits),
                control_accesses=list(control_accesses),paired_misses_per_call=misses,
                median_misses_per_call=statistics.median(misses),
                median_accesses_per_call=statistics.median((x-y)/n for x,y in zip(accesses,control_accesses)))
    wrong=0;worst=0;rows=[]
    width=32 if kind in (6,7,11,12) else 64
    floating=kind<=5 or kind in (10,11)
    for i in range(cases):
        a,b,expected=struct.unpack_from('<3Q',inputs,32+24*i)
        own,qfp=struct.unpack_from('<2Q',raw,result_offset+16*i)
        # The timing corpus contains finite values; any NaN result is wrong.
        assert own==expected,(chunk['operation'],hex(a),hex(b),hex(own),hex(expected))
        error=abs(ordered(qfp,width)-ordered(expected,width)) if floating else int(qfp!=expected)
        wrong+=qfp!=expected;worst=max(worst,error)
        rows.append(dict(a=f'{a:016X}',b=f'{b:016X}',expected=f'{expected:016X}',own=f'{own:016X}',qfplib=f'{qfp:016X}'))
    row=dict(index=chunk['index'],stream_index=chunk['stream_index'],part=chunk['part'],operation=chunk['operation'],
        stream=chunk['stream'],cases=cases,samples=n,rounds=rounds,app_warmup_us=h[9],timings=series,
        order_balanced=order_balanced(series),owned_wrong_rounding=0,
        qfplib_wrong_results=wrong,qfplib_worst_ulp=worst if floating else None,results=rows)
    row.update({k:chunk[k] for k in ('reference_kind','reference_formula','reference_domain') if k in chunk})
    return row


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--uid',required=True)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--operations',nargs='+')
    p.add_argument('--indexes',type=int,nargs='+')
    p.add_argument('--settle-ms',type=int,default=1000,help='Let terminal/display traffic settle before opening each benchmark APP.')
    p.add_argument('--stop-file',type=Path,help='Stop between completed chunks when this file exists; cleanup and preserve acquired results.')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    assert 0<=a.settle_ms<=10000
    config=json.loads((a.build/'benchmark.json').read_text());directory=config['directory']
    layout=config.get('production_layout',{})
    assert layout.get('status')=='PASS','A production math layout proof is required before hardware timing'
    assert sha(a.build/'layout-proof.json')==config['layout_proof_sha256']
    assert sha(a.build/'firmware/mk61s-picocalc-pico-h.elf')==layout['comparison_elf_sha256']==config['elf_sha256']
    assert config.get('linked_image_bytes')==config['firmware_manifest']['flash_bytes'],'Boot CRC extent is unverified'
    assert re.fullmatch(r'/MK61S-M0-TIMING-[A-Za-z0-9-]+',directory)
    assert re.fullmatch(r'[0-9A-F]{16}',a.uid)
    app=Path(config['app']);assert sha(app)==config['app_sha256']
    chunks=[g for g in config['chunks'] if (not a.operations or g['operation'] in a.operations) and (not a.indexes or g['index'] in a.indexes)]
    assert chunks
    if a.indexes:
        assert len(a.indexes)==len(set(a.indexes)),'Repeated chunk index'
        assert set(a.indexes)<={g['index'] for g in config['chunks']},'Unknown chunk index'
        priority={index:position for position,index in enumerate(a.indexes)}
        chunks.sort(key=lambda g:priority[g['index']])
    created=False;rows=[];before=None;after=None;final=None;failure=None;stopped=False
    with MathPort(a.port,keyboard_layout=0) as port:
        mode_status=port.status()
        if 'TERMINAL=COMMAND' not in mode_status:port.commands()
        identity=port.command('identity');assert 'UID='+a.uid in identity,identity
        initial=port.status();build=config['firmware_manifest']['build_id'].upper()
        for token in ('BUILD='+build,'RP2040 125 MHz','MATH_TEST=OK','FIRMWARE_CRC=valid','CRASH=NONE','RUN=0 BUSY=0','USB_DISK=0','RUNTIME=NONE','SERVICE=CLOSED','DIRTY=0'):
            assert token in initial,(token,initial)
        before={c:port.command(c) for c in ('reg','stk','hout','pwd')}
        assert directory[1:]+'/' not in port.command('ls /')
        try:
            answer=port.command('mkdir '+directory);assert 'ERROR' not in answer,answer;created=True
            write_file(port,directory+'/TIMING.APP',app.read_bytes())
            for chunk in chunks:
                if a.stop_file and a.stop_file.exists():
                    stopped=True;break
                path=Path(chunk['input']);assert sha(path)==chunk['input_sha256']
                data=path.read_bytes();write_file(port,directory+'/INPUT.bin',data)
                port.pump(a.settle_ms/1000.)
                answer=port.command('open "'+directory+'/TIMING.APP"',timeout=120)
                assert 'APP_FLOW_RESULT=0' in answer,answer
                raw=read_file(port,directory+'/RESULT.bin')
                (a.output/f"{chunk['index']:03d}.bin").write_bytes(raw)
                row=decode(raw,chunk,data);rows.append(row)
                if 'rounds' in config:assert row['rounds']==config['rounds'],'APP round count differs from frozen contract'
                assert row['app_warmup_us']>=config.get('app_warmup_us',0),'APP warm-up shorter than the frozen benchmark contract'
                (a.output/f"{chunk['index']:03d}.json").write_text(json.dumps(row,indent=2)+'\n')
                displayed=row['order_balanced']['us_per_call'] if config.get('primary_estimator')=='order_balanced_median' else {k:v['median_us'] for k,v in row['timings'].items()}
                print(chunk['index'],chunk['operation'],chunk['stream'],
                    {k:round(v,6) for k,v in displayed.items()},'QFP errors',row['qfplib_wrong_results'],flush=True)
        except BaseException as error:
            failure=repr(error);raise
        finally:
            cleanup_session(port,a.output,before,directory,created,identity,initial,failure)
    groups=[]
    for index in sorted({r['stream_index'] for r in rows}):
        parts=[r for r in rows if r['stream_index']==index];cases=sum(r['cases'] for r in parts)
        first=parts[0]
        balanced=config.get('primary_estimator')=='order_balanced_median'
        if balanced:assert all(r['order_balanced']['rounds_excluded']==0 for r in parts)
        mean={k:sum((r['order_balanced']['us_per_call'][k] if balanced else r['timings'][k]['median_us'])*r['cases'] for r in parts)/cases for k in ('own','qfplib')}
        groups.append(dict(stream_index=index,operation=first['operation'],stream=first['stream'],cases=cases,
            us_per_call=mean,own_over_qfplib=mean['own']/mean['qfplib'] if mean['qfplib']>0 else None,
            estimator='order_balanced_median' if balanced else 'legacy_per_library_median'))
        groups[-1].update({k:first[k] for k in ('reference_kind','reference_formula','reference_domain') if k in first})
    report=dict(status='PARTIAL_STOPPED' if stopped else 'PASS',recorded_at=datetime.now(timezone.utc).isoformat(),identity=identity,
        host_runner_sha256=sha(Path(__file__)),
        terminal_settle_ms=a.settle_ms,
        firmware_manifest=config['firmware_manifest'],method=config['method'],groups=groups,chunks=rows,
        all_prepared_chunks_completed=len(rows)==len(config['chunks']),calculator_data_preserved=True,
        selected_chunks_completed=len(rows)==len(chunks),stop_requested=stopped,
        temporary_directory_removed=True,primary_estimator=config.get('primary_estimator','legacy_per_library_median'),
        scope='Physical RP2040 timings; finite controlled workloads. Group times weight per-chunk estimates by case count. New reports use medians of opposite-order pair averages from twelve calibrated rounds; legacy reports retain per-library medians from nine rounds. Raw batches and both summaries remain available. Qfplib output error is reported separately.')
    report.update({k:config[k] for k in ('comparison_set','composition_scope','composition_source_sha256') if k in config})
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
