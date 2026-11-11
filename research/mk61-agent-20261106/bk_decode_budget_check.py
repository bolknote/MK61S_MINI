"""Regression: a long unrelated prompt cannot truncate a short valid answer."""
from types import SimpleNamespace
import torch
from transformers import AutoTokenizer
import aq_eval
from aq_common import ACTION_IDS, END
from bj_common import SOURCES
from bk_independent_generate import generate


class Backbone(torch.nn.Module):
    def forward(self, input_ids, **kwargs):
        return SimpleNamespace(last_hidden_state=torch.ones((*input_ids.shape, 1)))


class Scripted(torch.nn.Module):
    def __init__(self, answer):
        super().__init__(); self.embedding = torch.nn.Embedding(8224, 1)
        self.embedding.weight.data.zero_(); self.embedding.weight.data[ACTION_IDS[0]] = 1
        self.model = Backbone(); self.answer = answer

    def get_input_embeddings(self):
        return self.embedding

    def generate(self, input_ids, max_new_tokens, **kwargs):
        tail = torch.tensor(self.answer[:max_new_tokens]).expand(len(input_ids), -1)
        return torch.cat([input_ids, tail], dim=1)


def main():
    tokenizer = AutoTokenizer.from_pretrained(SOURCES['full'] / 'hf', local_files_only=True)
    body = tokenizer.encode('FF 22 00', add_special_tokens=False)
    model = Scripted(body + [END])
    saved = aq_eval.prompt_ids
    try:
        aq_eval.prompt_ids = lambda tokenizer, text: [1] * (12 if text == 'short<' else 1015)
        old = aq_eval.generate(model, tokenizer, ['short<', 'long<'])
        new = generate(model, tokenizer, ['short<', 'long<'])
        assert old[0]['codec_error'] == old[1]['codec_error'] == 'incomplete'
        assert new[0]['codec_error'] is None and new[0]['body'] == [255, 34, 0]
        assert new[1]['codec_error'] == 'incomplete'
        assert generate(model, tokenizer, ['short<'])[0]['generated_token_ids'] == new[0]['generated_token_ids']
    finally:
        aq_eval.prompt_ids = saved
    print('PASS: reproduced batch truncation; short valid output survives unrelated long prompt; genuine long overflow remains')


if __name__ == '__main__':
    torch.set_num_threads(2); main()
