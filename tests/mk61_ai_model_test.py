#!/usr/bin/env python3
"""Independent HF tokenizer/logit oracle for the portable native model runtime."""
import argparse
import ctypes as C
import json
from pathlib import Path
import random
import struct
import sys
import zlib

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library',type=Path,default=ROOT/'.build/mk61ai/model-probe.dylib')
    p.add_argument('--package',type=Path,default=ROOT/'.build/mk61ai/sd/AI/MODEL.MKA')
    p.add_argument('--hf',type=Path,default=ROOT/'.build/mk61-agent-20261106/distill-hard/export/baseline/hf')
    p.add_argument('--weights',type=Path,default=ROOT/'.build/mk61-agent-20261106/distill-hard/export/baseline/model.mkq4')
    a=p.parse_args()
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    torch.set_num_threads(2)
    lib=C.CDLL(str(a.library.resolve()))
    lib.mk_ai_open.argtypes=[C.c_void_p,C.c_uint]
    lib.mk_ai_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint),C.c_int]
    lib.mk_ai_decode.argtypes=[C.c_ushort,C.c_void_p,C.c_uint,C.POINTER(C.c_uint)]
    lib.mk_ai_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float),C.c_int]
    lib.mk_ai_rewind.argtypes=[C.c_uint]
    lib.mk_ai_forward_only.argtypes=[C.c_ushort,C.POINTER(C.c_ushort),C.c_uint]
    raw=a.package.read_bytes();source=C.create_string_buffer(raw)
    assert lib.mk_ai_open(source,len(raw))==0,'package open'
    tokenizer=AutoTokenizer.from_pretrained(a.hf)
    def encode(text,bos=True,capacity=2048):
        out=(C.c_ushort*capacity)();n=C.c_uint()
        status=lib.mk_ai_encode(text.encode(),out,capacity,C.byref(n),bos)
        assert status==0,(status,repr(text))
        return list(out[:n.value])
    samples=['', 'Привет!', '12.3 ё е\u0308 й и\u0306', '<bos>Привет<eos>', "I'm not sure we'll do it.",
        ' a  b\n c\t 2', 'abc\n  ', ' .12 -5.2', 'Раз, два — ёжик!', '中文日本語 한국어 한글',
        '👩\u200d💻 😀🚀', 'Á Å A\u030A a\u0327\u0301', '₁ ² Ⅲ ١ 𝟚', '\r\n\t x',
        'x\u001cy\u0085 z\u00A0t', " 's  're can't shouldn't", 'x<bos>2<eos>y<pad>']
    rng=random.Random(6101)
    alphabet=list('абвгдеёжзийклмнопрстуфхцчшщъыьэюя ABCxyz0123\n\t.,:!?+-=/<>\'')+['\u0308','\u0301','\u0306','é','😀','漢','١','\u00a0']
    samples += [''.join(rng.choices(alphabet,k=rng.randrange(1,100))) for _ in range(600)]
    for text in samples:
        for bos in (False,True):
            got=encode(text,bos);expected=tokenizer.encode(text,add_special_tokens=bos)
            assert got==expected,{'text':repr(text),'native':got,'oracle':expected}
    # Byte fragments must be concatenated before UTF-8 decoding, as on device.
    for text in samples[:17]:
        ids=encode(text);decoded=bytearray()
        for token in ids:
            buf=C.create_string_buffer(2049);used=C.c_uint()
            assert lib.mk_ai_decode(token,buf,len(buf),C.byref(used))==0
            decoded+=buf.raw[:used.value]
        assert decoded.decode(errors='replace')==tokenizer.decode(ids,skip_special_tokens=False,clean_up_tokenization_spaces=False)
    print('tokenizer parity:',len(samples)*2,'cases',flush=True)
    sys.path.insert(0,str(ROOT/'research/mk61-agent-20261106'))
    from quantization import load_q4
    model=AutoModelForCausalLM.from_pretrained(a.hf,torch_dtype=torch.float32,attn_implementation='eager').eval()
    load_q4(model,a.weights)
    prompt='Задача: сложи R0 и R1.\nАссистент: '
    ids=encode(prompt);vocab=model.config.vocab_size
    with torch.inference_mode():reference=model(torch.tensor([ids]),use_cache=False).logits[0].numpy()
    lib.mk_ai_reset();best=C.c_ushort();out=(C.c_float*vocab)();deltas=[]
    for pos,token in enumerate(ids):
        assert lib.mk_ai_forward(token,1,C.byref(best),out,0)==0
        delta=float(np.abs(np.ctypeslib.as_array(out)-reference[pos]).max());deltas.append(delta)
        assert delta<0.002,(pos,delta)
        assert best.value==int(reference[pos].argmax()),(pos,best.value,int(reference[pos].argmax()))
    variants={}
    integer_reference=[]
    for mode,name in [(1,'int8'),(2,'lut_int8'),(3,'lut_float32')]:
        lib.mk_ai_reset();errors=[];matches=0
        for pos,token in enumerate(ids):
            assert lib.mk_ai_forward(token,1,C.byref(best),out,mode)==0
            values=np.ctypeslib.as_array(out).copy()
            errors.append(float(np.abs(values-reference[pos]).max()))
            matches+=best.value==int(reference[pos].argmax())
            if mode==1:integer_reference.append(values)
            if mode==2:assert np.abs(values-integer_reference[pos]).max()<0.00001,(pos,'integer LUT mismatch')
            if mode==3:assert errors[-1]<0.002 and best.value==int(reference[pos].argmax()),(pos,errors[-1])
        variants[name]={'max_logit_delta':max(errors),'argmax_matches':matches,'positions':len(ids)}
    assert not lib.mk_ai_rewind(len(ids)+1)
    assert lib.mk_ai_rewind(5)
    for pos in range(5,len(ids)):
        assert lib.mk_ai_forward(ids[pos],1,C.byref(best),out,3)==0
        assert np.abs(np.ctypeslib.as_array(out)-reference[pos]).max()<0.002
        assert best.value==int(reference[pos].argmax())
    lib.mk_ai_reset()
    assert lib.mk_ai_forward_only(1,C.byref(best),123)==0 and best.value==123
    lib.mk_ai_reset()
    assert lib.mk_ai_forward_only(1,C.byref(best),vocab+1)==2 and lib.mk_ai_position()==0
    # Cancellation in the middle of a layer may not commit a KV position.
    lib.mk_ai_reset()
    for token in ids[:2]:assert lib.mk_ai_forward(token,0,C.byref(best),None,0)==0
    lib.mk_ai_cancel_after(5)
    assert lib.mk_ai_forward(ids[2],1,C.byref(best),out,0)==6
    assert lib.mk_ai_position()==2
    lib.mk_ai_cancel_after(-1)
    assert lib.mk_ai_forward(ids[2],1,C.byref(best),out,0)==0
    assert np.abs(np.ctypeslib.as_array(out)-reference[2]).max()<0.002
    # Bad package bytes and a fully occupied context fail explicitly.
    broken=bytearray(raw);broken[-1]^=1;bad=C.create_string_buffer(bytes(broken));assert lib.mk_ai_open(bad,len(broken))==2
    short=bytearray(raw);struct.pack_into('<I',short,44,1);struct.pack_into('<I',short,124,zlib.crc32(short[:124]))
    small=C.create_string_buffer(bytes(short));assert lib.mk_ai_open(small,len(short))==0
    assert lib.mk_ai_forward(1,0,C.byref(best),None,0)==0
    assert lib.mk_ai_forward(1,0,C.byref(best),None,0)==5
    assert lib.mk_ai_open(source,len(raw))==0
    report={'prefix_rewind_parity':'passed','argmax_policy':'passed','tokenizer_cases':len(samples)*2,'logit_positions':len(deltas),'max_logit_delta':max(deltas),
        'workspace_bytes':lib.mk_ai_workspace(),'kv_bytes':lib.mk_ai_cache(),
        'cancellation_retry':'passed','corrupt_package':'rejected','context_limit':'passed','arithmetic':variants,
        'scope':'host reference arithmetic; device performance and INT8 quality not asserted'}
    target=ROOT/'.build/mk61ai/model-checks.json';target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
