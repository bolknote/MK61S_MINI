#!/usr/bin/env python3
"""Pin and tokenize TinyStories into compact document-disjoint language streams."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

REVISION = "f54c09fd23315a6f9c86f9dc80f725de7d8f9c64"
SHARDS = [
    ("data/train-00000-of-00004-2d5a1467fff1081b.parquet", "77cf780cebe52b6e83e3a2ac84bc56d8059363113e41d17a023f1d8b2ed0fc0b", 248731111),
    ("data/train-00001-of-00004-5852b56a2bd28fd9.parquet", "e2f173a6dcc2b5895183e8ad376e115bd5c06764eb0cfc01ce1add156b2d017f", 248171980),
]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="tagged-init")
    parser.add_argument("--output", default="language-data")
    parser.add_argument("--tokens", type=int, default=100000000)
    args = parser.parse_args()
    os.environ['TOKENIZERS_PARALLELISM'] = 'true';os.environ['RAYON_NUM_THREADS'] = '4'
    sys.path.insert(0, str(Path('pydeps').resolve()))
    import numpy as np
    import pyarrow.parquet as pq
    from transformers import AutoTokenizer
    root = Path(args.output);root.mkdir(parents=True, exist_ok=True)
    assert not (root / 'train.u16').exists()
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    tokenizer.model_max_length = 10 ** 9  # Storage stream; training windows are cut separately.
    assert len(tokenizer) < 65536
    counts = {'train': 0, 'validation': 0};docs = dict(counts)
    limits = {'train': args.tokens, 'validation': 200000}
    files = {name: (root / (name + '.u16')).open('wb') for name in counts}
    sources = [];started = time.monotonic();seen_docs = 0
    try:
        for filename, expected, size in SHARDS:
            raw = root / Path(filename).name
            url = f'https://huggingface.co/datasets/roneneldan/TinyStories/resolve/{REVISION}/{filename}'
            if not raw.exists():
                print(json.dumps({'phase': 'download', 'url': url, 'bytes': size}), flush=True)
                temporary = raw.with_suffix('.partial')
                with urllib.request.urlopen(url, timeout=180) as response, temporary.open('wb') as stream:
                    for chunk in iter(lambda: response.read(4 * 1024 * 1024), b''):stream.write(chunk)
                assert temporary.stat().st_size == size and sha(temporary) == expected
                temporary.rename(raw)
            assert raw.stat().st_size == size and sha(raw) == expected
            sources.append({'url': url, 'sha256': expected, 'bytes': size})
            for batch in pq.ParquetFile(raw).iter_batches(batch_size=256, columns=['text']):
                texts = [text for text in batch.column(0).to_pylist() if isinstance(text, str) and text.strip()]
                encoded = tokenizer(texts, add_special_tokens=False)['input_ids']
                for text, tokens in zip(texts, encoded):
                    seen_docs += 1
                    name = 'validation' if int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) % 100 == 0 else 'train'
                    if counts[name] >= limits[name]:continue
                    tokens = (tokens + [tokenizer.eos_token_id])[:limits[name] - counts[name]]
                    files[name].write(np.asarray(tokens, dtype='<u2').tobytes())
                    counts[name] += len(tokens);docs[name] += 1
                if seen_docs % (256 * 128) == 0:
                    print(json.dumps({'phase': 'tokenize', 'documents': seen_docs, 'tokens': counts,
                                      'seconds': round(time.monotonic() - started, 1)}), flush=True)
                if all(counts[name] >= limits[name] for name in counts):break
            if all(counts[name] >= limits[name] for name in counts):break
    finally:
        for stream in files.values():stream.close()
    assert counts['train'] >= args.tokens and counts['validation'] == limits['validation']
    report = {'dataset': 'roneneldan/TinyStories', 'revision': REVISION, 'license': 'cdla-sharing-1.0',
              'sources': sources, 'tokens': counts, 'documents': docs,
              'split': 'Document SHA256 modulo 100; 1% validation; identical stories always share a split',
              'dtype': 'little-endian uint16', 'eos_token_id': tokenizer.eos_token_id, 'vocab_size': len(tokenizer),
              'tokenizer_sha256': sha(Path(args.model) / 'tokenizer.json'),
              'files': {name: {'bytes': (root / (name + '.u16')).stat().st_size,
                               'sha256': sha(root / (name + '.u16'))} for name in counts},
              'seconds': time.monotonic() - started, 'conversation_audit_opened': False}
    (root / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
