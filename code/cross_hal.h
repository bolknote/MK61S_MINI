#ifndef MK61_MK52_CROSS_HAL
#define MK61_MK52_CROSS_HAL

#include "rust_types.h"
#include "keyboard.h"

class __attribute__((__packed__)) TMK61_cross_key {
  public:
    u8 x, y;
    u16 as_u16(void) const {
      return *(u16*) this;
    }
};

#if defined(MK61_KEYBOARD_CLASSIC)
static const u32               KEY_Px     =   23;
static const u32               KEY_xP     =   22;
static const u32               KEY_BP     =   21;
static const u32               KEY_PP     =   20;
static const u32               KEY_RUN    =   25;
static const u32               KEY_RET    =   26;
static const u32               KEY_FRW    =   28;
static const u32               KEY_BKW    =   27;
static const u32               KEY_BASIC  =   34;
static const u32               KEY_K      =   24;
static const u32               KEY_F      =   29;
static const u32               KEY_ESC    =   39;

static constexpr i32 KEY_PUSH_B   =   5;
static constexpr i32 KEY_DEGREE   =   30;
static constexpr i32 KEY_EPOWER   =   1;
static constexpr i32 KEY_NEG      =   3;
static constexpr i32 KEY_GRADE    =   31;
static constexpr i32 KEY_RADIAN   =   32;
static constexpr i32 KEY_USER     =   35;
static constexpr i32 KEY_SAVE     =   34;
static constexpr i32 KEY_LOAD     =   33;
static constexpr i32 KEY_LEFT     =   38;
static constexpr i32 KEY_RIGHT    =   36;
static constexpr i32 KEY_ALPHA    =   KEY_F;
static constexpr i32 KEY_OK       =   37;

enum class sw : u32 {
  CX  =00, POW, NEG, DOT, _0,
  Bx  =05, XY,  _3,  _2,  _1,
  MUL =10, ADD, _6,  _5,  _4,
  DIV =15, SUB, _9,  _8,  _7,
  JSR =20, JP,  xP,  Px,  K,
  RUN =25, RET, FW,  BK,  F,
  NON =30, NO1, NO2, NO3, NO4
};

#else
static const u32               KEY_Px     =   28;
static const u32               KEY_xP     =   27;
static const u32               KEY_BP     =   26;
static const u32               KEY_PP     =   25;
static const u32               KEY_RUN    =   30;
static const u32               KEY_RET    =   31;
static const u32               KEY_FRW    =   32;
static const u32               KEY_BKW    =   33;
static const u32               KEY_K      =   37;
static const u32               KEY_F      =   38;
static const u32               KEY_ESC    =   39;

static constexpr i32 KEY_PUSH_B   =   1;
static constexpr i32 KEY_DEGREE   =   4;
static constexpr i32 KEY_EPOWER   =   5;
static constexpr i32 KEY_NEG      =   10;
static constexpr i32 KEY_GRADE    =   9;
static constexpr i32 KEY_RADIAN   =   14;
static constexpr i32 KEY_USER     =   19;
static constexpr i32 KEY_SAVE     =   36;
static constexpr i32 KEY_LOAD     =   35;
static constexpr i32 KEY_LEFT     =   34;
static constexpr i32 KEY_RIGHT    =   24;
static constexpr i32 KEY_ALPHA    =   KEY_F;
static constexpr i32 KEY_OK       =   29;

enum class sw : u32 {
  CX  =00, Bx, MUL, DIV,
  POW =05, XY, ADD, SUB,
  NEG =10, _3, _6, _9, 
  DOT =15, _2, _5, _8, 
  _0  =20, _1, _4, _7, 
  JSR =25, JP, xP, Px,
  RUN =30, RET, FW, BK,
  NON =35, NO1, K, F
};
#endif

static const i32 KEY_LOAD_PRESS   =   KEY_LOAD  | (i32) key_state::PRESSED;
static const i32 KEY_USER_PRESS   =   KEY_USER  | (i32) key_state::PRESSED;
static const i32 KEY_ESC_PRESS    =   KEY_ESC   | (i32) key_state::PRESSED;
static const i32 KEY_LEFT_PRESS   =   KEY_LEFT  | (i32) key_state::PRESSED;
static const i32 KEY_RIGHT_PRESS  =   KEY_RIGHT | (i32) key_state::PRESSED;
static const i32 KEY_OK_PRESS     =   KEY_OK    | (i32) key_state::PRESSED;
static const i32 KEY_RUN_PRESS    =   KEY_RUN   | (i32) key_state::PRESSED;
static const i32 KEY_FRW_PRESS    =   KEY_FRW   | (i32) key_state::PRESSED;
static const i32 KEY_BKW_PRESS    =   KEY_BKW   | (i32) key_state::PRESSED;
#if defined(MK61_KEYBOARD_MINI)
static const i32 KEY_SHG_RIGHT_PRESS = KEY_BKW_PRESS;
static const i32 KEY_SHG_LEFT_PRESS  = KEY_FRW_PRESS;
#else
static const i32 KEY_SHG_RIGHT_PRESS = KEY_FRW_PRESS;
static const i32 KEY_SHG_LEFT_PRESS  = KEY_BKW_PRESS;
#endif

