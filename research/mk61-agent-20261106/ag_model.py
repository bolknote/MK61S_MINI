"""Continue the selected, exactly export-aligned rank16 factors."""
from af_model import Agent as Parent,action_weight,correct_weight
from ag_common import START,ARMS

class Agent(Parent):
    def __init__(self,arm='balanced',device='cuda',checkpoint=None):
        assert arm in [*ARMS,'initial']
        super().__init__('replay',device,checkpoint or START);self.training_arm=arm

