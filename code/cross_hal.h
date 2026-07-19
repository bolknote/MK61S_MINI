#ifndef MK61_MK52_CROSS_HAL
#define MK61_MK52_CROSS_HAL

#include "rust_types.h"
#include "keyboard.h"
#include "keyboard_layout.hpp"

class __attribute__((__packed__)) TMK61_cross_key {
  public:
    u8 x, y;
    u16 as_u16(void) const {
      return (u16) x | ((u16) y << 8);
    }
};

static constexpr i32 KEY_Px       = keyboard_layout::ACTIVE.p_to_x;
static constexpr i32 KEY_xP       = keyboard_layout::ACTIVE.x_to_p;
static constexpr i32 KEY_CX       = keyboard_layout::ACTIVE.cx;
static constexpr i32 KEY_BP       = keyboard_layout::ACTIVE.bp;
static constexpr i32 KEY_PP       = keyboard_layout::ACTIVE.pp;
static constexpr i32 KEY_RUN      = keyboard_layout::ACTIVE.run;
static constexpr i32 KEY_RET      = keyboard_layout::ACTIVE.ret;
static constexpr i32 KEY_FRW      = keyboard_layout::ACTIVE.frw;
static constexpr i32 KEY_BKW      = keyboard_layout::ACTIVE.bkw;
static constexpr i32 KEY_K        = keyboard_layout::ACTIVE.k;
static constexpr i32 KEY_F        = keyboard_layout::ACTIVE.alpha;
static constexpr i32 KEY_ESC      = keyboard_layout::ACTIVE.esc;

static constexpr i32 KEY_PUSH_B   = keyboard_layout::ACTIVE.bx;
static constexpr i32 KEY_DEGREE   = keyboard_layout::ACTIVE.degree;
static constexpr i32 KEY_EPOWER   = keyboard_layout::ACTIVE.power;
static constexpr i32 KEY_NEG      = keyboard_layout::ACTIVE.neg;
static constexpr i32 KEY_GRADE    = keyboard_layout::ACTIVE.grade;
static constexpr i32 KEY_RADIAN   = keyboard_layout::ACTIVE.radian;
static constexpr i32 KEY_USER     = keyboard_layout::ACTIVE.user;
static constexpr i32 KEY_SAVE     = keyboard_layout::ACTIVE.save;
static constexpr i32 KEY_LOAD     = keyboard_layout::ACTIVE.load;
static constexpr i32 KEY_LEFT     = keyboard_layout::ACTIVE.left;
static constexpr i32 KEY_RIGHT    = keyboard_layout::ACTIVE.right;
static constexpr i32 KEY_ALPHA    = keyboard_layout::ACTIVE.alpha;
static constexpr i32 KEY_OK       = keyboard_layout::ACTIVE.ok;

#if defined(MK61_KEYBOARD_CLASSIC)
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
static constexpr i32 KEY_SHG_RIGHT_PRESS = keyboard_layout::ACTIVE.shg_right;
static constexpr i32 KEY_SHG_LEFT_PRESS  = keyboard_layout::ACTIVE.shg_left;

static const i32 KEY_USER_RELEASE =   KEY_USER  | (i32) key_state::RELEASED;
static const i32 KEY_ESC_RELEASE  =   KEY_ESC   | (i32) key_state::RELEASED;
static const i32 KEY_RUN_RELEASE  =   KEY_RUN   | (i32) key_state::RELEASED;

constexpr u32 seq(sw KEY0, sw KEY1, sw KEY2, sw KEY3) {return i32 ( ((u32) KEY3 << 24) | ((u32) KEY2 << 16) | ((u32) KEY1 << 8) | (u32) KEY0 );}
constexpr u32 seq(sw KEY0, sw KEY1, sw KEY2) {return i32 (0xFF000000 | ( ((u32) KEY2 << 16) | ((u32) KEY1 << 8) | (u32) KEY0 ));}
constexpr u32 seq(sw KEY0, sw KEY1) {return i32 (0xFFFF0000 | ( ((u32) KEY1 << 8) | (u32) KEY0 ));}
constexpr u32 seq(sw KEY) {return (i32) i32 (0xFFFFFF00 | (u32) KEY);}

static const TMK61_cross_key   NON     =   {0, 0};
static const TMK61_cross_key   F       =   {11, 9};  // F
static const TMK61_cross_key   K       =   {10, 9};  // K
static const TMK61_cross_key   SB      =   {7, 9};   // ШГ->
static const TMK61_cross_key   SF      =   {9, 9};   // ШГ<-
static const TMK61_cross_key   Px      =   {8, 9};   // П->X
static const TMK61_cross_key   xP      =   {6, 9};   // X->П
static const TMK61_cross_key   _0_     =   {2, 1};   // 0
static const TMK61_cross_key   _1_     =   {3, 1};   // 1
static const TMK61_cross_key   _2_     =   {4, 1};   // 2
static const TMK61_cross_key   _3_     =   {5, 1};   // 3
static const TMK61_cross_key   _4_     =   {6, 1};   // 4
static const TMK61_cross_key   _5_     =   {7, 1};   // 5
static const TMK61_cross_key   _6_     =   {8, 1};   // 6
static const TMK61_cross_key   _7_     =   {9, 1};   // 7
static const TMK61_cross_key   _8_     =   {10, 1};  // 8
static const TMK61_cross_key   _9_     =   {11, 1};  // 9
static const TMK61_cross_key   SUB     =   {3, 8};   // -
static const TMK61_cross_key   ADD     =   {2, 8};   // +
static const TMK61_cross_key   DIV     =   {5, 8};   // /
static const TMK61_cross_key   MUL     =   {4, 8};   // *
static const TMK61_cross_key   DOT     =   {7, 8};   // .
static const TMK61_cross_key   POW     =   {9, 8};   // ВП
static const TMK61_cross_key   NEG     =   {8, 8};   // /-/
static const TMK61_cross_key   Cx      =   {10, 8};  // Cx
static const TMK61_cross_key   Bx      =   {11, 8};  // Bx
static const TMK61_cross_key   XY      =   {6, 8};   // X<->Y
static const TMK61_cross_key   RET     =   {4, 9};   // В/О
static const TMK61_cross_key   JMP     =   {3, 9};   // БП
static const TMK61_cross_key   JSR     =   {5, 9};   // ПП
static const TMK61_cross_key   RUN     =   {2, 9};   // С/П

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
