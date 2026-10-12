#ifndef MK61_LANGUAGE_VM_PROFILE_HPP
#define MK61_LANGUAGE_VM_PROFILE_HPP

// Diagnostic-only cycle attribution. No fields, callbacks or counters enter
// the VM ABI; ordinary APPs compile this completely out.
#if defined(MK61_VM_OPCODE_PROFILE) && MK61_VM_OPCODE_PROFILE && \
    defined(MK61_BUILD_PORTABLE_SYSTEM) && defined(__arm__)
namespace language_vm {
class OpcodeProfile {
  struct Row { uint64_t cycles; uint32_t count, integers; };
  Row rows_[8] = {};
  uint32_t overhead_;
  static uint32_t cycles() {
    __asm__ __volatile__("" ::: "memory");
    const uint32_t value = *(volatile uint32_t*)UINT32_C(0xE0001004);
    __asm__ __volatile__("" ::: "memory");
    return value;
  }
  static unsigned group(Op op) {
    if((op>=Op::LOAD && op<=Op::STORE) || op==Op::UPDATE_LOCAL) return 1;
    if(op==Op::LOAD_ARRAY || op==Op::STORE_ARRAY || op==Op::LOAD_ARRAY_FIXED ||
       op==Op::ARRAY_CELL || op==Op::TARGET_ARRAY) return 2;
    if(op==Op::ADD || op==Op::SUB) return 3;
    if(op==Op::MUL) return 4;
    if(op==Op::DIV || op==Op::MOD || op==Op::FLOOR_DIV) return 5;
    if((op>=Op::EQ && op<=Op::XOR) || op==Op::COMPARE_FALSE) return 6;
    if((op>=Op::CONST_0 && op<=Op::CONST_15) || op==Op::CONST_I8 ||
       op==Op::CONST_I16 || op==Op::CONST_I32 || op==Op::CONST_F64 ||
       op==Op::CONST_DEC8 || op==Op::CONST_DEC16) return 0;
    return 7;
  }
public:
  explicit OpcodeProfile(const View&) {
    const uint32_t start=cycles();
    overhead_=cycles()-start;
  }
  ~OpcodeProfile() {
    for(unsigned i=0;i<8;++i) {
      const auto& r=rows_[i];
      if(!r.count) continue;
      (void)portable_system::call(MK61_SERVICE_VM_PROFILE,i,r.count,r.integers,
                                  (void*)&r.cycles);
    }
  }
  class Sample {
    OpcodeProfile& owner_;
    unsigned group_;
    bool integer_;
    uint32_t start_;
  public:
    Sample(OpcodeProfile& owner, Op op, const Continuation& s, const Bindings& data)
        : owner_(owner), group_(group(op)), integer_(false) {
      if(group_>=3 && group_<=6 && s.sp>=2)
        integer_=data.stack[s.sp-1].integer() && data.stack[s.sp-2].integer();
      start_=cycles();
    }
    ~Sample() {
      const uint32_t elapsed=cycles()-start_;
      auto& row=owner_.rows_[group_];
      row.cycles += elapsed>owner_.overhead_ ? elapsed-owner_.overhead_ : 0;
      ++row.count;row.integers+=integer_;
    }
  };
};
}
#define VM_OPCODE_PROFILE(view) language_vm::OpcodeProfile vm_opcode_profile(view)
#define VM_OPCODE_SAMPLE(op,state,data) language_vm::OpcodeProfile::Sample vm_opcode_sample(vm_opcode_profile,op,state,data)
#else
#define VM_OPCODE_PROFILE(view) ((void)0)
#define VM_OPCODE_SAMPLE(op,state,data) ((void)0)
#endif
#endif
