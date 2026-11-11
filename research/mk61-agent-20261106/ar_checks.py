"""Independent ROM differential and leakage checks for the new verifier."""
import json
from ar_spec import infer, verify, equivalent
from ar_data import bank
from full_isa_vm import FullVM
from full_isa_math import UNARY, BINARY, compile_expr
from full_isa_protocol import REGISTERS
from ha_protocol import encode, assemble


def main():
    vm=FullVM();pool=['0','1','-1','2.5'];count=0
    for angle in ['RAD','DEG','GRAD']:
        for op in UNARY:
            cases=bank('unit'if op in ['asin','acos']else'positive',310001,8)
            expr=[op,'R0'];spec={'X':expr,'writes':{},'angle':angle}
            body=encode(compile_expr(expr)+[0x50],pool,'asm')
            a=verify(vm,body,pool,spec,cases)
            assert a['status']=='TESTED',(angle,op,a)
            assert equivalent(infer(body,pool,angle),spec,cases)['tested_equal']
            count+=a['cases']
        for op in BINARY:
            expr=[op,'R0','R1'];spec={'X':expr,'writes':{},'angle':angle}
            body=encode(compile_expr(expr)+[0x50],pool,'asm');cases=bank('positive',310002,8)
            a=verify(vm,body,pool,spec,cases);assert a['status']=='TESTED',(op,a)
            assert equivalent(infer(body,pool,angle),spec,cases)['tested_equal'];count+=a['cases']
    for expr in [{'constant':'-2.5'}, {'constant':'0'}, {'constant':'2.5'}, {'pi':True},
                 ['+',['pow','R0','R1'],['square','R2']]]:
        spec={'X':expr,'writes':{},'angle':'RAD'};body=encode(compile_expr(expr)+[0x50],pool,'asm')
        cases=bank('positive',310003,8);a=verify(vm,body,pool,spec,cases)
        assert a['status']=='TESTED',(expr,a)
        assert equivalent(infer(body,pool,'RAD'),spec,cases)['tested_equal'];count+=a['cases']
    # Store then recall must refer to initial state, not reuse an initial name.
    body=[0x60,0x22,0x40,0x60,0x61,0x10,0x43,0x50]
    spec=infer(body,pool,'RAD');a=verify(vm,body,pool,spec,bank('signed',310004,12))
    assert a['status']=='TESTED',a;count+=a['cases']
    # Preserving every unnamed register is part of the postcondition.
    spec={'X':['square','R0'],'writes':{},'angle':'RAD'}
    a=verify(vm,[0x60,0x22,0x41,0x50],pool,spec,bank('signed',310005,8))
    assert a['status']=='FAIL'and a['name']=='R1',a
    # A self-consistent wrong intent must never pass the separate task audit.
    wrong=[0x60,0x22,0x22,0x50];declared=infer(wrong,pool,'RAD')
    assert verify(vm,wrong,pool,declared,bank('signed',310006,8))['status']=='TESTED'
    assert verify(vm,wrong,pool,spec,bank('signed',310006,8))['status']=='FAIL'
    assert not equivalent(declared,spec,bank('signed',310006,8))['tested_equal']
    for body in [[0x51,0,0x50],[0x60,0x24,0x50],[0x60,0x22]]:
        try:infer(body,pool,'RAD')
        except ValueError:pass
        else:raise AssertionError(('unsupported accepted',body))
    assert verify(vm,[0x50],pool,None,[])['status']=='UNKNOWN'
    print(json.dumps({'ROM_differential_cases':count,'negative_and_unknown_checks':'passed',
                      'self_spec_is_not_task_truth':'passed'}))


if __name__=='__main__':main()
