#include "z80.h"
#include <stddef.h>
#include <string.h>

#if defined(MK61_TARGET_PICOCALC) && defined(__arm__)
_Static_assert(offsetof(z80,a)<32 && offsetof(z80,f)<32 && offsetof(z80,r)<32 &&
               offsetof(z80,iff_delay)<32,"Keep live Z80 byte registers in Thumb-1's short load range");
_Static_assert(offsetof(z80,contention_mask)<64 && offsetof(z80,bus)<128 &&
               offsetof(z80,wait)<128 && offsetof(z80,m1)<128,
               "Keep Z80 bus state in Thumb-1's short load range");
#endif

/* Local port: embedded builds have no stderr; undocumented opcodes remain NOPs. */
#if defined(MK61_TARGET_PICOCALC)
#define Z80_DIAGNOSTIC(...) ((void)0)
#else
#define Z80_DIAGNOSTIC(...) fprintf(stderr, __VA_ARGS__)
#endif

// MARK: timings
static const uint8_t cyc_00[256] = {4, 10, 7, 6, 4, 4, 7, 4, 4, 11, 7, 6, 4, 4,
    7, 4, 8, 10, 7, 6, 4, 4, 7, 4, 12, 11, 7, 6, 4, 4, 7, 4, 7, 10, 16, 6, 4, 4,
    7, 4, 7, 11, 16, 6, 4, 4, 7, 4, 7, 10, 13, 6, 11, 11, 10, 4, 7, 11, 13, 6,
    4, 4, 7, 4, 4, 4, 4, 4, 4, 4, 7, 4, 4, 4, 4, 4, 4, 4, 7, 4, 4, 4, 4, 4, 4,
    4, 7, 4, 4, 4, 4, 4, 4, 4, 7, 4, 4, 4, 4, 4, 4, 4, 7, 4, 4, 4, 4, 4, 4, 4,
    7, 4, 7, 7, 7, 7, 7, 7, 4, 7, 4, 4, 4, 4, 4, 4, 7, 4, 4, 4, 4, 4, 4, 4, 7,
    4, 4, 4, 4, 4, 4, 4, 7, 4, 4, 4, 4, 4, 4, 4, 7, 4, 4, 4, 4, 4, 4, 4, 7, 4,
    4, 4, 4, 4, 4, 4, 7, 4, 4, 4, 4, 4, 4, 4, 7, 4, 4, 4, 4, 4, 4, 4, 7, 4, 4,
    4, 4, 4, 4, 4, 7, 4, 5, 10, 10, 10, 10, 11, 7, 11, 5, 10, 10, 0, 10, 17, 7,
    11, 5, 10, 10, 11, 10, 11, 7, 11, 5, 4, 10, 11, 10, 0, 7, 11, 5, 10, 10, 19,
    10, 11, 7, 11, 5, 4, 10, 4, 10, 0, 7, 11, 5, 10, 10, 4, 10, 11, 7, 11, 5, 6,
    10, 4, 10, 0, 7, 11};

static unsigned ed_cycles(unsigned opcode) {
  static const uint8_t columns[]={12,12,15,20,8,14,8};
  static const uint8_t last_column[]={9,9,9,9,18,18,8,8};
  if((opcode&0xc0)==0x40) {
    const unsigned column=opcode&7;
    return column==7?last_column[(opcode>>3)&7]:columns[column];
  }
  return (opcode&0xe4)==0xa0?16:8; // Block instructions and undefined opcodes.
}

static const uint8_t cyc_ddfd_low[64] = {
     4,  4,  4,  4,  4,  4,  4,  4,  4, 15,  4,  4,  4,  4,  4,  4,
     4,  4,  4,  4,  4,  4,  4,  4,  4, 15,  4,  4,  4,  4,  4,  4,
     4, 14, 20, 10,  8,  8, 11,  4,  4, 15, 20, 10,  8,  8, 11,  4,
     4,  4,  4,  4, 23, 23, 19,  4,  4, 15,  4,  4,  4,  4,  4,  4,
};
static const uint8_t cyc_ddfd_high[32] = {
     4, 14,  4, 23,  4, 15,  4,  4,  4,  8,  4,  4,  4,  4,  4,  4,
     4,  4,  4,  4,  4,  4,  4,  4,  4, 10,  4,  4,  4,  4,  4,  4,
};

static unsigned ddfd_cycles(unsigned opcode) {
  if(opcode<0x40) return cyc_ddfd_low[opcode];
  if(opcode>=0xe0) return cyc_ddfd_high[opcode&31];
  if(opcode>=0xc0) return opcode==0xcb?0:4;
  if(opcode==0x76) return 4; // HALT ignores the prefix.
  // LD and ALU use the same operand encoding. Only LD can write an
  // indexed register or (IX/IY+d), so consider its destination as well.
  const unsigned src=opcode&7,dst=opcode<0x80?(opcode>>3)&7:0;
  if(src==6 || dst==6) return 19;
  return (src&6)==4 || (dst&6)==4?8:4;
}

// MARK: helpers

static inline bool bus_timed(const z80* z) {
#ifdef Z80_NO_WAIT_STATES
    (void)z;return false;
#else
    return z->wait!=NULL;
#endif
}

/* Combine LDIR repeats only within the caller's interrupt/time slice.
 * Read/write views must already be hot; a clean cached page traps its first
 * store before it becomes writable here. Keep forward-overlap semantics and
 * reject a destination that can modify either opcode byte through an alias. */
static void block_copy(z80* z) {
    const unsigned pc=z->pc,hl=z->hl,de=z->de,mask=z->contention_mask;
    const bool timed=bus_timed(z);
    const bool contended=timed && ((pc&mask)==0x4000 || (hl&mask)==0x4000 || (de&mask)==0x4000);
    const uint32_t end=contended?z->ldir_contended_until:z->ldir_until;
    const int32_t budget=(int32_t)(end-(uint32_t)z->cyc);
    if(budget<4*21 || z->nmi_pending || z->iff_delay || z->halted || (z->int_pending && z->iff1)) return;
    const unsigned offset=pc&16383;
    const uint8_t* code=z->read_map[pc>>14];
    unsigned code_left=16384-offset;
    if(code) code+=offset;
    else {
        code=z->read_pages[pc>>10];code_left=1024-(pc&1023);
        if(code) code+=pc&1023;
    }
    if(!code || code_left<2 || code[0]!=0xED || code[1]!=0xB0) return;
    if(z->m1 && ((uint16_t)(pc-z->m1_start)<=z->m1_limit || (uint16_t)(pc+1-z->m1_start)<=z->m1_limit)) return;
    unsigned count=(unsigned)budget/21;
    if(count>z->bc) count=z->bc;
    const uint8_t* from=z->read_map[hl>>14];
    uint8_t* to=z->write_map[de>>14];
    unsigned src_left=16384-(hl&16383),dst_left=16384-(de&16383);
    if(from) from+=hl&16383;
    else {
        from=z->read_pages[hl>>10];src_left=1024-(hl&1023);
        if(from) from+=hl&1023;
    }
    if(to) to+=de&16383;
    else {
        to=z->write_pages[de>>10];dst_left=1024-(de&1023);
        if(to) to+=de&1023;
    }
    if(!from || !to) return;
    if(count>src_left) count=src_left;
    if(count>dst_left) count=dst_left;
    if(count<4) return;
    const uintptr_t src=(uintptr_t)from,dst=(uintptr_t)to,instruction=(uintptr_t)code;
    if(dst<instruction+2 && dst+count>instruction) return;
    if(dst==src+1) memset(to,*from,count);
    else if((src>=dst && src-dst>=count) || (dst>=src && dst-src>=count)) memcpy(to,from,count);
    else for(unsigned i=0;i<count;++i) to[i]=from[i];
    const uint8_t result=(uint8_t)(to[count-1]+z->a);
    z->hl=(uint16_t)(hl+count);z->de=(uint16_t)(de+count);z->bc-=count;
    z->f=(z->f&0xC1)|(result&8)|((result&2)<<4)|(z->bc?4:0);
    z->r=(z->r&128)|((z->r+2*count)&127);
    z->mem_ptr=(uint16_t)(pc+1);
    const unsigned cycles=21*count-(z->bc?0:5);
    z->cyc+=cycles;if(!z->bc) z->pc+=2;
    if(timed) z->bus=(uint32_t)z->cyc;
}


// get bit "n" of number "val"
#define GET_BIT(n, val) (((val) >> (n)) & 1)

#if defined(__GNUC__)
#define Z80_HOT_INLINE __attribute__((always_inline))
#else
#define Z80_HOT_INLINE
#endif

