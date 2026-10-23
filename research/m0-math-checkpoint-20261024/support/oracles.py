"""Two independent RNE references: directed MPFR and exact integer arithmetic."""
import ctypes as C
import math
import struct
from support.m0_mpfr_oracle import Oracle,_Number


def params(width):
    f,e=(23,8) if width==32 else (52,11)
    sign=1<<(width-1); inf=((1<<e)-1)<<f
    return f,e,sign,inf,1<<(f-1)


def is_nan(x,width):
    f,e,sign,inf,quiet=params(width)
    return (x&(sign-1))>inf


def equal(got,expected,width):
    f,e,sign,inf,quiet=params(width)
    return bool(is_nan(got,width) and got&quiet) if is_nan(expected,width) else got==expected


def decode(x,width):
    f,e,sign,inf,quiet=params(width);bias=(1<<(e-1))-1
    field=(x&(sign-1))>>f;frac=x&((1<<f)-1)
    return (-1 if x&sign else 1),frac|((1<<f) if field else 0),(field-bias-f if field else 1-bias-f)


def round_ratio(num,den,scale,width,negative=False):
    assert num>=0 and den>0
    f,e,sign,inf,quiet=params(width);sign=sign if negative else 0
    if not num:return sign
    bias=(1<<(e-1))-1;emin=1-bias;emax=bias
    k=num.bit_length()-den.bit_length()
    if (num<(den<<k) if k>=0 else (num<<-k)<den):k-=1
    exponent=k+scale
    if exponent>emax:return sign|inf
    quantum=max(exponent-f,emin-f);shift=scale-quantum
    n,d=(num<<shift,den) if shift>=0 else (num,den<<-shift)
    retained,tail=divmod(n,d)
    retained+=2*tail>d or (2*tail==d and bool(retained&1))
    if not retained:return sign
    bit=retained.bit_length()-1;output_exponent=quantum+bit
    if output_exponent>emax:return sign|inf
    if output_exponent<emin:return sign|retained
    significand=retained>>(bit-f) if bit>=f else retained<<(f-bit)
    return sign|((output_exponent+bias)<<f)|(significand&((1<<f)-1))


def integer_binary(op,a,b=0,width=32):
    f,e,sign,inf,quiet=params(width);mask=sign-1
    if op=='frsub':return integer_binary('sub',b,a,width)
    if op=='sub':b^=sign;op='add'
    if is_nan(a,width) or is_nan(b,width):return inf|quiet
    ma,mb=a&mask,b&mask
    if op=='add':
        if ma==inf or mb==inf:
            return inf|quiet if ma==mb==inf and bool((a^b)&sign) else (a if ma==inf else b)
        sa,na,ea=decode(a,width);sb,nb,eb=decode(b,width)
        if not na and not nb:return (a&b)&sign
        base=min(ea,eb);total=sa*(na<<(ea-base))+sb*(nb<<(eb-base))
        return round_ratio(abs(total),1,base,width,total<0)
    negative=bool((a^b)&sign)
    if op=='mul':
        if ma==inf or mb==inf:return inf|quiet if not ma or not mb else (sign if negative else 0)|inf
        sa,na,ea=decode(a,width);sb,nb,eb=decode(b,width)
        return round_ratio(na*nb,1,ea+eb,width,negative)
    assert op=='div'
    if (ma==mb==inf) or not(ma or mb):return inf|quiet
    if ma==inf or not mb:return (sign if negative else 0)|inf
    if not ma or mb==inf:return sign if negative else 0
    sa,na,ea=decode(a,width);sb,nb,eb=decode(b,width)
    return round_ratio(na,nb,ea-eb,width,negative)


