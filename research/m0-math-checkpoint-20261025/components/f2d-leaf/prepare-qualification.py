from pathlib import Path
W=Path(__file__).resolve().parent
source=(W/'probe.py').read_text();anchor="states={'READY':";assert source.count(anchor)==1
source=source.replace('import hashlib,json,random,struct,sys','import gzip,hashlib,json,random,struct,sys')
extra='''raw_path=Q/'float-f2d.records.bin.gz';raw_bytes=gzip.decompress(raw_path.read_bytes())
assert len(raw_bytes)%48==0
for x,b,c,old,exact,mpfr in struct.iter_unpack('<6Q',raw_bytes):
 assert x<(1<<32) and b==c==0 and equal(exact,mpfr,64)
 assert equal(integer_cast(x,32,64),exact,64)
 add(x,'old9122_raw_records')
for exponent in range(1,255):
 for high in (0,1,0x3ffff,0x40000,0x7ffff,0x80000,0xffffe,0xfffff):
  for low in range(8):
   fraction=(high<<3)|low
   for sign in (0,1<<31):add(sign|(exponent<<23)|fraction,'all_normal_payload_split_classes')
for width in range(1,24):
 first=1<<(width-1);last=(1<<width)-1
 values=set(range(first,min(first+256,last+1)))
 values.update(range(max(first,last-255),last+1))
 values.update(rng.randrange(first,last+1) for _ in range(256))
 for value in values:
  for sign in (0,1<<31):add(sign|value,'all23_subnormal_widths_dense_heads_tails_random')
for bit in range(23):
 for fraction in (1<<bit,((1<<23)-1)^(1<<bit),(1<<bit)|1):
  if fraction:
   for sign in (0,1<<31):add(sign|0x7f800000|fraction,'NaN_payload_bit_controls')
for _ in range(4096):
 for sign in (0,1<<31):add(sign|0x7f800000|rng.getrandbits(23),'NaN_full_mantissa_random')
for _ in range(65536):add(rng.getrandbits(32),'uniform_raw65536')
vector_data=b''.join(struct.pack('<I',x) for x in jobs)
(W/'qualification-inputs.bin').write_bytes(vector_data)
print('prepared',len(jobs),'inputs',flush=True)
'''
source=source.replace(anchor,extra+anchor)
source=source.replace("'status':'F2D_PUBLIC_LEAF_SHORT_PROBE'","'status':'AUTHOR_FULL_PROFILE_F2D_LEAF'")
source=source.replace("'hardware_accessed':False}","'hardware_accessed':False,'all_cases_profiled':True,'old_raw_source_sha256':sha(raw_path),'qualification_inputs_sha256':sha(W/'qualification-inputs.bin'),'reference_comparison_has_no_domain_filter':True}")
source=source.replace("W/'probe.json'","W/'qualification.json'")
(W/'qualify.py').write_text(source)
print('Created qualify.py from unchanged successful probe execution loop')
