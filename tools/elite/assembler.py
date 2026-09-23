"""Small relocating assembler for the banked MK61s ELITE program.

This builds calculator opcodes, not a host implementation of the game.
"""
from dataclasses import dataclass
import json

BANK_SIZE = 112
DATA_BANKS = range(24, 30)
READ, WRITE, CALL, DATA_END = 63, 70, 76, 82
GLYPHS = dict(zip('0123456789', [63, 6, 91, 79, 102, 109, 125, 7, 127, 111]))
GLYPHS.update({' ':0, '-':64, 'A':119, 'b':124, 'C':57, 'd':94,
               'E':121, 'F':113, 'G':61, 'H':118, 'I':6, 'L':56,
               'n':84, 'O':63, 'P':115, 'r':80, 'S':109, 't':120,
               'U':62, 'Y':110, 'С':57, 'П':55, '三':73})
ALPHABET = 'AbCdEFGHLnOPrtUY'
OP = {'+':0x10, '-':0x11, '*':0x12, '/':0x13, 'swap':0x14,
      'sqrt':0x21, 'square':0x22, 'abs':0x31, 'int':0x34,
      'frac':0x35, 'enter':0x0E, 'cx':0x0D, 'neg':0x0B,
      'ret':0x52, 'stop':0x50, 'roll':0x25, 'pow':0x24}

def reg(r):
    return int(r, 16) if isinstance(r, str) else r

def bcd(n):
    assert 0 <= n < 10000
    s = f'{n:04d}'
    return [int(s[:2], 16), int(s[2:], 16)]

def screen(text):
    masks = []
    for ch in text:
        if ch == '.':
            if not masks:
                raise ValueError('point without character')
            masks[-1] |= 128
        else:
            masks.append(GLYPHS[ch])
    if len(masks) > 12:
        raise ValueError(f'screen too long: {text!r}')
    return masks + [0] * (12-len(masks))

