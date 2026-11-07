"""A paired full-HEX / constant-and-label assembler experiment."""
from pathlib import Path
from tasks import BUILD
from full_isa_common import read,sha,write,compact_head

ROOT=BUILD/'harness-ablation-v1'
PREVIOUS=BUILD/'full-isa-natural-v1'
if not(PREVIOUS/'export/selected-budget/hf').exists():PREVIOUS=PREVIOUS/'server-results'
INITIAL=PREVIOUS/'export/selected-budget/hf'
INITIAL_PACKET=PREVIOUS/'export/selected-budget/model.mkqb'
ARMS=['direct','asm']
HERE=Path(__file__).parent


def allowed():
    import json
    return json.loads((ROOT/'output-token-ids.json').read_text())