static void contend_bus(z80* z,unsigned duration) {
  const unsigned delay=z->wait(z->userdata,z->bus);
  z->bus+=duration+delay;z->cyc+=delay;
}
static inline Z80_HOT_INLINE void bus_cycle(z80* z,uint16_t address,unsigned duration) {
  if((address&z->contention_mask)==0x4000) contend_bus(z,duration);
  else z->bus+=duration;
}

/* Internal cycles may keep a contended address on the bus for several
 * individual T-states. Opcode refresh is part of its single 4T access. */
static void idle_bus(z80* z,uint16_t address,unsigned count) {
  if(!bus_timed(z)) return;
  if((address&z->contention_mask)!=0x4000) z->bus+=count;
  else while(count--) contend_bus(z,1);
}
static uint16_t ir(const z80* z) { return (uint16_t)((z->i<<8)|z->r); }

static inline Z80_HOT_INLINE uint8_t read_mapped(z80* const z, uint16_t addr) {
  const uint8_t* base=z->read_pages[addr>>10];
  if(base) return base[addr&1023];
  return z->read_byte(z->userdata,addr);
}

static inline uint8_t rb(z80* const z, uint16_t addr) {
  if(bus_timed(z)) bus_cycle(z,addr,3);
  return read_mapped(z,addr);
}

static inline void wb(z80* const z, uint16_t addr, uint8_t val) {
  if(bus_timed(z)) {
    bus_cycle(z,addr,3);
    if(z->before_store) z->before_store(z->userdata,addr,z->bus);
  }
  uint8_t* base=z->write_pages[addr>>10];
  if(base) { base[addr&1023]=val;return; }
  z->write_byte(z->userdata, addr, val);
}

/* Z80's register encoding is shared by LD and the byte ALU. Decode it
 * once instead of retaining a separate operand-fetch body per register. */
static const uint8_t register_offsets[8]={offsetof(z80,b),offsetof(z80,c),offsetof(z80,d),offsetof(z80,e),
    offsetof(z80,h),offsetof(z80,l),0,offsetof(z80,a)};
static const uint8_t pair_offsets[4]={offsetof(z80,bc),offsetof(z80,de),offsetof(z80,hl),offsetof(z80,sp)};
static inline uint16_t* register_pair(z80* z,unsigned opcode) {
  return (uint16_t*)((uint8_t*)z+pair_offsets[(opcode>>4)&3]);
}
_Static_assert(offsetof(z80,a)<256 && offsetof(z80,l)<256,"Byte register offsets must fit");
static inline Z80_HOT_INLINE uint8_t reg_byte(z80* z,unsigned reg) {
  return reg==6?rb(z,z->hl):*((uint8_t*)z+register_offsets[reg]);
}
static inline Z80_HOT_INLINE void set_reg_byte(z80* z,unsigned reg,uint8_t value) {
  if(reg==6)wb(z,z->hl,value);else *((uint8_t*)z+register_offsets[reg])=value;
}

static inline uint16_t rw(z80* const z, uint16_t addr) {
  const uint8_t low=rb(z,addr);
  return (rb(z,(uint16_t)(addr+1))<<8)|low;
}

static inline void ww(z80* const z, uint16_t addr, uint16_t val) {
  wb(z, addr, val & 0xFF);
  wb(z, (uint16_t)(addr + 1), val >> 8);
}

static inline void pushw(z80* const z, uint16_t val) {
  wb(z,--z->sp,val>>8);
  wb(z,--z->sp,val&255);
}
static void push(z80* z,uint16_t value) { idle_bus(z,ir(z),1);pushw(z,value); }
static uint16_t exchange_stack(z80* z,uint16_t value) {
  const uint16_t high=(uint16_t)(z->sp+1);
  const uint16_t saved=rw(z,z->sp);
  idle_bus(z,high,1);
  wb(z,high,value>>8);wb(z,z->sp,value&255);
  idle_bus(z,z->sp,2);
  return saved;
}

static inline uint16_t popw(z80* const z) {
  z->sp += 2;
  return rw(z, z->sp - 2);
}

static inline Z80_HOT_INLINE uint8_t nextb(z80* const z) {
  return rb(z, z->pc++);
}
#if defined(__GNUC__)
__attribute__((noinline))
#endif
static uint8_t opcode_notify(z80* const z, uint16_t address) {
  z->m1(z->userdata,address,true);
  const uint8_t value=read_mapped(z,z->pc++);
  if(z->m1) z->m1(z->userdata,address,false);
  return value;
}
static inline Z80_HOT_INLINE uint8_t mapped_opcode(z80* const z,uint16_t address) {
  if(z->m1 && (uint16_t)(address-z->m1_start)<=z->m1_limit)
    return opcode_notify(z,address);
  return read_mapped(z,z->pc++);
}
static inline Z80_HOT_INLINE uint8_t opcode_byte(z80* const z) {
  const uint16_t address=z->pc;
  if(bus_timed(z)) bus_cycle(z,address,4);
  return mapped_opcode(z,address);
}

static inline uint16_t nextw(z80* const z) {
  z->pc += 2;
  return rw(z, z->pc - 2);
}

static void io_cycle(z80* z,uint16_t port) {
  if(!bus_timed(z)) {z->io_at=(uint32_t)z->cyc;return;}
  bus_cycle(z,port,1);
  if(!(port&1)) contend_bus(z,3);
  else idle_bus(z,port,3);
  z->io_at=z->bus;
}
static uint8_t input(z80* z,uint16_t port) { io_cycle(z,port);return z->port_in(z,port); }
static void output(z80* z,uint16_t port,uint8_t value) { io_cycle(z,port);z->port_out(z,port,value); }

static inline uint16_t get_bc(z80* const z) {
  return z->bc;
}

static inline uint16_t get_de(z80* const z) {
  return z->de;
}

static inline uint16_t get_hl(z80* const z) {
  return z->hl;
}

static inline void set_bc(z80* const z, uint16_t val) {
  z->bc = val;
}

static inline void set_de(z80* const z, uint16_t val) {
  z->de = val;
}

static inline void set_hl(z80* const z, uint16_t val) {
  z->hl = val;
}

static inline uint8_t get_f(z80* const z) { return z->f; }
static inline void set_f(z80* const z, uint8_t val) { z->f=val; }

// increments R, keeping the highest byte intact
static inline Z80_HOT_INLINE void inc_r(z80* const z) {
  z->r = (z->r & 0x80) | ((z->r + 1) & 0x7f);
}

/* S/Z/undocumented 5/3/parity depend only on the result byte. Keep them
 * together, avoiding eight separate F updates and an eight-iteration
 * parity loop on Cortex-M0+. Arithmetic replaces P with overflow. */
static const uint8_t szp_flags[256] = {
  0x44, 0x00, 0x00, 0x04, 0x00, 0x04, 0x04, 0x00, 0x08, 0x0c, 0x0c, 0x08, 0x0c, 0x08, 0x08, 0x0c,
  0x00, 0x04, 0x04, 0x00, 0x04, 0x00, 0x00, 0x04, 0x0c, 0x08, 0x08, 0x0c, 0x08, 0x0c, 0x0c, 0x08,
  0x20, 0x24, 0x24, 0x20, 0x24, 0x20, 0x20, 0x24, 0x2c, 0x28, 0x28, 0x2c, 0x28, 0x2c, 0x2c, 0x28,
  0x24, 0x20, 0x20, 0x24, 0x20, 0x24, 0x24, 0x20, 0x28, 0x2c, 0x2c, 0x28, 0x2c, 0x28, 0x28, 0x2c,
  0x00, 0x04, 0x04, 0x00, 0x04, 0x00, 0x00, 0x04, 0x0c, 0x08, 0x08, 0x0c, 0x08, 0x0c, 0x0c, 0x08,
  0x04, 0x00, 0x00, 0x04, 0x00, 0x04, 0x04, 0x00, 0x08, 0x0c, 0x0c, 0x08, 0x0c, 0x08, 0x08, 0x0c,
  0x24, 0x20, 0x20, 0x24, 0x20, 0x24, 0x24, 0x20, 0x28, 0x2c, 0x2c, 0x28, 0x2c, 0x28, 0x28, 0x2c,
  0x20, 0x24, 0x24, 0x20, 0x24, 0x20, 0x20, 0x24, 0x2c, 0x28, 0x28, 0x2c, 0x28, 0x2c, 0x2c, 0x28,
  0x80, 0x84, 0x84, 0x80, 0x84, 0x80, 0x80, 0x84, 0x8c, 0x88, 0x88, 0x8c, 0x88, 0x8c, 0x8c, 0x88,
  0x84, 0x80, 0x80, 0x84, 0x80, 0x84, 0x84, 0x80, 0x88, 0x8c, 0x8c, 0x88, 0x8c, 0x88, 0x88, 0x8c,
  0xa4, 0xa0, 0xa0, 0xa4, 0xa0, 0xa4, 0xa4, 0xa0, 0xa8, 0xac, 0xac, 0xa8, 0xac, 0xa8, 0xa8, 0xac,
  0xa0, 0xa4, 0xa4, 0xa0, 0xa4, 0xa0, 0xa0, 0xa4, 0xac, 0xa8, 0xa8, 0xac, 0xa8, 0xac, 0xac, 0xa8,
  0x84, 0x80, 0x80, 0x84, 0x80, 0x84, 0x84, 0x80, 0x88, 0x8c, 0x8c, 0x88, 0x8c, 0x88, 0x88, 0x8c,
  0x80, 0x84, 0x84, 0x80, 0x84, 0x80, 0x80, 0x84, 0x8c, 0x88, 0x88, 0x8c, 0x88, 0x8c, 0x8c, 0x88,
  0xa0, 0xa4, 0xa4, 0xa0, 0xa4, 0xa0, 0xa0, 0xa4, 0xac, 0xa8, 0xa8, 0xac, 0xa8, 0xac, 0xac, 0xa8,
  0xa4, 0xa0, 0xa0, 0xa4, 0xa0, 0xa4, 0xa4, 0xa0, 0xa8, 0xac, 0xac, 0xa8, 0xac, 0xa8, 0xa8, 0xac,
};
static void exec_opcode(z80* const z, uint8_t opcode);
static void exec_opcode_cb(z80* const z, uint8_t opcode);
static void exec_opcode_dcb(
    z80* const z, const uint8_t opcode, const uint16_t addr);