def integer_sqrt(a,width=32):
    f,e,sign,inf,quiet=params(width);mag=a&(sign-1)
    if not mag:return a
    if is_nan(a,width) or a&sign:return inf|quiet
    if mag==inf:return a
    s,n,scale=decode(a,width)
    exponent=(n.bit_length()-1+scale)//2;quantum=exponent-f
    shift=scale-2*quantum
    num,den=(n<<shift,1) if shift>=0 else (n,1<<-shift)
    q=math.isqrt(num//den);lhs=4*num;rhs=den*(2*q+1)**2
    q+=lhs>rhs or (lhs==rhs and bool(q&1))
    return round_ratio(q,1,quantum,width)


def integer_cast(a,source_width,target_width):
    f,e,sign,inf,quiet=params(source_width);tf,te,ts,ti,tq=params(target_width)
    mag=a&(sign-1);negative=bool(a&sign)
    if mag>=inf:return (ts if negative else 0)|ti|(tq if mag>inf else 0)
    s,n,scale=decode(a,source_width)
    return round_ratio(n,1,scale,target_width,negative)


def integer_fma(a,b,c):
    width=64;f,e,sign,inf,quiet=params(width);mask=sign-1
    if any(is_nan(x,width) for x in (a,b,c)):return inf|quiet
    ma,mb,mc=a&mask,b&mask,c&mask;negative=bool((a^b)&sign)
    if ma==inf or mb==inf:
        if not ma or not mb or (mc==inf and negative!=bool(c&sign)):return inf|quiet
        return (sign if negative else 0)|inf
    if mc==inf:return c
    sa,na,ea=decode(a,width);sb,nb,eb=decode(b,width);sc,nc,ec=decode(c,width)
    product=na*nb;ep=ea+eb
    if not product and not nc:return (sign if negative else 0)&c
    base=min(ep,ec);total=sa*sb*(product<<(ep-base))+sc*(nc<<(ec-base))
    return round_ratio(abs(total),1,base,width,total<0)


def comparison(a,b):
    if is_nan(a,32) or is_nan(b,32):return 2
    if a==b or not((a|b)&0x7fffffff):return 0
    if (a^b)&0x80000000:return -1 if a&0x80000000 else 1
    return (-1 if a>b else 1) if a&0x80000000 else (-1 if a<b else 1)


def float_integer(a,signed):
    s,n,e=decode(a,32);mag=a&0x7fffffff
    if is_nan(a,32):value=0
    elif mag==0x7f800000:value=s*((1<<64)-1)
    else:value=s*(n<<e if e>=0 else n>>-e)
    lo,hi=(-(1<<31),(1<<31)-1) if signed else (0,(1<<32)-1)
    return min(hi,max(lo,value))&0xffffffff,mag<0x7f800000 and lo<=value<=hi


class DirectMPFR:
    def __init__(self):
        self.base=Oracle();self.lib=self.base.lib;self.version=self.base.version;self.max_precision=0
        self.fma_precision_counts={}
        p=C.POINTER(_Number)
        self.lib.mpfr_get_flt.argtypes=[p,C.c_int];self.lib.mpfr_get_flt.restype=C.c_float
        self.lib.mpfr_set.argtypes=[p,p,C.c_int]
        self.lib.mpfr_set_si.argtypes=[p,C.c_long,C.c_int]
        self.lib.mpfr_set_ui.argtypes=[p,C.c_ulong,C.c_int]

    def float(self,op,*args):
        is_integer=op in ('i2f','ui2f')
        source_width=64 if op=='d2f' else 32
        target_width=64 if op=='f2d' else 32
        f,e,sign,inf,quiet=params(source_width)
        if not is_integer:
            for a in args:
                if is_nan(a,source_width):return params(target_width)[3]|params(target_width)[4]
        inputs=[_Number() for _ in args]
        for n,a in zip(inputs,args):
            self.lib.mpfr_init2(C.byref(n),64)
            if is_integer:
                value=a-(1<<32) if op=='i2f' and a>>31 else a
                setter=self.lib.mpfr_set_si if op=='i2f' else self.lib.mpfr_set_ui
                setter(C.byref(n),value,0)
            else:
                value=struct.unpack('<d' if source_width==64 else '<f',struct.pack('<Q' if source_width==64 else '<I',a))[0]
                self.lib.mpfr_set_d(C.byref(n),value,0)
        name={'add':'add','sub':'sub','frsub':'sub','mul':'mul','div':'div','sqrt':'sqrt',
              'd2f':'set','f2d':'set','i2f':'set','ui2f':'set'}[op]
        values=list(reversed(inputs)) if op=='frsub' else inputs
        function=getattr(self.lib,'mpfr_'+name)
        getter=self.lib.mpfr_get_d if target_width==64 else self.lib.mpfr_get_flt
        encode=lambda x:struct.unpack('<Q' if target_width==64 else '<I',struct.pack('<d' if target_width==64 else '<f',x))[0]
        try:
            precision=128
            while precision<=16384:
                bounds=[]
                for direction in (3,2):
                    out=_Number();self.lib.mpfr_init2(C.byref(out),precision)
                    try:
                        function(C.byref(out),*map(C.byref,values),direction)
                        bounds.append(encode(getter(C.byref(out),0)))
                    finally:self.lib.mpfr_clear(C.byref(out))
                if equal(bounds[0],bounds[1],target_width):
                    self.max_precision=max(self.max_precision,precision);return bounds[0]
                if op in ('add','sub','frsub') and not((bounds[0]|bounds[1])&(params(target_width)[2]-1)):
                    out=_Number();self.lib.mpfr_init2(C.byref(out),precision)
                    try:
                        function(C.byref(out),*map(C.byref,values),0)
                        self.max_precision=max(self.max_precision,precision);return encode(getter(C.byref(out),0))
                    finally:self.lib.mpfr_clear(C.byref(out))
                precision*=2
            raise AssertionError(('Direct MPFR did not converge',op,args))
        finally:
            for n in inputs:self.lib.mpfr_clear(C.byref(n))

    def fma(self,*args):
        inputs=[_Number() for _ in args]
        for n,a in zip(inputs,args):
            self.lib.mpfr_init2(C.byref(n),53)
            self.lib.mpfr_set_d(C.byref(n),struct.unpack('<d',struct.pack('<Q',a))[0],0)
        try:
            precision=128
            while precision<=16384:
                bounds=[]
                for direction in (3,2):
                    out=_Number();self.lib.mpfr_init2(C.byref(out),precision)
                    try:
                        self.lib.mpfr_fma(C.byref(out),*map(C.byref,inputs),direction)
                        bounds.append(struct.unpack('<Q',struct.pack('<d',self.lib.mpfr_get_d(C.byref(out),0)))[0])
                    finally:self.lib.mpfr_clear(C.byref(out))
                if equal(bounds[0],bounds[1],64):
                    self.fma_precision_counts[precision]=self.fma_precision_counts.get(precision,0)+1
                    return bounds[0]
                if not((bounds[0]|bounds[1])&0x7fffffffffffffff):
                    out=_Number();self.lib.mpfr_init2(C.byref(out),precision)
                    try:
                        self.lib.mpfr_fma(C.byref(out),*map(C.byref,inputs),0)
                        value=struct.unpack('<Q',struct.pack('<d',self.lib.mpfr_get_d(C.byref(out),0)))[0]
                        self.fma_precision_counts[precision]=self.fma_precision_counts.get(precision,0)+1
                        return value
                    finally:self.lib.mpfr_clear(C.byref(out))
                precision*=2
            raise AssertionError(('FMA MPFR did not converge',args))
        finally:
            for n in inputs:self.lib.mpfr_clear(C.byref(n))


def self_test():
    import random
    rng=random.Random(0xF32F6A);mp=DirectMPFR()
    for op in ('add','sub','frsub','mul','div'):
        for _ in range(1500):
            a,b=rng.getrandbits(32),rng.getrandbits(32)
            x=mp.float(op,a,b);y=integer_binary(op,a,b)
            assert equal(x,y,32),(op,hex(a),hex(b),hex(x),hex(y))
    for _ in range(1500):
        a=rng.getrandbits(32)
        for op in ('sqrt','f2d'):
            x=mp.float(op,a);y=integer_sqrt(a) if op=='sqrt' else integer_cast(a,32,64)
            assert equal(x,y,32 if op=='sqrt' else 64),(op,hex(a),hex(x),hex(y))
        b=rng.getrandbits(64);assert equal(mp.float('d2f',b),integer_cast(b,64,32),32)
        for signed in (False,True):
            op='i2f' if signed else 'ui2f';value=a-(1<<32) if signed and a>>31 else a
            assert equal(mp.float(op,a),round_ratio(abs(value),1,0,32,value<0),32)
    for _ in range(2000):
        args=tuple(rng.getrandbits(64) for _ in range(3))
        x=mp.fma(*args);y=integer_fma(*args)
        assert equal(x,y,64),('fma',args,hex(x),hex(y))
    assert integer_fma(0x3ff0000002000000,0x3feffffffc000000,0xbff0000000000000)==0xbc90000000000000
    return dict(status='PASS',random_float_binary_pairs_per_op=1500,float_unary_conversion_inputs=1500,
                random_binary64_FMA_triples=2000,MPFR_version=mp.version,maximum_float_MPFR_precision=mp.max_precision,
                semantics='Independent exact integer/rational RNE versus direct MPFR binary32 extraction; no firmware results used.')


if __name__=='__main__':
    import json
    print(json.dumps(self_test(),indent=2))
