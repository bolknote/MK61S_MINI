#!/usr/bin/env python3
"""Qualify captured M0/M3 game diagnostics; this tool never opens hardware."""
import argparse
import json
from pathlib import Path
import re

COUNTERS=('PHYSICAL_KEYS','SETTINGS_WRITES','RTC_SET','ERRORS','QPI_FALLBACKS','TAIL_TIMEOUTS',
          'CRC_ERRORS','DMA_TIMEOUTS','LCD_ERRORS','SD_SPEED_FALLBACKS','SD_PROBE_FAILURES',
          'I2C_TIMEOUTS','I2C_ABORTS','SCREEN_ERRORS')

def field(text,key):
    values=re.findall(r'\b'+re.escape(key)+r'=([^\s]+)',text)
    if not values:raise ValueError('Missing native field '+key)
    if len(set(values))!=1:raise ValueError('Conflicting native field '+key)
    return values[0]

def qualify(wire,before,after,mode='remote',minimum_frames=590,run_frames=None,preserved_boot=None,require_nrz4=False):
    if run_frames is not None and (type(run_frames) is not int or not 600<=run_frames<=30000):
        raise ValueError('run_frames must be an integer in 600..30000')
    if require_nrz4 and mode!='remote':raise ValueError('NRZ4 qualification requires remote audio')
    # A documented crash predating this run must remain visible. Accept it
    # only with an explicitly pinned complete boot tuple, checked at BOTH
    # endpoints. Never infer a waiver from the observed crash flag itself.
    if preserved_boot is not None:
        if (not isinstance(preserved_boot,dict) or set(preserved_boot)!={'BOOTS','BOOT_WATCHDOG','RESET_REASON','CRASH'} or
            preserved_boot['CRASH']!='AVAILABLE' or preserved_boot['BOOT_WATCHDOG']!='0' or
            not all(isinstance(v,str) for v in preserved_boot.values())):
            raise ValueError('preserved_boot must pin BOOTS, BOOT_WATCHDOG=0, RESET_REASON and CRASH=AVAILABLE')
    rows=re.findall(r'(?m)^SP3 RESULT mode=(\d+) frames=(\d+) cycles=(\d+) us=(\d+) starved=(\d+)\r?$',wire)
    frame=re.findall(r'(?m)^SP3 FRAME min_us=(\d+) max_us=(\d+) late_1ms=(\d+) max_lag_us=(\d+) strict_fault=(\d+)\r?$',wire)
    policy=re.findall(r'(?m)^SP3 POLICY remote_only=(\d+)\r?$',wire)
    if len(rows)!=1 or len(frame)!=1 or len(policy)!=1:raise ValueError('Missing/ambiguous finite game records')
    engine,frames,cycles,elapsed,starved=map(int,rows[0]);fmin,fmax,late,lag,fault=map(int,frame[0])
    expected=2 if mode=='remote'else 1
    frame_limit=3100 if run_frames is None else run_frames
    elapsed_limit=35000000 if run_frames is None else max(35000000,run_frames*22000+5000000)
    cycle_limit=elapsed_limit*7//2
    required_frames=minimum_frames if run_frames is None else max(minimum_frames,run_frames-2)
    timing_valid=0<frames<=frame_limit and 0<cycles<=cycle_limit and 0<elapsed<=elapsed_limit
    checks={'selected_backend':engine==expected,'strict_remote_policy':int(policy[0])==(mode=='remote'),
            'complete_run':timing_valid and frames>=required_frames,
            'no_probe_fault':not fault and 'SP3 FAULT'not in wire,'producer_not_starved':starved==0,
            # Accept only the actual one-microsecond timestamp uncertainty;
            # 3.4998MHz over a multi-second run does not pass this predicate.
            'z80_at_least_3_5MHz':timing_valid and cycles*2>=7*max(0,elapsed-1),
            'z80_paced':timing_valid and cycles*2000<=7007*elapsed,
            'no_frame_delays_over_1ms':timing_valid and late==0,'frame_lag_bounded':timing_valid and lag<=1000}
    for key,value in {'SYS_HZ':'125000000','PERI_HZ':'48000000','KBD':'OK','SD':'OK',
                      'SERVICE':'CLOSED','RUNTIME':'NONE','UI':'CALCULATOR','CRASH':preserved_boot['CRASH']if preserved_boot else'NONE',
                      'FIRMWARE_CRC':'valid','APP_BUFFERS':'0','APP_BUFFER_BYTES':'0',
                      'APP_EXTERNAL_BYTES':'0','APP_WINDOWS':'0'}.items():
        checks['native_'+key]=field(after,key)==value
    if preserved_boot:
        for key,value in preserved_boot.items():
            checks['preserved_boot_'+key]=field(before,key)==field(after,key)==value
    for key in ('BUILD','ACTUAL','EXPECTED','BOOTS',*COUNTERS):
        checks['unchanged_'+key]=field(before,key)==field(after,key)
    checks['no_dma_underruns']=int(field(after,'SYNTH_UNDERRUNS'))==0
    checks['no_fallback']=field(after,'M3_FALLBACKS')==field(before,'M3_FALLBACKS')
    metrics={'mode':engine,'frames':frames,'cycles':cycles,'elapsed_us':elapsed,
             'timing_valid':timing_valid,'mhz':cycles/elapsed if timing_valid else None,
             'fps':frames*1e6/elapsed if timing_valid else None,
             'starved':starved,'frame_min_us':fmin,'frame_max_us':fmax,'late_frames_1ms':late,'max_frame_lag_us':lag}
    if mode=='remote':
        for key in ('M3_ERROR','M3_UNDERRUNS','M3_UART_ERRORS','M3_UNLOAD_FAILURES','M3_READY_POLLS','M3_LATE_BLOCKS'):
            checks['zero_'+key]=int(field(after,key))==0
        checks['native_profile']=field(after,'M3_PROFILE')=='1'
        checks['fused_input_supported']=field(after,'M3_INLINE_INPUT')=='1'
        checks['fused_input_exercised']=int(field(after,'M3_INLINE_REQUESTS'))>0
        checks['no_stream_write_roundtrips']=int(field(after,'M3_STREAM_WRITE_REQUESTS'))==0
        # SYNTH_DMA is the live ownership flag, cleared by AUDIO_CLOSE.
        # The retained refill counter proves DMA ran; leaving it active
        # after native return is a resource leak, not successful playback.
        checks['real_dma_output']=int(field(after,'SYNTH_BLOCKS'))>0
        checks['dma_released']=field(after,'SYNTH_DMA')=='0'
        samples=int(field(after,'M3_SAMPLES'));blocks=int(field(after,'M3_BLOCKS'))
        checks['continuous_sample_coverage']=timing_valid and samples>=max(192,cycles*95//14000)
        checks['profile_sample_coverage']=int(field(after,'M3_RENDER_SAMPLES'))==samples
        checks['started_promptly']=int(field(after,'M3_PRIME_US'))<=20000
        checks['native_slices_bounded']=int(field(after,'M3_RENDER_MAX_SLICE_US'))<=2000
        metrics.update(samples=samples,blocks=blocks,block_max_us=int(field(after,'M3_BLOCK_US')),
                       block_min_us=int(field(after,'M3_BLOCK_MIN_US')),prime_us=int(field(after,'M3_PRIME_US')),
                       min_queued=int(field(after,'M3_MIN_QUEUED')),
                       inline_requests=int(field(after,'M3_INLINE_REQUESTS')),
                       stream_write_requests=int(field(after,'M3_STREAM_WRITE_REQUESTS')),
                       transport_tx_bytes=int(field(after,'M3_TX_BYTES')),
                       transport_rx_bytes=int(field(after,'M3_RX_BYTES')),
                       native_render_us=int(field(after,'M3_RENDER_US')),
                       exchange_block_us=int(field(after,'M3_BLOCK_TOTAL_US')))
        if require_nrz4:
            nrz_blocks=int(field(after,'M3_NRZ4_BLOCKS'));nrz_bytes=int(field(after,'M3_NRZ4_BYTES'))
            nrz_returns=int(field(after,'M3_NRZ4_RETURNS'))
            # Archived uncompressed PCM measurements at either wire rate.
            checks.update(nrz4_capability=bool(int(field(after,'M3_TRANSPORT_FLAGS'))&(64|128)),
                          nrz4_no_errors=int(field(after,'M3_NRZ4_ERRORS'))==0,
                          nrz4_block_coverage=nrz_blocks>=blocks>0,
                          nrz4_pcm_coverage=nrz_bytes>=samples>0,
                          nrz4_all_pins_returned=nrz_returns==nrz_blocks)
            metrics.update(nrz4_blocks=nrz_blocks,nrz4_bytes=nrz_bytes,nrz4_returns=nrz_returns,
                           nrz4_restore_us=int(field(after,'M3_NRZ4_RESTORE_US')),
                           nrz4_transport_us=int(field(after,'M3_NRZ4_TRANSPORT_US')),
                           nrz4_wait_us=int(field(after,'M3_NRZ4_WAIT_US')),
                           nrz4_hold_us=int(field(after,'M3_NRZ4_HOLD_US')))
    failures=[k for k,v in checks.items()if not v]
    return dict(status='PASS'if not failures else'FAIL',mode=mode,checks=checks,failures=failures,preserved_boot=preserved_boot,
                metrics=metrics,physical_io=False,source='captured hardware logs; no new device access')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--wire',type=Path,required=True);ap.add_argument('--before',type=Path,required=True)
    ap.add_argument('--after',type=Path,required=True);ap.add_argument('--mode',choices=['remote','local'],default='remote')
    ap.add_argument('--run-frames',type=int,help='Expected fixture length for a continuous 600..30000-frame run')
    ap.add_argument('--preserved-boot',type=Path,help='JSON with the exact documented pre-existing BOOTS/BOOT_WATCHDOG/RESET_REASON/CRASH tuple; no crash clearing')
    ap.add_argument('--require-nrz4',action='store_true',help='Qualify archived uncompressed NRZ4 PCM, with zero NRZ errors and every pin lease returned')
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():raise SystemExit('Refusing to replace an existing qualification')
    try:result=qualify(args.wire.read_text(),args.before.read_text(),args.after.read_text(),args.mode,run_frames=args.run_frames,
                       preserved_boot=json.loads(args.preserved_boot.read_text())if args.preserved_boot else None,require_nrz4=args.require_nrz4)
    except ValueError as error:result={'status':'HOLD','error':str(error),'physical_io':False}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS'else 1

if __name__=='__main__':raise SystemExit(main())