static void exec_opcode_ed(z80* const z, uint8_t opcode);
static void exec_opcode_ddfd(z80* const z, uint8_t opcode, uint16_t* const iz);

// MARK: opcodes
// jumps to an address
static inline void jump(z80* const z, uint16_t addr) {
  z->pc = addr;
  z->mem_ptr = addr;
}

// jumps to next word in memory if condition is true
static bool condition(const z80* z, uint8_t opcode) {
  static const uint8_t masks[]={0x40,0x01,0x04,0x80};
  return ((z->f&masks[(opcode>>4)&3])!=0)==((opcode&8)!=0);
}

static inline void cond_jump(z80* const z, bool condition) {
  const uint16_t addr = nextw(z);
  if (condition) {
    jump(z, addr);
  }
  z->mem_ptr = addr;
}

// calls to next word in memory
static inline void call(z80* const z, uint16_t addr) {
  pushw(z, z->pc);
  z->pc = addr;
  z->mem_ptr = addr;
}

// calls to next word in memory if condition is true
static inline void cond_call(z80* const z, bool condition) {
  const uint16_t addr = nextw(z);
  if (condition) {
    idle_bus(z,(uint16_t)(z->pc-1),1);
    call(z, addr);
    z->cyc += 7;
  }
  z->mem_ptr = addr;
}

// returns from subroutine
static inline void ret(z80* const z) {
  z->pc = popw(z);
  z->mem_ptr = z->pc;
}

// returns from subroutine if condition is true
static inline void cond_ret(z80* const z, bool condition) {
  idle_bus(z,ir(z),1);
  if (condition) {
    ret(z);
    z->cyc += 6;
  }
}

static inline void jr(z80* const z, int8_t displacement) {
  idle_bus(z,(uint16_t)(z->pc-1),5);
  z->pc += displacement;
  z->mem_ptr = z->pc;
}

static inline void cond_jr(z80* const z, bool condition) {
  const int8_t b = nextb(z);
  if (condition) {
    jr(z, b);
    z->cyc += 5;
  }
}

// ADD Byte: adds two bytes together
static inline uint8_t addb(z80* const z, uint8_t a, uint8_t b, bool cy) {
  const unsigned wide = (unsigned)a + b + cy;
  const uint8_t result = (uint8_t)wide;
  z->f = (szp_flags[result] & ~4U) | ((a ^ b ^ result) & 16) |
         ((~(a ^ b) & (a ^ result) & 128) >> 5) | (wide >> 8);
  return result;
}

// SUBstract Byte: substracts two bytes (with optional carry)
static inline uint8_t subb(z80* const z, uint8_t a, uint8_t b, bool cy) {
  const uint16_t wide = (uint16_t)((unsigned)a - b - cy);
  const uint8_t result = (uint8_t)wide;
  z->f = (szp_flags[result] & ~4U) | ((a ^ b ^ result) & 16) |
         (((a ^ b) & (a ^ result) & 128) >> 5) | ((wide >> 8) & 1) | 2;
  return result;
}

static __attribute__((noinline)) void add_pair(z80* z,uint16_t* reg,uint16_t val) {
  idle_bus(z,ir(z),7);
  const uint16_t before=*reg;
  const uint32_t wide=(uint32_t)before+val;
  const uint16_t result=(uint16_t)wide;
  z->f=(z->f&0xC4)|((result>>8)&0x28)|(((before^val^result)>>8)&0x10)|(wide>>16);
  z->mem_ptr=(uint16_t)(before+1);*reg=result;
}

static inline void adc_sbc_hl(z80* z,uint16_t value,bool subtract) {
  idle_bus(z,ir(z),7);
  const uint32_t before=z->hl,operand=(uint32_t)value+z->cf;
  const uint32_t wide=subtract?before-operand:before+operand;
  const uint16_t result=(uint16_t)wide;
  const unsigned differing_signs=before^value;
  const unsigned overflow=(before^result)&(subtract?differing_signs:~differing_signs);
  z->f=((result>>8)&0xa8)|(result?0:0x40)|(((before^value^result)>>8)&0x10)|
       ((overflow>>13)&4)|((wide>>16)&1)|(subtract?2:0);
  z->mem_ptr=(uint16_t)(before+1);z->hl=result;
}

/* Carry is preserved; the other INC/DEC flags depend only on the result.
 * These tables avoid per-opcode half-carry/overflow reconstruction. */
static uint8_t adjust_byte(z80* z, uint8_t a, bool decrement) {
  const unsigned subtract = (unsigned)decrement * 2;
  const uint8_t result = (uint8_t)(a + 1 - subtract);
  z->f = (z->f & 1) | (szp_flags[result] & ~4U) | ((a ^ result) & 16) |
         (a == 0x7f + (unsigned)decrement ? 4 : 0) | subtract;
  return result;
}
static inline uint8_t inc(z80* z,uint8_t a) { return adjust_byte(z,a,false); }
static inline uint8_t dec(z80* z,uint8_t a) { return adjust_byte(z,a,true); }

// MARK: bitwise

// executes a logic "and" between register A and a byte, then stores the
// result in register A
static inline void land(z80* const z, uint8_t val) {
  const uint8_t result = z->a & val;
  z->f = szp_flags[result] | 16;
  z->a = result;
}

// executes a logic "xor" between register A and a byte, then stores the
// result in register A
static inline void lxor(z80* const z, const uint8_t val) {
  const uint8_t result = z->a ^ val;
  z->f = szp_flags[result];
  z->a = result;
}

// executes a logic "or" between register A and a byte, then stores the
// result in register A
static inline void lor(z80* const z, const uint8_t val) {
  const uint8_t result = z->a | val;
  z->f = szp_flags[result];
  z->a = result;
}

// compares a value with register A
static inline void cp(z80* const z, const uint8_t val) {
  subb(z, z->a, val, 0);

  // the only difference between cp and sub is that
  // the xf/yf are taken from the value to be substracted,
  // not the result
  z->f = (z->f & ~0x28U) | (val & 0x28);
}

static __attribute__((noinline)) void byte_alu(z80* z, unsigned operation, uint8_t value) {
  switch(operation) {
  case 0: case 1: z->a=addb(z,z->a,value,(operation&1) && z->cf);break;
  case 2: case 3: z->a=subb(z,z->a,value,(operation&1) && z->cf);break;
  case 4: land(z,value);break;
  case 5: lxor(z,value);break;
  case 6: lor(z,value);break;
  case 7: cp(z,value);break;
  }
}

#if defined(MK61_TARGET_PICOCALC)
static uint32_t dec_memory_end(z80* z,uint32_t time) {
  time+=3+z->wait(z->userdata,time);
  time+=1+z->wait(z->userdata,time);
  return time+3+z->wait(z->userdata,time);
}

static const uint8_t* repeat_code(const z80* z,unsigned length) {
  const unsigned pc=z->pc,offset=pc&1023;
  if(z->m1 || z->nmi_pending || z->iff_delay || (z->int_pending && z->iff1) ||
     (pc&z->contention_mask)==0x4000 || ((z->i<<8)&z->contention_mask)==0x4000 || offset>1024-length) return NULL;
  const uint8_t* page=z->read_pages[pc>>10];
  return page?page+offset:NULL;
}

/* DJNZ -2 has no data accesses. Leave its final iteration to the
 * interpreter and keep the refresh register exact. */
