"""Identical 3M Q4/rank16 starts, comparing only two lower learning rates."""
from af_model import Agent as Parent,action_weight,correct_weight
from ai_common import START,ARMS

class Agent(Parent):
    def __init__(self,arm='lr20',device='cuda',checkpoint=None):
        assert arm in [*ARMS,'initial']
        super().__init__('replay',device,checkpoint or START);self.training_arm=arm

