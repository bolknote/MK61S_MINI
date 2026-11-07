#!/usr/bin/env python3
"""Activate unused attention directions while preserving the existing Q4 function.

The Net2Net expansion duplicated adjacent Q/K/V rows and output columns. If both
members of each attention product stay duplicated, training preserves the symmetry.
Give Q and V antisymmetric, exactly Q4-representable components. Their contribution
cancels against the still-symmetric K and output matrices, but K/output gradients
can now learn in the extra directions. No evaluation prompts are used here.
"""
import argparse
import json
from pathlib import Path
import shutil
from common import core, load_model, quantize, logps, qat_modules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--data', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--control-output', help='Save the same dequantized baseline before activation for a matched control')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--seed', type=int, default=617281)
    args = parser.parse_args()
    import torch
    model, tokenizer, device = load_model(args)
    model.eval();quantize.roundtrip(model)
    assert model.config.hidden_size == 256
    if args.control_output:
        control = Path(args.control_output);assert not control.exists()
        model.save_pretrained(control, safe_serialization=True);tokenizer.save_pretrained(control);quantize.copy_notices(args.model, control)
        for name in ['LANGUAGE_DATA.md', 'tokenizer.ttbpe']:
            source = Path(args.model) / name
            if source.exists():shutil.copyfile(source, control / name)
    source_rows = core.read_rows(Path(args.data) / 'train.jsonl')
    rows, _ = core.encode_rows(tokenizer, source_rows[:64], 128)
    rows = rows[:8]
    ids, _, mask = core.batch(rows, tokenizer.eos_token_id, device)
    with torch.no_grad():before = model(input_ids=ids, attention_mask=mask, use_cache=False).logits
    changes = {}
    with torch.no_grad():
        for layer, block in enumerate(model.transformer.h):
            attention = block.attn.attention
            for module in [attention.q_proj, attention.k_proj, attention.v_proj]:
                assert torch.equal(module.weight[::2], module.weight[1::2])
            assert torch.equal(attention.out_proj.weight[:, ::2], attention.out_proj.weight[:, 1::2])
            for name in ['q_proj', 'v_proj']:
                weight = getattr(attention, name).weight
                scale, codes, padded = quantize.blocks(weight[::2].contiguous())
                assert padded == weight.shape[1]
                signed = codes.long() - 8
                delta = (torch.randint(0, 2, signed.shape, device=device) * 2 - 1) * 2
                delta[(signed < -5) | (signed > 4)] = 0
                even = ((signed + delta).float() * scale.float()).reshape_as(weight[::2])
                odd = ((signed - delta).float() * scale.float()).reshape_as(weight[1::2])
                old = weight.clone()
                weight[::2].copy_(even);weight[1::2].copy_(odd)
                assert torch.equal(weight[::2] + weight[1::2], old[::2] + old[1::2])
                assert torch.equal(quantize.dequantized(weight), weight)
                changes[f'layer{layer}.{name}'] = {'antisymmetric_relative_norm': float((even - odd).norm() / weight.norm()),
                                                 'changed_elements': int((weight != old).sum())}
        after = model(input_ids=ids, attention_mask=mask, use_cache=False).logits
    selected = mask.bool().unsqueeze(-1).expand_as(before)
    error = float((before - after).abs()[selected].max())
    argmax_equal = torch.equal(before.argmax(-1)[mask.bool()], after.argmax(-1)[mask.bool()])
    assert error < .001 and argmax_equal, (error, argmax_equal)
    # Verify that the formerly redundant key and output directions get gradients.
    qat = qat_modules(model)
    _, loss, _, _ = logps(model, rows, tokenizer, device)
    loss.backward()
    gradients = {}
    for layer, block in enumerate(model.transformer.h):
        a = block.attn.attention
        k = a.k_proj.parametrizations.weight.original.grad
        out = a.out_proj.parametrizations.weight.original.grad
        gradients[str(layer)] = {'key_antisymmetric_gradient_norm': float((k[::2] - k[1::2]).norm()),
                                 'output_antisymmetric_gradient_norm': float((out[:, ::2] - out[:, 1::2]).norm())}
        assert gradients[str(layer)]['key_antisymmetric_gradient_norm'] > 0
        assert gradients[str(layer)]['output_antisymmetric_gradient_norm'] > 0
    output = Path(args.output);assert not output.exists();output.mkdir(parents=True)
    model.config.tinytalk_attention_capacity_activation = 'Q/V antisymmetric Q4 integer perturbations; K/output initially symmetric; original Q4 function preserved'
    quantize.save_qat_checkpoint(model, output, qat);tokenizer.save_pretrained(output);quantize.copy_notices(args.model, output)
    for name in ['LANGUAGE_DATA.md', 'tokenizer.ttbpe']:
        source = Path(args.model) / name
        if source.exists():shutil.copyfile(source, output / name)
    report = {'source_sha256': core.digest(Path(args.model) / 'model.safetensors'),
              'output_sha256': core.digest(output / 'model.safetensors'), 'parameters': sum(p.numel() for p in model.parameters()),
              'q4_function_max_abs_logit_error': error, 'training_argmax_unchanged': argmax_equal,
              'changes': changes, 'gradients': gradients, 'reserved_prompts_used': False}
    core.save(output / 'capacity-activation.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':main()
