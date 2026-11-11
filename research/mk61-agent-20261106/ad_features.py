"""Task-independent listing statistics and conservative structural observations."""
from functools import lru_cache
import collections
import json
import math
from ad_common import PRIOR_ROOT,PREVIOUS
from opcode_statistics import commands
from ha_protocol import assemble,unaddress
from full_isa_protocol import linear_instructions


class Prior:
    def __init__(self,name='verified_training'):
        data=json.loads((PRIOR_ROOT/(name+'-counts.json')).read_text())
        self.name=name;self.alphabet=data['alphabet'];self.one={r['tokens'][0]:r['count']for r in data['unigrams']}
        self.two={tuple(r['tokens']):r['count']for r in data['bigrams']};self.three={tuple(r['tokens']):r['count']for r in data['trigrams']}
        self.c2=collections.Counter();self.c3=collections.Counter()
        for (a,b),n in self.two.items():self.c2[a]+=n
        for (a,b,c),n in self.three.items():self.c3[a,b]+=n
        self.total=sum(self.one.values());self.catalog={r['code']:r for r in json.loads((PREVIOUS/'catalog.json').read_text())}

    def logp(self,a,b,c):
        p=(self.one.get(c,0)+.5)/(self.total+.5*len(self.alphabet))
        p=(self.two.get((b,c),0)+5*p)/(self.c2[b]+5)
        p=(self.three.get((a,b,c),0)+5*p)/(self.c3[a,b]+5)
        return math.log(p)

    def score(self,tokens):
        a=b='START';logs=[]
        for c in tokens+['END']:logs.append(self.logp(a,b,c));a,b=b,c
        return math.fsum(logs)/(len(tokens)+1)


def repeated_fraction(tokens):
    """Adjacent duplicate blocks; no assumption that repetition implies an error."""
    covered=set()
    for size in range(2,min(12,len(tokens)//2)+1):
        for at in range(len(tokens)-2*size+1):
            if tokens[at:at+size]==tokens[at+size:at+2*size]:covered.update(range(at+size,at+2*size))
    return len(covered)/max(1,len(tokens))


def structure(code):
    ins=linear_instructions(code);by={i['pc']:i for i in ins};returns=[i['pc']+2 for i in ins if i['opcode']==0x53]
    unknown=False;seen=set();todo=[0];bad_targets=[]
    while todo:
        pc=todo.pop()
        if pc in seen:continue
        if pc not in by:
            if pc<len(code):unknown=True
            continue
        seen.add(pc);i=by[pc];op=i['opcode'];nxt=pc+(2 if i['operand']is not None else 1)
        if op==0x50:continue
        if op==0x52:todo+=returns;continue
        if 0x70<=op<=0xEE and op%16<=14:unknown=True
        if i['operand']is not None:
            try:dest=unaddress(i['operand'])
            except ValueError:bad_targets.append(pc);continue
            if dest not in by:bad_targets.append(pc);unknown=True
            todo.append(dest)
            if op!=0x51:todo.append(nxt)
        else:todo.append(nxt)
    # Indirect jumps and overlays make a linear reachability inference unreliable.
    unreachable=[]if unknown else[i['pc']for i in ins if i['pc']not in seen]
    return {'instruction_count':len(ins),'unreachable_on_first_run':unreachable,
       'unreachable_fraction':len(unreachable)/max(1,len(ins)), 'reachability_unknown':unknown,
       'bad_direct_target_cells':bad_targets,'calls':sum(i['opcode']==0x53 for i in ins),'returns':sum(i['opcode']==0x52 for i in ins)}


class Critic:
    def __init__(self,prior='verified_training'):self.prior=Prior(prior)

    @lru_cache(maxsize=30000)
    def inspect(self,body,pool):
        try:
            code=assemble(list(body),list(pool),'asm');tokens=commands(code,self.prior.catalog)
            if tokens is None:raise ValueError('Missing jump address')
            graph=structure(code)
            return {'valid':True,'code':code,'tokens':tokens,'log_prior':self.prior.score(tokens),
                    'repeat_fraction':repeated_fraction(tokens),**graph}
        except (ValueError,ArithmeticError)as error:return {'valid':False,'error':str(error),'log_prior':-100.,'repeat_fraction':1.,'unreachable_fraction':1.}

    def score(self,features,config):
        if not features['valid']:return -1e9
        return config.get('weight',1.)*features['log_prior']-config.get('repeat',0.)*features['repeat_fraction']-config.get('unreachable',0.)*features['unreachable_fraction']

    def note(self,features,threshold):
        parts=[]
        if not features['valid']:parts.append('код не собирается: '+features['error'])
        else:
            if features['log_prior']<threshold:parts.append('необычная последовательность команд')
            if features['repeat_fraction']>=.15:parts.append('есть повторяющиеся блоки')
            if features['unreachable_fraction']>=.2:parts.append('есть команды вне первого запуска; проверь, нужны ли продолжения')
        return ('Проверка кода: '+'; '.join(parts)+'. Проверь программу по условию; эта оценка не доказывает ошибку.')if parts else''
