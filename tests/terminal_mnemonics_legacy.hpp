#ifndef MK61_TERMINAL_MNEMONICS_LEGACY_HPP
#define MK61_TERMINAL_MNEMONICS_LEGACY_HPP

// Frozen assembler vocabulary before the M8 migration (669a29817^).
// Keep independent of the production generator to detect shifted opcodes.
static constexpr char LEGACY_ISA_61[] =
"0,1,2,3,4,5,6,7,8,9,dot,neg,pow10,clr,push,preX,\
add,sub,mul,div,swap,e10,exp,lg,ln,asin,acos,atg,sin,cos,tg,?,\
pi,sqrt,sqr,rec,pow,rot,toM,?,?,?,toMS,?,?,?,?,?,\
inMS,mod,sgn,inM,int,frc,max,and,or,xor,not,rnd,?,?,?,?,\
sto0,sto1,sto2,sto3,sto4,sto5,sto6,sto7,sto8,sto9,stoA,stoB,stoC,stoD,stoE,?,\
hlt,jmp,ret,call,nop,?,?,jz,rpt2,jl,rpt3,rpt1,jme,rpt0,jnz,?,\
ld0,ld1,ld2,ld3,ld4,ld5,ld6,ld7,ld8,ld9,ldA,ldB,ldC,ldD,ldE,?,\
jz[0],jz[1],jz[2],jz[3],jz[4],jz[5],jz[6],jz[7],jz[8],jz[9],jz[A],jz[B],jz[C],jz[D],jz[E],?,\
jmp[0],jmp[1],jmp[2],jmp[3],jmp[4],jmp[5],jmp[6],jmp[7],jmp[8],jmp[9],jmp[A],jmp[B],jmp[C],jmp[D],jmp[E],?,\
jlz[0],jlz[1],jlz[2],jlz[3],jlz[4],jlz[5],jlz[6],jlz[7],jlz[8],jlz[9],jlz[A],jlz[B],jlz[C],jlz[D],jlz[E],?,\
call[0],call[1],call[2],call[3],call[4],call[5],call[6],call[7],call[8],call[9],call[A],call[B],call[C],call[D],call[E],?,\
sto[0],sto[1],sto[2],sto[3],sto[4],sto[5],sto[6],sto[7],sto[8],sto[9],sto[A],sto[B],sto[C],sto[D],sto[E],?,\
jme[0],jme[1],jme[2],jme[3],jme[4],jme[5],jme[6],jme[7],jme[8],jme[9],jme[A],jme[B],jme[C],jme[D],jme[E],?,\
ld[0],ld[1],ld[2],ld[3],ld[4],ld[5],ld[6],ld[7],ld[8],ld[9],ld[A],ld[B],ld[C],ld[D],ld[E],?,\
jnz[0],jnz[1],jnz[2],jnz[3],jnz[R4],jnz[5],jnz[6],jnz[7],jnz[8],jnz[9],jnz[A],jnz[B],jnz[C],jnz[D],jnz[E],?";

#endif
