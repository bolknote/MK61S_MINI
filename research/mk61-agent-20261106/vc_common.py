from pathlib import Path
from tasks import BUILD
from ha_common import read,sha,write

HERE=Path(__file__).resolve().parent
ROOT=BUILD/'harness-verifier-v1'
CODER=BUILD/'harness-debug-v3'
if not(CODER/'export/selected-budget/hf').exists():CODER=CODER/'server-results'
INITIAL=CODER/'export/selected-budget/hf'
INITIAL_PACKET=CODER/'export/selected-budget/model.mkqb'
ARMS=['slow','fast']
