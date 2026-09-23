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
    settle: bool = False

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
        return self.raw(0x0E,*(int(c) for c in str(abs(int(n)))),*([0x0B] if n<0 else []))

    def ld(self, r): return self.raw(0x60 + reg(r))
    def st(self, r): return self.raw(0x40 + reg(r))
    def set(self, r, value):
        return (self.op('cx') if value==0 else self.n(value)).st(r)
    def add(self, r, value): return self.ld(r).n(value).op('+').st(r)
    def ptr(self, r, label):
        self.items.append(Item('ptr', reg(r), label)); return self
    def branch(self, opcode, label):
        previous=next((i for i in reversed(self.items) if i.kind!='label'),None)
        arithmetic={0x0B,0x10,0x11,0x12,0x13,0x21,0x22,0x24,0x31,0x34,0x35}
        settle=(previous is not None and previous.kind=='bytes' and
                previous.value[-1] in arithmetic)
        self.items.append(Item('branch', opcode, label,settle=settle)); return self
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
    def mod(self, n):
        # Fraction extraction loses low bits on the eight-digit calculator.
        return self.op('enter').n(n).op('/','int').n(n).op('*','-')

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

    @staticmethod
    def size(item):
        if item.kind=='bytes':return len(item.value)
        if item.kind=='branch':
            return 2 if item.short else (5 if item.settle and item.value in (0x57,0x59,0x5C,0x5E) else 4)
        return {'label':0,'ptr':6}[item.kind]

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
            for index,item in enumerate(module.items):
                if item.kind=='label':
                    pending_labels.append(item.value)
                    continue
                # Reserve a far jump for a continuation unless no real code remains.
                remaining=sum(self.size(i) for i in module.items[index:])
                size=self.size(item)
                needs_bridge=falls_through
                ends_flow=((item.kind=='bytes' and item.value[-1]==0x52) or
                           (item.kind=='branch' and item.value==0x51))
                if offset+remaining > 112 and offset+size > (112 if ends_flow else 108):
                    fits=[i for i,(_,o) in enumerate(free) if 112-o>=size+(4 if remaining>112-o else 0)]
                    if not fits: raise ValueError(f'bank budget exceeded in {module.name}')
                    pick=max(fits,key=lambda i:112-free[i][1])
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
                usage[bank][1]=offset
                falls_through=not ends_flow
            for label in pending_labels: labels[label]=bank*112+offset
            if 112-offset>=8:free.append((bank,offset))
        return labels,placements,bridges,usage

    def link(self):
        self.fold_tail_calls()
        # Start with near branches; expand crossing branches monotonically.
        # Never shrink again: moving a continuation can otherwise oscillate.
        for m in self.modules:
            for i in m.items:
                if i.kind=='branch':i.short=True
        for _ in range(100):
            labels,placements,bridges,usage=self.layout()
            changed=False
            for address,item in placements:
                if item.kind=='branch':
                    desired=address//112==labels[item.target]//112
                    if item.short and not desired:
                        item.short=False; changed=True
            if not changed: break
        else: raise ValueError('linker did not converge')
        banks={b:bytearray([0x50]*112) for b in usage}
        occupied=set()
        def claim(address, size):
            positions=set(range(address,address+size))
            if address//112!=(address+size-1)//112 or occupied & positions:
                raise ValueError(f'overlapping or straddling instruction at {address}')
            occupied.update(positions)
        for b,values in self.data.items():
            banks.setdefault(b,bytearray([0x50]*112))
            claim(b*112,DATA_END)
            banks[b][:DATA_END]=data_page(values)
        for address,target in bridges:
            claim(address,4)
            banks[address//112][address%112:address%112+4]=bytes([0x1F,0x51,*bcd(target)])
        for address,item in placements:
            if item.kind=='bytes': value=item.value
            elif item.kind=='ptr': value=[0x0E,*map(int,f'{labels[item.target]:04d}'),0x40+item.value]
            elif item.short:
                offset=labels[item.target]%112
                value=[item.value,(offset//10)*16+offset%10]
            else:
                # The ROM can still be committing an arithmetic sign at the
                # prefetch hook used by 1F. One native NOP settles X before
                # a far predicate samples it; unlike ENTER it preserves stack.
                barrier=[0x54] if item.settle and item.value in (0x57,0x59,0x5C,0x5E) else []
                value=[*barrier,0x1F,item.value,*bcd(labels[item.target])]
            assert len(value)==self.size(item)
            claim(address,len(value))
            offset=address%112
            assert offset+len(value)<=112
            banks[address//112][offset:offset+len(value)]=bytes(value)
        for bank,buf in banks.items():
            assert len(buf)==112
        return banks, {'occupied_bytes':len(occupied),'free_bytes':32*112-len(occupied),
                       'labels':labels,'banks':{str(b):{'module':name,'used':used} for b,(name,used) in usage.items()}}
