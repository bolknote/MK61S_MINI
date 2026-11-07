"""Measure serialization and vocabulary costs without changing any trained model."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
import re

from byte_codec import Codec,huffman


def read(p):return [json.loads(x)for x in p.read_text().splitlines()]
def quant_matrix_bytes(rows,cols):return rows*cols//2+rows*(cols//32)*2


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    from transformers import AutoTokenizer,AddedToken
    from course_common import answer
    from emulator import Emulator
    from harness import check_program
    out=root/'codec-study';out.mkdir(exist_ok=True)
    tokenizer=AutoTokenizer.from_pretrained(root/'export/small/hf',local_files_only=True,trust_remote_code=False)
    source_files=[root/'course/train.jsonl',root/'phase4-extra-train.jsonl',root/'course/formal-replay.jsonl',root/'phase4-feedback.jsonl']
    train=[]
    for path in source_files:
        if not path.exists():continue
        for row in read(path):train.append(answer(row)if 'reference_code'in row else row['answer'])
    dev_tasks=[r for level in [1,2,3]for r in read(root/f'development{level}.jsonl')]
    dev_tasks+=read(root/'course/formal-development.jsonl')
    dev=[answer(t)if 'expression'in t else'<write>'+' '.join(f'{x:02X}'for x in t['reference_code'])+'</write><run/>'for t in dev_tasks]
    pattern=re.compile(r'<write>\s*([0-9A-Fa-f\s]+)\s*</write>')
    def programs(texts):
        return [[int(x,16)for x in match.group(1).split()]for text in texts for match in pattern.finditer(text)]
    train_programs=programs(train);frequencies=collections.Counter(x for code in train_programs for x in code)
    books={radix:huffman(frequencies,radix)for radix in [2,16,32,64,256]}
    codecs={r:Codec(book,r)for r,book in books.items()}
    metrics={}
    for split,texts in [('training_inventory',train),('development',dev)]:
        codes=programs(texts);bodies=[' '.join(f'{x:02X}'for x in code)for code in codes]
        body_tokens=tokenizer(bodies,add_special_tokens=False)['input_ids']
        full_tokens=tokenizer(texts,add_special_tokens=False)['input_ids']
        total_bytes=sum(map(len,codes));hex_tokens=sum(map(len,body_tokens));formatted={}
        for radix,codec in codecs.items():
            count=sum(len(codec.encode(code))for code in codes)
            assert all(codec.decode(codec.encode(code),105)==code for code in codes)
            formatted[str(radix)]={'code_symbols':count,'symbols_per_byte':count/total_bytes,'body_reduction_vs_hex':1-count/hex_tokens}
            if radix in [32,256]:
                # These are virtual new tokens for length measurement only.
                # No model is resized, trained or evaluated with them here.
                variant=copy.deepcopy(tokenizer);tags=[f'<mk{i:03d}>'for i in range(radix)]
                variant.add_tokens([AddedToken(tag,normalized=False,special=False)for tag in tags])
                assert all(len(variant.encode(tag,add_special_tokens=False))==1 for tag in tags)
                def substitute(m):return '<write>'+''.join(tags[i]for i in codec.encode([int(x,16)for x in m.group(1).split()]))+'</write>'
                changed=[pattern.sub(substitute,text)for text in texts]
                new_lengths=variant(changed,add_special_tokens=False)['input_ids']
                formatted[str(radix)]['full_answer_tokens_with_existing_markers']=sum(map(len,new_lengths))
        metrics[split]={'answers':len(texts),'programs':len(codes),'program_bytes':total_bytes,
          'hex_body_tokens':hex_tokens,'hex_body_tokens_per_byte':hex_tokens/total_bytes,
          'full_answer_tokens':sum(map(len,full_tokens)),'codes':formatted,
          'observed_target_token_ids':sorted(set(t for ids in full_tokens for t in ids)|{tokenizer.eos_token_id})}
    # A code-only output alphabet must cover every byte/address, not just seen opcodes.
    universal=set([tokenizer.eos_token_id]);calc=set()
    for start in range(0,256,16):
        texts=[f'<write>{a:02X} {b:02X}</write><run/>'for a in range(start,start+16)for b in range(256)]
        universal.update(t for ids in tokenizer(texts,add_special_tokens=False)['input_ids']for t in ids)
    for text in ['<trace/>','<done/>','<write>','</write>','<run/>']:
        universal.update(tokenizer.encode(text,add_special_tokens=False))
    ops=['+','-','*','/','abs','neg','square']
    for op in ops:
        for child in ops:
            for r in range(4):
                text=f'<calc>{op} {child} R{r} R{(r+1)%4} R{(r+2)%4}</calc><write>60 61 10 50</write><run/>'
                calc.update(tokenizer.encode(text,add_special_tokens=False))
    allowed=universal|calc|set(metrics['training_inventory']['observed_target_token_ids'])
    (out/'output-token-ids.json').write_text(json.dumps(sorted(allowed))+'\n')
    # Prefix truncation is dependency-closed for this learned BPE. Measure the
    # longer input, rather than assuming smaller vocabulary gives more context.
    original=json.loads((root/'export/small/hf/tokenizer.json').read_text());pruned={}
    from tokenizers import Tokenizer
    texts=[t['task']for t in dev_tasks]
    original_lengths=[len(tokenizer.encode(x,add_special_tokens=False))for x in texts]
    for size in [1024,2048,4096]:
        state=copy.deepcopy(original);vocab={k:v for k,v in state['model']['vocab'].items()if v<size}
        merges=[pair for pair in state['model']['merges']if ''.join(pair)in vocab]
        assert all(a in vocab and b in vocab for a,b in merges)
        assert len(vocab)==size and set(vocab.values())==set(range(size))
        state['model'].update(vocab=vocab,merges=merges)
        variant=Tokenizer.from_str(json.dumps(state,ensure_ascii=False));lengths=[len(variant.encode(x,add_special_tokens=False).ids)for x in texts]
        assert all(variant.decode(variant.encode(x,add_special_tokens=False).ids)==x for x in texts)
        pruned[str(size)]={'input_tokens':sum(lengths),'input_inflation':sum(lengths)/sum(original_lengths),
          'parameters_small':3017984-(8192-size)*128,'parameters_champion':5789568-(8192-size)*256,
          'q4_weight_bytes_saved_small':quant_matrix_bytes(8192-size,128),
          'q4_weight_bytes_saved_champion':quant_matrix_bytes(8192-size,256),
          'no_quality_measurement':True}
    verified=0;em=Emulator()
    for task in dev_tasks[:24]:
        code=task['reference_code'];original_result=check_program(em,code,task['public_tests']+task['hidden_tests'])
        for radix in [32,256]:
            decoded=codecs[radix].decode(codecs[radix].encode(code),105)
            result=check_program(em,decoded,task['public_tests']+task['hidden_tests'])
            assert result==original_result
            verified+=1
    for radix,book in books.items():
        (out/f'codebook-{radix}.json').write_text(json.dumps({'radix':radix,'pseudocount':1,'byte_to_symbols':{f'{k:02X}':list(v)for k,v in sorted(book.items())}},indent=2)+'\n')
    summary={'metrics':metrics,'target_token_alphabet':{'code_only_all_256_bytes':len(universal),'code_calc_and_observed_tools':len(allowed),
      'rows':sorted(allowed),'source_vocabulary':len(tokenizer),'projection_pruning_removes_input_embedding_weights':False},
      'pruned_vocabulary':pruned,'original_input_tokens':sum(original_lengths),
      'top_bytes':[{'hex':f'{k:02X}','count':v,'huffman32_symbols':list(books[32][k])}for k,v in frequencies.most_common(24)],
      'source_files_sha256':{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest()for f in source_files if f.exists()},
      'embedding_and_output_weights_tied':True,'new_256_q4_embedding_bytes':{'small':quant_matrix_bytes(256,128),'champion':quant_matrix_bytes(256,256)},
      'emulator_roundtrips':verified,'all_256_bytes_representable':True,'models_modified':False,
      'new_codec_quality_measured':False,'primary_closed_test_reused_for_quality_selection':False,
      'scope':'Serialization costs and reversible prototypes only. Huffman fitted on training inventory. Development used for length and lossless checks.'}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items()if k not in ['metrics','source_files_sha256','top_bytes']},ensure_ascii=False),flush=True)
    print(json.dumps(metrics,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
