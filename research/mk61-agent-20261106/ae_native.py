"""Native actions plus a semantic-head margin, sharing one weight buffer and KV."""
import ctypes as C
from ac_native import Engine as Parent
from ae_common import ACTION_IDS,CORRECT_IDS


class Engine(Parent):
    def prefill(self,text,segmented=False):
        self.last_margin=None
        if not segmented:return super().prefill(text,False)
        assert text.endswith('<');encoded=(C.c_ushort*1024)();used=C.c_uint();best=C.c_ushort()
        if self.lib.codec_encode(text[:-1].encode(),encoded,1023,C.byref(used))!=0:return None
        encoded[used.value]=30;used.value+=1
        if used.value>=1016:return None
        inputs=list(encoded[:used.value]);allowed=ACTION_IDS+CORRECT_IDS;ids=(C.c_ushort*len(allowed))(*allowed)
        self.lib.codec_set_mask(ids,len(allowed));logits=(C.c_float*8224)();self.lib.mk_ai_reset()
        for at,token in enumerate(inputs):
            last=at+1==len(inputs)
            assert self.lib.codec_forward(token,int(last),C.byref(best),logits if last else None)==0
        best.value=max(ACTION_IDS,key=lambda i:logits[i]);self.last_margin=float(logits[CORRECT_IDS[1]]-logits[CORRECT_IDS[0]])
        return inputs,best

    def generate(self,text):
        result=super().generate(text);result['correctness_margin']=self.last_margin;return result
