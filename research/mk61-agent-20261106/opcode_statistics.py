"""Post-hoc opcode-language diagnostics, with no task answer or neural changes."""
import collections
import hashlib
import json
import math
from pathlib import Path
from ha_protocol import assemble,constants

BASE=Path(__file__).resolve().parents[2]/'.build/mk61-agent-20261106'
ROOT=BASE/'opcode-statistics-v1'
EXAM=BASE/'debug-adapter-v2/server-results'


def read(path):return [json.loads(s)for s in path.read_text().splitlines()if s.strip()]


def commands(code,catalog,normalize=True):
    """Listing order, not dynamic execution. Skip direct address operands."""
    result=[];at=0
    while at<len(code):
        op=code[at];at+=1;name=f'{op:02X}'
        if normalize and op<=0x0A:
            while at<len(code)and code[at]<=0x0C:at+=1
            name='NUMBER'
        elif normalize and 0x40<=op<=0x4E:name='STORE'
        elif normalize and 0x60<=op<=0x6E:name='LOAD'
        elif normalize and 0x70<=op<=0xEE and op%16<=14:name=f'INDIRECT_{op//16:X}'
        elif normalize and op in [0x58,0x5A,0x5B,0x5D]:name='LOOP'
        if catalog[op]['takes_address']:
            if at>=len(code):return None
            at+=1
        result.append(name)
    return result


class Language:
    def __init__(self,sequences,alphabet):
        self.one=collections.Counter();self.two=collections.Counter();self.three=collections.Counter()
        self.ctx2=collections.Counter();self.ctx3=collections.Counter();self.programs=len(sequences)
        # All documented/undocumented canonical tokens are assigned probability;
        # the number of unseen tokens cannot depend on the final exam.
        self.alphabet=set(alphabet)
        for seq in sequences:
            a=b='START'
            for c in seq+['END']:
                self.one[c]+=1;self.two[b,c]+=1;self.three[a,b,c]+=1
                self.ctx2[b]+=1;self.ctx3[a,b]+=1;a,b=b,c
        self.total=sum(self.one.values())

    def probability(self,a,b,c,order):
        p=(self.one[c]+.5)/(self.total+.5*len(self.alphabet))
        if order>=2:p=(self.two[b,c]+5*p)/(self.ctx2[b]+5)
        if order>=3:p=(self.three[a,b,c]+5*p)/(self.ctx3[a,b]+5)
        return p

    def score(self,seq,order):
        a=b='START';bits=[]
        for c in seq+['END']:
            bits.append(-math.log2(self.probability(a,b,c,order)));a,b=b,c
        return -math.fsum(bits)/(len(seq)+1)

    def export(self):
        def rows(counter):return [{'tokens':list(k)if isinstance(k,tuple)else[k],'count':v}for k,v in sorted(counter.items())]
        return {'programs':self.programs,'commands_with_END':self.total,'unigrams':rows(self.one),'bigrams':rows(self.two),'trigrams':rows(self.three),
                'smoothing':{'unigram_additive':.5,'bigram_prior_strength':5,'trigram_prior_strength':5},'alphabet':sorted(self.alphabet)}


def auc(positive,negative):
    # Mann-Whitney, including ties. Larger score means more typical.
    rows=sorted([(v,1)for v in positive]+[(v,0)for v in negative]);rank_sum=0.;at=0
    while at<len(rows):
        end=at+1
        while end<len(rows)and rows[end][0]==rows[at][0]:end+=1
        rank=(at+1+end)/2;rank_sum+=rank*sum(label for _,label in rows[at:end]);at=end
    n=len(positive);m=len(negative)
    return (rank_sum-n*(n+1)/2)/(n*m)if n and m else None


