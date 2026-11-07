#!/usr/bin/env python3
"""Reallocate TinyTalk's vocabulary budget to a wider transformer.

Keep 16384 ordinary GPT-2 tokens, chat markers and EOS; double hidden/MLP widths,
and retain 256 learned positions. FP32 logits for retained token IDs are
preserved before a small deliberate symmetry-breaking perturbation. GPT-Neo
uses UNSCALED QK attention; the construction is verified against local HF code.
This is an isolated initialization experiment, not a trained replacement.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import struct

from common import core, quantize


def smaller_tokenizer(tokenizer, limit, vocabulary_data=None):
    from tokenizers import Tokenizer
    data = json.loads(tokenizer.backend_tokenizer.to_str())
    original_vocab = data["model"]["vocab"]
    token_by_id = {index: token for token, index in original_vocab.items()}
    parents = {left + right: (left, right) for left, right in data["model"]["merges"]}
    retained = set(range(limit)) if vocabulary_data is None else set(range(256))
    def retain(token):
        index = original_vocab[token]
        if index in retained:return
        if token in parents:
            for part in parents[token]:retain(part)
        retained.add(index)
    # Keep the established chat markers and identity spelling intact.
    for index in tokenizer.encode("User: \nBot: TinyTalk TinyTalk", add_special_tokens=False):
        retain(token_by_id[index])
    selection = {"policy": "GPT-2 rank prefix plus critical chat markers"}
    if vocabulary_data is not None:
        counts = Counter()
        for row in core.read_rows(vocabulary_data):
            weight = 0.05 if row["kind"] == "replay" else 1.0
            text = core.render(row["messages"]) + " " + row["target"]
            for index in tokenizer.encode(text, add_special_tokens=False):
                if index != tokenizer.eos_token_id:counts[index] += weight
        def missing(token):
            index = original_vocab[token]
            if index in retained:return set()
            result = {index}
            for part in parents.get(token, ()):result.update(missing(part))
            return result
        order = [index for index, _ in counts.most_common()] + list(range(tokenizer.eos_token_id))
        for index in order:
            if len(retained) == limit:break
            extra = missing(token_by_id[index])
            if len(retained) + len(extra) <= limit:retained.update(extra)
        assert len(retained) == limit
        total = sum(counts.values())
        selection = {"policy": "Training token frequency, complete merge ancestry, 5% weight for natural-dialogue replay",
                     "source_training_sha256": core.digest(vocabulary_data), "weighted_tokens": total,
                     "retained_weighted_token_fraction": sum(counts[i] for i in retained) / total,
                     "gpt2_prefix_weighted_token_fraction": sum(value for i, value in counts.items() if i < limit) / total,
                     "evaluation_data_used": False}
    keep = sorted(retained) + [tokenizer.eos_token_id]
    vocab = {token_by_id[old]: new for new, old in enumerate(keep)}
    data["model"]["vocab"] = vocab
    data["model"]["merges"] = [pair for pair in data["model"]["merges"] if pair[0] + pair[1] in vocab]
    for item in data["added_tokens"]:
        assert item["content"] == tokenizer.eos_token
        item["id"] = len(keep) - 1
    result = copy.deepcopy(tokenizer)
    result._tokenizer = Tokenizer.from_str(json.dumps(data))
    result.pad_token = result.eos_token
    result.model_max_length = 256
    assert len(result) == len(keep) and result.eos_token_id == len(keep) - 1
    return result, keep, selection


def compact_tokenizer(tokenizer, path, allow_missing_bytes=False):
    """Serialize actual byte strings and merge triples; no native encoder is claimed."""
    data = json.loads(tokenizer.backend_tokenizer.to_str())
    vocab = tokenizer.get_vocab()
    allowed = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    encoder = {value: chr(value) for value in allowed}
    for index, value in enumerate(value for value in range(256) if value not in encoder):
        encoder[value] = chr(256 + index)
    decoder = {char: value for value, char in encoder.items()}
    special_ids = {item["id"] for item in data["added_tokens"] if item.get("special")}
    tokens = [None] * len(vocab)
    for token, index in vocab.items():
        tokens[index] = b"" if index in special_ids else bytes(decoder[char] for char in token)
    records, blob = bytearray(), bytearray()
    for value in tokens:
        records.extend(struct.pack("<IH", len(blob), len(value)));blob.extend(value)
    missing_bytes=[value for value in range(256)if encoder[value]not in vocab]
    if missing_bytes and not allow_missing_bytes:raise ValueError(f'Tokenizer lacks base byte IDs: {missing_bytes}')
    fallback=tokenizer.unk_token_id if tokenizer.unk_token_id is not None else tokenizer.eos_token_id
    byte_map = b"".join(struct.pack("<H", vocab.get(encoder[value],fallback)) for value in range(256))
    triples = sorted((vocab[left], vocab[right], vocab[left + right]) for left, right in data["model"]["merges"])
    merges = b"".join(struct.pack("<HHH", *triple) for triple in triples)
    parts = [("byte_to_id", byte_map), ("token_records", records), ("token_bytes", blob), ("merges", merges)]
    offset = 0;entries = {}
    for name, value in parts:
        entries[name] = {"offset": offset, "bytes": len(value)};offset += len(value)
    metadata = {"format": "TTBPE1", "vocab_size": len(vocab), "eos_token_id": tokenizer.eos_token_id,
                "special_token_ids": sorted(special_ids),
                "merge_count": len(triples), "parts": entries, "payload_bytes": offset,
                "token_record": "u32 byte offset, u16 byte length", "merge_record": "u16 left, u16 right, u16 result; sorted by pair",
                "native_encoder_implemented": False}
    if missing_bytes:metadata.update(missing_base_bytes=missing_bytes,missing_byte_fallback_token_id=fallback)
    header = json.dumps(metadata, separators=(",", ":")).encode()
    beginning = b"TTBPE1\0\0" + struct.pack("<I", len(header)) + header
    beginning += bytes((-len(beginning)) % 16)
    raw = beginning + b"".join(bytes(value) for _, value in parts)
    Path(path).write_bytes(raw)
    # Verify byte decoding from the serialized records, including multibyte UTF-8.
    blob_start = len(beginning) + entries["token_bytes"]["offset"]
    record_start = len(beginning) + entries["token_records"]["offset"]
    examples = ["Hello! How are you?", "A small paper boat.\n", "Привет, мир!", "I'm TinyTalk."]
    for text in examples:
        restored = bytearray()
        for token in tokenizer.encode(text, add_special_tokens=False):
            at, size = struct.unpack_from("<IH", raw, record_start + token * 6)
            restored.extend(raw[blob_start + at:blob_start + at + size])
        expected=tokenizer.decode(tokenizer.encode(text,add_special_tokens=False),skip_special_tokens=True) if allow_missing_bytes else text
        assert restored.decode("utf8") == expected
    return metadata | {"file_bytes": len(raw), "file_sha256": hashlib.sha256(raw).hexdigest(), "byte_decode_checks": len(examples)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--normal-vocab", type=int, default=16384)
    parser.add_argument("--symmetry-noise", type=float, default=0.001)
    parser.add_argument("--source-q4", action="store_true")
    parser.add_argument("--vocabulary-data")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=65132)
    args = parser.parse_args()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):raise ValueError("Use a new output directory")
    source, tokenizer, device = core.load(args)
    source.eval().requires_grad_(False)
    if args.source_q4:quantize.roundtrip(source)
    smaller, keep_ids, vocabulary_selection = smaller_tokenizer(tokenizer, args.normal_vocab, args.vocabulary_data)
    keep = torch.tensor(keep_ids, device=device)
    remap = {old: new for new, old in enumerate(keep_ids)}
    config = copy.deepcopy(source.config)
    config.hidden_size = 256;config.intermediate_size = 1024;config.vocab_size = len(keep_ids)
    config.max_position_embeddings = 256;config.layer_norm_epsilon /= 2
    config.bos_token_id = config.eos_token_id = config.pad_token_id = smaller.eos_token_id
    config.tinytalk_runtime_context = 128
    config.tinytalk_vocabulary_selection = vocabulary_selection
    config.tinytalk_rebalanced_from = {"checkpoint_sha256": core.digest(Path(args.model) / "model.safetensors"),
                                     "hidden_size": 128, "vocab_size": 50257, "ordinary_vocab_retained": args.normal_vocab,
                                     "source_q4_rounded": args.source_q4}
    wider = AutoModelForCausalLM.from_config(config, attn_implementation="eager").to(device).eval()
    hidden = torch.arange(128, device=device).repeat_interleave(2)
    feedforward = torch.arange(512, device=device).repeat_interleave(2)
    old_parameters = dict(source.named_parameters())
    root2 = 2 ** 0.5
    with torch.no_grad():
        for name, value in wider.named_parameters():
            old = old_parameters[name]
            if name == "transformer.wte.weight":replacement = old[keep][:, hidden] / root2
            elif name == "transformer.wpe.weight":replacement = old[:256, hidden] / root2
            elif ".ln_" in name:replacement = old[hidden] / root2
            elif ".attn.attention." in name:
                replacement = old[hidden][:, hidden] / 2 if value.ndim == 2 else old[hidden] / root2
            elif name.endswith("mlp.c_fc.weight"):replacement = old[feedforward][:, hidden] / root2
            elif name.endswith("mlp.c_fc.bias"):replacement = old[feedforward]
            elif name.endswith("mlp.c_proj.weight"):replacement = old[hidden][:, feedforward] / (2 * root2)
            elif name.endswith("mlp.c_proj.bias"):replacement = old[hidden] / root2
            else:raise ValueError(name)
            assert replacement.shape == value.shape
            value.copy_(replacement)
    assert wider.lm_head.weight is wider.transformer.wte.weight
    prompts = ["Hello!", "What is your name?", "I feel tired.", "What could I draw?", "Can you ask me something?"]
    old_inputs, new_inputs = [], []
    for text in prompts:
        prompt = core.render([{"role": "user", "content": text}])
        original = tokenizer(prompt, add_special_tokens=False, return_tensors="pt").to(device)
        converted = smaller(prompt, add_special_tokens=False, return_tensors="pt").to(device)
        if any(index not in remap for index in original.input_ids[0].tolist()):continue
        expected = torch.tensor([[remap[index] for index in original.input_ids[0].tolist()]], device=device)
        assert torch.equal(expected, converted.input_ids)
        old_inputs.append(original);new_inputs.append(converted)
    assert len(old_inputs) >= 3
    with torch.inference_mode():
        old_logits = [source(**batch, use_cache=False).logits[..., keep] for batch in old_inputs]
        exact = [wider(**batch, use_cache=False).logits for batch in new_inputs]
        preservation = max(float((old - new).abs().max()) for old, new in zip(old_logits, exact))
    assert preservation < 1e-4, preservation
    # Opposite perturbations keep the mean of each replicated pair unchanged.
    with torch.no_grad():
        embedding = wider.transformer.wte.weight
        noise = torch.randn_like(embedding[:, ::2]) * args.symmetry_noise
        embedding[:, ::2] += noise;embedding[:, 1::2] -= noise
        for block in wider.transformer.h:
            weight = block.mlp.c_fc.weight
            noise = torch.randn_like(weight[::2]) * (args.symmetry_noise / 2)
            weight[::2] += noise;weight[1::2] -= noise
    with torch.inference_mode():
        perturbed = [wider(**batch, use_cache=False).logits for batch in new_inputs]
        noisy_error = max(float((old - new).abs().max()) for old, new in zip(old_logits, perturbed))
        agrees = sum(int((old.argmax(-1) == new.argmax(-1)).sum()) for old, new in zip(old_logits, perturbed))
        positions = sum(old.shape[1] for old in old_logits)
    output.mkdir(parents=True)
    wider.save_pretrained(output, safe_serialization=True);smaller.save_pretrained(output);quantize.copy_notices(args.model, output)
    reloaded_tokenizer = AutoTokenizer.from_pretrained(output, local_files_only=True)
    assert reloaded_tokenizer.eos_token_id == smaller.eos_token_id and len(reloaded_tokenizer) == len(keep_ids)
    for text in prompts + ["Привет, мир!", "User: Hi\nBot: hello<|endoftext|>\nUser: Bye\nBot:"]:
        assert reloaded_tokenizer.decode(reloaded_tokenizer.encode(text, add_special_tokens=False)) == text
    packed = quantize.export(wider, output / "model.ttq4", {"derived_from": core.MODEL, **config.tinytalk_rebalanced_from,
                             "change": "Prune ordinary vocab to 16384; widen hidden/FFN by two; 256 positions; 128-token runtime design"})
    token_table = compact_tokenizer(reloaded_tokenizer, output / "tokenizer.ttbpe")
    total = packed["file_bytes"] + token_table["file_bytes"] + 1048576 + 262144
    assert total <= 8388608
    quantize.roundtrip(wider)
    reference = {name: p.detach().clone() for name, p in wider.named_parameters()}
    quantize.restore(wider, output / "model.ttq4")
    reload_error = max(float((reference[name] - p.detach()).abs().max()) for name, p in wider.named_parameters())
    assert reload_error == 0
    report = {"parameters": sum(p.numel() for p in wider.parameters()), "core_parameters": sum(p.numel() for p in wider.transformer.h.parameters()),
              "vocab": len(smaller), "hidden_size": 256, "intermediate_size": 1024, "layers": 8,
              "function_preservation_scope": "Retained token IDs, first 256 positions, FP32 before deliberate symmetry noise",
              "source_q4_rounded": args.source_q4,
              "vocabulary_selection": vocabulary_selection,
              "fp32_before_noise_max_abs_error": preservation, "symmetry_noise_std": args.symmetry_noise,
              "fp32_after_noise_max_abs_error": noisy_error, "retained_vocab_argmax_agreement": [agrees, positions],
              "packed": packed, "token_table": token_table, "packed_reload_max_abs_error": reload_error,
              "psram_design_bytes_context128": total, "psram_remaining_design_bytes": 8388608 - total,
              "native_runtime_measured": False, "trained": False}
    core.save(output / "rebalancing.json", report)
    print(json.dumps({k: report[k] for k in ["parameters", "core_parameters", "fp32_before_noise_max_abs_error", "fp32_after_noise_max_abs_error", "retained_vocab_argmax_agreement", "psram_design_bytes_context128", "psram_remaining_design_bytes"]}), flush=True)


if __name__ == "__main__":
    main()
