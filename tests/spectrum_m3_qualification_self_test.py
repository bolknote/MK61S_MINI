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
            M3_SAMPLES=307200,M3_BLOCKS=3200,M3_RENDER_SAMPLES=307200,M3_PRIME_US=7680,
            M3_RENDER_MAX_SLICE_US=600,M3_BLOCK_US=3700,M3_BLOCK_MIN_US=3100,M3_MIN_QUEUED=32,
            M3_RENDER_US=9000000,M3_BLOCK_TOTAL_US=11520000)
def status(changes=None):
    d=dict(base);d.update(changes or {});return '\n'.join(f'{k}={v}'for k,v in d.items())
def wire(mode=2,elapsed=12247040,fault=0,policy=1):
    return (f'SP3 POLICY remote_only={policy}\nSP3 RESULT mode={mode} frames=598 cycles=42864640 us={elapsed} starved=0\n'
            f'SP3 FRAME min_us=20470 max_us=20490 late_1ms=0 max_lag_us=20 strict_fault={fault}\n')
assert q.qualify(wire(),status(),status())['status']=='PASS'
assert q.qualify(wire(elapsed=12247041),status(),status())['status']=='PASS' # 1us timestamp uncertainty.
assert not q.qualify(wire(elapsed=12247042),status(),status())['checks']['z80_at_least_3_5MHz']
assert not q.qualify(wire(elapsed=round(42864640/3.4998)),status(),status())['checks']['z80_at_least_3_5MHz']
for changes,key in [({'M3_FALLBACKS':1},'no_fallback'),({'M3_LATE_BLOCKS':1},'zero_M3_LATE_BLOCKS'),
                    ({'M3_READY_POLLS':1},'zero_M3_READY_POLLS'),({'I2C_ABORTS':55},'unchanged_I2C_ABORTS'),
                    ({'M3_SAMPLES':672,'M3_RENDER_SAMPLES':672},'continuous_sample_coverage'),
                    ({'M3_ERROR':-29},'zero_M3_ERROR'),({'SYS_HZ':200000000},'native_SYS_HZ'),
                    ({'SYNTH_DMA':1},'dma_released'),({'SYNTH_BLOCKS':0},'real_dma_output')]:
    result=q.qualify(wire(),status(),status(changes));assert result['status']=='FAIL' and key in result['failures'],result
assert not q.qualify(wire(fault=1),status(),status())['checks']['no_probe_fault']
assert not q.qualify(wire(policy=0),status(),status())['checks']['strict_remote_policy']
assert q.qualify(wire(mode=1,policy=0),status(),status(),mode='local')['status']=='PASS'
try:q.qualify(wire(),status(),status().replace('M3_PROFILE=1',''))
except ValueError:pass
else:raise AssertionError('Incomplete diagnostics must hold qualification')
print('M3 qualification: exact3.5MHz/1us uncertainty, no hidden local200 fallback, native errors/late blocks/polls, full sample coverage and unchanged startup counters PASS')
