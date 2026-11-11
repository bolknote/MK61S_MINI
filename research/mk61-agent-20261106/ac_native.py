"""Two parameter profiles streamed into one weight buffer and one native model."""
import ctypes as C
import json
from pathlib import Path
from ha_protocol import parse_call
OLD_ACTIONS=['write','patch','run','trace','diag','done','unsure']


class Engine:
    def __init__(self,root,arm='selected-research'):
        self.root=Path(root);self.tool=arm;self.role=None
        self.lib=C.CDLL(str(self.root/'native/codec-probe.dylib'))
        self.parser=C.CDLL(str(self.root/'native/action-probe.dylib'));l=self.lib;p=self.parser
        l.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];l.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
        l.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
        l.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
        l.mk_ai_decode.argtypes=[C.c_ushort,C.c_char_p,C.c_uint,C.POINTER(C.c_uint)]
        p.ab_allows.argtypes=[C.c_ushort,C.c_char_p];p.ab_accept.argtypes=[C.c_ushort,C.c_char_p];p.ab_body.argtypes=[C.POINTER(C.c_ubyte)]
        self.capacity=max((self.root/'export'/a/'model.mka').stat().st_size for a in ['compiler',arm])
        self.buffer=C.create_string_buffer(self.capacity);self.loads=0

    def open(self,role):
        if self.role==role:return
        folder=self.root/'export'/('compiler'if role=='compiler'else self.tool)
        n=(folder/'model.mka').stat().st_size
        with(folder/'model.mka').open('rb')as f:
            used=f.readinto(memoryview(self.buffer).cast('B')[:n]);assert used==n
        assert self.lib.mk_ai_open(self.buffer,n)==0
        self.allowed=json.loads((folder/'output-token-ids.json').read_text());self.pieces={}
        chars=C.create_string_buffer(128);size=C.c_uint()
        for token in self.allowed:
            assert self.lib.mk_ai_decode(token,chars,len(chars),C.byref(size))==0
            self.pieces[token]=chars.raw[:size.value]
        if role!='compiler':self.headers=json.loads((folder/'protocol.json').read_text())['neural_headers']
        self.role=role;self.loads+=1

    def mask(self,parser=False):
        allowed=[i for i in self.allowed if not parser or self.parser.ab_allows(i,self.pieces[i])]
        assert allowed
        ids=(C.c_ushort*len(allowed))(*allowed);self.lib.codec_set_mask(ids,len(allowed))

    def prefill(self,text,segmented=False):
        encoded=(C.c_ushort*1024)();used=C.c_uint();best=C.c_ushort()
        if segmented:
            assert text.endswith('<');text=text[:-1]
        if self.lib.codec_encode(text.encode(),encoded,1023 if segmented else 1024,C.byref(used))!=0:return None
        if segmented:encoded[used.value]=30;used.value+=1
        if used.value >= (1016 if segmented else 1024):return None
        inputs=list(encoded[:used.value]);self.lib.mk_ai_reset()
        for i,token in enumerate(inputs):assert self.lib.codec_forward(token,int(i+1==len(inputs)),C.byref(best),None)==0
        return inputs,best

    def compile(self,text):
        self.open('compiler');self.mask();state=self.prefill(text)
        if state is None:return {'codec_error':'context_overflow','action':None,'body':[],'generated_token_ids':[]}
        inputs,best=state;tokens=[]
        for _ in range(min(512,1024-len(inputs))):
            token=best.value
            if token==2:break
            tokens.append(token);assert self.lib.codec_forward(token,1,C.byref(best),None)==0
        reply=b''.join(self.pieces[t]for t in tokens).decode()
        try:action,body=parse_call(reply);error=None
        except ValueError:action=None;body=[];error='invalid_compiler_reply'
        return {'action':action,'body':body,'reply':reply,'codec_error':error,'generated_token_ids':tokens,'input_token_ids':inputs}

    def generate(self,text):
        self.open('tool');p=self.parser;p.ab_reset();self.mask(True);state=self.prefill(text,True)
        if state is None:return {'codec_error':'context_overflow','action':None,'body':[],'generated_token_ids':[]}
        inputs,best=state;token=best.value;assert p.ab_accept(token,self.pieces[token]);tokens=[token]
        if not p.ab_complete():
            action=OLD_ACTIONS[p.ab_action()];header=self.headers[action];self.mask(True)
            for i,token in enumerate(header):assert self.lib.codec_forward(token,int(i+1==len(header)),C.byref(best),None)==0
        else:header=[]
        for _ in range(0 if p.ab_complete()else min(511,1024-len(inputs)-len(header))):
            token=best.value;assert p.ab_accept(token,self.pieces[token])
            if token!=30:tokens.append(token)
            if p.ab_complete():break
            self.mask(True);assert self.lib.codec_forward(token,1,C.byref(best),None)==0
        if not p.ab_complete():
            return {'action':None,'body':[],'codec_error':'incomplete','generated_token_ids':tokens,'input_token_ids':inputs}
        body=(C.c_ubyte*512)();n=p.ab_body(body)
        return {'action':OLD_ACTIONS[p.ab_action()],'body':list(body[:n]),'codec_error':None,'generated_token_ids':tokens,'input_token_ids':inputs}
