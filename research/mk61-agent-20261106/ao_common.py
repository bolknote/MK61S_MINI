"""Balanced standalone recognition of operation, argument, and order faults."""
from tasks import BUILD
from an_common import HERE,read,write,sha
ROOT=BUILD/'error-recognizer-v1'
PARENT=BUILD/'hex-hypothesis-v2'
PARENT=PARENT if(PARENT/'export/direct-research/hf').exists()else PARENT/'server-results'
INITIAL=PARENT/'export/direct-research/hf'
INITIAL_PACKET=PARENT/'export/direct-research/model.mkqb'
ARMS=['head','adapt']
CLASSES=['operation','argument','order','correct']
DIAG_IDS=[8201,8202,8203,8204]
SPLITS=['development','novel-development','fresh','novel-fresh']