static const i32 KEY_USER_RELEASE =   KEY_USER  | (i32) key_state::RELEASED;
static const i32 KEY_ESC_RELEASE  =   KEY_ESC   | (i32) key_state::RELEASED;
static const i32 KEY_RUN_RELEASE  =   KEY_RUN   | (i32) key_state::RELEASED;

constexpr u32 seq(sw KEY0, sw KEY1, sw KEY2, sw KEY3) {return i32 ( ((u32) KEY3 << 24) | ((u32) KEY2 << 16) | ((u32) KEY1 << 8) | (u32) KEY0 );}
constexpr u32 seq(sw KEY0, sw KEY1, sw KEY2) {return i32 (0xFF000000 | ( ((u32) KEY2 << 16) | ((u32) KEY1 << 8) | (u32) KEY0 ));}
constexpr u32 seq(sw KEY0, sw KEY1) {return i32 (0xFFFF0000 | ( ((u32) KEY1 << 8) | (u32) KEY0 ));}
constexpr u32 seq(sw KEY) {return (i32) i32 (0xFFFFFF00 | (u32) KEY);}

static const TMK61_cross_key   NON     =   {.x=0, .y=0};
static const TMK61_cross_key   F       =   {.x=11, .y=9};  // F
static const TMK61_cross_key   K       =   {.x=10, .y=9};  // K
static const TMK61_cross_key   SB      =   {.x=7, .y=9};   // ШГ->
static const TMK61_cross_key   SF      =   {.x=9, .y=9};   // ШГ<-
static const TMK61_cross_key   Px      =   {.x=8, .y=9};   // П->X
static const TMK61_cross_key   xP      =   {.x=6, .y=9};   // X->П
static const TMK61_cross_key   _0_     =   {.x=2, .y=1};   // 0
static const TMK61_cross_key   _1_     =   {.x=3, .y=1};   // 1
static const TMK61_cross_key   _2_     =   {.x=4, .y=1};   // 2
static const TMK61_cross_key   _3_     =   {.x=5, .y=1};   // 3
static const TMK61_cross_key   _4_     =   {.x=6, .y=1};   // 4
static const TMK61_cross_key   _5_     =   {.x=7, .y=1};   // 5
static const TMK61_cross_key   _6_     =   {.x=8, .y=1};   // 6
static const TMK61_cross_key   _7_     =   {.x=9, .y=1};   // 7
static const TMK61_cross_key   _8_     =   {.x=10, .y=1};  // 8
static const TMK61_cross_key   _9_     =   {.x=11, .y=1};  // 9
static const TMK61_cross_key   SUB     =   {.x=3, .y=8};   // -
static const TMK61_cross_key   ADD     =   {.x=2, .y=8};   // +
static const TMK61_cross_key   DIV     =   {.x=5, .y=8};   // /
static const TMK61_cross_key   MUL     =   {.x=4, .y=8};   // *
static const TMK61_cross_key   DOT     =   {.x=7, .y=8};   // .
static const TMK61_cross_key   POW     =   {.x=9, .y=8};   // ВП
static const TMK61_cross_key   NEG     =   {.x=8, .y=8};   // /-/
static const TMK61_cross_key   Cx      =   {.x=10, .y=8};  // Cx
static const TMK61_cross_key   Bx      =   {.x=11, .y=8};  // Bx
static const TMK61_cross_key   XY      =   {.x=6, .y=8};   // X<->Y
static const TMK61_cross_key   RET     =   {.x=4, .y=9};   // В/О
static const TMK61_cross_key   JMP     =   {.x=3, .y=9};   // БП
static const TMK61_cross_key   JSR     =   {.x=5, .y=9};   // ПП
static const TMK61_cross_key   RUN     =   {.x=2, .y=9};   // С/П

extern const TMK61_cross_key KeyPairs[40];

struct TMnemo {
  u8      fix;
  char*   txt;
};

extern const char* mnemo_code[40];
extern const u8    mnemo_code_register[40];
extern const char* mnemo_code_F[40];
extern const char* mnemo_code_K[40];
static const u8    STORE_KEY = 0x80;

#endif
