"""Debugging continuation of the selected 3M Q4 student."""
from pathlib import Path
from tasks import BUILD
from ha_common import read,sha,write,compact_head

HERE=Path(__file__).resolve().parent
ROOT=BUILD/'harness-debug-v3'
PREVIOUS=BUILD/'harness-debug-v2'
if not(PREVIOUS/'export/selected-budget/hf').exists():PREVIOUS=PREVIOUS/'server-results'
INITIAL=PREVIOUS/'export/selected-budget/hf'
INITIAL_PACKET=PREVIOUS/'export/selected-budget/model.mkqb'
ARMS=['safe','active']


def allowed():
    import json
    return json.loads((ROOT/'output-token-ids.json').read_text())