static void repeat_djnz(z80* z,unsigned budget) {
  if(z->b<5) return;
  const uint8_t* code=repeat_code(z,2);
  if(!code || code[0]!=0x10 || code[1]!=0xfe) return;
  unsigned count=budget/13;
  if(count>=z->b) count=z->b-1;
  z->b=(uint8_t)(z->b-count);
  z->r=(z->r&128)|((z->r+count)&127);
  z->cyc+=count*13;z->bus=(uint32_t)z->cyc;
}

/* BIT n,(HL) / JR Z holds a read-only mapped byte until the next IRQ or
 * scheduler turn. The contended read and its internal cycle still wait. */
static void repeat_bit_poll(z80* z,unsigned budget) {
  const uint8_t* code=repeat_code(z,4);
  if(!code || code[0]!=0xcb || (code[1]&0xc7)!=0x46 || code[2]!=0x28 || code[3]!=0xfc) return;
  const unsigned hl=z->hl;
  const uint8_t* data=z->read_pages[hl>>10];
  if(!data || (data[hl&1023]&(1u<<((code[1]>>3)&7)))) return;
  unsigned count=budget/24,elapsed=count*24;
  if((hl&z->contention_mask)==0x4000) {
    const uint32_t first=(uint32_t)z->cyc+8;
    count=elapsed=0;
    while(budget-elapsed>=24) {
      const uint32_t read=first+elapsed;
      const unsigned wait=z->wait(z->userdata,read);
      const unsigned duration=24+wait+z->wait(z->userdata,read+3+wait);
      if(duration>budget-elapsed) break;
      elapsed+=duration;++count;
    }
  }
  if(!count) return;
  z->f=(z->f&1u)|0x54u|((z->pc>>8)&0x28u);
  z->r=(z->r&128)|((z->r+3*count)&127);
  z->cyc+=elapsed;z->bus=(uint32_t)z->cyc;
}

/* Read loops in the 48K ROM until the next EAR edge or CPU slice. At the
 * taken JR Z, INC B cannot wrap and both conditional returns stay untaken.
 * An input span certifies the keyboard bit and the EAR level separately. */
static void repeat_edge_poll(z80* z,unsigned budget) {
  static const uint8_t loop[]={0x04,0xc8,0x3e,0x7f,0xdb,0xfe,0x1f,0xd0,0xa9,0xe6,0x20,0x28,0xf3};
  const uint8_t* code=repeat_code(z,sizeof(loop));
  if(!code || memcmp(code,loop,sizeof(loop))) return;
  const unsigned span=z->port_span(z,0x7ffe,0x41,(uint8_t)(1+((z->c&0x20)<<1)));
  if(budget>span) budget=span;
  const uint32_t begin=(uint32_t)z->cyc;
  unsigned elapsed=0,count=0;
  while(budget-elapsed>=59 && count<255u-z->b) {
    // The IN's first bus cycle starts at 23T. Both parts of port
    // 7FFE are contended, even when the routine is sourced from ROM.
    const uint32_t first=begin+elapsed+23;
    const unsigned wait=z->wait(z->userdata,first);
    const unsigned duration=59+wait+z->wait(z->userdata,first+1+wait);
    if(duration>budget-elapsed) break;
    elapsed+=duration;++count;
  }
  if(!count) return;
  z->b=(uint8_t)(z->b+count);z->a=0;z->f=0x54;
  z->r=(z->r&128)|((z->r+9*count)&127);
  z->io_at=begin+elapsed-32;
  z->cyc+=elapsed;z->bus=(uint32_t)z->cyc;
}

/* Batch the taken iterations of exact fill and verify/clear loops. The
 * writable view must be stable and no instruction or store observer may
 * need the intermediate state. Exits and mismatches use scalar execution. */
static void repeat_memory_loop(z80* z,unsigned budget,bool verify) {
  static const uint8_t check[]={0xa7,0xed,0x52,0x19,0x23,0x30,0x06,0x35,0x28,0x03,0x35,0x28,0xf3};
  static const uint8_t fill[]={0x36,0x02,0x2b,0xbc,0x20,0xfa};
  const unsigned hl=z->hl;
  const unsigned length=verify?sizeof(check):6;
  if(z->before_store) return;
  const uint8_t* code=repeat_code(z,length);
  if(verify && hl>=z->de) return;
  const unsigned address=hl+verify,page=address>>10;
  uint8_t* dst=z->write_pages[page];
  if(!code || !dst) return;
  unsigned taken;
  if(memcmp(code,verify?check:fill,length)) return;
  if(verify) {
    if(z->read_pages[page]!=dst) return;
    taken=z->de-hl;
  } else {
    const unsigned next=(uint16_t)(hl-1);
    if((next>>8)==z->a) return;
    taken=(uint16_t)(next-((z->a<<8)|255));
  }
  const unsigned offset=address&1023,available=verify?1024-offset:offset+1;
  unsigned count=verify?budget/84:budget/32;
  if(count>taken) count=taken;
  if(count>available) count=available;
  if(count<4) return;
  uint8_t* first=dst+(verify?offset:available-count);
  if((uintptr_t)first<(uintptr_t)code+length && (uintptr_t)first+count>(uintptr_t)code) return;
  const bool contended=(address&z->contention_mask)==0x4000;
  unsigned elapsed;
  if(verify) {
    // From AND A to the first read of DEC (HL) is 47T. There are 11T
    // from its store to the second read and 12T from the final store
    // to the end of the taken JR Z. Both DEC instructions preserve C.
    const uint32_t start=(uint32_t)z->cyc;
    unsigned done=0;elapsed=0;
    while(done<count && first[done]==2) {
      const uint32_t now=start+elapsed;
      const unsigned cycles=contended?dec_memory_end(z,dec_memory_end(z,now+47)+11)+12-now:84;
      if(cycles>budget-elapsed) break;
      first[done++]=0;elapsed+=cycles;
    }
    if(!done) return;
    z->hl=(uint16_t)(hl+done);z->f=0x43;
    count=done*10;
  } else {
    elapsed=count*32;
    if(contended) {
      const uint32_t store=(uint32_t)z->cyc+7;
      unsigned done=0;elapsed=0;
      while(done<count && budget-elapsed>=32) {
        const unsigned wait=z->wait(z->userdata,store+elapsed);
        if(wait>budget-elapsed-32) break;
        elapsed+=32+wait;++done;
      }
      count=done;
      if(count<4) return;
    }
    memset(dst+available-count,2,count);
    z->hl=(uint16_t)(hl-count);cp(z,z->h);
    count*=4;
  }
  z->r=(z->r&128)|((z->r+count)&127);
  z->cyc+=elapsed;z->bus=(uint32_t)z->cyc;
}
#endif

// 0xCB opcodes
// rotate left with carry
static inline uint8_t cb_rlc(z80* const z, uint8_t val) {
  const bool old = val >> 7;
  val = (val << 1) | old;
  z->f = szp_flags[val] | old;
  return val;
}

// rotate right with carry
static inline uint8_t cb_rrc(z80* const z, uint8_t val) {
  const bool old = val & 1;
  val = (val >> 1) | (old << 7);
  z->f = szp_flags[val] | old;
  return val;
}

// rotate left (simple)
static inline uint8_t cb_rl(z80* const z, uint8_t val) {
  const bool cf = z->cf;
  const bool old = val >> 7;
  val = (val << 1) | cf;
  z->f = szp_flags[val] | old;
  return val;
}

// rotate right (simple)
static inline uint8_t cb_rr(z80* const z, uint8_t val) {
  const bool c = z->cf;
  const bool old = val & 1;
  val = (val >> 1) | (c << 7);
  z->f = szp_flags[val] | old;
  return val;
}

// shift left preserving sign
static inline uint8_t cb_sla(z80* const z, uint8_t val) {
  const bool old = val >> 7;
  val <<= 1;
  z->f = szp_flags[val] | old;
  return val;
}

// SLL (exactly like SLA, but sets the first bit to 1)
static inline uint8_t cb_sll(z80* const z, uint8_t val) {
  const bool old = val >> 7;
  val <<= 1;
  val |= 1;
  z->f = szp_flags[val] | old;
  return val;
}

// shift right preserving sign
static inline uint8_t cb_sra(z80* const z, uint8_t val) {
  const bool old = val & 1;
  val = (val >> 1) | (val & 0x80); // 0b10000000
  z->f = szp_flags[val] | old;
  return val;
}

// shift register right
static inline uint8_t cb_srl(z80* const z, uint8_t val) {
  const bool old = val & 1;
  val >>= 1;
  z->f = szp_flags[val] | old;
  return val;
}

static __attribute__((noinline)) uint8_t cb_rotate(z80* z, unsigned operation, uint8_t value) {
  switch(operation) {
  case 0: return cb_rlc(z,value);
  case 1: return cb_rrc(z,value);
  case 2: return cb_rl(z,value);
  case 3: return cb_rr(z,value);
  case 4: return cb_sla(z,value);
  case 5: return cb_sra(z,value);
  case 6: return cb_sll(z,value);
  default: return cb_srl(z,value);
  }
}

