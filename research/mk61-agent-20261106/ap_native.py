"""The six-action diagnostic agent on the existing portable Q4 engine."""
import ctypes as C
import json
from pathlib import Path
from ac_native import Engine as Parent
from aj_native import prepare_source,MAX_INPUT_BYTES
from ap_common import ACTIONS,ACTION_IDS,ACTION_ID,CORRECT_IDS


class Engine(Parent):
    def __init__(self,root,arm='full'):
        self.root=Path(root);self.tool=arm;self.role=None;self.forced_action=None
        self.lib=C.CDLL(str(self.root/'native/codec-probe.dylib'))
        self.parser=C.CDLL(str(self.root/'native/action-probe.dylib'));l=self.lib;p=self.parser
        l.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];l.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
        l.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
        l.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
        l.mk_ai_decode.argtypes=[C.c_ushort,C.c_char_p,C.c_uint,C.POINTER(C.c_uint)]
        p.ab_allows.argtypes=[C.c_ushort,C.c_char_p];p.ab_accept.argtypes=[C.c_ushort,C.c_char_p];p.ab_body.argtypes=[C.POINTER(C.c_ubyte)]
        self.capacity=max((self.root/'export'/a/'model.mka').stat().st_size for a in ['full','short'])
        self.buffer=C.create_string_buffer(self.capacity);self.loads=0

    def open(self,role='tool'):
        if self.role==self.tool:return
        folder=self.root/'export'/self.tool;path=folder/'model.mka';n=path.stat().st_size
        with path.open('rb')as stream:assert stream.readinto(memoryview(self.buffer).cast('B')[:n])==n
        assert self.lib.mk_ai_open(self.buffer,n)==0
        self.allowed=json.loads((folder/'output-token-ids.json').read_text());self.pieces={}
        chars=C.create_string_buffer(128);size=C.c_uint()
        for token in self.allowed:
            assert self.lib.mk_ai_decode(token,chars,len(chars),C.byref(size))==0;self.pieces[token]=chars.raw[:size.value]
        self.headers=json.loads((folder/'protocol.json').read_text())['neural_headers'];self.role=self.tool;self.loads+=1

    def prefill(self,text,segmented=False):
        assert segmented and text.endswith('<')and len(text.encode())<=MAX_INPUT_BYTES
        encoded=(C.c_ushort*1024)();used=C.c_uint();best=C.c_ushort()
        if self.lib.codec_encode(text[:-1].encode(),encoded,1023,C.byref(used))!=0:return None
        encoded[used.value]=30;used.value+=1
        if used.value>=1016:return None
        inputs=list(encoded[:used.value]);allowed=ACTION_IDS+CORRECT_IDS;ids=(C.c_ushort*len(allowed))(*allowed)
        self.lib.codec_set_mask(ids,len(allowed));logits=(C.c_float*8224)();self.lib.mk_ai_reset()
        for at,token in enumerate(inputs):
            last=at+1==len(inputs)
            assert self.lib.codec_forward(token,int(last),C.byref(best),logits if last else None)==0
        best.value=ACTION_ID[self.forced_action]if self.forced_action else max(ACTION_IDS,key=lambda i:logits[i])
        self.last_margin=float(logits[CORRECT_IDS[1]]-logits[CORRECT_IDS[0]])
        return inputs,best

    def generate(self,text,forced_action=None):
        self.forced_action=forced_action;self.last_margin=None
        try:
            result=super().generate(text);result['correctness_margin']=self.last_margin;return result
        finally:self.forced_action=None
