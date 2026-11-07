#!/usr/bin/env python3
"""Refresh private act-token anchors after language training; preserve all ordinary rows."""
import argparse
from pathlib import Path
import shutil
from common import core, load_model, quantize
from prepare_tagged import WORDS
from rebalance import compact_tokenizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--seed', type=int, default=41592)
    parser.add_argument('--add-play-move', action='store_true')
    args = parser.parse_args()
    import torch
    model, tokenizer, device = load_model(args)
    output = Path(args.output);assert not output.exists()
    tags = dict(model.config.tinytalk_intent_token_ids)
    normal_ids = [i for i in range(len(tokenizer)) if i not in tags.values()]
    before = model.transformer.wte.weight.detach()[normal_ids].clone()
    if args.add_play_move and 'play_move' not in tags:
        token = '<|tt_intent:play_move|>'
        complete = [f'<|tt_intent:{kind}|>' for kind in tags] + [token]
        tokenizer.add_special_tokens({'additional_special_tokens': complete})
        model.resize_token_embeddings(len(tokenizer), mean_resizing=False)
        tags['play_move'] = tokenizer.convert_tokens_to_ids(token)
        model.config.tinytalk_intent_token_ids = tags
    embedding = model.transformer.wte.weight
    with torch.no_grad():
        for kind, token in tags.items():
            anchor = tokenizer.encode(' ' + WORDS[kind], add_special_tokens=False)
            embedding[token].copy_(quantize.dequantized(embedding[anchor]).mean(0))
    assert torch.equal(before, embedding.detach()[normal_ids])
    model.config.tinytalk_conversation_parent_sha256 = core.digest(Path(args.model) / 'model.safetensors')
    model.config.tinytalk_intent_anchors_refreshed = True
    output.mkdir(parents=True)
    model.save_pretrained(output, safe_serialization=True);tokenizer.save_pretrained(output);quantize.copy_notices(args.model, output)
    for token in tags.values():
        assert tokenizer.decode([token] + tokenizer.encode(' Hello!', add_special_tokens=False), skip_special_tokens=True).strip() == 'Hello!'
    extra = Path(args.model) / 'LANGUAGE_DATA.md'
    if extra.exists():shutil.copyfile(extra, output / extra.name)
    table = compact_tokenizer(tokenizer, output / 'tokenizer.ttbpe')
    core.save(output / 'refresh.json', {'parent_sha256': model.config.tinytalk_conversation_parent_sha256,
              'normal_embeddings_unchanged': True, 'tags_refreshed': len(tags), 'table_bytes': table['file_bytes']})


if __name__ == '__main__':
    main()
