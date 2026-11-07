#!/usr/bin/env python3
"""Mine the current Q4 student's bad replies and pair them with acceptable corrections."""
import argparse
import json
from pathlib import Path
import random

from common import core, decode, quantize, logps, load_model
from grade import grade


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="/previous")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=68021)
    parser.add_argument("--data", default="data")
    parser.add_argument("--output", default="pairs")
    parser.add_argument("--limit", type=int, default=4000)
    parser.add_argument("--natural-only", action="store_true")
    parser.add_argument("--min-pairs", type=int, default=200)
    args = parser.parse_args()
    import torch
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    model, tokenizer, device = load_model(args)
    model.eval().requires_grad_(False); quantize.roundtrip(model)
    source = [row for row in core.read_rows(Path(args.data) / "train.jsonl") if row["kind"] != "replay"]
    context = getattr(model.config, 'tinytalk_runtime_context', 256)
    if args.natural_only:
        source = [row for row in source if row.get('source') not in ['variable_value_skill_curriculum',
            'consistent_variable_curriculum','compositional_semantic_curriculum','on_policy_curriculum','authored_curriculum']]
    source = [row for row in source if len(tokenizer.encode(core.render(row["messages"]), add_special_tokens=False)) + 40 <= context]
    rng=random.Random(args.seed);rng.shuffle(source)
    groups={kind:[row for row in source if row['kind']==kind]for kind in sorted({row['kind']for row in source})}
    source=[]
    while len(source)<args.limit and any(groups.values()):
        for kind in groups:
            if groups[kind]and len(source)<args.limit:source.append(groups[kind].pop())
    accepted = []
    for start in range(0, len(source), 64):
        rows = source[start:start + 64]
        negatives = decode(model, tokenizer, rows, device, batch_size=32)
        items, responses = [], []
        for row, negative in zip(rows, negatives):
            items.extend([dict(row, id=row["id"] + ":gold"), dict(row, id=row["id"] + ":bad")])
            responses.extend([row.get('plain_target',row["target"]), negative["reply"]])
        assessment = grade(items, responses, root / "grade-cache", workers=12)
        for index, (row, negative) in enumerate(zip(rows, negatives)):
            good_grade, bad_grade = assessment["details"][2*index:2*index+2]
            if not good_grade["pass"] or bad_grade["pass"] or row["target"].strip().lower() == negative["reply"].strip().lower():
                continue
            if not negative['ended_with_eos'] or not negative['reply']:continue
            generated=negative['raw_token_ids']
            assert generated[-1]==tokenizer.eos_token_id
            rejected_text=tokenizer.decode(generated[:-1],skip_special_tokens=False).strip()
            chosen, _ = core.encode_rows(tokenizer, [row], context)
            rejected, _ = core.encode_rows(tokenizer, [dict(row, target=rejected_text)], context)
            if not chosen or not rejected:continue
            prefix=tokenizer.encode(core.render(row['messages']),add_special_tokens=False)
            if rejected[0][0][len(prefix):]!=generated:continue
            with torch.inference_mode():
                a, _, _, _ = logps(model, chosen, tokenizer, device)
                b, _, _, _ = logps(model, rejected, tokenizer, device)
            accepted.append({**row, "chosen": row["target"], "rejected": rejected_text,
                             "reference_chosen_logp": float(a[0]), "reference_rejected_logp": float(b[0]),
                             "chosen_grade": good_grade, "rejected_grade": bad_grade})
        core.save(root / "progress.json", {"processed": min(start + 64, len(source)), "total": len(source), "pairs": len(accepted)})
        print(json.dumps({"processed": min(start + 64, len(source)), "total": len(source), "pairs": len(accepted)}), flush=True)
    path = root / "train.jsonl";path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in accepted))
    core.save(root / "manifest.json", {"pairs": len(accepted), "sha256": core.digest(path),
                                       "reference_checkpoint_sha256": core.digest(Path(args.model) / "model.safetensors"),
                                       "source_train_sha256": core.digest(Path(args.data)/'train.jsonl'),"settings":vars(args),
                                       "runtime_context":context,"reference_precision": "Q4 quantize/dequantize, FP32 inference", "training_data_only": True})
    if len(accepted) < args.min_pairs:
        raise ValueError("Too few useful preference pairs")


if __name__ == "__main__":
    main()
