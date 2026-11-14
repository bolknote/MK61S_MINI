#!/usr/bin/env python3
"""Reject silent fallback, underruns, slow Z80 and incomplete M3 evidence."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('s3qual',ROOT/'tools/apps/spectrum/qualify_spectrum_m3_run.py')
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
base=dict(SYS_HZ=125000000,PERI_HZ=48000000,KBD='OK',SD='OK',SERVICE='CLOSED',RUNTIME='NONE',
          UI='CALCULATOR',CRASH='NONE',FIRMWARE_CRC='valid',APP_BUFFERS=0,APP_BUFFER_BYTES=0,
          APP_EXTERNAL_BYTES=0,APP_WINDOWS=0,BUILD='AABBCCDD',ACTUAL='12345678',EXPECTED='12345678',BOOTS=4)
base.update({key:0 for key in q.COUNTERS});base['I2C_ABORTS']=54
base.update(SYNTH_UNDERRUNS=0,M3_FALLBACKS=0,M3_ERROR=0,M3_UNDERRUNS=0,M3_UART_ERRORS=0,
            M3_UNLOAD_FAILURES=0,M3_READY_POLLS=0,M3_LATE_BLOCKS=0,M3_PROFILE=1,SYNTH_DMA=0,SYNTH_BLOCKS=9600,
            M3_INLINE_INPUT=1,M3_INLINE_REQUESTS=2000,M3_STREAM_WRITE_REQUESTS=0,M3_TX_BYTES=100000,M3_RX_BYTES=400000,
            M3_SAMPLES=307200,M3_BLOCKS=3200,M3_RENDER_SAMPLES=307200,M3_PRIME_US=7680,
            M3_RENDER_MAX_SLICE_US=600,M3_BLOCK_US=3700,M3_BLOCK_MIN_US=3100,M3_MIN_QUEUED=32,
            M3_RENDER_US=9000000,M3_BLOCK_TOTAL_US=11520000)
def status(changes=None):
    d=dict(base);d.update(changes or {});return '\n'.join(f'{k}={v}'for k,v in d.items())
def wire(mode=2,elapsed=12247040,fault=0,policy=1):
    return (f'SP3 POLICY remote_only={policy}\nSP3 RESULT mode={mode} frames=598 cycles=42864640 us={elapsed} starved=0\n'
            f'SP3 FRAME min_us=20470 max_us=20490 late_1ms=0 max_lag_us=20 strict_fault={fault}\n')
assert q.qualify(wire(),status(),status())['status']=='PASS'
nrz=dict(M3_TRANSPORT_FLAGS=103,M3_NRZ4_BLOCKS=3200,M3_NRZ4_BYTES=700000,M3_NRZ4_RETURNS=3200,
         M3_NRZ4_ERRORS=0,M3_NRZ4_RESTORE_US=9,M3_NRZ4_TRANSPORT_US=800,M3_NRZ4_WAIT_US=200,M3_NRZ4_HOLD_US=3900)
assert q.qualify(wire(),status(),status(nrz),require_nrz4=True)['status']=='PASS'
for changes,key in (({'M3_TRANSPORT_FLAGS':39},'nrz4_capability'),({'M3_NRZ4_ERRORS':1},'nrz4_no_errors'),
                    ({'M3_NRZ4_BLOCKS':0},'nrz4_block_coverage'),({'M3_NRZ4_BYTES':0},'nrz4_pcm_coverage'),
                    ({'M3_NRZ4_RETURNS':3199},'nrz4_all_pins_returned')):
    assert not q.qualify(wire(),status(),status({**nrz,**changes}),require_nrz4=True)['checks'][key]
try:q.qualify(wire(),status(),status(),require_nrz4=True)
except ValueError:pass
else:raise AssertionError('UART-only diagnostics cannot qualify NRZ4')
try:q.qualify(wire(mode=1,policy=0),status(),status(nrz),mode='local',require_nrz4=True)
except ValueError:pass
else:raise AssertionError('Local audio cannot qualify NRZ4')
known={'BOOTS':'20','BOOT_WATCHDOG':'0','RESET_REASON':'00010001','CRASH':'AVAILABLE'}
observed=status(known)
assert q.qualify(wire(),observed,observed)['status']=='FAIL'
result=q.qualify(wire(),observed,observed,preserved_boot=known)
assert result['status']=='PASS'and result['preserved_boot']==known
for key,value in (('BOOTS','21'),('BOOT_WATCHDOG','1'),('RESET_REASON','00000001'),('CRASH','NONE')):
    assert not q.qualify(wire(),observed,status({**known,key:value}),preserved_boot=known)['checks']['preserved_boot_'+key]
    assert not q.qualify(wire(),status({**known,key:value}),observed,preserved_boot=known)['checks']['preserved_boot_'+key]
for invalid in ({'CRASH':'AVAILABLE'},{**known,'BOOT_WATCHDOG':'1'},{**known,'CRASH':'NONE'},True):
    try:q.qualify(wire(),observed,observed,preserved_boot=invalid)
    except ValueError:pass
    else:raise AssertionError('Incomplete/unsafe preserved boot tuple accepted')
assert q.qualify(wire(elapsed=12247041),status(),status())['status']=='PASS' # 1us timestamp uncertainty.
assert not q.qualify(wire(elapsed=12247042),status(),status())['checks']['z80_at_least_3_5MHz']
assert not q.qualify(wire(elapsed=round(42864640/3.4998)),status(),status())['checks']['z80_at_least_3_5MHz']
for changes,key in [({'M3_FALLBACKS':1},'no_fallback'),({'M3_LATE_BLOCKS':1},'zero_M3_LATE_BLOCKS'),
                    ({'M3_READY_POLLS':1},'zero_M3_READY_POLLS'),({'I2C_ABORTS':55},'unchanged_I2C_ABORTS'),
                    ({'M3_SAMPLES':672,'M3_RENDER_SAMPLES':672},'continuous_sample_coverage'),
                    ({'M3_ERROR':-29},'zero_M3_ERROR'),({'SYS_HZ':200000000},'native_SYS_HZ'),
                    ({'SYNTH_DMA':1},'dma_released'),({'SYNTH_BLOCKS':0},'real_dma_output'),
                    ({'M3_INLINE_INPUT':0},'fused_input_supported'),({'M3_INLINE_REQUESTS':0},'fused_input_exercised'),
                    ({'M3_STREAM_WRITE_REQUESTS':1},'no_stream_write_roundtrips')]:
    result=q.qualify(wire(),status(),status(changes));assert result['status']=='FAIL' and key in result['failures'],result
assert not q.qualify(wire(fault=1),status(),status())['checks']['no_probe_fault']
assert not q.qualify(wire(policy=0),status(),status())['checks']['strict_remote_policy']
early=wire(fault=1).replace('frames=598 cycles=42864640 us=12247040',
                           'frames=4294967295 cycles=4294895456 us=3853025742')
result=q.qualify(early,status(),status())
assert not result['checks']['complete_run'] and not result['metrics']['timing_valid']
assert result['metrics']['mhz'] is None and result['metrics']['fps'] is None
empty=wire(fault=1).replace('frames=598 cycles=42864640 us=12247040','frames=0 cycles=0 us=0')
result=q.qualify(empty,status(),status())
for key in ('complete_run','z80_at_least_3_5MHz','z80_paced','no_frame_delays_over_1ms',
            'frame_lag_bounded','continuous_sample_coverage'):
    assert not result['checks'][key],key
assert q.qualify(wire(mode=1,policy=0),status(),status(),mode='local')['status']=='PASS'
# A long test must cover its entire requested duration. Extending the finite
# run cap never relaxes rates, late-block/frame, startup or native-slice limits.
long_cycles=29998*71680;long_us=long_cycles*2//7
long_wire=wire().replace('frames=598 cycles=42864640 us=12247040',
                         f'frames=29998 cycles={long_cycles} us={long_us}')
long_status=status({'M3_SAMPLES':long_us//40+2048,'M3_RENDER_SAMPLES':long_us//40+2048})
assert q.qualify(long_wire,status(),long_status)['status']=='FAIL'
assert q.qualify(long_wire,status(),long_status,run_frames=30000)['status']=='PASS'
assert not q.qualify(wire(),status(),status(),run_frames=30000)['checks']['complete_run']
for changes,key in [({'M3_LATE_BLOCKS':1},'zero_M3_LATE_BLOCKS'),
                    ({'M3_PRIME_US':20001},'started_promptly'),
                    ({'M3_RENDER_MAX_SLICE_US':2001},'native_slices_bounded')]:
    after=status({
        'M3_SAMPLES':long_us//40+2048,'M3_RENDER_SAMPLES':long_us//40+2048,**changes})
    assert not q.qualify(long_wire,status(),after,run_frames=30000)['checks'][key]
assert not q.qualify(long_wire.replace('late_1ms=0','late_1ms=1'),status(),long_status,
                     run_frames=30000)['checks']['no_frame_delays_over_1ms']
assert not q.qualify(long_wire.replace(f'us={long_us}',f'us={round(long_cycles/3.4998)}'),
                     status(),long_status,run_frames=30000)['checks']['z80_at_least_3_5MHz']
for invalid in (599,30001,True,600.0):
    try:q.qualify(long_wire,status(),long_status,run_frames=invalid)
    except ValueError:pass
    else:raise AssertionError('Invalid finite run length accepted')
try:q.qualify(wire(),status(),status().replace('M3_PROFILE=1',''))
except ValueError:pass
else:raise AssertionError('Incomplete diagnostics must hold qualification')
print('M3 qualification: exact3.5MHz/1us uncertainty, no hidden local200 fallback, native errors/late blocks/polls, full sample coverage and unchanged startup counters PASS')
