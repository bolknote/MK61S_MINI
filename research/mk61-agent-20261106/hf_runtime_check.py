"""Check stale-run invalidation and demonstrate that the gate has no oracle."""
from hf_runtime import Session
from hf_runtime import prompt
from ha_protocol import prompt as original_prompt
from full_isa_vm import FullVM


class Forbidden:
    def __iter__(self):raise AssertionError('Hidden fixtures accessed')
    def __getitem__(self,key):raise AssertionError('Reference answer accessed')


def main():
    task={'id':'runtime-check','task':'Выдай в X число 0.','angle':'DEG',
          'public_tests':[{'segments':[{'inputs':{'X':str(x)},'expected':Forbidden()}]}for x in [-3,2.5]],
          'hidden_tests':Forbidden()}
    assert prompt(task)==original_prompt(task,'asm')
    s=Session(task,'asm',body=[0xFF,1,0,0x50],vm=FullVM());s.run(0)
    assert s.apply('<done/>')=='done_rejected'and not s.finished
    assert s.apply('<run>01</run>')=='run'and s.eligibility()[0]
    before=dict(s.runs);revision=s.revision
    assert s.apply('<patch>00 00 FF 01 FE 50</patch><run/>')=='error'
    assert s.runs==before and s.revision==revision
    assert s.apply('<patch>00 02 01 50</patch><run/>')=='patch'
    assert s.revision==revision+1 and set(s.runs)=={1}
    assert s.apply('<done/>')=='done_rejected'
    s.apply('<run>00</run>');assert s.eligibility()[0]
    text=s.request();assert 'Факт 00'in text and 'Факт 01'in text
    s.apply('<trace/>');assert s.eligibility()[0]
    assert s.apply('<done/>')=='done'and s.finished
    # This program returns 1 despite a request for 0: structural gating alone
    # deliberately cannot certify semantics and does not consult expected data.
    assert s.runs[0][0]['X']=='1'
    print('runtime checks passed; wrong result accepted after all runs proves absence of semantic oracle')


if __name__=='__main__':main()
