"""Download an immutable public Safetensors checkpoint; never execute model code."""
import hashlib
import json
import math
from pathlib import Path
import struct
import urllib.request

MODEL = "akanemind/Flourish-3M"
DEST = Path(__file__).resolve().parents[2] / ".build/mk61-agent-20261106/flourish-original"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen("https://huggingface.co/api/models/" + MODEL, timeout=30) as response:
        meta = json.load(response)
    revision = meta["sha"]
    files = [f["rfilename"] for f in meta["siblings"]]
    kept = []
    allowed = {"config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json",
               "special_tokens_map.json", "vocab.json", "merges.txt", "model.safetensors", "README.md"}
    for name in files:
        if name not in allowed:
            continue
        target = DEST / name
        url = f"https://huggingface.co/{MODEL}/resolve/{revision}/{name}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        target.write_bytes(data)
        kept.append({"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        print(name, len(data), flush=True)
    origin = {"model": MODEL, "revision": revision, "files": kept, "remote_code_executed": False}
    (DEST / "origin.json").write_text(json.dumps(origin, indent=2) + "\n")
    config = json.loads((DEST / "config.json").read_text())
    with (DEST / "model.safetensors").open("rb") as stream:
        length = struct.unpack("<Q", stream.read(8))[0]
        header = json.loads(stream.read(length))
    count = sum(math.prod(v["shape"]) for k, v in header.items() if k != "__metadata__")
    print(json.dumps({"origin": origin, "config": config, "stored_parameters": count}, indent=2))


if __name__ == "__main__":
    main()
