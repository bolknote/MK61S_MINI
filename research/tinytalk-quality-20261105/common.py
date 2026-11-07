"""Reuse the previously verified TinyTalk loader, tokenizer, Q4 layout and renderer."""
from pathlib import Path
import sys

try:
    import legacy_train as legacy
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tinytalk-conversation-20261105"))
    import train_chat as legacy

core = legacy.core
quantize = legacy.quantize
actual_q4 = legacy.actual_q4
nll = legacy.nll


def load_model(args, model_dir=None):
    """Load either verified TinyTalk size without mutating the legacy loader."""
    import torch
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(4)
    torch.manual_seed(args.seed)
    path = Path(model_dir or args.model)
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    config=AutoConfig.from_pretrained(path,local_files_only=True,trust_remote_code=False)
    if getattr(config,'tinytalk_control_input_rows',0):
        from safetensors.torch import load_file
        from control_embeddings import install
        model=AutoModelForCausalLM.from_config(config,trust_remote_code=False,attn_implementation='eager')
        install(model)
        state=load_file(str(path/'model.safetensors'),device='cpu')
        assert 'transformer.wte.weight'in state and 'transformer.wte.control_flat'in state
        loaded=model.load_state_dict(state,strict=False)
        assert not loaded.unexpected_keys and set(loaded.missing_keys)<= {'lm_head.weight'}
        del state
    else:
        model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, trust_remote_code=False,
                                                  dtype=torch.float32, attn_implementation="eager")
    config = model.config
    hidden = config.hidden_size; width = config.intermediate_size or hidden * 4
    assert config.num_layers == 8 and config.num_heads == 16
    if hidden == 128:
        assert config.vocab_size == 50257 and config.max_position_embeddings == 2048 and width in (512, 1536)
    else:
        assert hidden == 256 and 16385 <= config.vocab_size < 16449
        assert config.max_position_embeddings == 256 and width in (1024, 1280)
        assert config.tinytalk_runtime_context == 128
    expected = config.vocab_size * hidden + config.max_position_embeddings * hidden + 8 * (4 * hidden ** 2 + 2 * hidden * width + width + 6 * hidden) + 2 * hidden
    expected+=getattr(config,'tinytalk_control_input_rows',0)*hidden
    assert sum(p.numel() for p in model.parameters()) == expected
    assert model.lm_head.weight is model.transformer.wte.weight
    assert len(tokenizer) == config.vocab_size and tokenizer.eos_token_id == config.eos_token_id
    device = "cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu" if args.device == "auto" else args.device
    return model.to(device), tokenizer, device


def qat_modules(model, cuda_graphs=False):
    """Use the same block quantizer for either size and preserve tied Parameters."""
    import torch
    from torch.nn.utils import parametrize
    identities = {id(p) for p in model.parameters()}
    class FakeQ4(torch.nn.Module):
        def __init__(self):
            super().__init__()
            if cuda_graphs:
                from q4_graph import CudaQ4
                self.quantizer=CudaQ4(quantize.dequantized)
            else:self.quantizer=quantize.dequantized
        def forward(self, weight):
            with torch.no_grad():
                quantized = self.quantizer(weight)
            return weight + (quantized - weight).detach()
    modules = [module for module in model.modules() if isinstance(module, (torch.nn.Linear, torch.nn.Embedding))]
    for module in modules:
        parametrize.register_parametrization(module, "weight", FakeQ4())
    assert identities == {id(p) for p in model.parameters()}
    assert model.lm_head.parametrizations.weight.original is model.transformer.wte.parametrizations.weight.original
    return modules, FakeQ4


def fp16_cache_factory(model):
    """Store KV in actual FP16; read FP32 for the verified host attention path."""
    import torch
    from transformers.cache_utils import Cache, DynamicLayer
    class HalfKVLayer(DynamicLayer):
        def update(self, key_states, value_states, *extra, **kwargs):
            keys, values = super().update(key_states.half(), value_states.half(), *extra, **kwargs)
            assert self.keys.dtype == self.values.dtype == torch.float16
            return keys.float(), values.float()
    return lambda: Cache(layers=[HalfKVLayer() for _ in range(model.config.num_layers)])