// tests bit "n" from a byte
static inline void cb_bit(z80* const z, uint8_t val, uint8_t n) {
  const uint8_t result = val & (1 << n);
  z->f=(z->f&1)|(val&0x28)|0x10|(result?(result&0x80):0x44);
}

static inline void ldx(z80* const z,int step) {
  const uint16_t de = get_de(z);
  const uint16_t hl = get_hl(z);
  const uint8_t val = rb(z, hl);

  wb(z, de, val);
  idle_bus(z,de,2);

  set_hl(z, get_hl(z) + step);
  set_de(z, get_de(z) + step);
  set_bc(z, get_bc(z) - 1);

  // see https://wikiti.brandonw.net/index.php?title=Z80_Instruction_Set
  // for the calculation of xf/yf on LDI
  const uint8_t result = val + z->a;
  z->f=(z->f&0xc1)|(result&8)|((result&2)<<4)|(z->bc?4:0);
}

static inline void cpx(z80* const z,int step) {
  bool cf = z->cf;
  const uint8_t result = subb(z, z->a, rb(z, get_hl(z)), 0);
  idle_bus(z,z->hl,5);
  set_hl(z, get_hl(z) + step);
  set_bc(z, get_bc(z) - 1);
  const uint8_t adjusted=(uint8_t)(result-z->hf);
  z->f=(z->f&0xd2)|cf|(adjusted&8)|((adjusted&2)<<4)|(z->bc?4:0);
  z->mem_ptr += step;
}

static void in_r_c(z80* const z, uint8_t* r) {
  *r = input(z, get_bc(z));
  z->f=(z->f&0x29)|(szp_flags[*r]&0xc4);
}

static void inx(z80* const z,int step) {
  idle_bus(z,ir(z),1);
  uint8_t val = input(z, get_bc(z));
  wb(z, get_hl(z), val);
  set_hl(z, get_hl(z) + step);
  z->b -= 1;
  z->zf = z->b == 0;
  z->nf = 1;
  z->mem_ptr = get_bc(z) + (step>0?1:-2);
}

static void outx(z80* const z,int step) {
  idle_bus(z,ir(z),1);
  const uint8_t value=rb(z,z->hl);
  --z->b;
  output(z,z->bc,value);
  set_hl(z, get_hl(z) + step);
  z->zf = z->b == 0;
  z->nf = 1;
  z->mem_ptr = get_bc(z) + (step>0?1:-2);
}

static void repeat_ed(z80* z,uint16_t address) {
  idle_bus(z,address,5);
  z->pc-=2;
  z->cyc+=5;
}

static void daa(z80* const z) {
  // "When this instruction is executed, the A register is BCD corrected
  // using the  contents of the flags. The exact process is the following:
  // if the least significant four bits of A contain a non-BCD digit
  // (i. e. it is greater than 9) or the H flag is set, then $06 is
  // added to the register. Then the four most significant bits are
  // checked. If this more significant digit also happens to be greater
  // than 9 or the C flag is set, then $60 is added."
  // > http://z80-heaven.wikidot.com/instructions-set:daa
  uint8_t correction = 0;

  if ((z->a & 0x0F) > 0x09 || z->hf) {
    correction += 0x06;
  }

  if (z->a > 0x99 || z->cf) {
    correction += 0x60;
    z->cf = 1;
  }

  const bool substraction = z->nf;
  if (substraction) {
    z->hf = z->hf && (z->a & 0x0F) < 0x06;
    z->a -= correction;
  } else {
    z->hf = (z->a & 0x0F) > 0x09;
    z->a += correction;
  }

  z->f=(z->f&0x13)|szp_flags[z->a];
}

static uint16_t index_address(z80* z,uint16_t base_addr,unsigned internal) {
  const int8_t displacement=(int8_t)nextb(z);
  idle_bus(z,(uint16_t)(z->pc-1),internal);
  const uint16_t addr = base_addr + displacement;
  z->mem_ptr = addr;
  return addr;
}

static inline void process_interrupts(z80* const z) {
  // "When an EI instruction is executed, any pending interrupt request
  // is not accepted until after the instruction following EI is executed."
  if (z->iff_delay > 0) {
    z->iff_delay -= 1;
    if (z->iff_delay == 0) {
      z->iff1 = 1;
      z->iff2 = 1;
    }
    return;
  }

  if (z->nmi_pending) {
    z->nmi_pending = 0;
    z->halted = 0;
    z->iff1 = 0;
    inc_r(z);

    if(bus_timed(z)) z->bus=(uint32_t)z->cyc+5;
    z->cyc += 11;
    call(z, 0x66);
    return;
  }

  if (z->int_pending && z->iff1) {
    z->int_pending = 0;
    z->halted = 0;
    z->iff1 = 0;
    z->iff2 = 0;
    inc_r(z);

    if(bus_timed(z)) z->bus=(uint32_t)z->cyc+7;
    switch (z->interrupt_mode) {
    case 0:
      /* An IM0 acknowledge replaces the normal opcode fetch. */
      if(bus_timed(z)) --z->bus;
      z->cyc += 2;
      exec_opcode(z, z->int_data);
      break;

    case 1:
      z->cyc += 13;
      call(z, 0x38);
      break;

    case 2:
      z->cyc += 19;
      pushw(z,z->pc);
      jump(z,rw(z,(z->i<<8)|z->int_data));
      break;

    default:
      Z80_DIAGNOSTIC("unsupported interrupt mode %d\n", z->interrupt_mode);
      break;
    }

    return;
  }
}

// MARK: interface
// initialises a z80 struct. Note that read_byte, write_byte, port_in, port_out
// and userdata must be manually set by the user afterwards.
void z80_init(z80* const z) {
  z->read_byte = NULL;
  z->write_byte = NULL;
  z->port_in = NULL;
  z->port_out = NULL;
  z->userdata = NULL;
  z->m1 = NULL;
  z->m1_start=0;z->m1_limit=65535;
  for(unsigned i=0;i<4;++i) { z->read_map[i]=NULL;z->write_map[i]=NULL; }
  for(unsigned i=0;i<64;++i) { z->read_pages[i]=NULL;z->write_pages[i]=NULL; }
  z->ldir_until=z->ldir_contended_until=0;
  z->wait=NULL;z->before_store=NULL;z->port_span=NULL;z->bus=z->io_at=0;z->contention_mask=0xc000;

  z->cyc = 0;

  z->pc = 0;
  z->sp = 0xFFFF;
  z->ix = 0;
  z->iy = 0;
  z->mem_ptr = 0;

  // af and sp are set to 0xFFFF after reset,
  // and the other values are undefined (z80-documented)
  z->a = 0xFF;
  z->b = 0;
  z->c = 0;
  z->d = 0;
  z->e = 0;
  z->h = 0;
  z->l = 0;

  z->a_ = 0;
  z->b_ = 0;
  z->c_ = 0;
  z->d_ = 0;
  z->e_ = 0;
  z->h_ = 0;
  z->l_ = 0;
  z->f_ = 0;

  z->i = 0;
  z->r = 0;

  z->f = 0xff;

  z->iff_delay = 0;
  z->interrupt_mode = 0;
  z->iff1 = 0;
  z->iff2 = 0;
  z->halted = 0;
  z->int_pending = 0;
  z->nmi_pending = 0;
  z->int_data = 0;
}

/* One dispatcher serves both single-opcode prefix/IM0 calls (cycles=0)
 * and instruction batches. Its stack frame is paid once per batch, not
 * for every emulated instruction. Interrupts still run after each one. */
static uint32_t execute(z80* z,uint32_t cycles,const bool* stop,uint8_t opcode);

// executes the next instruction in memory + handles interrupts
void z80_step(z80* const z) { (void)execute(z,1,NULL,0); }

uint32_t z80_run(z80* z, uint32_t cycles, const bool* stop) {
  if (cycles>INT32_MAX) cycles=INT32_MAX;
  return cycles?execute(z,cycles,stop,0):0;
}

// outputs to stdout a debug trace of the emulator
void z80_debug_output(z80* const z) {
  printf("PC: %04X, AF: %04X, BC: %04X, DE: %04X, HL: %04X, SP: %04X, "
         "IX: %04X, IY: %04X, I: %02X, R: %02X",
      z->pc, (z->a << 8) | get_f(z), get_bc(z), get_de(z), get_hl(z), z->sp,
      z->ix, z->iy, z->i, z->r);

  printf("\t(%02X %02X %02X %02X), cyc: %lu\n", rb(z, z->pc), rb(z, z->pc + 1),
      rb(z, z->pc + 2), rb(z, z->pc + 3), z->cyc);
}

