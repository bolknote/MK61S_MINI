"""Natural-language continuation from the completed full-instruction student."""
from tasks import BUILD
from full_isa_common import read,sha,write,allowed,task_prompt,target,compact_head

ROOT=BUILD/'full-isa-natural-v1'
PREVIOUS=BUILD/'full-isa-v1'
if not(PREVIOUS/'export/protected-best/hf').exists():PREVIOUS=PREVIOUS/'server-results'
INITIAL=PREVIOUS/'export/protected-best/hf'
INITIAL_PACKET=PREVIOUS/'export/protected-best/model.mkqb'

