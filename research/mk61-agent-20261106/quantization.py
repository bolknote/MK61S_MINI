"""Actual signed Q4 packing and checked reload, with FP16 per-32 scales."""
import json
import math
from pathlib import Path
import struct

import torch

MAGIC = b"MKQ4v1\0\0"


def quantize_matrix(weight):
    assert weight.ndim == 2 and weight.shape[-1] % 32 == 0
    groups = weight.float().reshape(weight.shape[0], -1, 32)
    scales = (groups.abs().amax(dim=-1, keepdim=True) / 7).clamp_min(2 ** -24).to(torch.float16).float()
    codes = torch.round(groups / scales).clamp(-7, 7)
    return codes, scales


def fake_q4(weight):
    codes, scales = quantize_matrix(weight)
    rounded = (codes * scales).reshape_as(weight).to(weight.dtype)
    return weight + (rounded - weight).detach()


@torch.no_grad()
def round_model(model):
    for parameter in model.parameters():
        if parameter.ndim == 2:
            codes, scales = quantize_matrix(parameter)
            parameter.copy_((codes * scales).reshape_as(parameter))


@torch.no_grad()
def export_q4(model, path):
    path = Path(path)
    chunks, tensors = [], []
    offset = 0
    for name, parameter in model.named_parameters():
        value = parameter.detach().cpu().float().contiguous()
        if value.ndim == 2:
            codes, scales = quantize_matrix(value)
            unsigned = (codes.reshape(-1).to(torch.int16) + 8).to(torch.uint8)
            assert unsigned.numel() % 2 == 0
            data = (unsigned[0::2] | (unsigned[1::2] << 4)).numpy().tobytes()
            scale_data = scales.to(torch.float16).contiguous().numpy().tobytes()
            chunk = data + scale_data
            record = {"name": name, "shape": list(value.shape), "format": "q4_group32", "codes_bytes": len(data)}
        else:
            chunk = value.numpy().tobytes()
            record = {"name": name, "shape": list(value.shape), "format": "fp32"}
        record.update(offset=offset, bytes=len(chunk))
        tensors.append(record)
        chunks.append(chunk)
        offset += len(chunk)
    header = json.dumps({"format": "MKQ4v1", "endianness": "little", "config": model.config.to_dict(), "tensors": tensors},
                        ensure_ascii=True, separators=(",", ":")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(MAGIC)
        stream.write(struct.pack("<I", len(header)))
        stream.write(header)
        for chunk in chunks:
            stream.write(chunk)
    return {"file": str(path), "bytes": path.stat().st_size, "payload_bytes": offset,
            "parameters": sum(x.numel() for x in model.parameters()), "tensors": len(tensors)}


@torch.no_grad()
def load_q4(model, path):
    import numpy as np
    data = Path(path).read_bytes()
    if data[:8] != MAGIC:
        raise ValueError("Invalid MKQ4v1 header")
    header_length = struct.unpack("<I", data[8:12])[0]
    header = json.loads(data[12:12 + header_length])
    payload = memoryview(data)[12 + header_length:]
    loaded = set()
    for tensor in header["tensors"]:
        name, shape = tensor["name"], tensor["shape"]
        parameter = model.get_parameter(name)
        if list(parameter.shape) != shape or tensor["offset"] + tensor["bytes"] > len(payload):
            raise ValueError("Invalid Q4 tensor shape or extent")
        chunk = payload[tensor["offset"]:tensor["offset"] + tensor["bytes"]]
        if tensor["format"] == "fp32":
            value = torch.from_numpy(np.frombuffer(chunk, dtype="<f4").copy()).reshape(shape)
        else:
            packed = np.frombuffer(chunk[:tensor["codes_bytes"]], dtype=np.uint8)
            unpacked = np.empty(packed.size * 2, dtype=np.int16)
            unpacked[0::2] = packed & 15
            unpacked[1::2] = packed >> 4
            codes = torch.from_numpy(unpacked - 8).float().reshape(shape[0], -1, 32)
            scales = torch.from_numpy(np.frombuffer(chunk[tensor["codes_bytes"]:], dtype="<f2").copy()).float().reshape(shape[0], -1, 1)
            value = (codes * scales).reshape(shape)
        parameter.copy_(value.to(parameter.device, parameter.dtype))
        loaded.add(name)
    if loaded != {name for name, _ in model.named_parameters()}:
        raise ValueError("Q4 tensor coverage is incomplete")
    return header