// function to call when an NMI is to be serviced
void z80_gen_nmi(z80* const z) {
  z->nmi_pending = 1;
}

// function to call when an INT is to be serviced
void z80_gen_int(z80* const z, uint8_t data) {
  z->int_pending = 1;
  z->int_data = data;
}

// executes a non-prefixed opcode
void exec_opcode(z80* const z, uint8_t opcode) {
  (void)execute(z,0,NULL,opcode);
}

#if defined(__GNUC__) && !defined(__clang__)
/* Keep the bus-timed and ordinary paths within the PicoCalc APP slot. */
__attribute__((optimize("Os")))
#endif
static uint32_t execute(z80* z,uint32_t cycles,const bool* stop,uint8_t opcode) {
  const unsigned long before=z->cyc;
  for(;;) {
    if(cycles) {
      if((uint32_t)(z->cyc-before)>=cycles || (stop && *stop))break;
      const bool halted=z->halted;
      const uint16_t address=z->pc-halted;
      if(bus_timed(z)) {
        const uint32_t start=(uint32_t)z->cyc;
        if((address&z->contention_mask)==0x4000) {
          z->bus=start;contend_bus(z,4);
        } else z->bus=start+4;
      }
      opcode=halted?0:mapped_opcode(z,address);
    }
  z->cyc += cyc_00[opcode];
  inc_r(z);

  switch (opcode) {
  case 0x40: case 0x41: case 0x42: case 0x43: case 0x44: case 0x45: case 0x46: case 0x47:
  case 0x48: case 0x49: case 0x4A: case 0x4B: case 0x4C: case 0x4D: case 0x4E: case 0x4F:
  case 0x50: case 0x51: case 0x52: case 0x53: case 0x54: case 0x55: case 0x56: case 0x57:
  case 0x58: case 0x59: case 0x5A: case 0x5B: case 0x5C: case 0x5D: case 0x5E: case 0x5F:
  case 0x60: case 0x61: case 0x62: case 0x63: case 0x64: case 0x65: case 0x66: case 0x67:
  case 0x68: case 0x69: case 0x6A: case 0x6B: case 0x6C: case 0x6D: case 0x6E: case 0x6F:
  case 0x70: case 0x71: case 0x72: case 0x73: case 0x74: case 0x75: case 0x77:
  case 0x78: case 0x79: case 0x7A: case 0x7B: case 0x7C: case 0x7D: case 0x7E: case 0x7F:
    set_reg_byte(z,(opcode>>3)&7,reg_byte(z,opcode&7));break; // ld r,r / r,(hl) / (hl),r

  case 0x3E: z->a = nextb(z); break; // ld a,*
  case 0x06: z->b = nextb(z); break; // ld b,*
  case 0x0E: z->c = nextb(z); break; // ld c,*
  case 0x16: z->d = nextb(z); break; // ld d,*
  case 0x1E: z->e = nextb(z); break; // ld e,*
  case 0x26: z->h = nextb(z); break; // ld h,*
  case 0x2E: z->l = nextb(z); break; // ld l,*
  case 0x36: wb(z, get_hl(z), nextb(z)); break; // ld (hl),*

  case 0x0A:
    z->a = rb(z, get_bc(z));
    z->mem_ptr = get_bc(z) + 1;
    break; // ld a,(bc)
  case 0x1A:
    z->a = rb(z, get_de(z));
    z->mem_ptr = get_de(z) + 1;
    break; // ld a,(de)
  case 0x3A: {
    const uint16_t addr = nextw(z);
    z->a = rb(z, addr);
    z->mem_ptr = addr + 1;
  } break; // ld a,(**)

  case 0x02:
    wb(z, get_bc(z), z->a);
    z->mem_ptr = (z->a << 8) | ((get_bc(z) + 1) & 0xFF);
    break; // ld (bc),a

  case 0x12:
    wb(z, get_de(z), z->a);
    z->mem_ptr = (z->a << 8) | ((get_de(z) + 1) & 0xFF);
    break; // ld (de),a

  case 0x32: {
    const uint16_t addr = nextw(z);
    wb(z, addr, z->a);
    z->mem_ptr = (z->a << 8) | ((addr + 1) & 0xFF);
  } break; // ld (**),a

  case 0x01: set_bc(z, nextw(z)); break; // ld bc,**
  case 0x11: set_de(z, nextw(z)); break; // ld de,**
  case 0x21: set_hl(z, nextw(z)); break; // ld hl,**
  case 0x31: z->sp = nextw(z); break; // ld sp,**

  case 0x2A: {
    const uint16_t addr = nextw(z);
    set_hl(z, rw(z, addr));
    z->mem_ptr = addr + 1;
  } break; // ld hl,(**)

  case 0x22: {
    const uint16_t addr = nextw(z);
    ww(z, addr, get_hl(z));
    z->mem_ptr = addr + 1;
  } break; // ld (**),hl

  case 0xF9: idle_bus(z,ir(z),2);z->sp = get_hl(z); break; // ld sp,hl

  case 0xEB: {
    const uint16_t de = get_de(z);
    set_de(z, get_hl(z));
    set_hl(z, de);
  } break; // ex de,hl

  case 0xE3: {
    const uint16_t val = exchange_stack(z,get_hl(z));
    set_hl(z, val);
    z->mem_ptr = val;
  } break; // ex (sp),hl

  case 0x80: case 0x81: case 0x82: case 0x83: case 0x84: case 0x85: case 0x86: case 0x87:
  case 0x88: case 0x89: case 0x8A: case 0x8B: case 0x8C: case 0x8D: case 0x8E: case 0x8F:
  case 0x90: case 0x91: case 0x92: case 0x93: case 0x94: case 0x95: case 0x96: case 0x97:
  case 0x98: case 0x99: case 0x9A: case 0x9B: case 0x9C: case 0x9D: case 0x9E: case 0x9F:
  case 0xA0: case 0xA1: case 0xA2: case 0xA3: case 0xA4: case 0xA5: case 0xA6: case 0xA7:
  case 0xA8: case 0xA9: case 0xAA: case 0xAB: case 0xAC: case 0xAD: case 0xAE: case 0xAF:
  case 0xB0: case 0xB1: case 0xB2: case 0xB3: case 0xB4: case 0xB5: case 0xB6: case 0xB7:
  case 0xB8: case 0xB9: case 0xBA: case 0xBB: case 0xBC: case 0xBD: case 0xBE: case 0xBF:
    byte_alu(z,(opcode>>3)&7,reg_byte(z,opcode&7));break;
  case 0xC6: case 0xCE: case 0xD6: case 0xDE: case 0xE6: case 0xEE: case 0xF6: case 0xFE:
    byte_alu(z,(opcode>>3)&7,nextb(z));break;

  case 0x09: case 0x19: case 0x29: case 0x39:
    add_pair(z,&z->hl,*register_pair(z,opcode));break;

  case 0xF3:
    z->iff1 = 0;
    z->iff2 = 0;
    break; // di
  case 0xFB: z->iff_delay = 1; break; // ei
  case 0x00: break; // nop
  case 0x76: z->halted = 1; break; // halt

  case 0x04: case 0x0c: case 0x14: case 0x1c: case 0x24: case 0x2c: case 0x34: case 0x3c:
  case 0x05: case 0x0d: case 0x15: case 0x1d: case 0x25: case 0x2d: case 0x35: case 0x3d: {
    const unsigned reg=(opcode>>3)&7;
    const uint8_t old=reg_byte(z,reg);
    const uint8_t result=adjust_byte(z,old,opcode&1);
    if(reg==6) idle_bus(z,z->hl,1);
    set_reg_byte(z,reg,result);
  } break;

  case 0x03: case 0x13: case 0x23: case 0x33:
  case 0x0B: case 0x1B: case 0x2B: case 0x3B:
    idle_bus(z,ir(z),2);*register_pair(z,opcode)+=(opcode&8)?-1:1;break;

  case 0x27: daa(z); break; // daa

  case 0x2F:
    z->a = ~z->a;
    z->nf = 1;
    z->hf = 1;
    z->xf = GET_BIT(3, z->a);
    z->yf = GET_BIT(5, z->a);
    break; // cpl

  case 0x37:
    z->cf = 1;
    z->nf = 0;
    z->hf = 0;
    z->xf = GET_BIT(3, z->a);
    z->yf = GET_BIT(5, z->a);
    break; // scf

  case 0x3F:
    z->hf = z->cf;
    z->cf = !z->cf;
    z->nf = 0;
    z->xf = GET_BIT(3, z->a);
    z->yf = GET_BIT(5, z->a);
    break; // ccf

  case 0x07: {
    z->cf = z->a >> 7;
    z->a = (z->a << 1) | z->cf;
    z->nf = 0;
    z->hf = 0;
    z->xf = GET_BIT(3, z->a);
    z->yf = GET_BIT(5, z->a);
  } break; // rlca (rotate left)

  case 0x0F: {
    z->cf = z->a & 1;
    z->a = (z->a >> 1) | (z->cf << 7);
    z->nf = 0;
    z->hf = 0;
    z->xf = GET_BIT(3, z->a);
    z->yf = GET_BIT(5, z->a);
  } break; // rrca (rotate right)

  case 0x17: {
    const bool cy = z->cf;
    z->cf = z->a >> 7;
    z->a = (z->a << 1) | cy;
    z->nf = 0;
    z->hf = 0;
    z->xf = GET_BIT(3, z->a);
    z->yf = GET_BIT(5, z->a);
  } break; // rla

  case 0x1F: {
    const bool cy = z->cf;
    z->cf = z->a & 1;
    z->a = (z->a >> 1) | (cy << 7);
    z->nf = 0;
    z->hf = 0;
    z->xf = GET_BIT(3, z->a);
    z->yf = GET_BIT(5, z->a);
  } break; // rra

  case 0xC3: jump(z, nextw(z)); break; // jm **
  case 0xC2: case 0xCA: case 0xD2: case 0xDA:
  case 0xE2: case 0xEA: case 0xF2: case 0xFA:
    cond_jump(z,condition(z,opcode));break;

  case 0x10: {
#if defined(MK61_TARGET_PICOCALC)
    const uint16_t pc=z->pc-1;
#endif
    idle_bus(z,ir(z),1);cond_jr(z,--z->b!=0);
#if defined(MK61_TARGET_PICOCALC)
    if(bus_timed(z) && z->pc==pc && (!stop || !*stop)) {
      const int32_t budget=(int32_t)(cycles-(uint32_t)(z->cyc-before));
      if(budget>=52) repeat_djnz(z,(unsigned)budget);
    }
#endif
  } break; // djnz *
  case 0x18: jr(z,nextb(z)); break; // jr *
  case 0x20: case 0x28: {
#if defined(MK61_TARGET_PICOCALC)
    const uint16_t after=z->pc+1;
#endif
    const bool verify=opcode==0x28;
    cond_jr(z, z->zf==verify);
#if defined(MK61_TARGET_PICOCALC)
    const unsigned back=(uint16_t)(after-z->pc);
    const bool bit_poll=verify && back==4;
    if(bus_timed(z) && (bit_poll || back==(verify?13:6)) && (!stop || !*stop)) {
      const int32_t budget=(int32_t)(cycles-(uint32_t)(z->cyc-before));
      if(budget>=4*32) {
        if(bit_poll) repeat_bit_poll(z,(unsigned)budget);
        else if(verify && z->pc==0x05ed && z->port_span) repeat_edge_poll(z,(unsigned)budget);
        else repeat_memory_loop(z,(unsigned)budget,verify);
      }
    }
#endif
  } break; // jr nz/z, *
  case 0x30: cond_jr(z, z->cf == 0); break; // jr nc, *
  case 0x38: cond_jr(z, z->cf == 1); break; // jr c, *

  case 0xE9: z->pc = get_hl(z); break; // jp (hl)
  case 0xCD: {
    const uint16_t addr=nextw(z);
    idle_bus(z,(uint16_t)(z->pc-1),1);
    call(z,addr);
  } break;

  case 0xC4: case 0xCC: case 0xD4: case 0xDC:
  case 0xE4: case 0xEC: case 0xF4: case 0xFC:
    cond_call(z,condition(z,opcode));break;

  case 0xC9: ret(z); break; // ret
  case 0xC0: case 0xC8: case 0xD0: case 0xD8:
  case 0xE0: case 0xE8: case 0xF0: case 0xF8:
    cond_ret(z,condition(z,opcode));break;

  case 0xC7: case 0xCF: case 0xD7: case 0xDF:
  case 0xE7: case 0xEF: case 0xF7: case 0xFF:
    idle_bus(z,ir(z),1);call(z,opcode&0x38);break;

  case 0xC5: push(z,get_bc(z)); break;
  case 0xD5: push(z,get_de(z)); break;
  case 0xE5: push(z,get_hl(z)); break;
  case 0xF5: push(z,(z->a<<8)|get_f(z)); break;

  case 0xC1: set_bc(z, popw(z)); break; // pop bc
  case 0xD1: set_de(z, popw(z)); break; // pop de
  case 0xE1: set_hl(z, popw(z)); break; // pop hl
  case 0xF1: {
    uint16_t val = popw(z);
    z->a = val >> 8;
    set_f(z, val & 0xFF);
  } break; // pop af

  case 0xDB: {
    const uint8_t port = nextb(z);
    const uint8_t a = z->a;
    z->a = input(z, (a << 8) | port);
    z->mem_ptr = (a << 8) | (z->a + 1);
  } break; // in a,(n)

  case 0xD3: {
    const uint8_t port = nextb(z);
    output(z, (z->a << 8) | port, z->a);
    z->mem_ptr = (port + 1) | (z->a << 8);
  } break; // out (n), a

  case 0x08: {
    uint8_t a = z->a;
    uint8_t f = get_f(z);

    z->a = z->a_;
    set_f(z, z->f_);

    z->a_ = a;
    z->f_ = f;
  } break; // ex af,af'
  case 0xD9: {
    const uint16_t bc=z->bc,de=z->de,hl=z->hl;
    z->bc=z->bc_;z->de=z->de_;z->hl=z->hl_;
    z->bc_=bc;z->de_=de;z->hl_=hl;
  } break; // exx

  case 0xCB: exec_opcode_cb(z, opcode_byte(z)); break;
  case 0xED: exec_opcode_ed(z, opcode_byte(z)); break;
  case 0xDD: exec_opcode_ddfd(z, opcode_byte(z), &z->ix); break;
  case 0xFD: exec_opcode_ddfd(z, opcode_byte(z), &z->iy); break;

  default: Z80_DIAGNOSTIC("unknown opcode %02X\n", opcode); break;
  }
    if(!cycles)break;
    process_interrupts(z);
    if(z->halted)break;
  }
  return (uint32_t)(z->cyc-before);
}

