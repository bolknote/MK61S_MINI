"""Corrective continuation after the completed and preserved format ablation."""
from tasks import BUILD
from ha_common import HERE,read,sha,write,compact_head

ROOT=BUILD/'harness-retention-v1'
BASE=BUILD/'harness-ablation-v1'
if not(BASE/'export/asm-best/hf').exists():BASE=BASE/'server-results'
INITIAL=BASE/'export/asm-best/hf'
INITIAL_PACKET=BASE/'export/asm-best/model.mkqb'
ARMS=['slow','fast']

