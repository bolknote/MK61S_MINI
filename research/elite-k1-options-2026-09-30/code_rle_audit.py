"""Count word and byte RLE opportunities in occupied ELITE code."""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path('/Users/bolk/Projects/MK61S_MINI')
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools/elite'))
from game import create_game

a=create_game()
banks,info=a.link()
labels,placements,bridges,usage=a.expand_branches()
code=set()
for address,item in placements:code.update(range(address,address+a.size(item)))
for address,dst in bridges:code.update(range(address,address+4))
for bank in a.data_helpers:code.update(range(bank*112+63,bank*112+76))
chunks=[]
runs=[]
integer_words=[]
for bank in range(32):
    data=banks.get(bank,bytes(112))
    current=[]
    for field in range(9):
        address=bank*112+field*7
        word=bytes(data[field*7:field*7+7]) if all(address+i in code for i in range(7)) else None
        if word is not None:
            chunks.append(word)
            if word[0]==0 and all((byte&15)<10 and (byte>>4)<10 for byte in word[1:]):
                digits=[v for byte in word[1:5] for v in (byte&15,byte>>4)]
                n=sum(v*10**i for i,v in enumerate(digits))
                exponent=(word[5]>>4)+10*(word[6]&15)
                if ((word[4]>>4)>0 and (word[5]&15) in (0,9) and word[6]>>4==0
                        and exponent<=7 and n%10**(7-exponent)==0):
                    integer_words.append((bank,field,word.hex()))
        if word is not None and current and word==current[-1]:current.append(word)
        else:
            if len(current)>1:runs.append((bank,len(current),current[0].hex()))
            current=[] if word is None else [word]
    if len(current)>1:runs.append((bank,len(current),current[0].hex()))

stream=bytes(banks[b][i] for b in sorted(banks) for i in range(112) if b*112+i in code)
byte_runs=1+sum(x!=y for x,y in zip(stream,stream[1:]))
report=dict(full_7_byte_code_records_in_exchange_heads=len(chunks),
            canonical_bounded_integer_words=integer_words,adjacent_equal_7_byte_code_runs=runs,
            code_bytes=len(stream),byte_rle_pairs_bytes=2*byte_runs,
            most_frequent_record_counts=[(w.hex(),n) for w,n in Counter(chunks).most_common(5)])
(HERE/'code-rle-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
