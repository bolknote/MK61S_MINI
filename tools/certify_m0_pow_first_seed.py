#!/usr/bin/env python3
"""Bind first-tier routing and exact-square rewrites to the qualified source."""
import argparse,hashlib,json
from pathlib import Path


def function(text,signature):
    start=text.index(signature);brace=text.index('{',start);depth=1;end=brace+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--baseline-root',type=Path,required=True)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();new=args.source_root/'code';old=args.baseline_root/'code'
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    fast=(new/'native_eabi_m0_pow_fast.inc').read_text();base=(old/'native_eabi_m0_pow_fast.inc').read_text()
    normalized=fast
    tiny_signature='static bool pow_tiny_integer('
    normalized=normalized.replace(function(fast,tiny_signature),function(base,tiny_signature))
    marker='// A first-tier approximation is only a hint.'
    at=normalized.index(marker);start=normalized.rfind('#if defined(MK61_M0_RP2040_EABI)',0,at)
    end=normalized.index('// For |f|=|x-1|<=2^-36',at)
    candidate=normalized[start:end]
    for token in ('const double *px,const double *py,U hint','const double x=*px,y=*py',
                  'pow_dyadic128(bits(x),bits(y),hint)','pow_refine_checked(x,y)'):
        assert token in candidate,token
    normalized=normalized[:start]+normalized[end:]
    definition='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#define M0_POW_EXP_CANDIDATE(value) return pow_first_candidate(&x,&y,value)
#endif
'''
    assert normalized.count(definition)==1;normalized=normalized.replace(definition,'')
    cleanup='''#ifdef M0_POW_EXP_CANDIDATE
#undef M0_POW_EXP_CANDIDATE
#endif
'''
    assert normalized.count(cleanup)==1;normalized=normalized.replace(cleanup,'')
    assert normalized==base,'A fast-file difference is outside the three inspected rewrites'
    body=(new/'native_eabi_m0_pow_exp_body.inc').read_text();body_base=(old/'native_eabi_m0_pow_exp_body.inc').read_text()
    at=body.index('#ifdef M0_POW_EXP_CANDIDATE');otherwise=body.index('#else\n',at);end=body.index('#endif\n',otherwise)
    normal_branch=body[at:otherwise]
    for token in ('(q+511+((q>>10)&1))>>10','rounding_tail-(512U-error)',
                  'M0_POW_EXP_CANDIDATE((U(k+1022)<<52)+rounded)'):
        assert token in normal_branch,token
    normalized_body=body[:at]+body[otherwise+len('#else\n'):end]+body[end+len('#endif\n'):]
    assert normalized_body==body_base,'An exp coefficient/domain/error guard changed'
    integer=(new/'native_eabi_m0_pow_integer128.inc').read_text();integer_base=(old/'native_eabi_m0_pow_integer128.inc').read_text()
    at=integer.index('// Exact64-bit square with three32x32 products.')
    end=integer.index('__attribute__((always_inline)) inline U pow_integer128_hint',at)
    square=integer[at:end]
    for token in ('wide32(low,low),cross=wide32(low,high),top=wide32(high,high)',
                  '(bottom>>32)+(U(uint32_t(cross))<<1)',
                  'top+((cross>>32)<<1)+(middle>>32)',
                  '2*a.error+(low?4:(a.error?1:0))'):
        assert token in square,token
    normalized_integer=(integer[:at]+integer[end:]).replace('pow_integer128_square(q);','pow_integer128_multiply(q,q);')
    assert normalized_integer==integer_base,'An integer-domain/rounding/error rule changed'
    dyadic=(new/'native_eabi_m0_pow_dyadic128.inc').read_text()
    normalized_dyadic=dyadic.replace('pow_integer128_square(q);','pow_integer128_multiply(q,q);')
    normalized_dyadic=normalized_dyadic.replace('pow_integer128_square(square);','pow_integer128_multiply(square,square);')
    assert normalized_dyadic==(old/'native_eabi_m0_pow_dyadic128.inc').read_text(), 'A dyadic midpoint acceptance rule changed'
    # With B=2^32, a=L+B*H and a^2=L^2+2*L*H*B+H^2*B^2.
    # The middle sum is below3B, so its carry fits two bits. The
    # final high word cannot overflow because a^2<2^128.
    radix=1<<32
    assert (radix-1)+2*(radix-1)<3*radix<1<<34
    assert ((1<<64)-1)**2<1<<128
    result=dict(status='PASS_SOURCE_REWRITE_LEMMAS',
        candidate_route='Only the normal-cell ambiguous exit changes. The rounded Q62 value is an untrusted hint. The existing dyadic midpoint inequalities retain authority; all overlap/domain declines use the identical previous refinement function. The synchronous call receives pointers to live double parameters and does not retain or modify them.',
        square_identity='Three exact32x32->64 products reconstruct the full64-bit square by the displayed radix identity and middle carry. The normalized128-bit square uses the same two equal cross-high terms and the identical propagated radius as the generic aliased product. This preserves the full output triple byte-for-byte; independent ARM tests check all carry/normalization cases.',
        unchanged_exp_coefficients_and_error_guards=True,unchanged_dyadic_acceptance_rules=True,
        unchanged_general_integer_multiply_and_pack=True,
        inspected_files={name:dict(current_sha256=sha(new/name),baseline_sha256=sha(old/name)) for name in
                         ('native_eabi_m0_pow_fast.inc','native_eabi_m0_pow_exp_body.inc',
                          'native_eabi_m0_pow_integer128.inc','native_eabi_m0_pow_dyadic128.inc')},
        producer_sha256=sha(__file__),
        scope='Exact source-rewrite equivalence and square carry bounds. The bounded tiny-helper bit-mask proof is separate. Compiled pointer ABI, exact square/enclosure results, RNE and M4/generic isolation require their independent ARM/compiler checks. No universal pow totality, cache policy or physical-speed proof.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: only inspected tiny-helper, untrusted seed-route and exact-square rewrites; all acceptance/error rules retained.')


if __name__=='__main__':main()