def pack_number(value):
    """Nine such 7-byte records are the exact 56/55 exchange representation."""
    negative = value < 0
    digits = str(abs(int(value)))
    if len(digits) > 8:
        raise ValueError('numeric word exceeds eight digits')
    exponent = len(digits)-1 if value else 0
    t = list(map(int, digits.ljust(8, '0')[::-1]))
    t += [9 if negative else 0, exponent % 10, exponent // 10, 0, 0, 0]
    return bytes((t[h] << 4) | t[h-1] for h in (13,1,3,5,7,9,11))

def data_page(values):
    assert len(values) == 9
    # Three entries share the close/return sequence at +67. 55/56 preserve X.
    access = bytes.fromhex('56 55 DB 4C 55 56 52 56 55 6C BB 51 67 56 55 1F AF 51 67')
    return b''.join(pack_number(x) for x in values) + access

@dataclass
class Item:
    kind: str
    value: object
    target: str = ''
    short: bool = False
    digits: int = 4
    negate: bool = False
    lift: bool = True

class Module:
    def __init__(self, bank, name):
        self.bank, self.name, self.items = bank, name, []

    def label(self, name):
        self.items.append(Item('label', name)); return self

    def raw(self, *values):
        self.items.append(Item('bytes', list(values)))
        return self

    def op(self, *names):
        return self.raw(*(OP[n] for n in names))

    def n(self, n):
        # Push a literal; callers with a dead X can explicitly clear it.
        digits=str(abs(int(n)))
        zeros=len(digits)-len(digits.rstrip('0')) if n else 0
        raw=[int(c) for c in digits]
        if zeros>2:raw=[*(int(c) for c in digits[:-zeros]),0x0C,*(int(c) for c in str(zeros))]
        return self.raw(0x0E,*raw,*([0x0B] if n<0 else []))

    def ld(self, r): return self.raw(0x60 + reg(r))
    def st(self, r): return self.raw(0x40 + reg(r))
    def set(self, r, value):
        return (self.op('cx') if value==0 else self.raw(*(int(c) for c in str(abs(int(value)))),*([0x0B] if value<0 else []))).st(r)
    def add(self, r, value): return self.ld(r).n(value).op('+').st(r)
    def ptr(self, r, label, negate=False, lift=True):
        # lift=False is an assignment: the caller guarantees closed number
        # entry and a dead prior X. A negative pointer can also be a flag.
        self.items.append(Item('ptr', reg(r), label, negate=negate, lift=lift)); return self
    def branch(self, opcode, label):
        self.items.append(Item('branch', opcode, label)); return self
    def call(self, label): return self.branch(0x53, label)
    def jump(self, label): return self.branch(0x51, label)
    def jz(self, label): return self.branch(0x57, label)
    def jnz(self, label): return self.branch(0x5E, label)
    def jneg(self, label): return self.branch(0x59, label)
    def jge(self, label): return self.branch(0x5C, label)
    def far(self, opcode, address): return self.raw(0x1F,opcode,*bcd(address))
    def get(self, bank, field):
        return self.set('B',field).far(0x53,bank*112+READ)
    def put(self, bank, field):
        return self.st('C').set('B',field).far(0x53,bank*112+WRITE)
    def putn(self, bank, field, value): return self.n(value).put(bank,field)
    def visit(self, bank, callback):
        return self.ptr('F',callback).far(0x53,bank*112+CALL)
    def max0(self):
        target=f'clamp0_{self.bank}_{len(self.items)}'
        return self.jge(target).op('cx').label(target)

    def mod(self, n):
        # RC is scratch. X2 retains the divisor while RC holds the quotient.
        # Fraction extraction loses low bits on the eight-digit calculator.
        return self.op('enter').n(n).op('/','int').st('C').raw(0x0A).ld('C').op('*','-')

class Assembler:
    def __init__(self):
        self.modules = []
        self.data = {}

    def module(self, bank, name):
        m=Module(bank,name); self.modules.append(m); return m

    def fold_tail_calls(self):
        """A final call can reuse its caller's return address.

        Only adjacent complete instructions qualify. In particular, a label
        before RET is an independent entry and prevents the rewrite.
        """
        for module in self.modules:
            items=module.items
            index=0
            while index+1<len(items):
                call,ret=items[index:index+2]
                folded=False
                if ret.kind=='bytes' and ret.value==[OP['ret']]:
                    if call.kind=='branch' and call.value==0x53:
                        call.value=0x51; folded=True
                    elif call.kind=='bytes' and len(call.value)==4 and call.value[:2]==[0x1F,0x53]:
                        call.value[1]=0x51; folded=True
                    elif call.kind=='bytes' and len(call.value)==2 and call.value[0]==0x1F and 0xA0<=call.value[1]<=0xAF:
                        call.value[1]-=0x20; folded=True
                if folded:del items[index+1]
                index+=1

    def fold_fallthrough_jumps(self):
        """Remove a jump over labels with a closed entry and a fresh recall.

        A preceding store closes numeric entry. The target's recall replaces
        X/X2 before either can be observed. A label on the jump is a separate
        entry and deliberately prevents this local rewrite.
        """
        for module in self.modules:
            items=module.items
            for index in range(len(items)-2,0,-1):
                item,previous=items[index],items[index-1]
                if item.kind!='branch' or item.value!=0x51:continue
                if previous.kind!='bytes' or not 0x40<=previous.value[-1]<=0x4F:continue
                end=index+1
                names=[]
                while end<len(items) and items[end].kind=='label':
                    names.append(items[end].value);end+=1
                if item.target not in names or end==len(items):continue
                first=items[end]
                if first.kind=='bytes' and 0x60<=first.value[0]<=0x6F:
                    del items[index]

    @staticmethod
    def size(item):
        if item.kind=='bytes':return len(item.value)
        if item.kind=='branch':
            return 2 if item.short else 4
        return 1+item.digits+int(item.negate)+int(item.lift) if item.kind=='ptr' else 0

    def layout(self):
        labels, placements, bridges, usage = {}, [], [], {}
        preferred={m.bank for m in self.modules}
        free=[(b,0) for b in range(32) if b not in preferred and b not in self.data]
        free += [(b,DATA_END) for b in self.data]
        for module in self.modules:
            bank, offset = module.bank, 0
            if bank in usage or bank in self.data:
                raise ValueError(f'duplicate bank {bank}')
            usage[bank]=[module.name,0]
            pending_labels=[]
            falls_through=True
            remaining=sum(self.size(i) for i in module.items)
            for index,item in enumerate(module.items):
                if item.kind=='label':
                    pending_labels.append(item.value)
                    continue
                # Reserve a far jump for a continuation unless no real code remains.
                size=self.size(item)
                needs_bridge=falls_through
                ends_flow=item.kind=='branch' and item.value==0x51
                if item.kind=='bytes':
                    value=item.value
                    if value[0]==0x1F:
                        # Address bytes are operands, even when one is 52.
                        ends_flow=((len(value)==4 and value[1]==0x51) or
                                   (len(value)==2 and 0x80<=value[1]<=0x8F))
                    else:ends_flow=value[-1]==0x52 or (len(value)==1 and 0x80<=value[0]<=0x8F)
                if offset+remaining > 112 and offset+size > (112 if ends_flow else 108):
                    fits=[i for i,(_,o) in enumerate(free) if 112-o>=size+(4 if remaining>112-o else 0)]
                    if not fits: raise ValueError(f'bank budget exceeded in {module.name}')
                    # Prefer the smallest hole holding the whole remainder.
                    # Otherwise use a large block to avoid extra bridges.
                    whole=[i for i in fits if 112-free[i][1]>=remaining]
                    pick=(min(whole,key=lambda i:112-free[i][1]) if whole else
                          max(fits,key=lambda i:112-free[i][1]))
                    next_bank,next_offset=free.pop(pick)
                    if needs_bridge:
                        bridges.append((bank*112+offset,next_bank*112+next_offset))
                        usage[bank][1]=offset+4
                    elif 112-offset>=8: free.append((bank,offset))
                    bank,offset=next_bank,next_offset
                    previous=usage.get(bank,['data' if bank in self.data else '',0])[0]
                    usage[bank]=[previous+' / '+module.name,offset]
                address=bank*112+offset
                for label in pending_labels:
                    if label in labels: raise ValueError('duplicate label '+label)
                    labels[label]=address
                pending_labels.clear()
                placements.append((address,item))
                offset+=size
                remaining-=size
                usage[bank][1]=offset
                falls_through=not ends_flow
            for label in pending_labels: labels[label]=bank*112+offset
            if 112-offset>=8:free.append((bank,offset))
        return labels,placements,bridges,usage

    def expand_branches(self):
        """Reach a valid layout by widening only; never oscillate in a trial."""
        for _ in range(100):
            labels,placements,bridges,usage=self.layout()
            changed=False
            for address,item in placements:
                if item.kind=='ptr' and item.digits<len(str(labels[item.target])):
                    item.digits=len(str(labels[item.target]));changed=True
                if item.kind=='branch':
                    desired=address//112==labels[item.target]//112
                    if item.short and not desired:
                        item.short=False; changed=True
            if not changed: break
        else: raise ValueError('linker did not converge')
        return labels,placements,bridges,usage

    def relax_branches(self):
        """Try each newly local far branch as an independent transaction.

        Relocation can make other branches far. Re-run widening and accept
        only a strictly smaller complete artifact, otherwise restore all flags.
        """
        result=self.expand_branches()
        branches=[i for m in self.modules for i in m.items if i.kind=='branch']
        pointers=[i for m in self.modules for i in m.items if i.kind=='ptr']
        def cost(layout):
            return sum(self.size(i) for _,i in layout[1])+4*len(layout[2])
        while True:
            labels,placements,_,_=result
            baseline_cost=cost(result)
            candidates=[i for address,i in placements if i.kind=='branch' and
                        not i.short and address//112==labels[i.target]//112]
            for candidate in candidates:
                flags=[i.short for i in branches]
                widths=[i.digits for i in pointers]
                candidate.short=True
                try:trial=self.expand_branches()
                except ValueError:trial=None
                if trial is not None and cost(trial)<baseline_cost:
                    result=trial;break
                for item,short in zip(branches,flags):item.short=short
                for item,width in zip(pointers,widths):item.digits=width
            else:return result

    def link(self):
        self.fold_tail_calls()
        self.fold_fallthrough_jumps()
        for m in self.modules:
            for i in m.items:
                if i.kind=='branch':i.short=True
                if i.kind=='ptr':i.digits=1
        labels,placements,bridges,usage=self.relax_branches()
        banks={b:bytearray(112) for b in usage}
        occupied=set()
        def claim(address, size):
            positions=set(range(address,address+size))
            if address//112!=(address+size-1)//112 or occupied & positions:
                raise ValueError(f'overlapping or straddling instruction at {address}')
            occupied.update(positions)
        for b,values in self.data.items():
            banks.setdefault(b,bytearray(112))
            usage.setdefault(b,['data',DATA_END])
            claim(b*112,DATA_END)
            banks[b][:DATA_END]=data_page(values)
        for address,target in bridges:
            claim(address,4)
            banks[address//112][address%112:address%112+4]=bytes([0x1F,0x51,*bcd(target)])
        for address,item in placements:
            if item.kind=='bytes': value=item.value
            elif item.kind=='ptr': value=[*([0x0E] if item.lift else []),*map(int,f'{labels[item.target]:0{item.digits}d}'),*([0x0B] if item.negate else []),0x40+item.value]
            elif item.short:
                offset=labels[item.target]%112
                value=[item.value,(offset//10)*16+offset%10]
            else:
                # Firmware completes X write-back inside the far prefix.
                value=[0x1F,item.value,*bcd(labels[item.target])]
            assert len(value)==self.size(item)
            claim(address,len(value))
            offset=address%112
            assert offset+len(value)<=112
            banks[address//112][offset:offset+len(value)]=bytes(value)
        for bank,buf in banks.items():
            assert len(buf)==112
        return banks, {'occupied_bytes':len(occupied),'free_bytes':32*112-len(occupied),
                       'labels':labels,'banks':{str(b):{'module':name,'used':used} for b,(name,used) in usage.items()}}
