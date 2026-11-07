#!/usr/bin/env python3
"""Pack TinyTalk into a documented Q4 container and verify exact reload.

The file is an experimental weights format, not firmware or a ready PicoCalc app.
Each row is padded to 32 weights; blocks store FP16 scale + 16 nibble bytes.
The two halves of 32 codes occupy the low/high nibbles respectively.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

MAGIC = b"TTQ4v1\0\0"


def copy_notices(source, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ["NOTICE.md", "LICENSE"]:
        path = Path(source) / name
        if path.is_file() and path.resolve() != (destination / name).resolve():
            shutil.copyfile(path, destination / name)


def blocks(weight):
    import torch
    rows, columns = weight.shape
    padded = (columns + 31) // 32 * 32
    values = torch.nn.functional.pad(weight, (0, padded - columns)).reshape(-1, 32)
    extreme = values.gather(1, values.abs().argmax(1, keepdim=True))
    scale = (extreme / -8).half()
    inverse = torch.where(scale != 0, scale.float().reciprocal(), 0)
    codes = torch.floor(values * inverse + 8.5).clamp(0, 15).to(torch.uint8)
    return scale, codes, padded


def dequantized(weight):
    scale, codes, padded = blocks(weight)
    return ((codes.float() - 8) * scale.float()).reshape(weight.shape[0], padded)[:, :weight.shape[1]]


def roundtrip(model):
    import torch
    total, matrices = 0, []
    with torch.no_grad():
        for name, parameter in model.named_parameters():
            if parameter.ndim != 2:
                total += parameter.numel() * 4
                continue
            restored = dequantized(parameter)
            size = parameter.shape[0] * ((parameter.shape[1] + 31) // 32) * 18
            matrices.append({"name": name, "bytes": size,
                             "rmse": float((parameter - restored).square().mean().sqrt())})
            parameter.copy_(restored)
            total += size
    return {"format": "TTQ4v1; 32 weights per FP16-scaled block; vectors FP32",
            "packed_weight_bytes": total, "matrices": matrices,
            "execution": "Dequantized host arithmetic; native device runtime not implemented"}


def export(model, path, origin):
    import numpy as np
    parts, tensors = [], []
    offset = 0
    for name, parameter in model.named_parameters():
        value = parameter.detach().float().cpu()
        entry = {"name": name, "shape": list(value.shape), "offset": offset}
        if value.ndim == 2:
            scales, codes, padded = blocks(value)
            packed = (codes[:, :16] | (codes[:, 16:] << 4)).numpy()
            scale_bytes = scales.numpy().astype("<f2").view(np.uint8).reshape(-1, 2)
            raw = np.concatenate([scale_bytes, packed], axis=1).tobytes()
            entry.update(format="q4_32", padded_columns=padded)
        else:
            raw = value.numpy().astype("<f4").tobytes()
            entry.update(format="fp32")
        entry["bytes"] = len(raw)
        parts.append(raw); tensors.append(entry); offset += len(raw)
    manifest = {"format": "TTQ4v1", "origin": origin,
                "parameters": sum(p.numel() for p in model.parameters()),
                "config": json.loads(model.config.to_json_string()),
                "tied_output": model.config.tie_word_embeddings,
                "payload_bytes": offset, "tensors": tensors,
                "layout": "magic[8], little-endian u32 JSON length, UTF8 JSON, pad to 16, tensor payload",
                "block": "little-endian fp16 d; 16 bytes q[j] | q[j+16]<<4; value=d*(q-8)"}
    header = json.dumps(manifest, separators=(",", ":")).encode()
    beginning = MAGIC + struct.pack("<I", len(header)) + header
    beginning += bytes((-len(beginning)) % 16)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(beginning)
        for part in parts:
            stream.write(part)
    return manifest | {"file_bytes": path.stat().st_size,
                       "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "header_bytes": len(beginning)}


def restore(model, path):
    import numpy as np
    import torch
    data = Path(path).read_bytes()
    assert data[:8] == MAGIC
    length = struct.unpack_from("<I", data, 8)[0]
    manifest = json.loads(data[12:12 + length])
    start = (12 + length + 15) // 16 * 16
    assert start + manifest["payload_bytes"] == len(data)
    parameters = dict(model.named_parameters())
    assert set(parameters) == {item["name"] for item in manifest["tensors"]}
    with torch.no_grad():
        for item in manifest["tensors"]:
            raw = memoryview(data)[start + item["offset"]:start + item["offset"] + item["bytes"]]
            if item["format"] == "q4_32":
                packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 18)
                scales = packed[:, :2].copy().reshape(-1).view("<f2").astype(np.float32).reshape(-1, 1)
                nibbles = np.concatenate([packed[:, 2:] & 15, packed[:, 2:] >> 4], axis=1).astype(np.float32)
                value = ((nibbles - 8) * scales).reshape(item["shape"][0], item["padded_columns"])[:, :item["shape"][1]]
            else:
                value = np.frombuffer(raw, dtype="<f4").reshape(item["shape"])
            parameters[item["name"]].copy_(torch.from_numpy(value.copy()).to(parameters[item["name"]].device))
    return manifest


def qat_modules(model):
    """STE on matrix weights; tied embedding/head keep one original Parameter."""
    import torch
    from torch.nn.utils import parametrize

    class FakeQ4(torch.nn.Module):
        def forward(self, weight):
            with torch.no_grad():
                quantized = dequantized(weight)
            return weight + (quantized - weight).detach()

    selected = []
    for module in model.modules():
        if isinstance(module, (torch.nn.Linear, torch.nn.Embedding)):
            selected.append(module)
    for module in selected:
        parametrize.register_parametrization(module, "weight", FakeQ4())
    assert sum(p.numel() for p in model.parameters()) == 8278400
    return selected, FakeQ4


def save_qat_checkpoint(model, path, qat_state):
    """Temporarily expose the same full-precision Parameters for stock HF saving."""
    from torch.nn.utils import parametrize
    modules, fake_type = qat_state
    before = {id(p) for p in model.parameters()}
    for module in modules:
        parametrize.remove_parametrizations(module, "weight", leave_parametrized=False)
    model.save_pretrained(path, safe_serialization=True)
    for module in modules:
        parametrize.register_parametrization(module, "weight", fake_type())
    assert {id(p) for p in model.parameters()} == before


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=".build/tinytalk-chat-20261105/model")
    parser.add_argument("--output", default=".build/tinytalk-train-20261105/quantized-original/model.ttq4")
    parser.add_argument("--report", default="research/tinytalk-train-20261105/quantized-original.json")
    args = parser.parse_args()
    import torch
    from transformers import AutoModelForCausalLM
    torch.set_num_threads(4)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32, local_files_only=True,
                                                trust_remote_code=False, attn_implementation="eager").eval().requires_grad_(False)
    origin = {"model": "TheREZOR/TinyTalk", "revision": "61c79ad139344cdd344a687b35fa8f1c52326154",
              "source_sha256": hashlib.sha256((Path(args.model) / "model.safetensors").read_bytes()).hexdigest()}
    manifest = export(model, args.output, origin)
    copy_notices(args.model, Path(args.output).parent)
    roundtrip(model)
    reference = {name: value.detach().clone() for name, value in model.named_parameters()}
    restore(model, args.output)
    error = max(float((reference[name] - value).abs().max()) for name, value in model.named_parameters())
    assert error == 0
    manifest.update(roundtrip_max_abs_error=error, packed_reload_verified=True,
                    native_device_runtime_implemented=False)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ["parameters", "payload_bytes", "header_bytes", "file_bytes", "file_sha256", "packed_reload_verified"]}), flush=True)


if __name__ == "__main__":
    main()
