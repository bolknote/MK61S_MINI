#include "coprime_residue.hpp"

using namespace m0_pow_coprime;

extern "C" uint32_t residue_reduce(uint64_t value, uint32_t offset) {
    return Ring{offset}.reduce(value);
}

extern "C" uint32_t residue_multiply_add_short(uint32_t value, uint32_t weight,
                                               uint32_t addend, uint32_t offset) {
    return Ring{offset}.multiply_add_short(value,uint16_t(weight),addend);
}

extern "C" int residue_reconstruct(const uint32_t* residues, unsigned count, uint32_t* digits) {
    if (!count || count > MaximumModuli)
        return 0;
    return reconstruct(count,digits,[&](unsigned i, const Ring&) { return residues[i]; },nullptr);
}

extern "C" int residue_compare(U x, U y, U lower, unsigned gap, uint32_t* digits, unsigned capacity) {
    return side(x,y,lower,gap,digits,capacity);
}

struct ArmCase {
    U x, y, lower;
    unsigned gap;
};

extern "C" int residue_arm(const ArmCase* input) {
    uint32_t digits[MaximumModuli];
    return side(input->x,input->y,input->lower,input->gap,digits,MaximumModuli);
}
