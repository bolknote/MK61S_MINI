"""Same actor input and tools, with real balanced starting cases."""
import hashlib
from ay_runtime import Session as Parent,render,snapshot,goal_state,view


def initial_case(goal):return int(hashlib.sha256(goal['id'].encode()).hexdigest()[-1],16)%2


class Session(Parent):
    def __init__(self,goal,body,vm,arm,declared_spec=None,gate=False,start_case=None):
        super().__init__(goal,body,vm,arm,declared_spec,gate)
        case=initial_case(goal)if start_case is None else start_case
        if body is not None:self.run(case)
        self.case=case;self.observation=None;self.history=[]
