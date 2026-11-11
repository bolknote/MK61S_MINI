"""Require exact continuation on the actual B200 backend before any SGD."""
import torch
from transformers import AutoModelForCausalLM
from bl_common import ROOT, PARENT, SOURCES, write, read, sha
from bl_model import agent
from native_export import packet


def main():
    out = {}
    for arm in ['lora', 'full']:
        checkpoint = PARENT / arm / 'last.safetensors'
        assert sha(checkpoint) == read(SOURCES[arm] / 'manifest.json')['selected_checkpoint_sha256']
        model = agent(arm, 'cuda', checkpoint)
        replica, _ = model.packed(ROOT / ('B200-preflight-' + arm + '.mkqb'))
        assert packet(ROOT / ('B200-preflight-' + arm + '.mkqb'))[1] == packet(SOURCES[arm] / 'model.mkqb')[1]
        master = model.merged_master()
        reference = AutoModelForCausalLM.from_pretrained(SOURCES[arm] / 'hf', local_files_only=True).float()
        assert all(torch.equal(p, dict(reference.named_parameters())[n]) for n, p in master.named_parameters())
        out[arm] = {'B200_master_exact': True, 'B200_Q4_exact': True, 'trainable': model.trainable_count(), 'optimizer_updates': 0}
        del model, replica, master, reference
    write(ROOT / 'parent-b200-preflight.json', out)
    print(out, flush=True)


if __name__ == '__main__':
    torch.set_num_threads(4); torch.backends.cuda.matmul.allow_tf32 = False; main()
