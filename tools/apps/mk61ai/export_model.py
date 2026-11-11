#!/usr/bin/env python3
"""Export existing MKQ4/MKQB weights and the exact Flourish BPE to native MKA.

No training code is imported or modified. Integers are little endian, tensor
records are 32 bytes, and payload CRC32 covers metadata and all model bytes.
Q2/Q3 retain MKQB's mid-rise grid; they are not offset-binary Q4 grids.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import unicodedata as ud
import zlib

MAGIC = b"M61AI01\0"


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def byte_alphabet():
    original = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    extra = 0
    mapping = {}
    for b in range(256):
        if b in original:
            mapping[b] = chr(b)
        else:
            mapping[b] = chr(256 + extra)
            extra += 1
    return mapping


def export(weights, tokenizer, output, layout='linear', vocab_limit=None):
    raw = weights.read_bytes()
    if raw[:8] not in (b"MKQ4v1\0\0", b"MKQBv1\0\0"):
        raise ValueError("Expected MKQ4v1 or MKQBv1")
    n = struct.unpack_from("<I", raw, 8)[0]
    source = json.loads(raw[12:12+n])
    cfg = source["config"]
    if cfg.get("model_type") != "qwen3" or not cfg.get("tie_word_embeddings"):
        raise ValueError("Native runtime requires tied-embedding Qwen3")
    if cfg.get("attention_bias") or cfg.get("hidden_act") != "silu":
        raise ValueError("Unsupported attention bias or activation")
    rope = cfg.get("rope_parameters") or cfg.get("rope_scaling") or {}
    if rope.get("rope_type", "default") != "default":
        raise ValueError("Only default RoPE is supported")
    tok = json.loads(tokenizer.read_text())
    original_vocab = tok["model"]["vocab"]
    source_vocab = cfg["vocab_size"]
    if len(original_vocab) != source_vocab or set(original_vocab.values()) != set(range(source_vocab)):
        raise ValueError("Non-contiguous vocabulary")
    if vocab_limit is not None:
        if not isinstance(vocab_limit, int) or not 259 <= vocab_limit <= source_vocab:
            raise ValueError("Vocabulary limit must retain special tokens and byte fallback")
        keep = {word: index for word, index in original_vocab.items() if index < vocab_limit}
        if any(ch not in keep for ch in byte_alphabet().values()):
            raise ValueError("Vocabulary limit drops a byte token")
        if any(cfg[key] >= vocab_limit for key in ("bos_token_id", "eos_token_id")):
            raise ValueError("Vocabulary limit drops BOS/EOS")
        tok["model"]["vocab"] = keep
        selected_merges = []
        for pair in tok["model"]["merges"]:
            left, right = pair if isinstance(pair, list) else pair.split(" ")
            if left in keep and right in keep and left + right in keep:
                selected_merges.append(pair)
        tok["model"]["merges"] = selected_merges
        cfg = dict(cfg, vocab_size=vocab_limit)
    expected_pre = {"type":"Sequence", "pretokenizers":[{"type":"Digits","individual_digits":True},
        {"type":"ByteLevel","add_prefix_space":False,"trim_offsets":True,"use_regex":True}]}
    if tok["model"]["type"] != "BPE" or tok.get("normalizer") != {"type":"NFC"} or tok.get("pre_tokenizer") != expected_pre:
        raise ValueError("Tokenizer normalization or pre-tokenization differs from the native contract")
    if any(t.get("single_word") or t.get("lstrip") or t.get("rstrip") or t.get("normalized") for t in tok["added_tokens"]):
        raise ValueError("Unsupported added-token matching rule")
    if [(t["id"],t["content"]) for t in tok["added_tokens"]] != [(0,"<pad>"),(1,"<bos>"),(2,"<eos>")]:
        raise ValueError("Unsupported special tokens")
    post = tok.get("post_processor", {})
    if post.get("type") != "TemplateProcessing" or post.get("single") != [{"SpecialToken":{"id":"<bos>","type_id":0}},{"Sequence":{"id":"A","type_id":0}}]:
        raise ValueError("Expected exactly one automatic BOS")
    blob = bytearray(128)
    def append(data, alignment=4):
        blob.extend(b"\0"*((-len(blob)) % alignment))
        offset = len(blob)
        blob.extend(data)
        return offset
    names = ["model.embed_tokens.weight", "model.norm.weight"]
    suffixes = ["input_layernorm.weight", "self_attn.q_proj.weight", "self_attn.k_proj.weight",
        "self_attn.v_proj.weight", "self_attn.q_norm.weight", "self_attn.k_norm.weight",
        "self_attn.o_proj.weight", "post_attention_layernorm.weight", "mlp.gate_proj.weight",
        "mlp.up_proj.weight", "mlp.down_proj.weight"]
    for layer in range(cfg["num_hidden_layers"]):
        names += [f"model.layers.{layer}.{s}" for s in suffixes]
    records = {t["name"]:t for t in source["tensors"]}
    if set(names) != set(records):
        raise ValueError("Tensor set differs from the supported architecture")
    tensor_offset = append(bytes(32*len(names)))
    payload = memoryview(raw)[12+n:]
    for i, name in enumerate(names):
        t = records[name]
        shape = t["shape"]
        chunk = bytes(payload[t["offset"]:t["offset"]+t["bytes"]])
        if len(chunk) != t["bytes"]:
            raise ValueError("Truncated tensor")
        if name == "model.embed_tokens.weight" and vocab_limit is not None:
            # Tied embedding/head: remove exactly the same rows from both
            # uses, retaining IDs of all surviving tokens. Other weights are
            # byte-identical. This changes tokenization and needs quality eval.
            if shape[0] != source_vocab or len(shape) != 2:
                raise ValueError("Unexpected tied embedding shape")
            bits = t.get("bits", 4)
            old_codes = t["codes_bytes"]
            new_codes = vocab_limit * shape[1] * bits // 8
            new_scales = vocab_limit * shape[1] // 16
            chunk = chunk[:new_codes] + chunk[old_codes:old_codes + new_scales]
            shape = [vocab_limit, shape[1]]
            t = dict(t, codes_bytes=new_codes)
        if len(shape) == 1:
            record = (1,shape[0],32,0,append(chunk),0,len(chunk),0)
        else:
            bits = t.get("bits",4)
            if bits not in (2,3,4) or shape[1] % 32:
                raise ValueError("Unsupported matrix packing")
            codes = t["codes_bytes"]
            if codes != shape[0]*shape[1]*bits//8 or len(chunk)-codes != shape[0]*shape[1]//16:
                raise ValueError("Invalid matrix group sizes")
            packed=chunk[:codes]
            planes=layout=='lut' or (layout=='hybrid' and bits==4 and shape[1]==128)
            if planes:
                reordered=bytearray(codes)
                for group in range(shape[0]*shape[1]//32):
                    original=packed[group*4*bits:(group+1)*4*bits]
                    values=[(int.from_bytes(original,'little')>>(i*bits))&((1<<bits)-1) for i in range(32)]
                    for bit in range(bits):
                        for quartet in range(8):
                            index=sum(((values[quartet*4+j]>>bit)&1)<<j for j in range(4))
                            reordered[group*4*bits+bit*4+quartet//2]|=index<<(4*(quartet%2))
                packed=bytes(reordered)
            record = (*shape,bits,(0 if bits==4 else 1)|(256 if planes else 0),append(packed),append(chunk[codes:]),codes,len(chunk)-codes)
        struct.pack_into("<8I",blob,tensor_offset+32*i,*record)
    vocab = tok["model"]["vocab"]
    if len(vocab) != cfg["vocab_size"] or set(vocab.values()) != set(range(len(vocab))):
        raise ValueError("Non-contiguous vocabulary")
    vocab_offset = append(bytes(8*len(vocab)))
    alphabet = byte_alphabet()
    inverse = {v:k for k,v in alphabet.items()}
    for word, token in sorted(vocab.items(),key=lambda item:item[1]):
        data = word.encode() if token<3 else bytes(inverse[c] for c in word)
        if len(data)>65535: raise ValueError("Oversized vocabulary token")
        offset = append(data,1)
        struct.pack_into("<IHBB",blob,vocab_offset+8*token,offset,len(data),token<3,0)
    merges=[]
    for rank,pair in enumerate(tok["model"]["merges"]):
        left,right=pair if isinstance(pair,list) else pair.split(" ")
        merges.append(((vocab[left]<<16)|vocab[right],vocab[left+right],rank))
    merge_offset=append(b"".join(struct.pack("<3I",*m) for m in sorted(merges)))
    byte_offset=append(struct.pack("<256H",*(vocab[alphabet[b]] for b in range(256))))
    decompositions=[];compositions=[]
    for cp in range(0x110000):
        if 0xAC00<=cp<=0xD7A3: continue # Hangul is normalized algorithmically.
        ch=chr(cp);nfd=ud.normalize("NFD",ch)
        if nfd!=ch:
            parts=list(map(ord,nfd))
            if len(parts)>4: raise ValueError("Canonical decomposition longer than four codepoints")
            decompositions.append((cp,len(parts),*(parts+[0]*(4-len(parts)))))
        direct=ud.decomposition(ch)
        if direct and not direct.startswith("<"):
            parts=[int(v,16) for v in direct.split()]
            if len(parts)==2 and ud.normalize("NFC",''.join(map(chr,parts)))==ch:
                compositions.append((*parts,cp))
    nfd_offset=append(b"".join(struct.pack("<6I",*r) for r in decompositions))
    compose_offset=append(b"".join(struct.pack("<3I",*r) for r in sorted(compositions)))
    spaces={*range(9,14),32,0x85,0xA0,0x1680,*range(0x2000,0x200B),0x2028,0x2029,0x202F,0x205F,0x3000}
    ranges=[];start=0;previous=0
    for cp in range(0x110001):
        if cp==0x110000: flags=0
        else:
            ch=chr(cp);category=ud.category(ch)
            flags=(ud.combining(ch)<<8)|(1 if category[0]=='L' else 2 if category[0]=='N' else 0)|(4 if cp in spaces else 0)
        if flags!=previous:
            if previous: ranges.append((start,cp-1,previous))
            start=cp;previous=flags
    class_offset=append(b"".join(struct.pack("<3I",*r) for r in ranges))
    dim=cfg["head_dim"];theta=rope.get("rope_theta",cfg.get("rope_theta",10000.0))
    rope_data=bytearray()
    for pos in range(cfg["max_position_embeddings"]):
        for j in range(dim//2):
            angle=f32(pos*f32(1.0/(theta**f32(2*j/dim))))
            rope_data+=struct.pack("<ff",math.cos(angle),math.sin(angle))
    rope_offset=append(rope_data)
    header=[0]*32
    header[2:14]=[1,len(blob),cfg["num_hidden_layers"],cfg["hidden_size"],cfg["intermediate_size"],
        cfg["num_attention_heads"],cfg["num_key_value_heads"],dim,cfg["vocab_size"],cfg["max_position_embeddings"],
        cfg["bos_token_id"],cfg["eos_token_id"]]
    header[14]=struct.unpack("<I",struct.pack("<f",cfg["rms_norm_eps"]))[0]
    header[15:28]=[tensor_offset,vocab_offset,merge_offset,len(merges),byte_offset,nfd_offset,len(decompositions),
        compose_offset,len(compositions),class_offset,len(ranges),rope_offset,0]
    header[28]=1
    header[29]=zlib.crc32(blob[128:])
    struct.pack_into("<32I",blob,0,*header);blob[:8]=MAGIC
    struct.pack_into("<I",blob,124,zlib.crc32(blob[:124]))
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(blob)
    report={"format":"M61AI01","file":str(output),"bytes":len(blob),"sha256":hashlib.sha256(blob).hexdigest(),
        "source_weights_sha256":hashlib.sha256(raw).hexdigest(),"unicode":ud.unidata_version,
        "tensors":len(names),"vocab":len(vocab),"merges":len(merges),"layout":layout,"architecture":cfg}
    if vocab_limit is not None:
        report["vocabulary_pruning"] = {"source_vocab":source_vocab, "kept_vocab":vocab_limit,
            "removed_parameters":(source_vocab-vocab_limit)*cfg["hidden_size"],
            "method":"ID prefix, preserve all bytes/specials, filter BPE merges, tied-row removal",
            "quality_verified":False}
        output.with_suffix('.tokenizer.json').write_text(json.dumps(tok,ensure_ascii=False)+'\n')
    output.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='architecture'},ensure_ascii=False))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--weights',type=Path,required=True)
    p.add_argument('--tokenizer',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--layout',choices=['linear','lut','hybrid'],default='lut')
    p.add_argument('--vocab-limit',type=int,help='Experimental prefix pruning; needs separate quality evaluation')
    a=p.parse_args();export(a.weights,a.tokenizer,a.output,a.layout,a.vocab_limit)


if __name__=='__main__':main()
