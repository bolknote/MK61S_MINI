"""Actual old/fixed Thumb-2 callbacks + exact watchdog predicate, modeled I2C.

The fixture models HAL's documented ADDR-clear side effect on a successful
sequential RX/TX call. It does not claim to observe STM32's internal state on
the physical failed device. UART/DMA and module code execute in the same VM.
"""
from pathlib import Path
import importlib.util,json,struct,sys
P=Path(__file__).resolve().parents[1];R=P.parent;ROOT=R.parents[1]
sys.path.insert(0,str(P/'tests'))
spec=importlib.util.spec_from_file_location('i2c_combined',P/'tests/combined_execution.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
B=ROOT/'.build/mk61ai/i2c-expiry-fix'
WRITE,READ=1,0 # HAL direction names describe the remote master's operation.
power_candidate=json.loads((B/'build.json').read_text())['variants'][1].get('power_status',False)

def target(fixed):
 c.B=B/('fixed'if fixed else'original')
 return c.Transport()

def select(t,reg):
 assert t.call('harness_address',WRITE)==0
 assert t.call('harness_rx_byte',reg)==1
 t.call('harness_stop')
 assert t.call('harness_state')==2

def response(t):
 held=t.call('harness_address',READ);word=t.call('harness_tx_word')
 t.call('harness_stop');return held,word

old=target(False);select(old,9);assert old.call('harness_watchdog',1263)==0
assert old.call('harness_address',READ)==1
assert old.call('harness_watchdog',15000)==0 and old.call('harness_held')==1
# A second write in the middle of a selection also leaves ADDR pending.
old2=target(False);select(old2,9);assert old2.call('harness_address',WRITE)==1

t=target(True);cases=0
for delay in (0,16,999,1000,1001,1263,5000):
 t.call('harness_set_clock',10000);select(t,9)
 assert t.call('harness_enqueue',1,27)==1
 state=t.call('harness_watchdog',10000+delay)
 assert state==(0 if delay>1000 else 2)
 held,word=response(t);assert not held
 if delay>1000:
  assert word==0 # No fake key, no FIFO pop after stale selection.
  assert t.call('harness_i2c',9,0,0)==0x11b
 else:assert word==0x11b
 assert t.call('harness_i2c',9,0,0)==0
 cases+=1

# An unsolicited read and repeated read return empty, without register writes.
before=t.call('harness_effects')
for _ in range(8):assert response(t)==(0,0)
assert t.call('harness_effects')==before

# Incomplete/expired writes are discarded; a fresh normal write applies once.
t.call('harness_set_clock',20000);select(t,0x85)
assert t.call('harness_rx_byte',123)==1
t.call('harness_watchdog',21263)
assert response(t)==(0,0) and t.call('harness_effects')==before
assert response(t)==(0,0) and t.call('harness_effects')==before
assert t.call('harness_i2c',5,1,32)==0x0520
assert t.call('harness_effects')==before+1

# Missing/short payloads must not replay the previous register's bytes.
# Count the RTC setters as side effects too, rather than trusting an echo.
for reg,n,reply_n in ((5,1,2),(10,1,2),(2,1,2),(0x12,1,2),
                      (0x13,1,2),(0x14,3,5),(0x15,3,4),
                      (0x16,3,5),(0x17,3,4)):
 select(t,reg|0x80)
 assert t.call('harness_rx_payload',0x030201,n)==1
 assert t.call('harness_address',READ)==0
 assert t.call('harness_tx_size')==reply_n
 t.call('harness_stop')
 before=t.call('harness_effects')
 assert response(t)==(0,0) and t.call('harness_effects')==before
 select(t,reg|0x80)
 assert response(t)==(0,0)
 assert t.call('harness_effects')==before
 # Start a separate read without sending even the register byte.
 assert t.call('harness_address',WRITE)==0
 assert response(t)==(0,0)
 assert t.call('harness_effects')==before

# New address supersedes an incomplete request, including after unanswered TX.
for old_reg in (9,0x0b,0x85):
 select(t,old_reg)
 assert t.call('harness_address',WRITE)==0
 assert t.call('harness_rx_byte',9)==1
 assert response(t)==(0,0)
 select(t,9);assert t.call('harness_address',READ)==0
 assert t.call('harness_address',WRITE)==0
 assert t.call('harness_rx_byte',9)==1
 assert response(t)==(0,0)

# Any HAL refusal quiesces the peripheral; the main-loop flag rearms it
# immediately, even though application FSM is IDLE and1s has not elapsed.
for failure in (1,2,3):
 t.call('harness_force_api',failure)
 assert t.call('harness_address',WRITE)==0 and not t.call('harness_enabled')
 t.call('harness_force_api',0);t.call('harness_watchdog',1)
 assert t.call('harness_enabled') and not t.call('harness_held')
 select(t,9);t.call('harness_force_api',failure)
 assert t.call('harness_address',READ)==0 and not t.call('harness_enabled')
 t.call('harness_force_api',0);t.call('harness_watchdog',1)
 assert t.call('harness_enabled') and t.call('harness_i2c',0x0b,0,0)==0x0bad

# Re-enable can admit an IRQ before reset returns. Main must not overwrite
# that new register-selection state afterwards.
select(t,9);t.call('harness_race_write');assert t.call('harness_watchdog',0x100000)==1
assert t.call('harness_rx_byte',9)==1 and response(t)==(0,0)

# Unsigned millisecond wrap still expires the old transaction exactly once.
t.call('harness_set_clock',0xffffff00);select(t,9)
assert t.call('harness_watchdog',0x100)==2
assert t.call('harness_watchdog',0x400)==0 and response(t)==(0,0)

if power_candidate:
 # The real PMU reader runs outside slave IRQs. Invalid telemetry is tagged,
 # and an expired POWER read must neither wedge the bus nor change settings.
 before=t.call('harness_effects')
 for raw,hal,online,status in ((0x2028,0,1,0xb7),(0x0428,0,1,0xbb),
                               (0x0028,0,1,0xb3),(0x0008,0,1,0xb1),
                               (0x2028,1,1,0xa0),(0x2028,0,0,0xa0)):
  value=t.call('harness_power',raw,hal,online)
  assert value&255==status
  assert bool(value&0x8000)==bool(status&4)
  assert t.call('harness_i2c',0x0f,0,0)==0x0f00+status
  assert t.call('harness_effects')==before
 t.call('harness_set_clock',29000);select(t,0x0f)
 t.call('harness_watchdog',30263)
 assert response(t)==(0,0) and t.call('harness_effects')==before
 assert t.call('harness_power',0x2028,0,1)&255==0xb7

# Keep UART DMA, its cached reply and native job alive across keyboard faults.
package=(ROOT/'.build/stm32-module-runtime-20261107/module/q4_dot.s3m').read_bytes()
t.call('harness_set_clock',30000)
t.request(1);module=t.load(package)
raw=struct.pack('<III32h',0x31544451,16,32,*([3]*32))+bytes([0x99]*256)
for at in range(0,len(raw),252):t.request(5,struct.pack('<I',at)+raw[at:at+252])
job=struct.unpack('<I',t.request(6,struct.pack('<III',module,len(raw),1000)))[0]
t.call('harness_force_api',2);assert t.call('harness_address',READ)==0
t.call('harness_force_api',0);t.call('harness_watchdog',30001)
for _ in range(32):
 status=struct.unpack('<7I',t.request(7,struct.pack('<I',job)))
 if status[1]==4:break
assert status[1:3]==(4,0),status
out=t.request(8,struct.pack('<III',job,0,72))
assert struct.unpack_from('<II',out)==(16,1)
assert struct.unpack_from('<16i',out,8)==tuple([96]*16)
assert t.call('harness_enqueue',1,27)==1 and t.call('harness_i2c',9,0,0)==0x11b
t.request(10)
report=dict(status='DELAYED_I2C_ARM_REGRESSION_PASS',physical_io=False,physical_timing=False,
 original_read_idle_addr_held_reproduced=True,original_watchdog_misses_idle_addr=True,
 original_write_nonidle_addr_held_reproduced=True,fixed_delay_cases=cases,
 no_fake_keys_or_fifo_loss_after_expired_selection=True,no_stale_register_write_replay=True,
 incomplete_selection_no_side_effects=True,hal_failure_quiesce_rearm=True,
 rearm_new_irq_not_erased=True,millisecond_wrap=True,uart_dma_and_native_job_survive=True,
 independent_native_rows=16,callback_watchdog_sources='exact installed sources plus reviewed minimal delta',
 power_status_coexists=bool(power_candidate),
 limitation='HAL side effects modeled; physical failed STM32 registers were not captured')
(B/'regression.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