def control_format_processor(model, tokenizer, prompt_length):
    """Constrain private wire tokens; all semantic choices still come from logits."""
    import torch
    intents=list(getattr(model.config,'tinytalk_intent_token_ids',{}).values())
    types=list(getattr(model.config,'tinytalk_answer_type_token_ids',{}).values())
    emit_intent=getattr(model.config,'tinytalk_emit_intent_token',True)
    separator=tokenizer.encode(' ',add_special_tokens=False)
    repeat=getattr(model.config,'tinytalk_no_repeat_ngram_size',0)
    say=getattr(model.config,'tinytalk_answer_focus_separator_id',None)
    focus_limit=getattr(model.config,'tinytalk_answer_focus_max_tokens',10)
    assert intents and (emit_intent or types)
    headers=([intents] if emit_intent else [])+([types] if types else [])
    class ControlFormat:
        def __call__(self,input_ids,scores):
            generated=input_ids.shape[1]-prompt_length
            allowed=None
            if generated<len(separator):allowed=[separator[generated]]
            elif generated-len(separator)<len(headers):allowed=headers[generated-len(separator)]
            if allowed is not None:
                filtered=torch.full_like(scores,-float('inf'));filtered[:,allowed]=scores[:,allowed]
                return filtered
            scores[:,intents+types]=-float('inf')
            # Only prevent repetitions in the generated spoken body. Never ban
            # repeating a fact or name merely because it appeared in the prompt.
            begin=prompt_length+len(separator)+len(headers)
            for row,body in enumerate(input_ids[:,begin:].tolist()):
                if say is not None:
                    if say not in body:
                        # The network supplies answer keywords. The only forced
                        # choice is the boundary after the declared length limit.
                        scores[row,tokenizer.eos_token_id]=-float('inf')
                        if len(body)>=focus_limit:
                            value=scores[row,say].clone();scores[row,:]=-float('inf');scores[row,say]=value
                            continue
                        if not body:scores[row,say]=-float('inf')
                    else:
                        body=body[body.index(say)+1:]
                        scores[row,say]=-float('inf')
                if repeat:
                    if len(body)<repeat-1:continue
                    prefix=body[-(repeat-1):]
                    for at in range(len(body)-repeat+1):
                        if body[at:at+repeat-1]==prefix:scores[row,body[at+repeat-1]]=-float('inf')
            return scores
    return ControlFormat()


