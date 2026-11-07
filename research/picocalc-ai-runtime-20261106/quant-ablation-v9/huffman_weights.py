from pathlib import Path
import json,heapq,struct,time,hashlib
B=Path(__file__).resolve().parent;raw=(B/'model/model-nibble.mka').read_bytes();h=struct.unpack_from('<32I',raw)
hist=json.loads((B/'weight-grid-report.json').read_text())['histogram'];heap=[];serial=0
for symbol,count in enumerate(hist):
 if count:heapq.heappush(heap,(count,serial,symbol));serial+=1
while len(heap)>1:
 a=heapq.heappop(heap);b=heapq.heappop(heap);heapq.heappush(heap,(a[0]+b[0],serial,(a[2],b[2])));serial+=1
lengths=[0]*16
def visit(node,depth):
 if isinstance(node,int):lengths[node]=depth
 else:visit(node[0],depth+1);visit(node[1],depth+1)
visit(heap[0][2],0)
code=0;last=0;codes={};tree={}
for length,symbol in sorted((n,s)for s,n in enumerate(lengths)if n):
 code<<=length-last;codes[symbol]=(code,length);node=tree
 for pos in range(length-1,-1,-1):node=node.setdefault((code>>pos)&1,{})
 node['symbol']=symbol;code+=1;last=length
matrices=[]
for tensor in range(2+11*h[4]):
 row,col,bits,grid,off,scales,nbytes,nscales=struct.unpack_from('<8I',raw,h[15]+tensor*32)
 if bits==4:matrices.append(dict(tensor=tensor,rows=row,columns=col,offset=off,bytes=nbytes,index_start=0))
matrices.sort(key=lambda x:x['offset']);stream=bytearray();indices=[];acc=nbits=totalbits=0
started=time.monotonic()
for m in matrices:
 m['index_start']=len(indices)
 for row in range(m['rows']):
  indices.append(totalbits)
  for byte in raw[m['offset']+row*m['columns']//2:m['offset']+(row+1)*m['columns']//2]:
   for symbol in [byte&15,byte>>4]:
    code,length=codes[symbol];acc=(acc<<length)|code;nbits+=length;totalbits+=length
    while nbits>=8:
     nbits-=8;stream.append((acc>>nbits)&255);acc&=(1<<nbits)-1
if nbits:stream.append(acc<<(8-nbits))
encode_s=time.monotonic()-started
spans=[];at=0
for m in matrices:
 if m['offset']>at:spans.append([at,m['offset']-at])
 at=m['offset']+m['bytes']
if at<len(raw):spans.append([at,len(raw)-at])
rest=b''.join(raw[at:at+n]for at,n in spans)
meta=json.dumps(dict(size=len(raw),spans=spans,matrices=matrices,lengths=lengths,bit_count=totalbits,row_indices=len(indices)),separators=(',',':')).encode()
blob=b'MKA_HUF1'+struct.pack('<II',len(meta),len(indices))+meta+struct.pack('<'+'I'*len(indices),*indices)+rest+stream
(B/'model/model-row-huffman.bin').write_bytes(blob)
# Independent row decoder; restore every raw and coded byte before claiming lossless compression.
restored=bytearray(len(raw));at=0
for dest,n in spans:restored[dest:dest+n]=rest[at:at+n];at+=n
started=time.monotonic()
for m in matrices:
 for row in range(m['rows']):
  pos=indices[m['index_start']+row];out=bytearray();low=None
  for _ in range(m['columns']):
   node=tree
   while 'symbol'not in node:node=node[(stream[pos>>3]>>(7-(pos&7)))&1];pos+=1
   symbol=node['symbol']
   if low is None:low=symbol
   else:out.append(low|(symbol<<4));low=None
  start=m['offset']+row*m['columns']//2;restored[start:start+len(out)]=out
assert restored==raw
result=dict(status='LOSSLESS_ROUNDTRIP_PASS',original_bytes=len(raw),compressed_bytes=len(blob),saved_bytes=len(raw)-len(blob),saving_fraction=1-len(blob)/len(raw),compressed_code_bytes=len(stream),uncompressed_remainder_bytes=len(rest),row_index_bytes=4*len(indices),metadata_bytes=len(meta)+16,rows=len(indices),huffman_lengths=lengths,host_encode_seconds=encode_s,host_decode_seconds=time.monotonic()-started,restored_sha256=hashlib.sha256(restored).hexdigest(),scope='actual zero-order global Huffman with every-row random-access index; host timing only, not RP2040 speed')
(B/'huffman-report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
