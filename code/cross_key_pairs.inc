// Core key coordinates; no display or board driver dependencies.
#ifdef SCAN_ROW
const TMK61_cross_key KeyPairs[40] = {
  NON, NON, NON, NON, NON, NON, NON, NON,
  F,   SB,  Px,  _7_, _8_, _9_,  SUB, DIV,
  K,   SF,  xP,  _4_, _5_, _6_,  ADD, MUL,
  NON, RET, JMP, _1_, _2_, _3_,  XY,   Bx,
  NON, RUN, JSR, _0_, DOT, NEG, POW,  Cx
};

#else
#if defined(MK61_KEYBOARD_CLASSIC)
const TMK61_cross_key KeyPairs[40] = {
   Cx, POW, NEG, DOT, _0_,
   Bx,  XY, _3_, _2_, _1_,
  MUL, ADD, _6_, _5_, _4_,
  DIV, SUB, _9_, _8_, _7_,
  JSR, JMP,  xP,  Px,   K,
  RUN, RET,  SF,  SB,   F,
  NON, NON, NON, NON, NON,
  NON, NON, NON, NON, NON
};
#else
const TMK61_cross_key KeyPairs[40] = {
   Cx,  Bx, MUL, DIV, NON,
  POW,  XY, ADD, SUB, NON,
  NEG, _3_, _6_, _9_, NON,
  DOT, _2_, _5_, _8_, NON,
  _0_, _1_, _4_, _7_, NON,
  JSR, JMP,  xP,  Px, NON,
  RUN, RET,  SF,  SB, NON,
  NON, NON,   K,   F, NON
};
#endif

#endif // SCAN_ROW
