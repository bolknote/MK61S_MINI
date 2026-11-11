"""Verify the real Thumb-2 kernels and DWT lifetime; modeled counter, no timing claim."""
import hashlib,json,random,struct
from arm_execution import Target,B
from unicorn import UC_HOOK_MEM_READ
OUT=B/'southbridge-runtime/module-bench'
t=Target(B/'southbridge-runtime/arm-harness/harness.elf')
t.u.mem_map(0xe0001000,0x1000);t.u.mem_map(0xe000e000,0x1000)
cycles=0
def get(a):return struct.unpack('<I',t.u.mem_read(a,4))[0]
def put(a,v):t.u.mem_write(a,struct.pack('<I',v))
def counter(uc,access,address,size,value,unused):
 global cycles
 if address==0xe0001004 and get(0xe0001000)&1 and get(0xe000edfc)&(1<<24):
  cycles+=17;put(address,cycles)
t.u.hook_add(UC_HOOK_MEM_READ,counter)
package=(OUT/'q4_m3_bench.s3m').read_bytes();module=t.load(package);checked=0
rng=random.Random(0x4d334457)
def write_input(raw):
 for at in range(0,len(raw),252):t.request(5,struct.pack('<I',at)+raw[at:at+252])
def output(job,n):
 result=bytearray()
 for at in range(0,n,252):result.extend(t.request(8,struct.pack('<III',job,at,min(252,n-at))))
 return result
for case in range(16):
 rows=case+1;xs=[-32768 if case==0 else 32767 if case==1 else rng.randint(-32768,32767)for _ in range(32)]
 weights=[[rng.randint(-8,7)for _ in range(32)]for _ in range(rows)]
 raw=struct.pack('<III32h',0x31544451,rows,32,*xs)+bytes((w[j]+8)|((w[j+1]+8)<<4)for w in weights for j in range(0,32,2))
 write_input(raw);job=struct.unpack('<I',t.request(6,struct.pack('<III',module,len(raw),1000)))[0]
 if case==0:assert t.send(t.last_frame)==t.last_reply
 for _ in range(rows):t.call('harness_tick')
 status=struct.unpack('<7I',t.request(7,struct.pack('<I',job)));assert status[1:3]==(4,0)
 result=output(job,64+4*rows);assert struct.unpack_from('<III',result)==(rows,case+1,16)
 actual=list(struct.unpack_from('<'+'i'*rows,result,64))
 assert actual==[sum(x*w for x,w in zip(xs,row))for row in weights];checked+=rows
 assert get(0xe0001000)&1 and get(0xe000edfc)&(1<<24)
for seed in [0,23,0x12345678,0xffffffff]:
 raw=struct.pack('<IIII',0x314d4350,512,seed,0);write_input(raw)
 job=struct.unpack('<I',t.request(6,struct.pack('<III',module,16,1000)))[0]
 assert t.call('harness_state')==4 # Complete during INIT, no STEP needed.
 assert output(job,512)==bytes((seed+29*i+(i>>4))&255 for i in range(512))
t.request(10);assert get(0xe0001000)==0 and get(0xe000edfc)==0
# Counter absence is a normal module error; it cannot silently report timings.
put(0xe0001000,1<<25);module=t.load(package)
raw=struct.pack('<III32h',0x31544451,1,32,*([1]*32))+bytes([0x88]*16);write_input(raw)
t.request(6,struct.pack('<III',module,len(raw),1000),expected=7);t.request(10)
assert get(0xe0001000)==1<<25 and get(0xe000edfc)==0
report=dict(status='M3_BENCH_ARM_PASS',physical_io=False,physical_timing=False,
            package_sha256=hashlib.sha256(package).hexdigest(),independent_int64_rows=checked,
            three_kernels_and16_samples_per_row=True,duplicate_start=True,
            pcm_bytes_verified=2048,dwt_ctrl_demcr_restored=True,counter_absence_rejected=True)
(OUT/'arm-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
