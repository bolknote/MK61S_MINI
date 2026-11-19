#include "native_eabi_m0_pow_residue.inc"
#include "mixed_residue.hpp"

using namespace m0_pow_mixed;

extern "C" unsigned mixed_capacity(unsigned mode, unsigned budget) {
    return mode >= binary && mode <= triple ? max_width(mode,budget) : 0;
}

extern "C" int mixed_compare(U x, U y, U lower, unsigned gap, unsigned mode, Word* scratch,
                             unsigned budget, Plan* plan, Work* work) {
    return side(x,y,lower,gap,mode,scratch,budget,*plan,*work);
}

extern "C" int single_compare(U x, U y, U lower, unsigned gap) {
    return m0_pow_residue::side(x,y,lower,gap,nullptr);
}

extern "C" int mixed_raw(U a, U b, unsigned mode, unsigned n, Word* scratch) {
    Work count{};
    const Plan p{mode,n,(rings(mode)+2)*(n+extra_word(mode)),0};
    return sign(p,{a,0},1,{b,0},0,false,0,0,scratch,count);
}

extern "C" uint64_t mixed_pairs(unsigned n, unsigned a, unsigned b, bool square, bool truncated) {
    return pair_count(n,a,b,square,truncated);
}

extern "C" unsigned mixed_ring(unsigned mode, unsigned n, unsigned op,
                                Word* a, unsigned used_a, Word* b, unsigned used_b,
                                Word* work, U shift_low, U shift_high) {
    Work count{};
    Ring ring(n,Modulus(mode),count);
    Number left{a,used_a}, right{b,used_b};
    if (op < 2)
        ring.multiply(left,op == 1 ? left : right,work,op == 1);
    else if (op == 2)
        ring.shift(left,Index::words(shift_low,shift_high),work);
    else
        left = ring.subtract(left,right,left.data);
    ring.copy(left,a);
    return left.used;
}

struct ArmCase {
    U x, y, midpoint_lower;
    unsigned gap;
};

extern "C" int mixed_arm(const ArmCase* input, unsigned mode) {
    Word scratch[BudgetWords];
    Plan plan;
    Work work;
    return side(input->x,input->y,input->midpoint_lower,input->gap,mode,scratch,BudgetWords,plan,work);
}

extern "C" int existing_arm(const ArmCase* input) {
    return m0_pow_residue::side(input->x,input->y,input->midpoint_lower,input->gap,nullptr);
}
