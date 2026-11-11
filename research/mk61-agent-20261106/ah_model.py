"""The same rank16 and 3M Q4 model, with no extra inference parameters."""
from ag_model import Agent as Parent,action_weight,correct_weight
from ah_common import START,ARMS

class Agent(Parent):
    def __init__(self,arm='replay',device='cuda',checkpoint=None):
        assert arm in [*ARMS,'initial']
        super().__init__('balanced',device,checkpoint or START);self.training_arm=arm

