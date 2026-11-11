"""Same public MK-61 state; only the meaning of WRITE's output bytes differs."""
import copy
from as_runtime import Session as Parent,render as native_render
from hf_runtime import Session as StateSession
from ay_common import MAX_TURNS
from ay_codec import to_program


def view(goal):
    return {'id':goal['id'],'task':goal['task'],'angle':goal['spec']['angle'],'constants':goal['pool'],
            'public_tests':[{'segments':[{'inputs':x}]}for x in goal['public_inputs']],
            'max_commands':128,'max_frames':1024}


def render(state,arm):
    runs={int(k):v for k,v in state['runs'].items()}
    text=native_render(state['view'],state['body'],state['pool'],runs,state['case'],state['revision'],
                       state['observation'],state.get('diagnosis'),state['remaining'])
    if arm=='spec':
        text=text.replace('Исправление: WRITE с полным HEX программы.','Исправление: WRITE с компактной спецификацией SPEC.')
        text=text.replace('<write>HEX</write>','<write>SPEC</write>')
    else:assert arm=='hex'
    return text


def snapshot(session):
    return {'view':copy.deepcopy(session.task),'pool':list(session.pool),'body':copy.deepcopy(session.body),
            'runs':copy.deepcopy(session.runs),'case':session.case,'revision':session.revision,
            'observation':session.observation,'diagnosis':copy.deepcopy(session.diagnosis),
            'remaining':MAX_TURNS-len(session.history)}


def goal_state(goal):
    return {'view':view(goal),'pool':list(goal['pool']),'body':None,'runs':{},'case':0,'revision':0,
            'observation':None,'diagnosis':None,'remaining':MAX_TURNS}


class Session(Parent):
    def __init__(self,goal,body,vm,arm,declared_spec=None,gate=False):
        StateSession.__init__(self,view(goal),'asm',body=copy.deepcopy(body),vm=vm,gate=False)
        self.output_arm=arm;self.declared_spec=copy.deepcopy(declared_spec)
        self.checker_inputs=goal['checker_inputs'];self.mechanical=gate;self.abstained=False
        self.diagnosis=None;self.gate_checks=[];self.gate_cache=None;self.last_written_spec=None
        if body is not None:
            for index in range(len(self.task['public_tests'])):self.run(index)
        self.case=0;self.observation=None;self.history=[]

    def request(self):return render(snapshot(self),self.output_arm)

    def apply_action(self,action,body):
        if action=='write':
            program,spec=to_program(body,self.pool,self.task['angle'],self.output_arm)
            result=super().apply_action(action,program)
            self.last_written_spec=spec
            return result
        return super().apply_action(action,body)
