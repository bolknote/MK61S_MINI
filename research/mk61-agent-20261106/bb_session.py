"""Optional host harness with a canonical table at the neural boundary."""
from az_runtime import Session as Base,snapshot,render
from bb_canonical import request_state,response_body


class Session(Base):
    def __init__(self,goal,body,vm,arm='spec',declared_spec=None,gate=False,start_case=None):
        if arm!='spec':raise ValueError('Canonical boundary requires SPEC output')
        super().__init__(goal,body,vm,arm,declared_spec,gate,start_case)

    def request(self):return render(request_state(snapshot(self)),'spec')

    def apply_action(self,action,body):
        return super().apply_action(action,response_body(action,body,snapshot(self)))
