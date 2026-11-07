"""Native Q4 generation with the allocation-free seven-action grammar."""
import ctypes as C
import json
from pathlib import Path
from aa_common import ACTIONS,ACTION_IDS


class Native:
    def __init__(self,folder):
        root=folder.parent.parent
        self.lib=C.CDLL(str(root/'native/codec-probe.dylib'))
        self.parser=C.CDLL(str(root/'native/action-probe.dylib'))
        l=self.lib;p=self.parser
        l.mk_ai_open.argtypes=[C.c_void_p,C.c_uint]
        l.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
        l.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
        l.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
        l.mk_ai_decode.argtypes=[C.c_ushort,C.c_char_p,C.c_uint,C.POINTER(C.c_uint)]
        p.aa_allows.argtypes=[C.c_ushort,C.c_char_p];p.aa_accept.argtypes=[C.c_ushort,C.c_char_p]
        p.aa_body.argtypes=[C.POINTER(C.c_ubyte)]
        self.buffer=C.create_string_buffer((folder/'model.mka').read_bytes())
        assert l.mk_ai_open(self.buffer,len(self.buffer)-1)==0
        self.allowed=json.loads((folder/'output-token-ids.json').read_text());self.pieces={}
        chars=C.create_string_buffer(128);count=C.c_uint()
        for token in self.allowed:
            assert l.mk_ai_decode(token,chars,len(chars),C.byref(count))==0
            self.pieces[token]=chars.raw[:count.value]

    def mask(self):
        allowed=[i for i in self.allowed if self.parser.aa_allows(i,self.pieces[i])]
        assert allowed
        values=(C.c_ushort*len(allowed))(*allowed);self.lib.codec_set_mask(values,len(allowed))

    def generate(self,text):
        l=self.lib;p=self.parser;p.aa_reset();self.mask()
        encoded=(C.c_ushort*1024)();used=C.c_uint();best=C.c_ushort()
        if l.codec_encode(text.encode(),encoded,1024,C.byref(used))!=0 or used.value>=1023:
            return {'action':None,'body':[],'codec_error':'context_overflow','generated_token_ids':[]}
        l.mk_ai_reset()
        for i,token in enumerate(encoded[:used.value]):
            assert l.codec_forward(token,int(i+1==used.value),C.byref(best),None)==0
        tokens=[]
        for _ in range(min(512,1024-used.value)):
            token=best.value
            assert p.aa_accept(token,self.pieces[token])
            if token!=2:tokens.append(token)
            if p.aa_complete():break
            self.mask();assert l.codec_forward(token,1,C.byref(best),None)==0
        if not p.aa_complete():
            return {'action':None,'body':[],'codec_error':'incomplete','generated_token_ids':tokens}
        body=(C.c_ubyte*512)();size=p.aa_body(body)
        return {'action':ACTIONS[p.aa_action()],'body':list(body[:size]),'codec_error':None,
                'generated_token_ids':tokens,'input_token_ids':list(encoded[:used.value])}
