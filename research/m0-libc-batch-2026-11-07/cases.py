"""One deterministic registry and Python oracle for all eight M0 functions."""
FUNCTIONS=('strlen','strcmp','strncmp','memcmp','strnlen','strcpy','strncpy','strncat')
LENGTHS=(0,1,2,3,4,7,8,9,15,16,27,31,32,63,64,81,127,128,243,255,512,729)
ALIGNMENTS=((0,0),(1,1),(2,2),(3,3),(0,1),(1,0),(1,3),(3,2))
BANKS=('SS','SF','FS','FF')
def text(n):return bytes(1+(128+37*i)%255 for i in range(n))
def sign(a,b):return (a>b)-(a<b)
def registry(*,full_alignments=False):
    aligns=tuple((a,b) for a in range(4) for b in range(4)) if full_alignments else ALIGNMENTS
    rows=[];seen=set()
    def add(op,a,b,n,aa,ba,banks,mode,seed=b''):
        key=(op,a,b,n,aa,ba,banks,seed)
        if key in seen:return
        seen.add(key)
        if op=='strlen':result=len(a);output=None;work=len(a)
        elif op=='strnlen':result=min(len(a),n);output=None;work=result
        elif op in ('strcmp','strncmp','memcmp'):
            x=a if op=='strcmp' else a[:n];y=b if op=='strcmp' else b[:n]
            if op!='memcmp':x=x.split(b'\0',1)[0];y=y.split(b'\0',1)[0]
            result=sign(x,y);output=None
            decisive=next((i for i,(u,v) in enumerate(zip(x,y)) if u!=v),min(len(x),len(y)))
            work=min(n,decisive+1) if op!='strcmp' else decisive+1
        elif op=='strcpy':result='destination';output=a+b'\0';work=len(a)+1
        elif op=='strncpy':result='destination';output=(a[:n]+b'\0'*max(0,n-len(a)));work=n
        else:
            result='destination';output=seed+a[:n]+b'\0';work=len(seed)+min(len(a),n)+1
        rows.append(dict(index=len(rows),function=op,length=n if op=='memcmp' else max(len(a),len(b)) if op in ('strcmp','strncmp') else len(a),left_hex=a.hex(),right_hex=b.hex(),count=n,
            alignment=[aa,ba],banks=banks,mode=mode,seed_hex=seed.hex(),expected=result,
            output_hex=output.hex() if output is not None else None,work=work))
    for op in FUNCTIONS:
        for length in LENGTHS:
            a=text(length)
            for aa,ba in aligns:
                if op in ('strlen','strnlen') and ba:continue
                for banks in BANKS:
                    if op not in ('strcmp','strncmp','memcmp') and banks not in ('SS','FS'):continue
                    if op in ('strlen','strcpy'):add(op,a,b'',None,aa,ba,banks,'ordinary');continue
                    if op in ('strnlen','strncpy','strncat'):
                        limits=sorted({0,1,max(0,length-1),length,length+1,length+7})
                        if op in ('strnlen','strncat'):limits+=[0xffffffff]
                        for n in limits:
                            for prefix in ([0,7,31] if op=='strncat' else [0]):add(op,a,b'',n,aa,ba,banks,'bounded',text(prefix))
                        continue
                    modes=['equal','first','middle','last','prefix-left','prefix-right','unsigned']
                    for mode in modes:
                        x,y=a,a
                        if mode in ('first','middle','last','unsigned'):
                            if not length:continue
                            at={'first':0,'middle':length//2,'last':length-1,'unsigned':length-1}[mode]
                            bx,by=bytearray(x),bytearray(y)
                            if mode=='unsigned':bx[at]=255;by[at]=127
                            else:by[at]=255 if bx[at]!=255 else 1
                            x,y=bytes(bx),bytes(by)
                        elif mode=='prefix-left':x=x[:length//2]
                        elif mode=='prefix-right':y=y[:length//2]
                        if op=='strcmp':add(op,x,y,None,aa,ba,banks,mode);continue
                        for n in sorted({0,1,max(0,length-1),length,length+1}):
                            if op=='memcmp':add(op,x+b'\0'+text(length+8),y+b'\0'+text(length+8),n,aa,ba,banks,mode)
                            else:add(op,x,y,n,aa,ba,banks,mode)
    return rows
