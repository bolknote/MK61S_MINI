"""Create the broader launcher by retaining the exact successful probe loop."""
from pathlib import Path
W=Path(__file__).resolve().parent
source=(W/'probe.py').read_text()
anchor="states={'READY':"
assert source.count(anchor)==1
extra='''# All old raw d2f records, including previously unprofiled adverse inputs.
source_pins={}
for name in ('float-d2f.records.bin.gz','addendum/float-d2f.records.bin.gz'):
 path=Q/name;source_pins[str(path.relative_to(ROOT))]=sha(path)
 data=gzip.decompress(path.read_bytes());assert len(data)%48==0
 for x,b,c,old,exact,mpfr in struct.iter_unpack('<6Q',data):
  assert b==c==0 and equal(exact,mpfr,32)
  assert equal(integer_cast(x,64,32),exact,32)
  add(x,'inherited_raw_float_corpus')
for exponent in range(2048):
 for fraction in (0,1,(1<<28)-1,1<<28,(1<<28)+1,(1<<29)-1,1<<51,(1<<52)-(1<<28),(1<<52)-1):
  for sign in (0,1<<63):add(sign|(exponent<<52)|fraction,'all2048_exponent_fields')
# All normal exponents, both signs, parity/guard/sticky/carry head classes.
normal_half_inputs=0
for exponent in range(897,1151):
 for high in (0,1,0x7ffff,0xffffe,0xfffff):
  for retained_low in range(8):
   for tail in (0,1,(1<<28)-1,1<<28,(1<<28)+1,(1<<29)-1):
    fraction=(high<<32)|(retained_low<<29)|tail
    for sign in (0,1<<63):
     add(sign|(exponent<<52)|fraction,'all_normal_exponent_RNE_grid')
     normal_half_inputs+=tail==(1<<28)
subnormal_half_inputs=0
for exponent in range(873,897):
 n=926-exponent;low=(1<<52)>>n;high=((1<<53)-1)>>n
 choices={low,low+1,high-1,high}
 choices.update(rng.randrange(low,high+1) for _ in range(32))
 for retained in choices:
  midpoint=(retained<<n)+(1<<(n-1))
  for delta in (-1,0,1):
   mantissa=midpoint+delta
   if not((1<<52)<=mantissa<(1<<53)):continue
   for sign in (0,1<<63):
    add(sign|(exponent<<52)|(mantissa-(1<<52)),'subnormal_actual_half_cells')
    subnormal_half_inputs+=delta==0
for bit in range(52):
 for fraction in (1<<bit,((1<<52)-1)^(1<<bit),(1<<bit)|1):
  for sign in (0,1<<63):add(sign|0x7ff0000000000000|fraction,'NaN_payload_bit_controls')
for _ in range(1024):
 for sign in (0,1<<63):add(sign|0x7ff0000000000000|rng.getrandbits(52),'NaN_full_mantissa_random')
for _ in range(65536):add(rng.getrandbits(64),'uniform_raw_65536')
vector_data=b''.join(struct.pack('<Q',x) for x in jobs)
(W/'qualification-inputs.bin').write_bytes(vector_data)
print('prepared',len(jobs),'inputs; actual normal halves',normal_half_inputs,'subnormal halves',subnormal_half_inputs,flush=True)
'''
source=source.replace(anchor,extra+anchor)
source=source.replace("'status':'D2F_PUBLIC_LEAF_SHORT_PROBE'","'status':'AUTHOR_FULL_PROFILE_D2F_LEAF'")
source=source.replace("'hardware_accessed':False}","'hardware_accessed':False,'all_cases_profiled':True,'source_pins':source_pins,'normal_actual_half_inputs_generated':normal_half_inputs,'subnormal_actual_half_inputs_generated':subnormal_half_inputs,'qualification_inputs_sha256':sha(W/'qualification-inputs.bin'),'reference_comparison_has_no_domain_filter':True}")
source=source.replace("W/'probe.json'","W/'qualification.json'")
(W/'qualify.py').write_text(source)
print('Created qualify.py from the unchanged probe execution loop')