// executes a DD/FD opcode (IZ = IX or IY)
void exec_opcode_ddfd(z80* const z, uint8_t opcode, uint16_t* const iz) {
  z->cyc += ddfd_cycles(opcode);
  inc_r(z);

#define IZD index_address(z,*iz,5)
#define IZH (*iz >> 8)
#define IZL (*iz & 0xFF)

  const unsigned from=opcode&7,to=(opcode>>3)&7;
  if(opcode>=0x40 && opcode<0x80 && opcode!=0x76 && (from==6 || to==6)) {
    // The memory forms use H and L unchanged, even with a DD or FD prefix.
    const uint16_t addr=IZD;
    if(to==6) wb(z,addr,reg_byte(z,from));
    else set_reg_byte(z,to,rb(z,addr));
    return;
  }
  if(opcode>=0x40 && opcode<0x80 && opcode!=0x76 && ((from&6)==4 || (to&6)==4)) {
    const unsigned val=from==4?IZH:from==5?IZL:reg_byte(z,from);
    if(to==4) *iz=(uint16_t)(IZL|val<<8);
    else if(to==5) *iz=(uint16_t)((*iz&0xff00)|val);
    else set_reg_byte(z,to,(uint8_t)val);
    return;
  }
  if(opcode>=0x80 && opcode<0xc0 && from>=4 && from<=6) {
    byte_alu(z,to,from==4?IZH:from==5?IZL:rb(z,IZD));
    return;
  }

  switch (opcode) {
  case 0xE1: *iz = popw(z); break; // pop iz
  case 0xE5: push(z,*iz); break; // push iz

  case 0xE9: jump(z, *iz); break; // jp iz

  case 0x09: case 0x19: case 0x29: case 0x39:
    add_pair(z,iz,opcode==0x29?*iz:*register_pair(z,opcode));break;

  case 0x23: idle_bus(z,ir(z),2);*iz += 1; break; // inc iz
  case 0x2B: idle_bus(z,ir(z),2);*iz -= 1; break; // dec iz

  case 0x34: {
    uint16_t addr = IZD;
    const uint8_t value=inc(z,rb(z,addr));
    idle_bus(z,addr,1);wb(z,addr,value);
  } break; // inc (iz+*)

  case 0x35: {
    uint16_t addr = IZD;
    const uint8_t value=dec(z,rb(z,addr));
    idle_bus(z,addr,1);wb(z,addr,value);
  } break; // dec (iz+*)

  case 0x24: *iz = IZL | ((inc(z, IZH)) << 8); break; // inc izh
  case 0x25: *iz = IZL | ((dec(z, IZH)) << 8); break; // dec izh
  case 0x2C: *iz = (IZH << 8) | inc(z, IZL); break; // inc izl
  case 0x2D: *iz = (IZH << 8) | dec(z, IZL); break; // dec izl

  case 0x2A: *iz = rw(z, nextw(z)); break; // ld iz,(**)
  case 0x22: ww(z, nextw(z), *iz); break; // ld (**),iz
  case 0x21: *iz = nextw(z); break; // ld iz,**

  case 0x36: {
    const uint16_t addr=index_address(z,*iz,0);
    const uint8_t value=nextb(z);
    idle_bus(z,(uint16_t)(z->pc-1),2);wb(z,addr,value);
  } break; // ld (iz+*),*

  case 0x26: *iz = (uint16_t)(IZL | (nextb(z) << 8)); break; // ld izh,*
  case 0x2E: *iz = (uint16_t)((IZH << 8) | nextb(z)); break; // ld izl,*

  case 0xF9: idle_bus(z,ir(z),2);z->sp = *iz; break; // ld sp,iz

  case 0xE3: {
    const uint16_t val = exchange_stack(z,*iz);
    *iz = val;
    z->mem_ptr = val;
  } break; // ex (sp),iz

  case 0xCB: {
    uint16_t addr = index_address(z,*iz,0);
    uint8_t op = nextb(z);
    idle_bus(z,(uint16_t)(z->pc-1),2);
    exec_opcode_dcb(z, op, addr);
  } break;

  default: {
    // any other FD/DD opcode behaves as a non-prefixed opcode:
    exec_opcode(z, opcode);
    // R should not be incremented twice:
    z->r = (z->r & 0x80) | ((z->r - 1) & 0x7f);
  } break;
  }

#undef IZD
#undef IZH
#undef IZL
}

