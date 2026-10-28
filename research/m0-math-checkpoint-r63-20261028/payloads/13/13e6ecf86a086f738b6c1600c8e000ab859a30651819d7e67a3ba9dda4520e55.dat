#ifndef MK61_LANGUAGE_VM_PROFILE_HPP
#define MK61_LANGUAGE_VM_PROFILE_HPP

// Diagnostic-only cycle attribution. No fields, callbacks or counters enter
// the VM ABI; ordinary APPs compile this completely out.
#if (defined(MK61_VM_OPCODE_PROFILE) && MK61_VM_OPCODE_PROFILE && \
     defined(MK61_BUILD_PORTABLE_SYSTEM) && defined(__arm__)) || \
    defined(LANGUAGE_VM_OPCODE_PROFILE_TEST)
#define LANGUAGE_VM_OPCODE_PROFILE_SUPPORTED 1
#ifndef MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS
#define MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS 1
#endif
#ifndef MK61_VM_OPCODE_PROFILE_TIMING
#define MK61_VM_OPCODE_PROFILE_TIMING 1
#endif
#if (MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS != 0 && MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS != 1) || \
    (MK61_VM_OPCODE_PROFILE_TIMING != 0 && MK61_VM_OPCODE_PROFILE_TIMING != 1)
#error "VM profile timing/integer census must be 0 or 1"
#endif
namespace language_vm {
#if defined(LANGUAGE_VM_OPCODE_PROFILE_TEST)
uint32_t opcode_profile_test_cycles();
#endif
class OpcodeProfile {
  uint32_t overhead_;
  static uint32_t cycles() {
#if defined(LANGUAGE_VM_OPCODE_PROFILE_TEST)
    return opcode_profile_test_cycles();
#else
    __asm__ __volatile__("" ::: "memory");
    const uint32_t value = *(volatile uint32_t*)UINT32_C(0xE0001004);
    __asm__ __volatile__("" ::: "memory");
    return value;
#endif
  }
public:
  __attribute__((noinline)) explicit OpcodeProfile(const View&) {
#if MK61_VM_OPCODE_PROFILE_TIMING
    const uint32_t start=cycles();
    overhead_=cycles()-start;
#else
    overhead_=0;
#endif
  }
  class Sample {
    uint32_t overhead_;
    uint8_t opcode_;
    bool integer_;
    uint8_t count_=1;
    uint32_t start_;
  public:
    Sample(OpcodeProfile& owner, Op op, const Continuation& s, const Bindings& data)
        : overhead_(owner.overhead_), opcode_((uint8_t)op), integer_(false) {
      if(MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS &&
         ((op>=Op::ADD && op<=Op::XOR && op!=Op::POW) || op==Op::FLOOR_DIV || op==Op::COMPARE_FALSE) && s.sp>=2)
        integer_=data.stack[s.sp-1].integer() && data.stack[s.sp-2].integer();
      start_=MK61_VM_OPCODE_PROFILE_TIMING?cycles():0;
    }
    // A guarded block replaces several logical instructions, not their
    // semantics. Attribute its elapsed time once, separately from scalar
    // opcode groups; n is the number of useful instructions it consumed.
    void fused(uint8_t count,bool integers=true) {
      integer_=MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS && integers;count_=count;
    }
    __attribute__((noinline)) ~Sample() {
      const uint32_t elapsed=MK61_VM_OPCODE_PROFILE_TIMING?cycles()-start_:0;
      const uint64_t measured=((uint64_t)overhead_<<32)|elapsed;
      // Classification/accumulation is diagnostic resident code. Sampling
      // stops before this call, so its cost is not attributed to an opcode.
      (void)portable_system::call(MK61_SERVICE_VM_PROFILE,
          MK61_VM_PROFILE_RAW_OPCODE|MK61_VM_PROFILE_CYCLE_PAIR|opcode_,count_,
          MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS && integer_?count_:0,(void*)&measured);
    }
  };
};
}
#define VM_OPCODE_PROFILE(view) language_vm::OpcodeProfile vm_opcode_profile(view)
#define VM_OPCODE_SAMPLE(op,state,data) language_vm::OpcodeProfile::Sample vm_opcode_sample(vm_opcode_profile,op,state,data)
#define VM_OPCODE_FUSED(count) vm_opcode_sample.fused((uint8_t)(count))
#define VM_OPCODE_FUSED_VALUE(count) vm_opcode_sample.fused((uint8_t)(count),false)
#else
#define LANGUAGE_VM_OPCODE_PROFILE_SUPPORTED 0
#define VM_OPCODE_PROFILE(view) ((void)0)
#define VM_OPCODE_SAMPLE(op,state,data) ((void)0)
#define VM_OPCODE_FUSED(count) ((void)0)
#define VM_OPCODE_FUSED_VALUE(count) ((void)0)
#endif
#endif
