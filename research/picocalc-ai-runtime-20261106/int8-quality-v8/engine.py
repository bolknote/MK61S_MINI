from pathlib import Path
import ctypes as C,json
B=Path(__file__).resolve().parent
class Engine:
 def __init__(self,mode,reuse=True):
  self.mode=mode;self.reuse=reuse;self.previous=[]
  self.lib=C.CDLL(str(B/'quality-probe.dylib'));l=self.lib
  l.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];l.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint];l.codec_set_mode.argtypes=[C.c_int]
  l.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
  l.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
  l.mk_ai_decode.argtypes=[C.c_ushort,C.c_char_p,C.c_uint,C.POINTER(C.c_uint)];l.mk_ai_rewind.argtypes=[C.c_uint]
  raw=(B/'model'/('model.mka'if mode=='lut-fp32'else'model-nibble.mka')).read_bytes();self.buffer=C.create_string_buffer(raw)
  assert l.mk_ai_open(self.buffer,len(raw))==0
  mask=json.loads((B/'model/output-token-ids.json').read_text());ids=(C.c_ushort*len(mask))(*mask);l.codec_set_mask(ids,len(mask));l.codec_set_mode({'lut-fp32':3,'int8':1,'swar-int8':4}[mode])
 def generate(self,text):
  l=self.lib;arr=(C.c_ushort*1024)();used=C.c_uint();status=l.codec_encode(text.encode(),arr,1024,C.byref(used))
  if status or not 0<used.value<1024:return dict(reply='',tokens=[],input_tokens=used.value,error='encode_or_context:'+str(status),reused=0)
  ids=list(arr[:used.value]);common=0
  if self.reuse:
   for a,b in zip(ids[:-1],self.previous):
    if a!=b:break
    common+=1
  if not common:l.mk_ai_reset()
  elif not l.mk_ai_rewind(common):raise RuntimeError('prefix rewind failed')
  best=C.c_ushort()
  for i in range(common,len(ids)):
   status=l.codec_forward(ids[i],int(i+1==len(ids)),C.byref(best),None)
   if status:raise RuntimeError('prefill status '+str(status))
  self.previous=ids;out=[];pieces=[];raw=C.create_string_buffer(2049);n=C.c_uint();eos=False
  for _ in range(min(512,1024-len(ids))):
   token=best.value
   if token==2:eos=True;break
   status=l.mk_ai_decode(token,raw,len(raw),C.byref(n))
   if status:raise RuntimeError('decode status '+str(status))
   out.append(token);pieces.append(raw.raw[:n.value]);status=l.codec_forward(token,1,C.byref(best),None)
   if status:raise RuntimeError('generation status '+str(status))
  return dict(reply=b''.join(pieces).decode(),tokens=out,input_tokens=len(ids),error=None,eos=eos,reused=common)
