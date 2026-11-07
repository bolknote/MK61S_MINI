#!/usr/bin/env python3
"""Audit shared weights and calculate embedded storage budgets for both candidates.

The packed tokenizer/runtime are designs, not implemented PicoCalc components.
Use the same row-padded 32-weight + FP16-scale Q4 layout as chat.py --q4.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch
from safetensors import safe_open
from sentencepiece import sentencepiece_model_pb2 as pb

ROOT = Path(__file__).resolve().parents[2]
CAPACITY = 8 * 1024 * 1024
RESERVE = 256 * 1024


def weights(path, include):
    matrices = []
    small = []
    with safe_open(path, framework="pt") as source:
        keys = set(source.keys())
        for key in sorted(keys):
            if not include(key):
                continue
            tensor = source.get_tensor(key)
            if tensor.ndim == 2 and key != "dwa_weights":
                rows, columns = tensor.shape
                matrices.append({"name": key, "parameters": tensor.numel(),
                                 "q4_32_bytes": rows * ((columns + 31) // 32) * 18,
                                 "q4_64_bytes": rows * ((columns + 63) // 64) * 34})
            else:
                small.append({"name": key, "parameters": tensor.numel(), "fp32_bytes": tensor.numel() * 4})
        alias_checks = 0
        if "output.weight" in keys:
            assert torch.equal(source.get_tensor("output.weight"), source.get_tensor("tok_embeddings.weight"))
            alias_checks += 1
            for key in sorted(keys):
                if key.startswith("layers."):
                    _, layer, suffix = key.split(".", 2)
                    other = f"_unique_layers.{int(layer) // 2}.{suffix}"
                    assert torch.equal(source.get_tensor(key), source.get_tensor(other)), (key, other)
                    alias_checks += 1
    return {"unique_parameters": sum(t["parameters"] for t in matrices + small),
            "identical_serialized_aliases_checked": alias_checks,
            "q4_32_bytes": sum(t["q4_32_bytes"] for t in matrices) + sum(t["fp32_bytes"] for t in small),
            "q4_64_bytes": sum(t["q4_64_bytes"] for t in matrices) + sum(t["fp32_bytes"] for t in small),
            "matrices": matrices, "small_fp32_parameters": small,
            "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def scenarios(weight_bytes, tokenizer_bytes, layers, kv_width, registers):
    results = []
    for context in [64, 128, 192, 256]:
        kv = layers * (context + registers) * 2 * kv_width * 2
        total = weight_bytes + tokenizer_bytes + kv + RESERVE
        results.append({"total_text_context_tokens": context, "register_tokens": registers,
                        "fp16_kv_bytes": kv, "weights_bytes": weight_bytes,
                        "tokenizer_bytes": tokenizer_bytes, "runtime_reserve_bytes": RESERVE,
                        "total_bytes": total, "remaining_bytes": CAPACITY - total,
                        "fits_arithmetically": total <= CAPACITY})
    return results


def main():
    directory = ROOT / ".build" / "brandon-chat-20261105" / "model"
    brandon = weights(directory / "model.safetensors", lambda name: not name.startswith("layers.") and name != "output.weight")
    proto = pb.ModelProto()
    proto.ParseFromString((directory / "tokenizer.model").read_bytes())
    assert len(proto.pieces) == 8192 and proto.trainer_spec.model_type == pb.TrainerSpec.BPE
    brandon["tokenizer_design"] = {
        "utf8_piece_pool_bytes": sum(len(piece.piece.encode("utf-8")) for piece in proto.pieces),
        "uint32_offsets_bytes": 4 * (len(proto.pieces) + 1),
        "uint16_sorted_piece_index_bytes": 2 * len(proto.pieces),
        "fp32_scores_bytes": 4 * len(proto.pieces), "uint8_types_bytes": len(proto.pieces),
        "normalization_table_bytes": len(proto.normalizer_spec.precompiled_charsmap),
        "metadata_bytes": 256,
        "lookup": "Binary search by piece bytes using a uint16 sorted index; scores/ranks remain indexed by token ID; scratch in reserve",
        "implemented": False}
    tok_bytes = sum(v for k, v in brandon["tokenizer_design"].items() if k.endswith("_bytes"))
    brandon["scenarios_q4_32"] = scenarios(brandon["q4_32_bytes"], tok_bytes, 24, 64, 4)
    brandon["scenarios_q4_64"] = scenarios(brandon["q4_64_bytes"], tok_bytes, 24, 64, 4)
    brandon["kv_note"] = "24 logical layers need separate KV caches even though only 12 weight blocks are unique"

    directory = ROOT / ".build" / "stentor-chat-20261105" / "model"
    stentor = weights(directory / "model.safetensors", lambda name: True)
    tokenizer = json.loads((directory / "tokenizer.json").read_text())
    vocab, merges = tokenizer["model"]["vocab"], tokenizer["model"]["merges"]
    assert len(vocab) <= 65536 and len(merges) <= 65536
    assert set(vocab.values()) == set(range(len(vocab)))
    for left, right in merges:
        assert left in vocab and right in vocab and left + right in vocab
    stentor["tokenizer_design"] = {
        "utf8_piece_pool_bytes": sum(len(piece.encode("utf-8")) for piece in vocab),
        "uint32_offsets_bytes": 4 * (len(vocab) + 1),
        "merge_rules_8_bytes": 8 * len(merges), "metadata_bytes": 256,
        "rule_layout": "uint16 left, right, output, rank; sorted by input pair for binary search",
        "implemented": False}
    tok_bytes = sum(v for k, v in stentor["tokenizer_design"].items() if k.endswith("_bytes"))
    stentor["scenarios_q4_32"] = scenarios(stentor["q4_32_bytes"], tok_bytes, 12, 192, 0)
    stentor["scenarios_q4_64"] = scenarios(stentor["q4_64_bytes"], tok_bytes, 12, 192, 0)
    for name, data in [("brandon", brandon), ("stentor", stentor)]:
        data.update({"psram_capacity_bytes": CAPACITY,
                     "status": "Design estimate; neither packed native runtime nor device performance verified",
                     "reserve": "PSRAM allowance for layer activations, DenseFormer current-token states, tokenization scratch, logits, headers and IO windows; not a measured runtime allocation",
                     "sram_note": "Firmware static SRAM, stack and heap are separate; native kernel SRAM usage must be measured",
                     "context_note": "Text context is the total prompt, previous turns and generated answer; registers add KV positions"})
        path = ROOT / "research" / f"{name}-chat-20261105" / "memory-budget.json"
        path.write_text(json.dumps(data, indent=2) + "\n")
        print(name, data["unique_parameters"], "Q4_32", data["q4_32_bytes"], "Q4_64", data["q4_64_bytes"])
        for scenario in data["scenarios_q4_32"]:
            print(scenario)


if __name__ == "__main__":
    main()
