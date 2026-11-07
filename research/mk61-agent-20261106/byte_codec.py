"""Lossless byte-to-token prefix codes; symbol counts are learned from training only."""
import heapq
import itertools


def huffman(counts,radix):
    if not 2<=radix<=256:raise ValueError('Invalid alphabet size')
    serial=itertools.count();heap=[]
    for byte in range(256):heap.append((int(counts.get(byte,0))+1,next(serial),byte))
    padding=(-(len(heap)-1))%(radix-1)
    for _ in range(padding):heap.append((0,next(serial),None))
    heapq.heapify(heap)
    while len(heap)>1:
        children=[heapq.heappop(heap)for _ in range(radix)]
        heapq.heappush(heap,(sum(x[0]for x in children),next(serial),tuple(x[2]for x in children)))
    result={}
    def visit(node,code):
        if isinstance(node,tuple):
            for symbol,child in enumerate(node):visit(child,code+(symbol,))
        elif node is not None:result[node]=code
    visit(heap[0][2],())
    assert len(result)==256 and all(result.values())
    return result


class Codec:
    def __init__(self,codebook,radix):
        self.codebook={int(k):tuple(v)for k,v in codebook.items()};self.radix=radix;self.trie={}
        if set(self.codebook)!=set(range(256)):raise ValueError('Every byte must be represented')
        for byte,word in self.codebook.items():
            if not word:raise ValueError('Empty codeword')
            node=self.trie
            for symbol in word:
                if not isinstance(symbol,int)or not 0<=symbol<radix or 'byte'in node:raise ValueError('Invalid prefix code')
                node=node.setdefault(symbol,{})
            if node:raise ValueError('Ambiguous codeword')
            node['byte']=byte

    def encode(self,data):
        out=[]
        for byte in data:
            if byte not in self.codebook:raise ValueError('Not a byte')
            out.extend(self.codebook[byte])
        return out

    def decode(self,symbols,max_bytes=None):
        node=self.trie;out=[]
        for symbol in symbols:
            if symbol not in node:raise ValueError('Invalid symbol or unused padding code')
            node=node[symbol]
            if 'byte'in node:
                out.append(node['byte']);node=self.trie
                if max_bytes is not None and len(out)>max_bytes:raise ValueError('Program too long')
        if node is not self.trie:raise ValueError('Truncated codeword')
        return out