def main():
    ROOT.mkdir(exist_ok=True);catalog={r['code']:r for r in json.loads((EXAM/'catalog.json').read_text())}
    alphabet={commands([i,0]if catalog[i]['takes_address']else[i],catalog)[0]for i in range(256)}|{'END'}
    historic=read(BASE/'corpus/games-train.jsonl');historic=[r['bytes']for r in historic if r.get('usable_for_code')and r.get('bytes')]
    synthetic=[t['reference_code']for t in read(EXAM/'train.jsonl')]
    pools={'historical':historic,'verified_training':synthetic,'combined':historic+synthetic};models={};metadata={}
    for name,codes in pools.items():
        unique=list(dict.fromkeys(tuple(c)for c in codes));seqs=[commands(c,catalog)for c in unique];seqs=[s for s in seqs if s is not None]
        models[name]=Language(seqs,alphabet);metadata[name]={'source_rows':len(codes),'unique_byte_programs':len(unique),'decoded_programs':len(seqs)}
    tasks=read(EXAM/'fresh.jsonl');lookup={t['id']:t for t in tasks};seeds=read(EXAM/'fresh-seeds.jsonl')
    references=[commands(t['reference_code'],catalog)for t in tasks]
    negatives=[commands(s['candidate_code'],catalog)for s in seeds if not s['intentionally_correct']]
    report={'posthoc_only':True,'threshold_selected':False,'new_SGD_updates':0,'datasets':metadata,
            'game_test_split_opened':False,'task_answers_used_for_score':False,'probability_model_inputs':'only decoded opcode sequence, never task text',
            'address_operands_skipped':True,'registers_and_literal_values_normalized':True,'metrics':{},'counterexamples':{}}
    rng=__import__('random').Random(611811)
    shuffled=[]
    for seq in references:
        if seq is not None:
            x=seq[:];rng.shuffle(x);shuffled.append(x)
    audit=json.loads((EXAM/'sft-audit.json').read_text());good=[];bad=[];invalid=0
    for r in audit['tools']['details']:
        if not r['finished']:continue
        t=lookup[r['id']]
        try:seq=commands(assemble(r['body'],t.get('constants')or constants(t['task']),'asm'),catalog)
        except ValueError:seq=None
        if seq is None:invalid+=1;continue
        (good if r['program_correct']else bad).append(seq)
    for name,model in models.items():
        entries={}
        for order in [1,2,3]:
            score=lambda rows:[model.score(s,order)for s in rows if s is not None]
            positive=score(references);negative=score(negatives);shuffle=score(shuffled);g=score(good);b=score(bad)
            entries[str(order)]={'correct_reference_vs_known_wrong_AUC':auc(positive,negative),
               'reference_higher_than_own_corruption_rate':sum(model.score(a,order)>model.score(b,order)for a,b in zip(references,negatives)if a is not None and b is not None)/sum(a is not None and b is not None for a,b in zip(references,negatives)),
               'reference_vs_shuffled_AUC':auc(positive,shuffle),'correct_model_DONE_vs_false_DONE_AUC':auc(g,b),
               'correct_model_DONE_scored':len(g),'false_DONE_scored':len(b),'incomplete_instruction_false_DONE_not_scored':invalid,
               'reference_median_bits_per_command':-sorted(positive)[len(positive)//2],
               'wrong_median_bits_per_command':-sorted(negative)[len(negative)//2]}
        report['metrics'][name]=entries
        table=model.export();(ROOT/(name+'-counts.json')).write_text(json.dumps(table,ensure_ascii=False,indent=2)+'\n')
    examples={'sin22':[2,2,0x1C,0x50],'cos22':[2,2,0x1D,0x50],'sin_minus1':[1,0x0B,0x1C,0x50],
              'literal1':[1,0x50],'literal0':[0,0x50],'square':[0x22,0x50],'double_square':[0x22,0x22,0x50]}
    for name,code in examples.items():
        seq=commands(code,catalog);report['counterexamples'][name]={'code':code,'tokens':seq,
                   'combined_trigram_bits_per_command':-models['combined'].score(seq,3)}
    model=models['combined'];observed=len(model.one)+1
    report['compact_table_estimates']={'observed_token_types_with_START':observed,
        'observed_bigrams':len(model.two),'observed_trigrams':len(model.three),
        'sparse_bigram_counts_u8_u8_u16_bytes':4*len(model.two),
        'sparse_trigram_counts_u8_u8_u8_u16_bytes':5*len(model.three),
        'maximum_count':max(max(model.one.values()),max(model.two.values()),max(model.three.values())),
        'excludes_lookup_index_alignment_unigram_counts_and_smoothing_parameters':True}
    paths=[BASE/'corpus/games-train.jsonl',EXAM/'train.jsonl',EXAM/'fresh.jsonl',EXAM/'fresh-seeds.jsonl',EXAM/'sft-audit.json']
    report['source_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths}
    report.update(historical_exclusion_note='24 unique historical listings ended where sequential decoding required another address byte; conservatively excluded, not declared incorrect games. Embedded data and multiple entry points are not resolved.',
        corpus_correctness_note='Historical listings are syntax-parsed, not all independently verified playable games.',
        interpretation='AUC is a ranking statistic, not accuracy or probability that a particular program is correct.',
        evaluated_control_flow='listing order only; execution paths and dataflow are not reconstructed.',not_deployed=True)
    (ROOT/'diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
