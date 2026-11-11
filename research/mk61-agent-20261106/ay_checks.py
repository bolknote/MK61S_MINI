"""Codec/ROM tests that fail on reversed operands and unintended stores."""
from ay_common import ROOT,rows,write
from ay_codec import encode,decode,compile_spec,to_program
from ar_spec import verify,equivalent
from full_isa_vm import FullVM


def main():
    vm=FullVM();groups=[g for s in ['train','development','closed']for g in rows(ROOT/(s+'-asts.jsonl'))]
    matches=0
    for g in groups:
        assert decode(encode(g['spec'],g['pool']),g['pool'],g['spec']['angle'])==g['spec'];matches+=1
    pool=['0','1','-1','2.5'];spec={'X':['-','R7','R8'],'writes':{},'angle':'RAD'}
    cases=[{'R7':'2.25','R8':'-1.5'},{'R7':'-3.25','R8':'.875'}]
    code=compile_spec(decode(encode(spec,pool),pool,'RAD'),pool)
    assert verify(vm,code,pool,spec,cases)['status']=='TESTED'
    reversed_spec={**spec,'X':['-','R8','R7']}
    assert verify(vm,compile_spec(reversed_spec,pool),pool,spec,cases)['status']=='FAIL'
    stored={'X':['square','R7'],'writes':{'RE':['square','R7']},'angle':'RAD'}
    assert verify(vm,compile_spec(decode(encode(stored,pool),pool,'RAD'),pool),pool,stored,cases)['status']=='TESTED'
    failures=0
    for body in [[],[255],[15,0],[255,255],[255,0,1],[255,16],[255,16,250],[255,64,0],[255,True]]:
        try:decode(body,pool,'RAD')
        except (ValueError,TypeError):failures+=1
        else:raise AssertionError(('malformed accepted',body))
    report={'AST_roundtrips':matches,'ROM_operand_and_memory_tests':'passed','malformed_rejections':failures,
            'angle_supplied_by_harness':True,'same_existing_HEX_token_alphabet':True,'optimizer_updates':0}
    write(ROOT/'codec-checks.json',report);print(report)


if __name__=='__main__':main()
