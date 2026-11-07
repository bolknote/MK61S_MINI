"""Development-only comparison of unconstrained and one-intent output formats."""
import argparse
from pathlib import Path
from common import load_model, core
from evaluate import assess

parser = argparse.ArgumentParser()
parser.add_argument('--model', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--suite', default='suite')
parser.add_argument('--device', default='cuda')
parser.add_argument('--seed', type=int, default=7731)
args = parser.parse_args()
model, tokenizer, device = load_model(args)
cases = core.read_rows(Path(args.suite) / 'dev.jsonl')
results = {}
for flag in [False, True]:
    model.config.tinytalk_structured_intent_decoding = flag
    result = assess(model, tokenizer, device, cases, None, Path(args.output) / 'grade-cache', 'format')
    results[str(flag)] = result
    core.save(Path(args.output) / 'comparison.json', results)
    print({'structured': flag, 'direct': result['direct']['pass_rate'],
           'multi': result['multi_turn']['pass_rate'], 'malformed': result['malformed']}, flush=True)