// executes a CB opcode
void exec_opcode_cb(z80* const z, uint8_t opcode) {
  z->cyc += 8;
  inc_r(z);

  const unsigned operation=opcode>>6,bit=(opcode>>3)&7,reg=opcode&7;
  uint8_t value=reg_byte(z,reg);
  if(reg==6) idle_bus(z,z->hl,1);
  switch(operation) {
  case 0: value=cb_rotate(z,bit,value);break;
  case 1:
    cb_bit(z,value,bit);
    if(reg==6) {
      z->f=(z->f&~0x28)|((z->mem_ptr>>8)&0x28);
      z->cyc+=4;
    }
    return;
  case 2: value&=~(1u<<bit);break;
  default: value|=1u<<bit;break;
  }
  if(reg==6) z->cyc+=7;
  set_reg_byte(z,reg,value);
}

// executes a displaced CB opcode (DDCB or FDCB)
void exec_opcode_dcb(z80* const z, uint8_t opcode, uint16_t addr) {
  uint8_t val = rb(z, addr);
  idle_bus(z,addr,1);
  uint8_t result = 0;

  // decoding instructions from http://z80.info/decoding.htm#ddcb
  uint8_t x_ = (opcode >> 6) & 3; // 0b11
  uint8_t y_ = (opcode >> 3) & 7; // 0b111
  uint8_t z_ = opcode & 7; // 0b111

  switch (x_) {
  case 0: result=cb_rotate(z,y_,val);break;
  case 1: {
    cb_bit(z,val,y_);
    z->f=(z->f&~0x28)|((addr>>8)&0x28);
  } break; // bit y,(iz+d)
  case 2: result = val & ~(1 << y_); break; // res y, (iz+d)
  case 3: result = val | (1 << y_); break; // set y, (iz+d)

  default: Z80_DIAGNOSTIC("unknown XYCB opcode: %02X\n", opcode); break;
  }

  // ld r[z], rot[y] (iz+d)
  // ld r[z], res y,(iz+d)
  // ld r[z], set y,(iz+d)
  if(x_!=1 && z_!=6) set_reg_byte(z,z_,result);

  if (x_ == 1) {
    // bit instructions take 20 cycles, others take 23
    z->cyc += 20;
  } else {
    wb(z, addr, result);
    z->cyc += 23;
  }
}

// executes a ED opcode
void exec_opcode_ed(z80* const z, uint8_t opcode) {
  z->cyc += ed_cycles(opcode);
  inc_r(z);
  if((opcode&0xc7)==0x40) {
    const unsigned reg=(opcode>>3)&7;
    uint8_t value;
    in_r_c(z,reg==6?&value:(uint8_t*)z+register_offsets[reg]);
    if(reg==7) z->mem_ptr=z->bc+1;
    return;
  }
  switch (opcode) {
  case 0x47: idle_bus(z,ir(z),1);z->i = z->a; break; // ld i,a
  case 0x4F: idle_bus(z,ir(z),1);z->r = z->a; break; // ld r,a

  case 0x57: // ld a,i
  case 0x5F:
    idle_bus(z,ir(z),1);
    z->a=opcode&8?z->r:z->i;
    z->f=(z->f&0x29)|(szp_flags[z->a]&0xc0)|(z->iff2?4:0);
    break; // ld a,r

  case 0x45:
  case 0x55:
  case 0x5D:
  case 0x65:
  case 0x6D:
  case 0x75:
  case 0x7D:
    z->iff1 = z->iff2;
    ret(z);
    break; // retn
  case 0x4D: ret(z); break; // reti

  case 0xA0: case 0xA8: case 0xB8:
  case 0xB0: {
    const int step=opcode&8?-1:1;
    ldx(z,step);
    if((opcode&16) && z->bc) {
      repeat_ed(z,(uint16_t)(z->de-step));
      z->mem_ptr=z->pc+1;
      if(step>0 && z->ldir_until) block_copy(z);
    }
  } break; // ldi/ldd/ldir/lddr

  case 0xA1: case 0xA9: case 0xB1:
  case 0xB9: {
    const int step=opcode&8?-1:1;
    cpx(z,step);
    if(opcode&16) {
      if(z->bc && !z->zf) {
        repeat_ed(z,(uint16_t)(z->hl-step));
        if(step>0) z->mem_ptr=z->pc+1;
      } else ++z->mem_ptr;
    }
  } break; // cpi/cpd/cpir/cpdr

  case 0xA2: case 0xAA: case 0xB2: case 0xBA: {
    const int step=opcode&8?-1:1;
    inx(z,step);
    if((opcode&16) && z->b) repeat_ed(z,(uint16_t)(z->hl-step));
  } break; // ini/ind/inir/indr

  case 0x41: case 0x49: case 0x51: case 0x59: case 0x61: case 0x69:
    output(z,z->bc,reg_byte(z,(opcode>>3)&7));break;
  case 0x71: output(z,z->bc,0); break; // out (c), 0
  case 0x79:
    output(z,z->bc,z->a);
    z->mem_ptr = get_bc(z) + 1;
    break; // out (c), a

  case 0xA3: case 0xAB: case 0xB3: case 0xBB:
    outx(z,opcode&8?-1:1);
    if((opcode&16) && z->b) repeat_ed(z,z->bc);
    break; // outi/outd/otir/otdr

  case 0x42: case 0x52: case 0x62: case 0x72:
  case 0x4A: case 0x5A: case 0x6A: case 0x7A:
    adc_sbc_hl(z,*register_pair(z,opcode),!(opcode&8));break;
  case 0x43: case 0x53: case 0x63: case 0x73: {
    const uint16_t addr=nextw(z);
    ww(z,addr,*register_pair(z,opcode));
    z->mem_ptr=addr+1;
  } break;
  case 0x4B: case 0x5B: case 0x6B: case 0x7B: {
    const uint16_t addr=nextw(z);
    *register_pair(z,opcode)=rw(z,addr);
    z->mem_ptr=addr+1;
  } break;

  case 0x44:
  case 0x54:
  case 0x64:
  case 0x74:
  case 0x4C:
  case 0x5C:
  case 0x6C:
  case 0x7C: z->a = subb(z, 0, z->a, 0); break; // neg

  case 0x46:
  case 0x66: z->interrupt_mode = 0; break; // im 0
  case 0x56:
  case 0x76: z->interrupt_mode = 1; break; // im 1
  case 0x5E:
  case 0x7E: z->interrupt_mode = 2; break; // im 2

  case 0x67: // rrd
  case 0x6F: {
    const uint8_t a=z->a,val=rb(z,z->hl);
    idle_bus(z,z->hl,4);
    if(opcode&8) {
      z->a=(a&0xf0)|(val>>4);
      wb(z,z->hl,(val<<4)|(a&15));
    } else {
      z->a=(a&0xf0)|(val&15);
      wb(z,z->hl,(val>>4)|(a<<4));
    }
    z->f=(z->f&1)|szp_flags[z->a];
    z->mem_ptr=z->hl+1;
  } break; // rld

  default: Z80_DIAGNOSTIC("unknown ED opcode: %02X\n", opcode); break;
  }
}

#undef GET_BIT