def decode(model, tokenizer, cases, device, temperature=0, seed=7731, batch_size=8, cache_factory=None):
    import inspect
    import torch
    context = getattr(model.config, "tinytalk_runtime_context", 256)
    projected = []
    omissions = []
    for case in cases:
        messages = [dict(message) for message in case["messages"]]
        omitted = 0
        while len(tokenizer.encode(core.render(messages), add_special_tokens=False)) + 40 > context:
            if len(messages) < 3:raise ValueError("Current question does not fit the model's context")
            del messages[:2];omitted += 1
        projected.append(dict(case, messages=messages));omissions.append(omitted)
    torch.manual_seed(seed)
    tokenizer.padding_side = "left"
    replies = []
    intents = {token: kind for kind, token in getattr(model.config, "tinytalk_intent_token_ids", {}).items()}
    structured = getattr(model.config, "tinytalk_structured_intent_decoding", False)
    answer_types={token:kind for kind,token in getattr(model.config,'tinytalk_answer_type_token_ids',{}).items()}
    try:
        with torch.inference_mode():
            for start in range(0, len(projected), batch_size):
                group = projected[start:start + batch_size]
                encoded = tokenizer([core.render(row["messages"]) for row in group], padding=True,
                                    add_special_tokens=False, return_tensors="pt").to(device)
                assert encoded.input_ids.shape[1] + 40 <= context
                options = {"max_new_tokens": 40, "do_sample": temperature > 0, "use_cache": True,
                           "pad_token_id": tokenizer.eos_token_id, "eos_token_id": tokenizer.eos_token_id}
                if cache_factory is not None:
                    options['past_key_values'] = cache_factory()
                if temperature > 0:options.update(temperature=temperature, top_p=0.9, top_k=40)
                if structured:
                    assert intents
                    options["logits_processor"] = [control_format_processor(model,tokenizer,encoded.input_ids.shape[1])]
                if "logits_to_keep" in inspect.signature(model.forward).parameters:options["logits_to_keep"] = 1
                outputs = model.generate(**encoded, **options)[:, encoded.input_ids.shape[1]:]
                for at, (case, tokens) in enumerate(zip(group, outputs.tolist())):
                    ended = tokenizer.eos_token_id in tokens
                    if ended:tokens = tokens[:tokens.index(tokenizer.eos_token_id) + 1]
                    say=getattr(model.config,'tinytalk_answer_focus_separator_id',None)
                    focus=None;body_tokens=tokens
                    if say is not None:
                        if say in tokens:
                            boundary=tokens.index(say)
                            head=len(tokenizer.encode(' ',add_special_tokens=False))+int(getattr(model.config,'tinytalk_emit_intent_token',True))+bool(answer_types)
                            focus=tokenizer.decode(tokens[head:boundary],skip_special_tokens=True).strip()
                            body_tokens=tokens[boundary+1:]
                        else:body_tokens=[]
                    reply = tokenizer.decode(body_tokens, skip_special_tokens=True).strip()
                    words = reply.lower().split()
                    triples = [tuple(words[i:i + 3]) for i in range(len(words) - 2)]
                    predicted = [intents[token] for token in tokens if token in intents]
                    replies.append({"id": case["id"], "reply": reply, "ended_with_eos": ended,
                                    "bad": not ended or not reply or len(triples) != len(set(triples)), "tokens": len(tokens),
                                    "omitted_context_pairs": omissions[start + at], "intent_tokens": predicted,
                                    "answer_type_tokens":[answer_types[token] for token in tokens if token in answer_types],
                                    **({'answer_focus':focus} if say is not None else {}),
                                    "raw_token_ids": tokens})
    finally:tokenizer.padding_side = "right"
    return replies


def logps(model, rows, tokenizer, device, intent_weight=1.0, example_balanced=False):
    import torch
    ids, labels, mask = core.batch(rows, tokenizer.eos_token_id, device)
    hidden = model.transformer(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
    use = labels[:, 1:] != -100
    logits = model.lm_head(hidden[:, :-1][use])
    losses = torch.nn.functional.cross_entropy(logits.float(), labels[:, 1:][use], reduction="none")
    indices = use.nonzero(as_tuple=True)[0]
    scores = torch.zeros(len(rows), device=device).scatter_add(0, indices, -losses)
    targets = labels[:, 1:][use]
    weights = torch.ones_like(losses)
    if intent_weight != 1.0:
        control_ids=list(getattr(model.config,"tinytalk_intent_token_ids",{}).values())
        control_ids+=list(getattr(model.config,"tinytalk_answer_type_token_ids",{}).values())
        say=getattr(model.config,'tinytalk_answer_focus_separator_id',None)
        if say is not None:control_ids.append(say)
        for token in control_ids:
            weights[targets == token] = intent_weight
    if example_balanced:
        sums = torch.zeros(len(rows), device=device).scatter_add(0, indices, losses * weights)
        counts = torch.zeros(len(rows), device=device).scatter_add(0, indices, weights)
        assert torch.all(counts > 0)
        ce = (sums / counts).mean()
    elif intent_weight != 1.0:
        ce = (losses * weights).sum() / weights.sum()
    else:ce = losses.mean()
    return scores, ce, logits, targets
