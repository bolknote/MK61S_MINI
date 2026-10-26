/* Correctly-rounded tangent function for binary64 value.

Copyright (c) 2022-2025 Paul Zimmermann and Tom Hubrecht

This file is part of the CORE-MATH project
(https://core-math.gitlabpages.inria.fr/).

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

#include <stdint.h>
#include <inttypes.h>
#include <fenv.h> // for fegetround, FE_TONEAREST, FE_DOWNWARD, FE_UPWARD
#ifdef CORE_MATH_SUPPORT_ERRNO
#include <errno.h>
#endif

// Warning: clang also defines __GNUC__
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC diagnostic ignored "-Wunknown-pragmas"
#endif

#pragma STDC FENV_ACCESS ON

/******************** code copied from dint.h and pow.[ch] *******************/

typedef mk61_u128 u128;

using dint64_t = ::core_m0_shared::Trig;


#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
typedef union {
  u128 r;
  struct {
    uint64_t l;
    uint64_t h;
  };
} uint128_t;
#else
typedef union {
  u128 r;
  struct {
    uint64_t h;
    uint64_t l;
  };
} uint128_t;
#endif

typedef union {
  double f;
  uint64_t u;
} f64_u;

// Extract both the mantissa and exponent of a double
static inline void fast_extract (int64_t *e, uint64_t *m, double x) {
  f64_u _x = {.f = x};

  *e = (_x.u >> 52) & 0x7ff;
  *m = (_x.u & (~0ull >> 12)) + (*e ? (1ull << 52) : 0);
  *e = *e - 0x3fe;
}

// Return non-zero if a = 0
static inline int
dint_zero_p (const dint64_t *a)
{
  return a->hi == 0;
}

static inline int cmp(int64_t a, int64_t b) { return (a > b) - (a < b); }

static inline int cmpu128 (u128 a, u128 b) { return (a > b) - (a < b); }

/* ZERO is a dint64_t representation of 0, which ensures that
   dint_tod(ZERO) = 0 */
static const dint64_t ZERO = {.lo=0x0, .hi=0x0, .ex = -1076, .sgn = 0x0};
/* ONE is a dint64_t representation of 1 */
static const dint64_t ONE = {
    .lo=0x0, .hi=0x8000000000000000, .ex = 1, .sgn = 0x0};
// MAGIC is a dint64_t representation of 1/2^11
static const dint64_t MAGIC = {.lo=0x0, .hi=0x8000000000000000, .ex = -10, .sgn = 0x0};

// Compare the absolute values of a and b
// Return -1 if |a| < |b|
// Return  0 if |a| = |b|
// Return +1 if |a| > |b|
static inline signed char
cmp_dint_abs (const dint64_t *a, const dint64_t *b) {
  if (dint_zero_p (a))
    return dint_zero_p (b) ? 0 : -1;
  if (dint_zero_p (b))
    return +1;
  char c1 = cmp (a->ex, b->ex);
  return c1 ? c1 : cmpu128 (a->r, b->r);
}

// Copy a dint64_t value
static inline void cp_dint(dint64_t *r, const dint64_t *a) {
  r->ex = a->ex;
  r->r = a->r;
  r->sgn = a->sgn;
}

// Add two dint64_t values, with error bounded by 2 ulps (ulp_128)
// (more precisely 1 ulp when a and b have same sign, 2 ulps otherwise)
// Moreover, when Sterbenz theorem applies, i.e., |b| <= |a| <= 2|b|
// and a,b are of different signs, there is no error, i.e., r = a-b.
static inline void
add_dint (dint64_t *r, const dint64_t *a, const dint64_t *b) {
  if (!(a->hi | a->lo)) {
    cp_dint (r, b);
    return;
  }

  switch (cmp_dint_abs (a, b)) {
  case 0:
    if (a->sgn ^ b->sgn) {
      cp_dint (r, &ZERO);
      return;
    }

    cp_dint (r, a);
    r->ex++;
    return;

  case -1: // |A| < |B|
    {
      // swap operands
      const dint64_t *tmp = a; a = b; b = tmp;
      break; // fall through the case |A| > |B|
    }
  }

  // From now on, |A| > |B| thus a->ex >= b->ex

  u128 A = a->r, B = b->r;
  uint64_t k = a->ex - b->ex;

  if (k > 0) {
    /* Warning: the right shift x >> k is only defined for 0 <= k < n
       where n is the bit-width of x. See for example
       https://developer.arm.com/documentation/den0024/a/The-A64-instruction-set/Data-processing-instructions/Shift-operations
       where it is said that k is interpreted modulo n. */
    B = (k < 128) ? B >> k : u128(0);
  }

  u128 C;
  unsigned char sgn = a->sgn;

  r->ex = a->ex; /* tentative exponent for the result */

  if (a->sgn ^ b->sgn) {
    /* a and b have different signs C = A + (-B)
       Sterbenz case |a|/2 <= |b| <= |a| can occur only when:
       * k=0: then B is not truncated, and C is exact below
       * k=1 and ex>0 below: then we ensure C is exact
     */
    C = A - B;
    uint64_t ch = C >> 64;
    /* We can't have C=0 here since we excluded the case |A| = |B|,
       thus __builtin_clzll(C) is well-defined below. */
    uint64_t ex = ch ? __builtin_clzll(ch) : 64 + __builtin_clzll(C);
    /* The error from the truncated part of B (1 ulp) is multiplied by 2^ex,
       thus by 2 ulps when ex <= 1. */
    if (ex > 0)
    {
      if (k == 1) /* Sterbenz case */
        C = (A << ex) - (b->r << (ex - 1));
      else
        C = (A << ex) - (B << ex);
      /* If C0 is the previous value of C, we have:
         (C0-1)*2^ex < A*2^ex-B*2^ex <= C0*2^ex
         since some neglected bits from B might appear which contribute
         a value less than ulp(C0)=1.
         As a consequence since 2^(127-ex) <= C0 < 2^(128-ex), because C0 had
         ex leading zero bits, we have 2^127-2^ex <= A*2^ex-B*2^ex < 2^128.
         Thus the value of C, which is truncated to 128 bits, is the right
         one (as if no truncation); moreover in some rare cases we need to
         shift by 1 bit to the left. */
      r->ex -= ex;
      ex = __builtin_clzll (C >> 64);
      /* Fall through with the code for ex = 0. */
    }
    C = C << ex;
    r->ex -= ex;
    /* The neglected part of B is bounded by 2 ulp(C) when ex=0, 1 ulp
       when ex > 0 but ex=0 at the end, and by 2*ulp(C) when ex > 0 and there
       is an extra shift at the end (in that case necessarily ex=1). */
  } else {
    C = A + B;
    if (C < A)
    {
      C = ((u128) 1 << 127) | (C >> 1);
      r->ex ++;
    }
  }

  /* In the addition case, we loose the truncated part of B, which
     contributes to at most 1 ulp. If there is an exponent shift, we
     might also loose the least significant bit of C, which counts as
     1/2 ulp, but the truncated part of B is now less than 1/2 ulp too,
     thus in all cases the error is less than 1 ulp(r). */

  r->sgn = sgn;
  r->r = C;
}

// Multiply two dint64_t numbers, with error bounded by 6 ulps
// on the 128-bit floating-point numbers.
// Overlap between r and a is allowed
static inline void
mul_dint (dint64_t *r, const dint64_t *a, const dint64_t *b) {
  u128 bh = b->hi, bl = b->lo;

  /* compute the two middle terms */
  u128 m1 = (u128)(a->hi) * bl;
  u128 m2 = (u128)(a->lo) * bh;

  /* put the 128-bit product of the high terms in r */
  r->r = (u128)(a->hi) * bh;

  /* there can be no overflow in the following addition since r <= (B-1)^2
     with B=2^64, (m1>>64) <= B-1 and (m2>>64) <= B-1, thus the sum is
     bounded by (B-1)^2+2*(B-1) = B^2-1 */
  r->r += (m1 >> 64) + (m2 >> 64);

  // Ensure that r->hi starts with a 1
  uint64_t ex = r->hi >> 63;
  r->r = r->r << (1 - ex);

  // Exponent and sign
  // if ex=1, then ex(r) = ex(a) + ex(b)
  // if ex=0, then ex(r) = ex(a) + ex(b) - 1
  r->ex = a->ex + b->ex + ex - 1;
  r->sgn = a->sgn ^ b->sgn;

  /* The ignored part can be as large as 3 ulps before the shift (one
     for the low part of a->hi * bl, one for the low part of a->lo * bh,
     and one for the neglected a->lo * bl term). After the shift this can
     be as large as 6 ulps. */
}

// Multiply two dint64_t numbers, assuming the low part of b is zero
// with error bounded by 2 ulps
static inline void
mul_dint_21 (dint64_t *r, const dint64_t *a, const dint64_t *b) {
  u128 bh = b->hi;
  u128 hi = (u128) (a->hi) * bh;
  u128 lo = (u128) (a->lo) * bh;

  /* put the 128-bit product of the high terms in r */
  r->r = hi;

  /* add the middle term */
  r->r += lo >> 64;

  // Ensure that r->hi starts with a 1
  uint64_t ex = r->hi >> 63;
  r->r = r->r << (1 - ex);

  // Exponent and sign
  r->ex = a->ex + b->ex + ex - 1;
  r->sgn = a->sgn ^ b->sgn;

  /* The ignored part can be as large as 1 ulp before the shift (truncated
     part of lo). After the shift this can be as large as 2 ulps. */
}

/* for 0 <= i < 256, Tinv[i] = floor(2^127/(2^63+i*2^55+2^55-1)) */
static uint64_t Tinv[256] = { 0xff00ff00ff00ff02, 0xfe03f80fe03f80ff, 0xfd08e5500fd08e56, 0xfc0fc0fc0fc0fc11, 0xfb18856506ddaba7, 0xfa232cf252138ac1, 0xf92fb2211855a867, 0xf83e0f83e0f83e11, 0xf74e3fc22c700f76, 0xf6603d980f6603db, 0xf57403d5d00f5742, 0xf4898d5f85bb3952, 0xf3a0d52cba872338, 0xf2b9d6480f2b9d66, 0xf1d48bcee0d399fc, 0xf0f0f0f0f0f0f0f2, 0xf00f00f00f00f010, 0xef2eb71fc4345239, 0xee500ee500ee5010, 0xed7303b5cc0ed731, 0xec979118f3fc4da3, 0xebbdb2a5c1619c8d, 0xeae56403ab959010, 0xea0ea0ea0ea0ea10, 0xe939651fe2d8d35d, 0xe865ac7b7603a198, 0xe79372e225fe30da, 0xe6c2b4481cd8568a, 0xe5f36cb00e5f36cc, 0xe525982af70c880f, 0xe45932d7dc52100f, 0xe38e38e38e38e38f, 0xe2c4a6886a4c2e11, 0xe1fc780e1fc780e3, 0xe135a9c97500e137, 0xe070381c0e070383, 0xdfac1f74346c5760, 0xdee95c4ca037ba58, 0xde27eb2c41f3d9d2, 0xdd67c8a60dd67c8b, 0xdca8f158c7f91ab9, 0xdbeb61eed19c5959, 0xdb2f171df770291a, 0xda740da740da740f, 0xd9ba4256c0366e92, 0xd901b2036406c80f, 0xd84a598ec9151f44, 0xd79435e50d79435f, 0xd6df43fca482f00e, 0xd62b80d62b80d62c, 0xd578e97c3f5fe552, 0xd4c77b03531dec0e, 0xd4173289870ac52e, 0xd3680d3680d3680e, 0xd2ba083b445250ac, 0xd20d20d20d20d20e, 0xd161543e28e50275, 0xd0b69fcbd2580d0c, 0xd00d00d00d00d00e, 0xcf6474a8819ec8ea, 0xcebcf8bb5b4169cc, 0xce168a7725080ce2, 0xcd712752a886d243, 0xccccccccccccccce, 0xcc29786c7607f99f, 0xcb8727c065c393e1, 0xcae5d85f1bbd6c96, 0xca4587e6b74f032a, 0xc9a633fcd967300d, 0xc907da4e871146ad, 0xc86a78900c86a78a, 0xc7ce0c7ce0c7ce0d, 0xc73293d789b9f839, 0xc6980c6980c6980d, 0xc5fe740317f9d00d, 0xc565c87b5f9d4d1c, 0xc4ce07b00c4ce07c, 0xc4372f855d824ca6, 0xc3a13de60495c774, 0xc30c30c30c30c30d, 0xc2780613c0309e02, 0xc1e4bbd595f6e948, 0xc152500c152500c2, 0xc0c0c0c0c0c0c0c1, 0xc0300c0300c0300d, 0xbfa02fe80bfa02ff, 0xbf112a8ad278e8de, 0xbe82fa0be82fa0bf, 0xbdf59c91700bdf5a, 0xbd69104707661aa3, 0xbcdd535db1cc5b7c, 0xbc52640bc52640bd, 0xbbc8408cd63069a1, 0xbb3ee721a54d880c, 0xbab656100bab6562, 0xba2e8ba2e8ba2e8c, 0xb9a7862a0ff46588, 0xb92143fa36f5e02f, 0xb89bc36ce3e0453b, 0xb81702e05c0b8171, 0xb79300b79300b794, 0xb70fbb5a19be3659, 0xb68d31340e4307d9, 0xb60b60b60b60b60c, 0xb58a485518d1e7e4, 0xb509e68a9b948220, 0xb48a39d44685fe97, 0xb40b40b40b40b40c, 0xb38cf9b00b38cf9b, 0xb30f63528917c80c, 0xb2927c29da5519d0, 0xb21642c8590b2165, 0xb19ab5c45606f00c, 0xb11fd3b80b11fd3c, 0xb0a59b418d749d54, 0xb02c0b02c0b02c0b, 0xafb321a1496fdf0f, 0xaf3addc680af3ade, 0xaec33e1f671529a5, 0xae4c415c9882b931, 0xadd5e6323fd48a87, 0xad602b580ad602b6, 0xaceb0f891e6551bc, 0xac7691840ac76919, 0xac02b00ac02b00ac, 0xab8f69e28359cd12, 0xab1cbdd3e2970f60, 0xaaaaaaaaaaaaaaab, 0xaa392f35dc17f00b, 0xa9c84a47a07f5638, 0xa957fab5402a55ff, 0xa8e83f5717c0a8e9, 0xa87917088e262b70, 0xa80a80a80a80a80b, 0xa79c7b16ea64d422, 0xa72f05397829cbc2, 0xa6c21df6e1625c80, 0xa655c4392d7b73a8, 0xa5e9f6ed347f0721, 0xa57eb50295fad40b, 0xa513fd6bb00a5140, 0xa4a9cf1d96833751, 0xa44029100a440291, 0xa3d70a3d70a3d70b, 0xa36e71a2cb033129, 0xa3065e3fae7cd0e0, 0xa29ecf163bb6500a, 0xa237c32b16cfd772, 0xa1d139855f7268ee, 0xa16b312ea8fc377d, 0xa105a932f2ca891f, 0xa0a0a0a0a0a0a0a1, 0xa03c1688732b3032, 0x9fd809fd809fd80a, 0x9f747a152d7836d0, 0x9f1165e7254813e2, 0x9eaecc8d53ae2ddf, 0x9e4cad23dd5f3a20, 0x9deb06c9194aa416, 0x9d89d89d89d89d8a, 0x9d2921c3d6411308, 0x9cc8e160c3fb19b9, 0x9c69169b30446dfa, 0x9c09c09c09c09c0a, 0x9baade8e4a2f6e10, 0x9b4c6f9ef03a3caa, 0x9aee72fcf957c10f, 0x9a90e7d95bc609a9, 0x9a33cd67009a33ce, 0x99d722dabde58f06, 0x997ae76b50efd00a, 0x991f1a515885fb37, 0x98c3bac74f5db00a, 0x9868c809868c8099, 0x980e4156201301c8, 0x97b425ed097b425f, 0x975a750ff68a58af, 0x97012e025c04b80a, 0x96a850096a850097, 0x964fda6c0964fda7, 0x95f7cc72d1b887e9, 0x95a02568095a0257, 0x9548e4979e0829fd, 0x94f2094f2094f209, 0x949b92ddc02526e5, 0x9445809445809446, 0x93efd1c50e726b7c, 0x939a85c40939a85c, 0x93459be6b009345a, 0x92f113840497889c, 0x929cebf48bbd90e5, 0x9249249249249249, 0x91f5bcb8bb02d9cd, 0x91a2b3c4d5e6f809, 0x9150091500915009, 0x90fdbc090fdbc091, 0x90abcc0242af3009, 0x905a38633e06c43b, 0x9009009009009009, 0x8fb823ee08fb823f, 0x8f67a1e3fdc26179, 0x8f1779d9fdc3a219, 0x8ec7ab397255e41d, 0x8e78356d1408e783, 0x8e2917e0e702c6ce, 0x8dda520237694809, 0x8d8be33f95d71590, 0x8d3dcb08d3dcb08d, 0x8cf008cf008cf009, 0x8ca29c046514e023, 0x8c55841c815ed5ca, 0x8c08c08c08c08c09, 0x8bbc50c8deb420c0, 0x8b70344a139bc75b, 0x8b246a87e19008b2, 0x8ad8f2fba9386823, 0x8a8dcd1feeae465c, 0x8a42f8705669db46, 0x89f87469a23920e0, 0x89ae4089ae4089ae, 0x89645c4f6e055dec, 0x891ac73ae9819b50, 0x88d180cd3a4133d7, 0x8888888888888889, 0x883fddf00883fddf, 0x87f78087f78087f8, 0x87af6fd5992d0d40, 0x8767ab5f34e47ef1, 0x872032ac13008720, 0x86d905447a34acc6, 0x869222b1acf1ce96, 0x864b8a7de6d1d608, 0x86053c345a0b8473, 0x85bf37612cee3c9b, 0x85797b917765ab89, 0x8534085340853408, 0x84eedd357c1b0085, 0x84a9f9c8084a9f9d, 0x84655d9bab2f1008, 0x8421084210842108, 0x83dcf94dc7570ce1, 0x839930523fbe3368, 0x8355ace3c897db10, 0x83126e978d4fdf3b, 0x82cf750393ac3319, 0x828cbfbeb9a020a3, 0x824a4e60b3262bc5, 0x8208208208208208, 0x81c635bc123fdf8e, 0x81848da8faf0d277, 0x814327e3b94f462f, 0x8102040810204081, 0x80c121b28bd1ba98, 0x8080808080808081, 0x8040201008040201, 0x8000000000000000};

#if 0
// Prints a dint64_t value for debugging purposes
static inline void print_dint(const dint64_t *a) {
  printf("{.lo=0x%"PRIx64", .hi=0x%"PRIx64", .ex=%"PRId64", .sgn=0x%"PRIx64"}\n", a->hi, a->lo, a->ex,
         a->sgn);
}
#endif

/* put in r an approximation of 1/a, assuming a is not zero,
   with error bounded by 4.003 ulps (relative error < 2^-124.999) */
static inline void inv_dint (dint64_t *r, dint64_t *a)
{
  uint64_t h = a->hi; /* 2^63 <= h < 2^64 */
  /* First compute a 64-bit inverse t of h, such that
     t*h ~ 2^127, see routine inv_dint() in tan.sage.
     We note a = h/2^63, then 1 <= a < 2, and we write x = t/2^64 for
     the approximation of 1/a, with 1/2 <= x < 1. */
  int i = (h>>55) & 0xff;
  uint64_t t = Tinv[i];
  /* now t is accurate to about 8 bits, more precisely the integer residual
     2^127 - h*t is bounded by 662027951208051476078044039717322752 < 2^118.995
     (attained for i=0 and h=2^63). The integer residual 2^127 - t*h
     equals 2^127*(1-a*x), thus 0 <= 1-ax < 2^-8.005. */

  /* first Newton iteration */
  u128 e = (((u128) 1) << 127) - (u128) h * (u128) t; // exact
  /* as Tinv was computed, we have 0 < e < 2^119 */
  e = (u128) t * (e >> 55);
  t += e >> 72;
  /* If we had no truncation, the residual 1-ax is squared at each iteration,
     thus we would get 2^127 - h*t < 2^(2*118.995)/2^127 <= 2^110.99.
     The truncation e>>55 induces an error of at most t < 2^64 on the
     value of e after e = (u128) t * (e >> 55), thus of at most 2^-8 on t,
     while the truncation e >> 72 induces an error of at most 1 on t,
     thus the error on t is at most 1+2^-8.
     Since h < 2^64, this can increase by at most 2^64*(1+2^-8) the value
     of 2^127 - h*t:
     2^127 - h*t < 2^110.99 + 2^64*(1+2^-8) < 2^110.991.
  */

  /* second Newton iteration */
  e = (((u128) 1) << 127) - (u128) h * (u128) t; // 0 <= e < 2^111
  e = (u128) t * (e >> 47);
  t += e >> 80;
  /* With the same reasoning as above, the truncation e >> 47 induces an
     error of at most 2^-16 on t, and the truncation e >> 80 an error of
     at most 1, giving a total of 1+2^-16.
     Since h < 2^64, this can increase by at most 2^64*(1+2^-16) the value
     of 2^127 - h*t:
     2^127 - h*t < 2^(2*110.991)/2^127 + 2^64*(1+2^-16) < 2^94.9821. */
     

  /* third Newton iteration */
  e = (((u128) 1) << 127) - (u128) h * (u128) t; // 0 <= e < 2^95
  e = (u128) t * (e >> 31);
  t += e >> 96;
  /* With the same reasoning as above, the truncation e >> 31 induces an
     error of at most 2^-32 on t, and the truncation e >> 96 an error of
     at most 1, giving a total of 1+2^-32.
     Since h < 2^64, this can increase by at most 2^64*(1+2^-32) the value
     of 2^127 - h*t:
     2^127 - h*t < 2^(2*94.9821)/2^127 + 2^64*(1+2^-32) < 2^64.574.
     This corresponds to:
     1 - a*x < 2^64.574/2^127 = 2^-62.426, thus the relative error is at
     most 2^-62.426. */
  
  dint64_t q[1];
  r->hi = t;
  r->lo = 0;
  /* if a->ex = 0, then 1/2 <= a < 1, thus we should have
     1 < 1/a <= 2, thus r->ex = 1 */
  r->ex = 1 - a->ex;
  r->sgn = 1;
  /* we use Newton's iteration: r -> r + r*(1-a*r) */
  mul_dint_21 (q, a, r);     /* -a*r, error <= 2 ulps */
  r->sgn = 0;                /* restore sign */
  add_dint (q, &ONE, q);     /* 1-a*r, error <= 2 ulps */
  mul_dint (q, r, q);        /* r*(1-a*r), error <= 6 ulps */
  add_dint (r, r, q);        /* error <= 2 ulps */
  /* If all computations were exact, the residual would be squared,
     thus we would get 1-a*r = 2^(-2*62.426) = 2^-124.852.
     To simplify the error analysis, we assume 1 <= a < 2 and thus
     1/2 <= r <= 1.
     * since |ar| <= 1, the error of at most 2 ulps from mul_dint_21()
       translates to an absolute error of at most 2^-127; this error
       is multiplied by r <= 1, thus contributes to at most 2^-127 in the
       final value of r.
     * since 1-a*r < 2^-62.426, the error of at most 2 ulps in
       add_dint (&q, &ONE, &q) translates to an absolute error of at most
       2^-189; this error is multiplied by r <= 1, thus contributes to at most
       2^-189 in the final value of r.
     * since q < 2^-62.426 and r < 1, the value of q after mul_dint()
       satisfies q < 2^-62.426, thus the error of at most 6 ulps translates
       into an absolute error of at most 2^-187 in the final value of r.
     * since r <= 1, the error of at most 2 ulps in add_dint (r, r, &q)
       translates into an absolute error of at most 2^-127 in the final
       value of r.
     This yields a maximal absolute error of 2^-127+2^-189+2^-187+2^-127
     < 2^-125.999. Since r >= 1/2, this corresponds to a relative error
     bounded by 2^-124.999, or to less than 4.003 ulps, since in the
     binade [1/2,1), the ulp is 2^-128.
  */
}

/* put in r an approximation of b/a, assuming a is not zero,
   with relative error < 2^-123.67 */
static inline void div_dint (dint64_t *r, dint64_t *b, dint64_t *a)
{
  inv_dint (r, a);    // relative error bounded by 2^-124.999
  mul_dint (r, r, b); // error bounded by 6 ulps
  /* The error bound of 6 ulps for mul_dint() corresponds to a maximal
     error of 6*2^-128 in the binade [1/2,1), thus to a maximal relative
     error of 12*2^-128:
     r = b/a * (1 + eps1) * (1 + eps2)
     with |eps1| < 2^-124.999 and |eps2| < 12*2^-128,
     thus r = b/a * (1 + eps) with eps < (1 + 2^-124.999) * (1 + 12*2^-128) - 1
     < 2^-123.67. */
}

// Convert a non-zero double to the corresponding dint64_t value
static inline void dint_fromd (dint64_t *a, double b) {
  fast_extract (&a->ex, &a->hi, b);

  /* |b| = 2^(ex-52)*hi */

  uint32_t t = __builtin_clzll (a->hi);

  a->sgn = b < 0.0;
  a->hi = a->hi << t;
  a->ex = a->ex - (t > 11 ? t - 12 : 0);
  /* b = 2^ex*hi/2^64 where 1/2 <= hi/2^64 < 1 */
  a->lo = 0;
}

static inline void subnormalize_dint(dint64_t *a) {
  if (a->ex > -1023)
    return;

  uint64_t ex = -(1011 + a->ex);

  uint64_t hi = a->hi >> ex;
  uint64_t md = (a->hi >> (ex - 1)) & 0x1;
  uint64_t lo = (a->hi & (~0ull >> ex)) || a->lo;

  switch (fegetround()) {
  case FE_TONEAREST:
    hi += lo ? md : hi & md;
    break;
  case FE_DOWNWARD:
    hi += a->sgn & (md | lo);
    break;
  case FE_UPWARD:
    hi += (!a->sgn) & (md | lo);
    break;
  }

  a->hi = hi << ex;
  a->lo = 0;

  if (!a->hi) {
    a->ex++;
    a->hi = (1ull << 63);
  }
}

// Convert a dint64_t value to a double
static inline double dint_tod(dint64_t *a) {
  subnormalize_dint (a);

  f64_u r = {.u = (a->hi >> 11) | (0x3ffll << 52)};

  double rd = 0.0;
  if ((a->hi >> 10) & 0x1)
    rd += 0x1p-53;

  if (a->hi & 0x3ff || a->lo)
    rd += 0x1p-54;

  if (a->sgn)
    rd = -rd;

  r.u = r.u | a->sgn << 63;
  r.f += rd;

  f64_u e;

  if (a->ex > -1022) { // The result is a normal double
    if (a->ex > 1024)
      if (a->ex == 1025) {
        r.f = r.f * 0x1p+1;
        e.f = 0x1p+1023;
      } else {
        r.f = 0x1.fffffffffffffp+1023;
        e.f = 0x1.fffffffffffffp+1023;
      }
    else
      e.u = ((a->ex + 1022) & 0x7ff) << 52;
  } else {
    if (a->ex < -1073) {
      if (a->ex == -1074) {
        r.f = r.f * 0x1p-1;
        e.f = 0x1p-1074;
      } else {
        r.f = 0x0.0000000000001p-1022;
        e.f = 0x0.0000000000001p-1022;
      }
    } else {
      e.u = 1l << (a->ex + 1073);
    }
  }

  return r.f * e.f;
}

/**************** end of code copied from dint.h and pow.[ch] ****************/

typedef union {double f; uint64_t u;} b64u64_u;

/* This table approximates 1/(2pi) downwards with precision 1280:
   1/(2*pi) ~ T[0]/2^64 + T[1]/2^128 + ... + T[i]/2^((i+1)*64) + ...
   Computed with computeT() from sin.sage. */
static const uint64_t T[20] = {
  0x28be60db9391054a, // i=0
   0x7f09d5f47d4d3770,
   0x36d8a5664f10e410,
   0x7f9458eaf7aef158,
   0x6dc91b8e909374b8,
   0x1924bba82746487, // i=5
   0x3f877ac72c4a69cf,
   0xba208d7d4baed121,
   0x3a671c09ad17df90,
   0x4e64758e60d4ce7d,
   0x272117e2ef7e4a0e, // i=10
   0xc7fe25fff7816603,
   0xfbcbc462d6829b47,
   0xdb4d9fb3c9f2c26d,
   0xd3d18fd9a797fa8b,
   0x5d49eeb1faf97c5e, // i=15
   0xcf41ce7de294a4ba,
   0x9afed7ec47e35742,
   0x1580cc11bf1edaea,
   0xfc33ef0826bd0d87, // i=19
};

/* Table containing 128-bit approximations of sin2pi(i/2^11) for 0 <= i < 256
   (to nearest).
   Each entry is to be interpreted as (hi/2^64+lo/2^128)*2^ex*(-1)*sgn.
   Generated with computeS() from sin.sage. */
static constexpr const auto &S = core_sin::S;

/* Table containing 128-bit approximations of cos2pi(i/2^11) for 0 <= i < 256
   (to nearest).
   Each entry is to be interpreted as (hi/2^64+lo/2^128)*2^ex*(-1)*sgn.
   Generated with computeC() from sin.sage. */
static constexpr const auto &C = core_sin::C;

/* The following is a degree-7 polynomial with odd coefficients
   approximating sin2pi(x) for -2^-24 < x < 2^-11+2^-24
   with relative error 2^-77.306.
   Generated with sin_fast.sollya. */
static const  double PSfast[] = {
  0x1.921fb54442d18p+2, 0x1.1a62645446203p-52, // degree 1 (h+l)
  -0x1.4abbce625be53p5,                        // degree 3
  0x1.466bc678d8d63p6,                         // degree 5
  -0x1.331554ca19669p6,                        // degree 7
};

/* The following is a degree-6 polynomial with even coefficients
   approximating cos2pi(x) for -2^-24 < x < 2^-11+2^-24
   with relative error 2^-75.188.
   Generated with cos_fast.sollya. */
static const  double PCfast[] = {
  0x1p+0, -0x1.923015cp-77,                    // degree 0
  -0x1.3bd3cc9be45dep4,                        // degree 2
  0x1.03c1f080ad892p6,                         // degree 4
  -0x1.55a5c590f9e6ap6,                        // degree 6
};

/* The following is a degree-11 polynomial with odd coefficients
   approximating sin2pi(x) for 0 <= x < 2^-11 with relative error 2^-127.75.
   Generated with sin_accurate.sollya. */
static const dint64_t PS[] = {
  {.lo=0xc4c6628b80dc1cd1, .hi=0xc90fdaa22168c234, .ex = 3, .sgn=0}, // 1
  {.lo=0x5dc72f712aa57db4, .hi=0xa55de7312df295f5, .ex = 6, .sgn=1}, // 3
  {.lo=0x3f33be0021aa54d2, .hi=0xa335e33bad570e92, .ex = 7, .sgn=0}, // 5
  {.lo=0xe59d6ab8509a2025, .hi=0x9969667315ec2d9d, .ex = 7, .sgn=1}, // 7
  {.lo=0x7d5f8f76fa7d74ed, .hi=0xa83c1a43bf1c6485, .ex = 6, .sgn=0}, // 9
  {.lo=0xa7f0339113b8b3c5, .hi=0xf16ab2898eae62f9, .ex = 4, .sgn=1}, // 11
};

/* The following is a degree-10 polynomial with even coefficients
   approximating cos2pi(x) for 0 <= x < 2^-11 with relative error 2^-137.246.
   Generated with cos_accurate.sollya. */
static const dint64_t PC[] = {
  {.lo=0x0, .hi=0x8000000000000000, .ex = 1, .sgn=0}, // degree 0
  {.lo=0x56e26cd9808c1949, .hi=0x9de9e64df22ef2d2, .ex = 5, .sgn=1}, // 2
  {.lo=0x9980f00630cb655e, .hi=0x81e0f840dad61d9a, .ex = 7, .sgn=0}, // 4
  {.lo=0xa508509534006249, .hi=0xaae9e3f1e5ffcfe2, .ex = 7, .sgn=1}, // 6
  {.lo=0xe0603ce7044eeba, .hi=0xf0fa83448dd1e094, .ex = 6, .sgn=0},  // 8
  {.lo=0xec63157807ebffa, .hi=0xd368f6f4207cfe49, .ex = 5, .sgn=1},  // 10
};

/* Table generated with ./buildSC 15 using accompanying buildSC.c.
   For each i, 0 <= i < 256, xi=i/2^11+SC[i][0], with
   SC[i][1] and SC[i][2] approximating sin2pi(xi) and cos2pi(xi)
   respectively, both with 53+15 bits of accuracy. */
static const double SC[256][3] = {
   {0x0p+0, 0x0p+0, 0x1p+0}, /* 0 */
   {-0x1.c0f6cp-35, 0x1.921f892b900fep-9, 0x1.ffff621623fap-1}, /* 1 */
   {-0x1.9c7935ep-35, 0x1.921f0ea27ce01p-8, 0x1.fffd8858eca2ep-1}, /* 2 */
   {-0x1.d14d1acp-34, 0x1.2d96af779b0bbp-7, 0x1.fffa72c986392p-1}, /* 3 */
   {-0x1.dba8f6a8p-33, 0x1.921d1ce2d0a1cp-7, 0x1.fff62169dddaap-1}, /* 4 */
   {0x1.a6b7cdfp-32, 0x1.f6a29bdb7377p-7, 0x1.fff0943c02419p-1}, /* 5 */
   {0x1.b49618dp-33, 0x1.2d936d1506f3dp-6, 0x1.ffe9cb44829cp-1}, /* 6 */
   {-0x1.398d6fcp-35, 0x1.5fd4d1e21de6dp-6, 0x1.ffe1c687174b1p-1}, /* 7 */
   {-0x1.e9e9a8c8p-31, 0x1.9215597791e0ap-6, 0x1.ffd886097afcfp-1}, /* 8 */
   {-0x1.34e844cp-32, 0x1.c454f2e9480c7p-6, 0x1.ffce09ce95933p-1}, /* 9 */
   {-0x1.989a8a4p-32, 0x1.f693709b94f92p-6, 0x1.ffc251dfbac0cp-1}, /* 10 */
   {0x1.04a9b99p-30, 0x1.146860e69a571p-5, 0x1.ffb55e40a5c43p-1}, /* 11 */
   {-0x1.56947cp-36, 0x1.2d865748774adp-5, 0x1.ffa72efff95d1p-1}, /* 12 */
   {-0x1.c348768p-35, 0x1.46a396d34121ap-5, 0x1.ff97c420a8451p-1}, /* 13 */
   {0x1.9e80552p-32, 0x1.5fc00e6e4c65cp-5, 0x1.ff871dacd8761p-1}, /* 14 */
   {0x1.3f11d74p-34, 0x1.78dbaa97099ebp-5, 0x1.ff753bb18af95p-1}, /* 15 */
   {0x1.c039af4p-33, 0x1.91f65fc0abc0ap-5, 0x1.ff621e370ca7ap-1}, /* 16 */
   {0x1.53e1f8p-35, 0x1.ab101bf74ac2ep-5, 0x1.ff4dc54b00181p-1}, /* 17 */
   {0x1.114a649p-29, 0x1.c428d7de920e9p-5, 0x1.ff3830f2e9043p-1}, /* 18 */
   {0x1.adf0ef4p-31, 0x1.dd40723a3cdfbp-5, 0x1.ff21614b9d9adp-1}, /* 19 */
   {-0x1.d21f5918p-30, 0x1.f656e1e9e59cdp-5, 0x1.ff09565e83d77p-1}, /* 20 */
   {-0x1.4f54d708p-30, 0x1.07b612d6be078p-4, 0x1.fef0102c634e3p-1}, /* 21 */
   {-0x1.1efec9ap-30, 0x1.1440118ba7bdp-4, 0x1.fed58ecf342dap-1}, /* 22 */
   {0x1.cc17ba88p-29, 0x1.20c96cf0a7eedp-4, 0x1.feb9d24646fa6p-1}, /* 23 */
   {0x1.121dbe4p-33, 0x1.2d5209628edfp-4, 0x1.fe9cdacf99cffp-1}, /* 24 */
   {-0x1.9ecf61p-34, 0x1.39d9f103bf7f7p-4, 0x1.fe7ea854e6b08p-1}, /* 25 */
   {-0x1.04ede8ep-31, 0x1.466116c629e5cp-4, 0x1.fe5f3af4ee201p-1}, /* 26 */
   {-0x1.1821cecp-31, 0x1.52e773c9920c7p-4, 0x1.fe3e92c0e4108p-1}, /* 27 */
   {0x1.cdec726p-31, 0x1.5f6d02131f0b2p-4, 0x1.fe1cafc7f1a24p-1}, /* 28 */
   {-0x1.edece4dp-31, 0x1.6bf1b2653648cp-4, 0x1.fdf99233c230cp-1}, /* 29 */
   {-0x1.2aa4d1cp-31, 0x1.787585bc45f0fp-4, 0x1.fdd53a01d11d9p-1}, /* 30 */
   {0x1.d461592p-32, 0x1.84f871e32cf68p-4, 0x1.fdafa74f16482p-1}, /* 31 */
   {0x1.f0cbd728p-29, 0x1.917a71d3d2956p-4, 0x1.fd88da29f302ep-1}, /* 32 */
   {-0x1.583247p-30, 0x1.9dfb6c9865b06p-4, 0x1.fd60d2e14a6b1p-1}, /* 33 */
   {-0x1.2e81bf4p-30, 0x1.aa7b706bfdbbap-4, 0x1.fd3791484ff5p-1}, /* 34 */
   {-0x1.13941418p-28, 0x1.b6fa680a05c27p-4, 0x1.fd0d15a4b8471p-1}, /* 35 */
   {0x1.71098ffp-30, 0x1.c3785eba12b42p-4, 0x1.fce15fceddccfp-1}, /* 36 */
   {-0x1.c3519e8p-32, 0x1.cff53302f059p-4, 0x1.fcb4703b969e1p-1}, /* 37 */
   {0x1.2f522a5p-27, 0x1.dc70fb84af16ep-4, 0x1.fc8646987fc1dp-1}, /* 38 */
   {-0x1.ae9bed8p-33, 0x1.e8eb7f8a589e2p-4, 0x1.fc56e3b91ca3ap-1}, /* 39 */
   {0x1.f8868b2p-30, 0x1.f564e87d2330fp-4, 0x1.fc264701f9a09p-1}, /* 40 */
   {-0x1.b07985f8p-29, 0x1.00ee8835051f4p-3, 0x1.fbf47105f7439p-1}, /* 41 */
   {0x1.cbdaa94p-30, 0x1.072a05e1d4d8ep-3, 0x1.fbc16172a9e36p-1}, /* 42 */
   {0x1.37c5b908p-28, 0x1.0d64df9619f0dp-3, 0x1.fb8d18b635327p-1}, /* 43 */
   {-0x1.068b5fc8p-28, 0x1.139f09bc617f5p-3, 0x1.fb5797351da85p-1}, /* 44 */
   {-0x1.8ea66818p-29, 0x1.19d8919fa4ec8p-3, 0x1.fb20dc7da8affp-1}, /* 45 */
   {0x1.6278ceb8p-28, 0x1.2011719d50b87p-3, 0x1.fae8e8bd4427fp-1}, /* 46 */
   {-0x1.096df84p-29, 0x1.264993433763ap-3, 0x1.faafbcbfca356p-1}, /* 47 */
   {0x1.9b2534fp-29, 0x1.2c810967bbf7p-3, 0x1.fa7557d8d987ep-1}, /* 48 */
   {0x1.215b4ep-34, 0x1.32b7bfa25c91bp-3, 0x1.fa39bac71954bp-1}, /* 49 */
   {-0x1.94db891p-30, 0x1.38edb9d29b39dp-3, 0x1.f9fce56700a6dp-1}, /* 50 */
   {0x1.7727f7b8p-29, 0x1.3f22f7c3cce3ap-3, 0x1.f9bed7b8c8d8cp-1}, /* 51 */
   {-0x1.0cb33038p-29, 0x1.45576971dd53p-3, 0x1.f97f925d53c83p-1}, /* 52 */
   {-0x1.9071106p-31, 0x1.4b8b175c71e22p-3, 0x1.f93f14feb8022p-1}, /* 53 */
   {0x1.62741e78p-29, 0x1.51bdfa7ea30d5p-3, 0x1.f8fd5fe3efac8p-1}, /* 54 */
   {0x1.f8e16d0cp-28, 0x1.57f00e80e6e12p-3, 0x1.f8ba733a1ceb1p-1}, /* 55 */
   {-0x1.76acbcap-31, 0x1.5e2143b7bc1c2p-3, 0x1.f8764fad5e9bfp-1}, /* 56 */
   {-0x1.0a0f73ap-30, 0x1.6451a76411746p-3, 0x1.f830f4ad232d8p-1}, /* 57 */
   {0x1.ca11d1bcp-28, 0x1.6a8135d7bd143p-3, 0x1.f7ea625eb5af7p-1}, /* 58 */
   {-0x1.02f23628p-29, 0x1.70afd74071191p-3, 0x1.f7a299d3f182ap-1}, /* 59 */
   {0x1.b34dcb8p-29, 0x1.76dda08544b5cp-3, 0x1.f7599a1ac7ecdp-1}, /* 60 */
   {0x1.161ff4p-32, 0x1.7d0a7bf2d4abap-3, 0x1.f70f64322da74p-1}, /* 61 */
   {-0x1.c49b8b4p-31, 0x1.83366ddb3de23p-3, 0x1.f6c3f7e7c2707p-1}, /* 62 */
   {0x1.21da851p-29, 0x1.8961743b1429p-3, 0x1.f6775552a6ba2p-1}, /* 63 */
   {0x1.ac63edap-30, 0x1.8f8b851098588p-3, 0x1.f6297cef0cdd6p-1}, /* 64 */
   {0x1.27ef489cp-27, 0x1.95b4a5b9f2cebp-3, 0x1.f5da6e7820551p-1}, /* 65 */
   {0x1.ae8937p-30, 0x1.9bdcc07900146p-3, 0x1.f58a2b0689c82p-1}, /* 66 */
   {0x1.eb48c7ep-29, 0x1.a203e4a4f950ep-3, 0x1.f538b1d392049p-1}, /* 67 */
   {-0x1.bfd282fp-29, 0x1.a829ffaad0d79p-3, 0x1.f4e603d51f1aap-1}, /* 68 */
   {0x1.7ccf638p-29, 0x1.ae4f1fa80e1b5p-3, 0x1.f492204c5ef9ep-1}, /* 69 */
   {-0x1.2435c578p-28, 0x1.b4732b72ebc86p-3, 0x1.f43d0890e1e72p-1}, /* 70 */
   {0x1.0293fecp-30, 0x1.ba9634155f866p-3, 0x1.f3e6bbb6c2ea4p-1}, /* 71 */
   {-0x1.7bb1f92p-29, 0x1.c0b82461f65ep-3, 0x1.f38f3ae6f9afcp-1}, /* 72 */
   {0x1.27aaebcp-29, 0x1.c6d906faacf65p-3, 0x1.f3368589e17a2p-1}, /* 73 */
   {-0x1.2e2bcd5p-27, 0x1.ccf8c3f74a6c9p-3, 0x1.f2dc9cfb5fa74p-1}, /* 74 */
   {-0x1.6f070acp-30, 0x1.d31773ba218a8p-3, 0x1.f2817fd4d045bp-1}, /* 75 */
   {0x1.469adfcp-29, 0x1.d935004779e57p-3, 0x1.f2252f59c122dp-1}, /* 76 */
   {0x1.4f51c18p-32, 0x1.df5164301377ap-3, 0x1.f1c7abdeaa3efp-1}, /* 77 */
   {0x1.78e44dap-29, 0x1.e56ca4202807cp-3, 0x1.f168f51c5d5d5p-1}, /* 78 */
   {0x1.49bb5f8p-32, 0x1.eb86b4a1b7e9bp-3, 0x1.f1090bc4b68p-1}, /* 79 */
   {-0x1.67ba541p-28, 0x1.f19f9369d5e93p-3, 0x1.f0a7effdc937fp-1}, /* 80 */
   {0x1.c0cab95p-29, 0x1.f7b74ab7219d2p-3, 0x1.f045a1219e594p-1}, /* 81 */
   {-0x1.2b77e32p-30, 0x1.fdcdc0ca3288dp-3, 0x1.efe220cf5c751p-1}, /* 82 */
   {-0x1.e0d8cbp-33, 0x1.01f18054c8362p-2, 0x1.ef7d6e54c347dp-1}, /* 83 */
   {-0x1.ecd5b9cp-29, 0x1.04fb7f6d35d68p-2, 0x1.ef178a6f9a987p-1}, /* 84 */
   {0x1.eb24de5p-29, 0x1.0804e1d369ff2p-2, 0x1.eeb074934fdfp-1}, /* 85 */
   {0x1.4a897c4p-30, 0x1.0b0d9d7b0d042p-2, 0x1.ee482e14bcdep-1}, /* 86 */
   {0x1.336c376p-30, 0x1.0e15b555e7becp-2, 0x1.eddeb6908ca8cp-1}, /* 87 */
   {-0x1.3952d9p-31, 0x1.111d25efd48b8p-2, 0x1.ed740e7eb8dd6p-1}, /* 88 */
   {0x1.fc2a5d4p-31, 0x1.1423ef5c7e1bdp-2, 0x1.ed0835dc24e89p-1}, /* 89 */
   {0x1.a88ed37p-29, 0x1.172a0eb8361dap-2, 0x1.ec9b2d0ec8288p-1}, /* 90 */
   {-0x1.8ca4cb94p-27, 0x1.1a2f7b10b6d7p-2, 0x1.ec2cf55d6117cp-1}, /* 91 */
   {0x1.0144524p-27, 0x1.1d3446fd0cd3fp-2, 0x1.ebbd8c1d62f96p-1}, /* 92 */
   {-0x1.abf810cp-28, 0x1.203855b85f89ap-2, 0x1.eb4cf57454132p-1}, /* 93 */
   {0x1.5d4c5d58p-28, 0x1.233bbcca40561p-2, 0x1.eadb2e40746cap-1}, /* 94 */
   {-0x1.a1b0c58p-29, 0x1.263e685b1d714p-2, 0x1.ea68396d87754p-1}, /* 95 */
   {-0x1.77c8dacp-29, 0x1.294061d2eb611p-2, 0x1.e9f41597393c8p-1}, /* 96 */
   {0x1.915540ep-30, 0x1.2c41a580014cfp-2, 0x1.e97ec348fb87fp-1}, /* 97 */
   {-0x1.abb6d9bp-28, 0x1.2f422b2d0990cp-2, 0x1.e90843c55b996p-1}, /* 98 */
   {-0x1.b8ee5d58p-28, 0x1.3241f8cea2836p-2, 0x1.e890962268c49p-1}, /* 99 */
   {-0x1.1cd29828p-28, 0x1.35410a8396266p-2, 0x1.e817baf85c094p-1}, /* 100 */
   {-0x1.e216afp-32, 0x1.383f5e08283e2p-2, 0x1.e79db2a188b0ap-1}, /* 101 */
   {-0x1.24afc3p-31, 0x1.3b3cef6993c0bp-2, 0x1.e7227dbf82004p-1}, /* 102 */
   {-0x1.aa1657cp-31, 0x1.3e39be4767224p-2, 0x1.e6a61c62d5274p-1}, /* 103 */
   {-0x1.c5b65fap-30, 0x1.4135c898485bbp-2, 0x1.e6288ee07fea5p-1}, /* 104 */
   {0x1.23e8978p-32, 0x1.44310de3c284bp-2, 0x1.e5a9d54bbd26cp-1}, /* 105 */
   {-0x1.2b1d77ap-29, 0x1.472b8976d498dp-2, 0x1.e529f06cb187dp-1}, /* 106 */
   {-0x1.daaa348p-31, 0x1.4a253cb97efd1p-2, 0x1.e4a8e007231a2p-1}, /* 107 */
   {-0x1.322f5708p-28, 0x1.4d1e2260c3422p-2, 0x1.e426a500f6e33p-1}, /* 108 */
   {0x1.64758e8p-29, 0x1.50163eca0b337p-2, 0x1.e3a33e996b722p-1}, /* 109 */
   {0x1.12486278p-28, 0x1.530d89a17e007p-2, 0x1.e31eae3fb917bp-1}, /* 110 */
   {-0x1.6c3416ccp-27, 0x1.5603fcf8cd8a3p-2, 0x1.e298f502a579bp-1}, /* 111 */
   {0x1.ab481ffp-29, 0x1.58f9a896aa209p-2, 0x1.e2121016e14fcp-1}, /* 112 */
   {-0x1.6eb838bp-29, 0x1.5bee77aaf890bp-2, 0x1.e18a032eb4df5p-1}, /* 113 */
   {-0x1.d159b8p-32, 0x1.5ee2734efeef5p-2, 0x1.e100ccaa6bd78p-1}, /* 114 */
   {-0x1.a42e4ap-34, 0x1.61d595bedeabcp-2, 0x1.e0766d944915ep-1}, /* 115 */
   {-0x1.43d0dcp-30, 0x1.64c7dd5cc0cd1p-2, 0x1.dfeae63903034p-1}, /* 116 */
   {-0x1.8c7bdb7p-27, 0x1.67b9453ca2122p-2, 0x1.df5e378482eaep-1}, /* 117 */
   {0x1.1c0ead6p-30, 0x1.6aa9d844c980ap-2, 0x1.ded05f6a23a52p-1}, /* 118 */
   {0x1.7d526p-31, 0x1.6d99867e90d92p-2, 0x1.de4160e97b2e2p-1}, /* 119 */
   {0x1.924e0368p-28, 0x1.7088555d3c816p-2, 0x1.ddb13afb14e37p-1}, /* 120 */
   {-0x1.74b7c3ep-30, 0x1.73763c09fba09p-2, 0x1.dd1fef5335416p-1}, /* 121 */
   {-0x1.7943adp-30, 0x1.766340685c982p-2, 0x1.dc8d7ccf2567ap-1}, /* 122 */
   {0x1.79dd614p-29, 0x1.794f5f7522b88p-2, 0x1.dbf9e402aa5c3p-1}, /* 123 */
   {0x1.7b64f32p-30, 0x1.7c3a939c32d81p-2, 0x1.db652607e0db1p-1}, /* 124 */
   {-0x1.2bea5ce8p-28, 0x1.7f24db825141cp-2, 0x1.dacf43268b5bp-1}, /* 125 */
   {0x1.733c024p-30, 0x1.820e3b8bf15ap-2, 0x1.da383a7aed887p-1}, /* 126 */
   {-0x1.eac0fc94p-27, 0x1.84f6a51d077b3p-2, 0x1.d9a00efd84537p-1}, /* 127 */
   {0x1.aca37338p-27, 0x1.87de2f4704f98p-2, 0x1.d906bbf17f4dap-1}, /* 128 */
   {-0x1.910c4fp-30, 0x1.8ac4b7dc0d986p-2, 0x1.d86c4862b5d6ep-1}, /* 129 */
   {-0x1.33bb86p-31, 0x1.8daa52b4dc041p-2, 0x1.d7d0b0374a559p-1}, /* 130 */
   {-0x1.69e1507p-27, 0x1.908ef408ad22p-2, 0x1.d733f5e71c3bcp-1}, /* 131 */
   {0x1.cffacf08p-27, 0x1.9372ab7784d36p-2, 0x1.d696161d786c9p-1}, /* 132 */
   {-0x1.8629d9fp-26, 0x1.965552b0849abp-2, 0x1.d5f7190eeae23p-1}, /* 133 */
   {0x1.415p-30, 0x1.99371687c64f3p-2, 0x1.d556f5155d9ddp-1}, /* 134 */
   {-0x1.bd37aad8p-27, 0x1.9c17cf40715cbp-2, 0x1.d4b5b2caf8386p-1}, /* 135 */
   {0x1.d02cde7p-26, 0x1.9ef79ea4d995dp-2, 0x1.d4134ac5eb246p-1}, /* 136 */
   {-0x1.10547acp-30, 0x1.a1d653d9adf5ep-2, 0x1.d36fc7d291602p-1}, /* 137 */
   {-0x1.01a1a228p-27, 0x1.a4b40f9c0120bp-2, 0x1.d2cb22b45236bp-1}, /* 138 */
   {0x1.3ce2bacp-29, 0x1.a790ce2056b9ap-2, 0x1.d2255c3ae11a5p-1}, /* 139 */
   {-0x1.ccb4a6p-32, 0x1.aa6c828db4ea8p-2, 0x1.d17e774d4e3e2p-1}, /* 140 */
   {0x1.5db4bp-29, 0x1.ad47321f29847p-2, 0x1.d0d672bc0b122p-1}, /* 141 */
   {0x1.32f6a6ep-29, 0x1.b020d7a285e23p-2, 0x1.d02d4fb84d334p-1}, /* 142 */
   {0x1.cf8e39bcp-26, 0x1.b2f97c27f7494p-2, 0x1.cf830c2248c5ep-1}, /* 143 */
   {0x1.8927bbp-30, 0x1.b5d10129a750ap-2, 0x1.ced7af22cb105p-1}, /* 144 */
   {-0x1.3dec3c1p-28, 0x1.b8a77f8d0bbc5p-2, 0x1.ce2b32e50d6cdp-1}, /* 145 */
   {-0x1.26ba536p-28, 0x1.bb7cf08f0290dp-2, 0x1.cd7d98fcf3b1ep-1}, /* 146 */
   {0x1.23c568ep-29, 0x1.be51524e3aa53p-2, 0x1.cccee1da3d56ep-1}, /* 147 */
   {-0x1.f3b3afp-29, 0x1.c1249c1f5f2f6p-2, 0x1.cc1f0f95e1e24p-1}, /* 148 */
   {-0x1.1286a47p-28, 0x1.c3f6d2ef7054bp-2, 0x1.cb6e20ff37e81p-1}, /* 149 */
   {0x1.641214ep-29, 0x1.c6c7f594003d9p-2, 0x1.cabc165bf1b6p-1}, /* 150 */
   {0x1.0cda7c9p-27, 0x1.c997ff2bffccbp-2, 0x1.ca08f0dee434cp-1}, /* 151 */
   {-0x1.5557ac9p-28, 0x1.cc66e7b42e8f1p-2, 0x1.c954b28bca62ep-1}, /* 152 */
   {0x1.555eb62p-28, 0x1.cf34bccc567a1p-2, 0x1.c89f57f6e20f3p-1}, /* 153 */
   {-0x1.4e0e361p-28, 0x1.d2016cbb5e39ap-2, 0x1.c7e8e59999e1fp-1}, /* 154 */
   {0x1.446da1ep-29, 0x1.d4cd039d0ed05p-2, 0x1.c731585f970ebp-1}, /* 155 */
   {0x1.103d328p-29, 0x1.d797767638decp-2, 0x1.c678b3174afe1p-1}, /* 156 */
   {0x1.5814d6p-28, 0x1.da60c7ae9dc22p-2, 0x1.c5bef522be6fbp-1}, /* 157 */
   {-0x1.5e2321ep-29, 0x1.dd28f054cbb3fp-2, 0x1.c5042052c8c42p-1}, /* 158 */
   {-0x1.a259ffep-29, 0x1.dfeff54854631p-2, 0x1.c44833611bc7dp-1}, /* 159 */
   {-0x1.4f28d8p-31, 0x1.e2b5d34665b35p-2, 0x1.c38b2f278ea7ep-1}, /* 160 */
   {-0x1.de571p-36, 0x1.e57a86d137f2p-2, 0x1.c2cd1493d05c2p-1}, /* 161 */
   {0x1.e0d8d14p-29, 0x1.e83e0ffb7bfb4p-2, 0x1.c20de3a08ea07p-1}, /* 162 */
   {-0x1.12a858ep-28, 0x1.eb0067e48baf4p-2, 0x1.c14d9e2bd511ep-1}, /* 163 */
   {0x1.9a17403p-27, 0x1.edc19997a4431p-2, 0x1.c08c413089b2ep-1}, /* 164 */
   {0x1.68c8636p-29, 0x1.f0819163d1bcp-2, 0x1.bfc9d21568f32p-1}, /* 165 */
   {0x1.4cc5eb8p-29, 0x1.f3405a482e11dp-2, 0x1.bf064dd580fc9p-1}, /* 166 */
   {-0x1.fce7cd8p-27, 0x1.f5fde8f3f11d4p-2, 0x1.be41b798f6b97p-1}, /* 167 */
   {-0x1.af8169p-29, 0x1.f8ba4c98a9816p-2, 0x1.bd7c0b1a7f14bp-1}, /* 168 */
   {0x1.6e39e2p-33, 0x1.fb7575d1ea75p-2, 0x1.bcb54cac5dde5p-1}, /* 169 */
   {0x1.30f9256p-28, 0x1.fe2f665dcd168p-2, 0x1.bbed7bd1e17bp-1}, /* 170 */
   {0x1.626de2p-31, 0x1.00740ca0d5fbbp-1, 0x1.bb2499f9fe7a3p-1}, /* 171 */
   {0x1.5cc703p-30, 0x1.01cfc8afeea0ep-1, 0x1.ba5aa650dd495p-1}, /* 172 */
   {-0x1.6191e6p-32, 0x1.032ae54fe4057p-1, 0x1.b98fa2065a5e6p-1}, /* 173 */
   {-0x1.6b1485p-31, 0x1.0485624c328c8p-1, 0x1.b8c38d39737bcp-1}, /* 174 */
   {-0x1.11fbc3ap-29, 0x1.05df3e66a716dp-1, 0x1.b7f668a580fdp-1}, /* 175 */
   {-0x1.0eca7fp-27, 0x1.07387825589ecp-1, 0x1.b728352c44517p-1}, /* 176 */
   {-0x1.8073bc9ep-25, 0x1.089109ef1284dp-1, 0x1.b658f630112edp-1}, /* 177 */
   {-0x1.9dcf0adp-27, 0x1.09e9051603e29p-1, 0x1.b588a13ab750fp-1}, /* 178 */
   {-0x1.06ea9fp-29, 0x1.0b405820e78e7p-1, 0x1.b4b740d3cc07bp-1}, /* 179 */
   {-0x1.36a8d0cp-30, 0x1.0c9704a1ea4e5p-1, 0x1.b3e4d40f5524dp-1}, /* 180 */
   {0x1.63d1f3p-30, 0x1.0ded0bc01a533p-1, 0x1.b3115a3a628afp-1}, /* 181 */
   {0x1.f3181f14p-26, 0x1.0f4270e4787bfp-1, 0x1.b23cd1314c779p-1}, /* 182 */
   {-0x1.f269b78p-29, 0x1.109723e75c5cfp-1, 0x1.b167430cfebdbp-1}, /* 183 */
   {0x1.1d84dc08p-27, 0x1.11eb36bc9db52p-1, 0x1.b090a4915ee88p-1}, /* 184 */
   {-0x1.08e60068p-27, 0x1.133e9ba0061d8p-1, 0x1.afb8fe69a6527p-1}, /* 185 */
   {0x1.cda72abp-27, 0x1.14915d557a7c9p-1, 0x1.aee049bc0aeep-1}, /* 186 */
   {-0x1.f32f95p-30, 0x1.15e36dfb6bb55p-1, 0x1.ae068f6991699p-1}, /* 187 */
   {0x1.138092dp-28, 0x1.1734d6f34d7fp-1, 0x1.ad2bc96c1e1f5p-1}, /* 188 */
   {0x1.6b382dd4p-26, 0x1.188595ae376a5p-1, 0x1.ac4ff962bdb6dp-1}, /* 189 */
   {-0x1.f12fafap-28, 0x1.19d59f592a587p-1, 0x1.ab7326685eb57p-1}, /* 190 */
   {-0x1.2909e5ap-28, 0x1.1b2500aed7ac6p-1, 0x1.aa954823cf815p-1}, /* 191 */
   {-0x1.d66a8978p-25, 0x1.1c73aa0150cf9p-1, 0x1.a9b668fb0503fp-1}, /* 192 */
   {0x1.311ea86p-27, 0x1.1dc1b7db74db1p-1, 0x1.a8d675d9c6cc8p-1}, /* 193 */
   {-0x1.41c02b8p-31, 0x1.1f0f08a1a06a4p-1, 0x1.a7f5853bb4309p-1}, /* 194 */
   {-0x1.ca1f4edp-26, 0x1.205ba57211271p-1, 0x1.a71391146958fp-1}, /* 195 */
   {-0x1.910ce77p-28, 0x1.21a7988f8326bp-1, 0x1.a63092626202fp-1}, /* 196 */
   {0x1.2bfadbeep-25, 0x1.22f2dc71afab6p-1, 0x1.a54c8cd9fd0d9p-1}, /* 197 */
   {-0x1.5f1c02a8p-27, 0x1.243d5df4afb93p-1, 0x1.a4678dbbe5e73p-1}, /* 198 */
   {-0x1.db12b9p-30, 0x1.2587347f493a4p-1, 0x1.a38184db0df23p-1}, /* 199 */
   {-0x1.7b29ep-30, 0x1.26d05490f2f61p-1, 0x1.a29a7a2f40b49p-1}, /* 200 */
   {-0x1.b3ddca4p-29, 0x1.2818be6930629p-1, 0x1.a1b26d8f070d7p-1}, /* 201 */
   {0x1.e112744p-29, 0x1.2960730ff2bcdp-1, 0x1.a0c95e3df5e0ep-1}, /* 202 */
   {-0x1.5269766p-28, 0x1.2aa76dafcbbf4p-1, 0x1.9fdf4fae1df6fp-1}, /* 203 */
   {-0x1.09777e1p-28, 0x1.2bedb1b6b4e15p-1, 0x1.9ef43f6cbe162p-1}, /* 204 */
   {0x1.ae2051fp-28, 0x1.2d333e4617f25p-1, 0x1.9e082e148680ep-1}, /* 205 */
   {-0x1.36f6ced8p-27, 0x1.2e780cb47180ep-1, 0x1.9d1b207f383c3p-1}, /* 206 */
   {-0x1.23fdc6bp-28, 0x1.2fbc23fba2f44p-1, 0x1.9c2d1197130a7p-1}, /* 207 */
   {0x1.bc540ep-33, 0x1.30ff7fd6d967dp-1, 0x1.9b3e0478b961bp-1}, /* 208 */
   {-0x1.cfb4ed7p-28, 0x1.32421da0bf0e9p-1, 0x1.9a4dfb1c89326p-1}, /* 209 */
   {0x1.55802aecp-26, 0x1.3384042a92b1dp-1, 0x1.995cf06920d11p-1}, /* 210 */
   {0x1.60719e4p-28, 0x1.34c52608e3a92p-1, 0x1.986aee6d6837ep-1}, /* 211 */
   {-0x1.cbf2e48p-30, 0x1.36058ac8863b6p-1, 0x1.9777ef832c986p-1}, /* 212 */
   {0x1.9061c32p-27, 0x1.374533ab707dp-1, 0x1.9683f2ad7e2ecp-1}, /* 213 */
   {-0x1.da84dfep-27, 0x1.3884160f9488fp-1, 0x1.958f000fdd50ap-1}, /* 214 */
   {0x1.92e8a74p-29, 0x1.39c23eba6b22ap-1, 0x1.94990dd9cee51p-1}, /* 215 */
   {-0x1.bff5d9ap-29, 0x1.3affa20756bddp-1, 0x1.93a225056084ap-1}, /* 216 */
   {0x1.4c462p-36, 0x1.3c3c4498e98ebp-1, 0x1.92aa41fbb951cp-1}, /* 217 */
   {-0x1.e4613e9p-28, 0x1.3d782261dff62p-1, 0x1.91b167e92d706p-1}, /* 218 */
   {0x1.0eb2964p-30, 0x1.3eb33ed579bbep-1, 0x1.90b794146043cp-1}, /* 219 */
   {-0x1.60abec2p-29, 0x1.3fed94c834d8ap-1, 0x1.8fbcca9583479p-1}, /* 220 */
   {0x1.6954977p-27, 0x1.4127281ddac03p-1, 0x1.8ec1085083553p-1}, /* 221 */
   {0x1.a16fec2p-29, 0x1.425ff1f841235p-1, 0x1.8dc452ca328d3p-1}, /* 222 */
   {-0x1.27bcdd3p-27, 0x1.4397f44aa44f2p-1, 0x1.8cc6a8771e165p-1}, /* 223 */
   {-0x1.60dded4p-28, 0x1.44cf317a563dbp-1, 0x1.8bc8076122736p-1}, /* 224 */
   {-0x1.9a8f405cp-26, 0x1.4605a2b02d705p-1, 0x1.8ac875232f3efp-1}, /* 225 */
   {0x1.32777dcp-27, 0x1.473b532bc5a67p-1, 0x1.89c7e8713120cp-1}, /* 226 */
   {-0x1.1418a7bp-26, 0x1.4870306ca20e2p-1, 0x1.88c670a0ea774p-1}, /* 227 */
   {-0x1.fed182ep-28, 0x1.49a44886b534p-1, 0x1.87c401fdf05e5p-1}, /* 228 */
   {0x1.86144d8p-27, 0x1.4ad796ea1410cp-1, 0x1.86c0a04dbacc5p-1}, /* 229 */
   {0x1.1bc2e6p-33, 0x1.4c0a14640d2afp-1, 0x1.85bc51aa114c2p-1}, /* 230 */
   {-0x1.f53d2fep-28, 0x1.4d3bc5aaa8cd5p-1, 0x1.84b7121b30a13p-1}, /* 231 */
   {-0x1.2e100ap-30, 0x1.4e6cab91556bep-1, 0x1.83b0e0e6b6cccp-1}, /* 232 */
   {-0x1.fa58c62p-29, 0x1.4f9cc1c69fddep-1, 0x1.82a9c1c1ab463p-1}, /* 233 */
   {0x1.bb491ep-33, 0x1.50cc09fdcbd92p-1, 0x1.81a1b3342f858p-1}, /* 234 */
   {0x1.a11541p-28, 0x1.51fa82c3aa029p-1, 0x1.8098b67ea8509p-1}, /* 235 */
   {0x1.ab0a5d3p-27, 0x1.53282b20b96b6p-1, 0x1.7f8ecc791953p-1}, /* 236 */
   {-0x1.cba0438p-28, 0x1.5454fe43a7d7cp-1, 0x1.7e83f96af78ap-1}, /* 237 */
   {-0x1.0dd83a4p-29, 0x1.5581033a81573p-1, 0x1.7d783712e20ecp-1}, /* 238 */
   {-0x1.e9a8299p-28, 0x1.56ac33fbb8253p-1, 0x1.7c6b8acf90fa6p-1}, /* 239 */
   {0x1.225c4aap-29, 0x1.57d6939d4b513p-1, 0x1.7b5df1da18065p-1}, /* 240 */
   {-0x1.82e66ep-27, 0x1.59001b9e64d79p-1, 0x1.7a4f72157cfdfp-1}, /* 241 */
   {0x1.51a6a354p-26, 0x1.5a28d5b36d597p-1, 0x1.794002a7c9023p-1}, /* 242 */
   {0x1.13917f4p-26, 0x1.5b50b4e10bec1p-1, 0x1.782faf6dc7ba2p-1}, /* 243 */
   {0x1.49310ccp-30, 0x1.5c77bc15ab4efp-1, 0x1.771e75c43942ep-1}, /* 244 */
   {0x1.24d493cp-30, 0x1.5d9dee9de49dbp-1, 0x1.760c529bc17bp-1}, /* 245 */
   {-0x1.04638f7p-26, 0x1.5ec347044e0f4p-1, 0x1.74f94b0af972p-1}, /* 246 */
   {-0x1.3f41b28p-29, 0x1.5fe7cb834600cp-1, 0x1.73e55936a516p-1}, /* 247 */
   {-0x1.a5f6f5cp-30, 0x1.610b7515d1562p-1, 0x1.72d083b8214ebp-1}, /* 248 */
   {0x1.19fb2ep-28, 0x1.622e459eafbc1p-1, 0x1.71bac8c7b0592p-1}, /* 249 */
   {-0x1.56d2c2bp-28, 0x1.6350396fe4e62p-1, 0x1.70a42bec51665p-1}, /* 250 */
   {-0x1.3c156c2p-28, 0x1.64715385bed93p-1, 0x1.6f8caa4969708p-1}, /* 251 */
   {-0x1.f23e576p-29, 0x1.659191d2fd57fp-1, 0x1.6e7445d74f711p-1}, /* 252 */
   {0x1.1e4be38p-30, 0x1.66b0f41d484c4p-1, 0x1.6d5afecd4938dp-1}, /* 253 */
   {-0x1.397cc8d8p-27, 0x1.67cf76eac73dfp-1, 0x1.6c40d89625f63p-1}, /* 254 */
   {-0x1.202f686p-28, 0x1.68ed1e0990551p-1, 0x1.6b25cf728c35p-1}, /* 255 */
};

// Multiply exactly a and b, such that *hi + *lo = a * b. 
static inline void a_mul(double *hi, double *lo, double a, double b) {
  *hi = a * b;
  *lo = __builtin_fma (a, b, -*hi);
}

/* Multiply a double with a double double : a * (bh + bl)
   with error bounded by ulp(lo) */
static inline void s_mul (double *hi, double *lo, double a, double bh,
                          double bl) {
  a_mul (hi, lo, a, bh); /* exact */
  *lo = __builtin_fma (a, bl, *lo);
  /* the error is bounded by ulp(lo), where |lo| < |a*bl| + ulp(hi) */
}

// Returns (ah + al) * (bh + bl) - (al * bl)
// We can ignore al * bl when assuming al <= ulp(ah) and bl <= ulp(bh)
static inline void d_mul(double *hi, double *lo, double ah, double al,
                         double bh, double bl) {
  double s, t;

  a_mul(hi, &s, ah, bh);
  t = __builtin_fma(al, bh, s);
  *lo = __builtin_fma(ah, bl, t);
}

static inline void
fast_two_sum(double *hi, double *lo, double a, double b)
{
  double e;

  *hi = a + b;
  e = *hi - a; /* exact */
  *lo = b - e; /* exact */
}

/* Put in h+l an approximation of sin2pi(xh+xl),
   for -2^-24 <= xh+xl < 2^-11 + 2^-24,
   and |xl| < 2^-52*|xh|, with relative error < 2^-71.61
   (see evalPSfast_all(K=8) in tan.sage).
   Assume uh + ul approximates (xh+xl)^2. */
static void
evalPSfast (double *h, double *l, double xh, double xl, double uh, double ul)
{
  double t;
  *h = PSfast[4]; // degree 7
  *h = __builtin_fma (*h, uh, PSfast[3]); // degree 5
  *h = __builtin_fma (*h, uh, PSfast[2]); // degree 3
  s_mul (h, l, *h, uh, ul);
  fast_two_sum (h, &t, PSfast[0], *h);
  *l += PSfast[1] + t;
  // multiply by xh+xl
  d_mul (h, l, *h, *l, xh, xl);
}

/* Put in h+l an approximation of cos2pi(xh+xl),
   for -2^-24 <= xh+xl < 2^-11 + 2^-24,
   and |xl| < 2^-52.36, with relative error < 2^-69.96
   (see evalPCfast(rel=true) in tan.sage).
   Assume uh + ul approximates (xh+xl)^2. */
static void
evalPCfast (double *h, double *l, double uh, double ul)
{
  double t;
  *h = PCfast[4]; // degree 6
  *h = __builtin_fma (*h, uh, PCfast[3]); // degree 4
  *h = __builtin_fma (*h, uh, PCfast[2]); // degree 2
  s_mul (h, l, *h, uh, ul);
  fast_two_sum (h, &t, PCfast[0], *h);
  *l += PCfast[1] + t;
}

/* Put in Y an approximation of sin2pi(X), for 0 <= X < 2^-11,
   where X2 approximates X^2.
   Absolute error bounded by 2^-132.999 with 0 <= Y < 0.003068
   (see evalPS() in sin.sage), and relative error bounded by
   2^-124.648 (see evalPSrel(K=8) in sin.sage). */
static void
evalPS (dint64_t *Y, dint64_t *X, dint64_t *X2)
{
  mul_dint_21 (Y, X2, PS+5); // degree 11
  add_dint (Y, Y, PS+4);     // degree 9
  mul_dint (Y, Y, X2);
  add_dint (Y, Y, PS+3);     // degree 7
  mul_dint (Y, Y, X2);
  add_dint (Y, Y, PS+2);     // degree 5
  mul_dint (Y, Y, X2);
  add_dint (Y, Y, PS+1);     // degree 3
  mul_dint (Y, Y, X2);
  add_dint (Y, Y, PS+0);     // degree 1
  mul_dint (Y, Y, X);        // multiply by X
}

/* Put in Y an approximation of cos2pi(X), for 0 <= X < 2^-11,
   where X2 approximates X^2.
   Absolute/relative error bounded by 2^-125.999 with 0.999995 < Y <= 1
   (see evalPC() in sin.sage). */
static void
evalPC (dint64_t *Y, dint64_t *X2)
{
  mul_dint_21 (Y, X2, PC+5); // degree 10
  add_dint (Y, Y, PC+4);     // degree 8
  mul_dint (Y, Y, X2);
  add_dint (Y, Y, PC+3);     // degree 6
  mul_dint (Y, Y, X2);
  add_dint (Y, Y, PC+2);     // degree 4
  mul_dint (Y, Y, X2);
  add_dint (Y, Y, PC+1);     // degree 2
  mul_dint (Y, Y, X2);
  add_dint (Y, Y, PC+0);     // degree 0
}

// normalize X such that X->hi has its most significant bit set (if X <> 0)
static void
normalize (dint64_t *X)
{
  int cnt;
  if (X->hi != 0)
  {
    cnt = __builtin_clzll (X->hi);
    if (cnt)
    {
      X->hi = (X->hi << cnt) | (X->lo >> (64 - cnt));
      X->lo = X->lo << cnt;
    }
    X->ex -= cnt;
  }
  else if (X->lo != 0)
  {
    cnt = __builtin_clzll (X->lo);
    X->hi = X->lo << cnt;
    X->lo = 0;
    X->ex -= 64 + cnt;
  }
}

/* Approximate X/(2pi) mod 1. If Xin is the input value, and Xout the
   output value, we have:
   |Xout - (Xin/(2pi) mod 1)| < 2^-126.67*|Xout|
   Assert X is normalized at input, and normalize X at output.
*/
static void
reduce (dint64_t *X)
{
  int e = X->ex;
  u128 u;

  if (e <= 1) // |X| < 2
  {
    /* multiply by T[0]/2^64 + T[1]/2^128, where
       |T[0]/2^64 + T[1]/2^128 - 1/(2pi)| < 2^-130.22 */
    u = (u128) X->hi * (u128) T[1];
    uint64_t tiny = u;
    X->lo = u >> 64;
    u = (u128) X->hi * (u128) T[0];
    X->lo += u;
    X->hi = (u >> 64) + (X->lo < (uint64_t) u);
    /* hi + lo/2^64 + tiny/2^128 = hi_in * (T[0]/2^64 + T[1]/2^128) thus
       |hi + lo/2^64 + tiny/2^128 - hi_in/(2*pi)| < hi_in * 2^-130.22
       Since X is normalized at input, hi_in >= 2^63, and since T[0] >= 2^61,
       we have hi >= 2^(63+61-64) = 2^60, thus the normalize() below
       perform a left shift by at most 3 bits */
    e = X->ex;
    normalize (X);
    e = e - X->ex;
    // put the upper e bits of tiny into X->lo
    if (e)
      X->lo |= tiny >> (64 - e);
    /* The error is bounded by 2^-130.22 (relative) + ulp(lo) (absolute).
       Since now X->hi >= 2^63, the absolute error of ulp(lo) converts into
       a relative error of less than 2^-127.
       This yields a maximal relative error of:
       (1 + 2^-130.22) * (1 + 2^-127) - 1 < 2^-126.852.
    */
    return;
  }

  // now 2 <= e <= 1024

  /* The upper 64-bit word X->hi corresponds to hi/2^64*2^e, if multiplied by
     T[i]/2^((i+1)*64) it yields hi*T[i]/2^128 * 2^(e-i*64).
     If e-64i <= -128, it contributes to less than 2^-128;
     if e-64i >= 128, it yields an integer, which is 0 modulo 1.
     We thus only consider the values of i such that -127 <= e-64i <= 127,
     i.e., (-127+e)/64 <= i <= (127+e)/64.
     Up to 4 consecutive values of T[i] can contribute (only 3 when e is a
     multiple of 64). */
  int i = (e < 127) ? 0 : (e - 127 + 64 - 1) / 64; // ceil((e-127)/64)
  // 0 <= i <= 15
  uint64_t c[5];
  u = (u128) X->hi * (u128) T[i+3]; // i+3 <= 18
  c[0] = u;
  c[1] = u >> 64;
  u = (u128) X->hi * (u128) T[i+2];
  c[1] += u;
  c[2] = (u >> 64) + (c[1] < (uint64_t) u);
  u = (u128) X->hi * (u128) T[i+1];
  c[2] += u;
  c[3] = (u >> 64) + (c[2] < (uint64_t) u);
  u = (u128) X->hi * (u128) T[i];
  c[3] += u;
  c[4] = (u >> 64) + (c[3] < (uint64_t) u);

  /* up to here, the ignored part hi*(T[i+4]+T[i+5]+...) can contribute by
     less than 2^64 in c[0], thus less than 1 in c[1] */

  int f = e - 64 * i; // hi*T[i]/2^128 is multiplied by 2^f
  /* {c, 5} = hi*(T[i]+T[i+1]/2^64+T[i+2]/2^128+T[i+3]/2^192) */
  /* now shift c[0..4] by f bits to the left */
  uint64_t tiny;
  if (f < 64)
  {
    X->hi = (c[4] << f) | (c[3] >> (64 - f));
    X->lo = (c[3] << f) | (c[2] >> (64 - f));
    tiny = (c[2] << f) | (c[1] >> (64 - f));
    /* the ignored part was less than 1 in c[1],
       thus less than 2^(f-64) <= 1/2 in tiny */
  }
  else if (f == 64)
  {
    X->hi = c[3];
    X->lo = c[2];
    tiny = c[1];
    /* the ignored part was less than 1 in c[1],
       thus less than 1 in tiny */
  }
  else /* 65 <= f <= 127: this case can only occur when e >= 65 */
  {
    int g = f - 64; /* 1 <= g <= 63 */
    /* we compute an extra term */
    u = (u128) X->hi * (u128) T[i+4]; // i+4 <= 19
    u = u >> 64;
    c[0] += u;
    c[1] += (c[0] < u);
    c[2] += (c[0] < u) && c[1] == 0;
    c[3] += (c[0] < u) && c[1] == 0 && c[2] == 0;
    c[4] += (c[0] < u) && c[1] == 0 && c[2] == 0 && c[3] == 0;
    X->hi = (c[3] << g) | (c[2] >> (64 - g));
    X->lo = (c[2] << g) | (c[1] >> (64 - g));
    tiny = (c[1] << g) | (c[0] >> (64 - g));
    /* the ignored part was less than 1 in c[0],
       thus less than 1/2 in tiny */
  }
  /* The approximation error between X/in(2pi) mod 1 and
     X->hi/2^64 + X->lo/2^128 + tiny/2^192 is:
     (a) the ignored part in tiny, which is less than ulp(tiny),
         thus less than 1/2^192;
     (b) the ignored terms hi*T[i+4] + ... or hi*T[i+5] + ...,
         which accumulate to less than ulp(tiny) too, thus
         less than 1/2^192.
     Thus the approximation error is less than 2^-191 (absolute).
  */
  X->ex = 0;
  normalize (X);
  /* the worst case (for 2^25 <= x < 2^1024) is X->ex = -61, attained
     for |x| = 0x1.6ac5b262ca1ffp+851 */
  if (X->ex < 0) // put the upper -ex bits of tiny into low bits of lo
    X->lo |= tiny >> (64 + X->ex);
  /* Since X->ex >= -61, it means X >= 2^-62 before the normalization,
     thus the maximal absolute error of 2^-191 yields a relative error
     bounded by 2^-191/2^-62 = 2^-129.
     There is an additional truncation error (for tiny) of at most 1 ulp
     of X->lo, thus at most 2^-127.
     The relative error is thus bounded by 2^-126.67. */
}

/* Given Xin:=X with 0 <= Xin < 1, return i and modify X such that
   Xin = i/2^11 + Xout, with 0 <= Xout < 2^-11.
   This operation is exact. */
static int
reduce2 (dint64_t *X)
{
  if (X->ex <= -11)
    return 0;
  int sh = 64 - 11 - X->ex;
  int i = X->hi >> sh;
  X->hi = X->hi & ((1ull << sh) - 1);
  normalize (X);
  return i;
}

/* h+l <- c1/2^64 + c0/2^128, rounded towards zero */
static void
set_dd (double *h, double *l, uint64_t c1, uint64_t c0)
{
  uint64_t e, f, g;
  b64u64_u t;
  if (c1)
    {
      e = __builtin_clzll (c1);
      if (e)
        {
          c1 = (c1 << e) | (c0 >> (64 - e));
          c0 = c0 << e;
        }
      f = 0x3fe - e;
      t.u = (f << 52) | ((c1 << 1) >> 12);
      *h = t.f;
      c0 = (c1 << 53) | (c0 >> 11);
      if (c0)
        {
          g = __builtin_clzll (c0);
          if (g)
            c0 = c0 << g;
          t.u = ((f - 53 - g) << 52) | ((c0 << 1) >> 12);
          *l = t.f;
        }
      else
        *l = 0;
    }
  else if (c0)
    {
      e = __builtin_clzll (c0);
      f = 0x3fe - 64 - e;
      c0 = c0 << (e+1); // most significant bit shifted out
      /* put the upper 52 bits of c0 into h */
      t.u = (f << 52) | (c0 >> 12);
      *h = t.f;
      /* put the lower 12 bits of c0 into l */
      c0 = c0 << 52;
      if (c0)
        {
          g = __builtin_clzll (c0);
          c0 = c0 << (g+1);
          t.u = ((f - 64 - g) << 52) | (c0 >> 12);
          *l = t.f;
        }
      else
        *l = 0;
    }
  else
    *h = *l = 0;
  /* Since we truncate from two 64-bit words to a double-double,
     we have another truncation error of less than 2^-106, thus
     the absolute error is bounded as follows:
     | h + l - frac(x/(2pi)) | < 2^-75.999 + 2^-106 < 2^-75.998 */
}

/* Assuming 0x1.7137449123ef6p-26 < x < +Inf,
   return i and set h,l such that i/2^11+h+l approximates frac(x/(2pi)):

   | i/2^11 + h + l - frac(x/(2pi)) | < 2^-104.815,
   with |h| < 2^-11 and |l| < 2^-52.36.
*/
static int
reduce_fast (double *h, double *l, double x)
{
  if (__builtin_expect(x <= 0x1.921fb54442d17p+2, 1)) // x < 2*pi
    {
      /* | CH+CL - 1/(2pi) | < 2^-110.523 */
#define CH 0x1.45f306dc9c883p-3
#define CL -0x1.6b01ec5417056p-57
      a_mul (h, l, CH, x);            // exact
      *l = __builtin_fma (CL, x, *l);
      /* The error in the above fma() is at most ulp(l),
         where |l| <= CL*|x|+|l_in|.
         Let xmax = 0x1.921fb54442d17p+2.
         We have x <= xmax and we can check that CH * xmax < 1.
         Then h <= 1 and |l_in| <= ulp(0.5) = 2^-53,
         where l_in is the value of l after a_mul.
         Then |l| <= |CL|*xmax + 2^-53 < 2^-52.361.
         The rounding error of the fma() is bounded by
         ulp(l) <= ulp(2^-52.361) = 2^-105.
         The error due to the approximation of 1/(2pi)
         is bounded by 2^-110.523*xmax <= 2^-107.871.
         Adding both errors yields:
         |h + l - x/(2pi)| < 2^-105 + 2^-107.871 < 2^-104.815.
      */
    }
  else // x > 0x1.921fb54442d17p+2
    {
      b64u64_u t = {.f = x};
      int e = (t.u >> 52) & 0x7ff; /* 1025 <= e <= 2046 */
      /* We have 2^(e-1023) <= x < 2^(e-1022), thus
         ulp(x) is a multiple of 2^(e-1075), for example
         if x is just above 2*pi, e=1025, 2^2 <= x < 2^3,
         and ulp(x) is a multiple of 2^-50.
         On the other side 1/(2pi) ~ T[0]/2^64 + T[1]/2^128 + T[2]/2^192 + ...
         Let i be the smallest integer such that 2^(e-1075)/2^(64*(i+1))
         is not an integer, i.e., e - 1139 - 64i < 0, i.e.,
         i >= (e-1138)/64. */
      uint64_t m = (1ull << 52) | (t.u & 0xfffffffffffffull);
      uint64_t c[3];
      u128 u, v;
      // x = m/2^53 * 2^(e-1022)
      if (e <= 1074) // 1025 <= e <= 1074: 2^2 <= x < 2^52
        {
          v = (u128) m * (u128) T[2];
          u = (u128) m * (u128) T[1];
          c[0] = u + (v >> 64);
          c[1] = (u >> 64) + (c[0] < (uint64_t) u);
          /* There can be no overflow in (u >> 64) + (c[0] < u) since
             u <= (2^64-1)*T[1] thus (u >> 64) < T[1], and T[1]+1
             does not overflow. */
          u = (u128) m * (u128) T[0];
          c[1] += u;
          c[2] = (u >> 64) + (c[1] < (uint64_t) u);
          /* Up to here, we multiplied exactly m by T[0] and T[1] and
             took into account the upper part of m*T[2]:
             c[2]*2^128+c[1]*2^64+c[0] = m*(T[1]+2^64*T[0])+floor(m*T[2]/2^64)
             |c[2]*2^128+c[1]*2^64+c[0]-m/(2pi)*2^128|
                < frac(m*T[2]/2^64) + (T[3]+1)/2^128
                < (2^64-1)/2^64 + (2^64-1)/2^128 < 1
             thus:
             | (c[2]*2^128+c[1]*2^64+c[0])*2^(e-1203) - x/(2pi) | < 2^(e-1203)
             | c[2]*2^(e-1075)+c[1]*2^(e-1139)+c[0]*2^(e-1203) - x/(2pi) |
               < 2^(e-1203)
             The low 1075-e bits of c[2] contribute to frac(x/(2pi)),
             and the ignored part is bounded by 1 with respect to c[0]. */
          e = 1075 - e; // 1 <= e <= 50
          // e is the number of low bits of c[2] contributing to frac(x/(2pi))
        }
      else // 1075 <= e <= 2046, 2^52 <= x < 2^1024
        {
          int i = (e - 1138 + 63) / 64; // i = ceil((e-1138)/64), 0 <= i <= 15
          /* m*T[i] contributes to f = 1139 + 64*i - e bits to frac(x/(2pi))
             with 1 <= f <= 64
             m*T[i+1] contributes a multiple of 2^(-f-64),
                      and at most to 2^(53-f)
             m*T[i+2] contributes a multiple of 2^(-f-128),
                      and at most to 2^(-11-f)
             m*T[i+3] contributes a multiple of 2^(-f-192),
                      and at most to 2^(-75-f) <= 2^-76
          */
          v = (u128) m * (u128) T[i+3];
          u = (u128) m * (u128) T[i+2];
          c[0] = u + (v >> 64);
          /* There can be no overflow in (u >> 64) + (c[0] < u) since
             u <= (2^64-1)*T[i+2] thus (u >> 64) < T[i+2], and T[i+2]+1
             does not overflow. */
          c[1] = (u >> 64) + (c[0] < (uint64_t) u);
          u = (u128) m * (u128) T[i+1];
          c[1] += u;
          c[2] = (u >> 64) + (c[1] < (uint64_t) u);
          u = (u128) m * (u128) T[i];
          c[2] += u;
          e = 1139 + (i<<6) - e; // 1 <= e <= 64
          /* Like in the previous case, the ignored part due to the
             ignored low part of m*T[i+3], and to the further terms
             m*T[i+4], ..., is at most 1 relative to c[0]. */
        }
      // e is the number of bits of c[2] to ignore
      if (e == 64)
        {
          /* we ignore all bits of c[0]: the ignored part with respect to
             the new value of c[0] is (2^64-1)/2^64 + 1/2^64 < 1 */
          c[0] = c[1];
          c[1] = c[2];
        }
      else
        {
          /* we ignore the low bits of c[0]: the ignored part with respect to
             the new value of c[0] is (2^64-1)/2^64 + 1/2^64 < 1 */
          c[0] = (c[1] << (64 - e)) | c[0] >> e;
          c[1] = (c[2] << (64 - e)) | c[1] >> e;
        }
      /* In all cases the ignored contribution from low(x*T[2]) and
         x*(T[i+3] + T[i+4] + ...) is less than 1 with respect to c[0],
         thus since we consider (c[1]*2^64+c[0])/2^128, it is < 2^-128. */
      set_dd (h, l, c[1], c[0]);
      /* set_dd() ensures |h| < 1 and |l| < ulp(h) <= 2^-53,
         with truncation error < 2^-106, thus the absolute error is
         bounded by 2^-106 + 2^-128 < 2^-105.999:
         |h + l - fracx/(2pi)| < 2^-105.999. */
    }

  /* In case x < 2pi we have:
     |h + l - x/(2pi)| < 2^-104.815,
  and in case 2pi < x we have:
  |h + l - frac(x/(2pi))| < 2^-105.999,
  thus in all cases:
  |h + l - frac(x/(2pi))| < 2^-104.815.
  
  Since we exclude |h+l| < 2^-37, the induced error
  relative to sin2pi(h+l) is bounded by
  2^-104.815/sin2pi(2^-37) < 2^-70.466. */

  double i = __builtin_floor (*h * 0x1p11);
  *h = __builtin_fma (i, -0x1p-11, *h);
  return i;
}

/* h + l <- (bh + bl) / (ah + al) with |bl|, |al| < 2^-49.47
   with relative error bounded by 2^-96.99:
   | h + l - (bh + bl) / (ah + al) | < 2^-96.99 * |h + l|. */
static inline void
fast_div (double *h, double *l, double bh, double bl, double ah, double al)
{
  /* We use here Karp-Markstein's trick for division:
     let b = bh+bl, a = ah+al, y = o(1/a), and z = o(b*y),
     then the approximation of b/a is z' = z + y*(b-a*z):
     b-a*z' = b-a*(z + y*(b-a*z)) = (b-a*z)*(1-a*y).
     We distinguish two errors:
     * the mathematical error, assuming z + y*(b-a*z) is computed exactly
       (but taking into account that y is not exactly 1/a, and z is not
       exactly b/a
     * the rounding errors in z + y*(b-a*z)
     For the error analysis, we assume 1 <= ah, bh < 2 for now.
  */
     
  double y = 1.0 / ah;
  /* y = 1/ah / (1 + eps1) with |eps1| < 2^-52.
     |1-ah*y| < |eps1| < 2^-52. */
  *h = bh * y;
  /* h = bh * y / (1 + eps2) with |eps2| < 2^-52
       = bh/ah / (1 + eps1) / (1 + eps2)
     thus writing z = h:
     bh = ah*z * (1 + eps1) * (1 + eps2)
     |bh - ah*z| < ah*z * (eps1 + eps2 + eps1*eps2)
     Since ah < 2 and z <= bh*y < 2, we have:
     |bh - ah*z| < 4 * (2*2^-52 + 2^-104) < 2^-48.999.
     It follows |bh-ah*z'| < (bh-ah*z)*(1-ah*y) < 2^-48.999*2^-52 < 2^-100.999
     Dividing by ah>=1 yields: |bh/ah-z'| < 2^-100.999 too.
     We assume the same bound hold for b,a: |b/a-z'| < 2^-100.999.
  */

  double eh = __builtin_fma (ah, -*h, bh);
  /* from the analysis above, we have |eh| < 2^-48.999 thus the rounding error
     is bounded by ulp(2^-48.999) = 2^-101 */
  double el = __builtin_fma (al, -*h, bl);
  /* here |al|, |bl| < 2^-49.47 and |h| < 2, thus |el| < 3*2^-49.47 and
     the rounding error is bounded by ulp(3*2^-49.47) = 2^-100. */
  *l = y * (eh + el);
  /* we have |eh+el| < 2^-48.999+3*2^-49.47 < 2^-47.33 thus the rounding error
     on eh+el is bounded by ulp(2^-47.33) = 2^-100.
     Then since y <= 1, the rounding error on l is bounded by 2^-100 too.
     The total rounding error is thus bounded by:
     2^-101+3*2^-100 < 2^-98.19.
     Adding the mathematical error yields:
     2^-100.999 + 2^-98.19 < 2^-97.99:
     | h + l - (bh + bl) / (ah + al) | < 2^-97.99.

     This was assuming 1 <= a,b < 2, thus with 1/2 <= h+l <= 2.
     For the relative error, this corresponds to 2^-97.99/(1/2) = 2^-96.99
     where 1/2 is the smallest possible value of h+l. */
}

/* given a finite input x with |x| > 0x1.d12ed0af1a27ep-27,
   put in h + l an approximation of tan(x),
   return the maximal absolute error err such that
   | h + l - tan(x) | < err */
static double
tan_fast (double *h, double *l, double x)
{
  int neg = x < 0, is_tan = 1;
  double absx = neg ? -x : x;

  /* now absx > 0x1.d12ed0af1a27ep-27 */
  int i = reduce_fast (h, l, absx);
  /* | i/2^11 + h + l - frac(x/(2pi)) | < 2^-104.815 */

  // if i >= 2^10: 1/2 <= frac(x/(2pi)) < 1 thus pi <= x <= 2pi
  // we use tan(pi+x) = tan(x)
  i = i & 0x3ff;
  // | i/2^11 + h + l - frac(x/(2pi)) | mod 1/2 < 2^-104.815

  // now i < 2^10
  // if i >= 2^9: 1/4 <= frac(x/(2pi)) < 1/2 thus pi/2 <= x <= pi
  // we use tan(pi/2+x) = -cot(x)
  is_tan = is_tan ^ (i >> 9);
  neg = neg ^ (i >> 9);
  i = i & 0x1ff;
  // | i/2^11 + h + l - frac(x/(2pi)) | mod 1/4 < 2^-104.815

  // now 0 <= i < 2^9
  // if i >= 2^8: 1/8 <= frac(x/(2pi)) < 1/4
  // we use tan(pi/2-x) = cot(x)
  if (i & 0x100) // case pi/4 <= x_red <= pi/2
    {
      is_tan = !is_tan;
      i = 0x1ff - i;
      /* 0x1p-11 - h is exact below: indeed, reduce_fast first computes
         a first value of h (say h0, with 0 <= h0 < 1), then i = floor(h0*2^11)
         and h1 = h0 - 2^11*i with 0 <= h1 < 2^-11.
         If i >= 2^8 here, this implies h0 >= 1/2^3, thus ulp(h0) >= 2^-55:
         h0 and h1 are integer multiples of 2^-55.
         Thus h1 = k*2^-55 with 0 <= k < 2^44 (since 0 <= h1 < 2^-11).
         Then 0x1p-11 - h = (2^44-k)*2^-55 is exactly representable.
         We can have a huge cancellation in 0x1p-11 - h, for example for
         x = 0x1.61a3db8c8d129p+1023 where we have before this operation
         h = 0x1.ffffffffff8p-12, and h = 0x1p-53 afterwards. */
      *h = 0x1p-11 - *h;
      *l = -*l;
    }

  /* The analysis of reduce_fast() proves that if we except i=0 and h<2^-37,
     then the error of reduce_fast() relative to both sin2pi(R) and cos2pi(R)
     is bounded by 2^-70.466:
     | R - frac(x/(2pi)) mod 1/4 | < 2^-70.466 * |sin2pi(R)|
     | R - frac(x/(2pi)) mod 1/4 | < 2^-70.466 * |cos2pi(R)|
     where R = i/2^11 + h + l, thus since the derivative of sin2pi and
     cos2pi is bounded by 2*pi and 2*pi*2^-70.466 < 2^-67.814:
     | sin2pi(R) - sin(x mod pi/2) | < 2^-67.814 * |sin2pi(R)|.
     | cos2pi(R) - cos(x mod pi/2) | < 2^-67.814 * |cos2pi(R)|.
     For i=0 and h<2^-37, we defer to the slow path. */
  if (__builtin_expect (i==0 && *h < 0x1p-37, 0))
    return 0x1p0;

  /* Now 0 <= i < 256 and 0 <= h+l < 2^-11
     with | i/2^11 + h + l - frac(x/(2pi)) | cmod 1/4 < 2^-104.815
     If is_tan=1, tan |x| = tan2pi (R + err1) with |err1| < 2^-104.815,
     if is_tan=0, tan |x| = cot2pi (R + err1) with |err1| < 2^-104.815.
     In both cases R = i/2^11 + h + l, 0 <= R < 1/4.
  */
  double sh, sl, ch, cl;
  /* since the SC[] table evaluates at i/2^11 + SC[i][0] and not at i/2^11,
     we must subtract SC[i][0] from h+l */
  /* Here h = k*2^-55 with 0 <= k < 2^44, and SC[i][0] is an integer
     multiple of 2^-62, with |SC[i][0]| < 2^-24, thus SC[i][0] = m*2^-62
     with |m| < 2^38. It follows h-SC[i][0] = (k*2^7 + m)*2^-62 with
     2^51 - 2^38 < k*2^7 + m < 2^51 + 2^38, thus h-SC[i][0] is exact. */
  *h -= SC[i][0];
  /* the following fast_two_sum() guarantees that |l| <= ulp(h) thus
     |l| <= 2^-52 |h| at input of evalPSfast() and evalPCfast() */
  fast_two_sum (h, l, *h, *l);
  // now -2^-24 < h < 2^-11+2^-24
  // from comments in reduce_fast() we have |l| < 2^-52.36
  double uh, ul;
  a_mul (&uh, &ul, *h, *h);
  ul = __builtin_fma (*h + *h, *l, ul);
  // uh+ul approximates (h+l)^2
  evalPSfast (&sh, &sl, *h, *l, uh, ul);
  /* the relative error of evalPSfast() is less than 2^-71.61 from
     routine evalPSfast_all(K=8) in tan.sage:
     | sh + sh - sin2pi(h+l) | < 2^-71.61 * |sin2pi(h+l)| */
  evalPCfast (&ch, &cl, uh, ul);
  /* the relative error of evalPCfast() is less than 2^-69.96 from
     routine evalPCfast() in sin.sage:
     | ch + cl - cos2pi(h+l) | < 2^-69.96 * |cos2pi(h+l)| */

  double sh0, sl0, ch0, cl0, h1, l1;
  s_mul (&sh0, &sl0, SC[i][2], sh, sl);
  s_mul (&ch0, &cl0, SC[i][1], ch, cl);
  fast_two_sum (&h1, &l1, ch0, sh0);
  l1 += sl0 + cl0;
  /* relative error bounded by 2^-67.777
     from global_error(is_sin=true,rel=true) in tan.sage:
     | h1 + l1 - sin2pi (R) | < 2^-67.777 * |sin2pi(R)|
     with in addition |l1| < 2^-49.47 */

  double h2, l2;
  s_mul (&ch, &cl, SC[i][2], ch, cl);
  s_mul (&sh, &sl, SC[i][1], sh, sl);
  fast_two_sum (&h2, &l2, ch, -sh);
  l2 += cl - sl;
  /* relative error bounded by 2^-68.073
     from global_error(is_sin=false,rel=true) in sin.sage:
     | h2 + l2 - cos2pi (R) | < 2^-68.073 * |cos2pi(R)|
     (where cos|x| has to be replaced by sin|x| for is_tan=0)
     with in addition |l2| < 2^-49.62 */

  /* here we have |l1|, |l1| < 2^-49.47 */
  if (is_tan)
    fast_div (h, l, h1, l1, h2, l2);
    /* |h_out+l_out - (h_in+l_in)/(hh+ll)| < 2^-96.99 * |h_out+l_out| */
  else
    fast_div (h, l, h2, l2, h1, l1);

  /* In summary we have when is_tan=1:
     h1+l1 = sin2pi(R) * (1 + eps1) with |eps1| < 2^-67.777
     h2+l2 = cos2pi(R) * (1 + eps2) with |eps2| < 2^-68.073
     sin2pi(R) = sin(x mod pi/2) * (1 + eps3) with |eps3| < 2^-67.814
     cos2pi(R) = cos(x mod pi/2) * (1 + eps4) with |eps4| < 2^-67.814
     h+l = (h1+l1)/(h2+l2) * (1 + eps5) with |eps5| < 2^-96.99
     This yields:
     h+l = tan(x mod pi/2) * (1+eps1)*(1+eps3)*(1+eps5)/(1+eps2)/(1+eps4)
     The largest value is obtained when eps1,eps3,eps5 are maximum, and
     eps2,eps4 minimum, and we get:
     h+l = tan(x mod pi/2) * (1+eps) with |eps| < 2^-65.864
     (the same bound holds for eps1,eps3,eps5 minimum and eps2,eps4 maximum).
     When is_tan=0, we get the same reasoning with inverse ratio, but the
     bounds are the same.
  */

  static const double sgn[2] = {1.0, -1.0};
  *h *= sgn[neg];
  *l *= sgn[neg];
  return *h * 0x1.1ap-66; // 2^-65.864 < 0x1.1ap-66
}

/* Assume x is a regular number, and |x| > 0x1.d12ed0af1a27ep-27. */
static double
tan_accurate (double x)
{
  double absx = (x > 0) ? x : -x;

  dint64_t X[1];
  dint_fromd (X, absx);

  /* reduce argument */
  reduce (X);
  
  // now |X - x/(2pi) mod 1| < 2^-126.67*X, with 0 <= X < 1.

  int is_tan = 1, neg = x < 0;

  // Write X = i/2^11 + r with 0 <= r < 2^11.
  int i = reduce2 (X); // exact

  i = i & 0x3ff; // if pi <= x < 2*pi, tan(x) = tan(x-pi)

  // now i < 2^10

  if (i & 0x200) // pi/2 <= x < pi: tan(x) = -1/tan(x-pi/2)
  {
    is_tan = 0;
    neg = !neg;
    i = i & 0x1ff;
  }

  // now 0 <= i < 2^9

  if (i & 0x100)
    // pi/4 <= x < pi/2: tan(x) = 1/tan(pi/2-x)
  {
    is_tan = !is_tan;
    X->sgn = 1; // negate X
    add_dint (X, &MAGIC, X); // X -> 2^-11 - X
    // here: 256 <= i <= 511
    i = 0x1ff - i;
    // now 0 <= i < 256
  }

  // now 0 <= i < 256 and 0 <= X < 2^-11

  /* If is_tan=1, tan |x| = tan2pi (R * (1 + eps))
        (cases 0 <= x < pi/4 and 3pi/4 <= x < pi)
     if is_tan=0, tan |x| = cot2pi (R * (1 + eps))
        (case pi/4 <= x < 3pi/4)
     In both cases R = i/2^11 + X, 0 <= R < 1/4, and |eps| < 2^-126.67.
  */

  dint64_t U[1], V[1], X2[1];
  mul_dint (X2, X, X);       // X2 approximates X^2
  evalPC (U, X2);    // cos2pi(X)
  /* since 0 <= X < 2^-11, we have 0.999 < U <= 1 */
  evalPS (V, X, X2); // sin2pi(X)
  /* since 0 <= X < 2^-11, we have 0 <= V < 0.0005 */

  // sin2pi(R) ~ sin2pi(i/2^11)*cos2pi(X)+cos2pi(i/2^11)*sin2pi(X)
  dint64_t Sin[1], UU[1], VV[1];
  mul_dint (UU, S+i, U);
  /* since 0 <= S[i] < 0.705 and 0.999 < Uin <= 1, we have
     0 <= U < 0.705 */
  mul_dint (VV, C+i, V);
  add_dint (Sin, UU, VV);
  /* For the error analysis, we distinguish the case i=0.
     For i=0, we have S[i]=0 and C[1]=1, thus V is the value computed
     by evalPS() above, with relative error < 2^-124.648.
     
     For 1 <= i < 256, analyze_sin_case1(rel=true) from sin.sage gives a
     relative error bound of -122.797 (obtained for i=1).
     In all cases, the relative error for the computation of
     sin2pi(i/2^11)*cos2pi(X)+cos2pi(i/2^11)*sin2pi(X) is bounded by -122.797
     not taking into account the approximation error in R:
     |S - sin2pi(R)| < |S| * 2^-122.797.

     For the approximation error in R, we have:
     sin |x| = sin2pi (R * (1 + eps))
     R = i/2^11 + X, 0 <= R < 1/4, and |eps| < 2^-126.67.
     Thus sin|x| = sin2pi(R+R*eps)
     = sin2pi(R)+R*eps*2*pi*cos2pi(theta), theta in [R,R+R*eps]
     Since 2*pi*R/sin(2*pi*R) < pi/2 for R < 1/4, it follows:
     | sin|x| - sin2pi(R) | < pi/2*R*|sin(2*pi*R)|
     | sin|x| - sin2pi(R) | < 2^-126.018 * |sin2pi(R)|.

     Adding both errors we get:
     | sin|x| - S | < |S| * 2^-122.797 + 2^-126.018 * |sin2pi(R)|
     < |S| * 2^-122.797 + 2^-126.018 * |S| * (1 + 2^-122.797)
     < |S| * 2^-122.650.
  */
  
  // cos2pi(R) ~ cos2pi(i/2^11)*cos2pi(X)-sin2pi(i/2^11)*sin2pi(X)
  dint64_t Cos[1];
  mul_dint (U, C+i, U);
  mul_dint (V, S+i, V);
  V->sgn = 1 - V->sgn; // negate V
  add_dint (Cos, U, V);
  /* For 0 <= i < 256, analyze_sin_case2(rel=true) from sin.sage gives a
     relative error bound of -123.540 (obtained for i=0):
     |C - cos2pi(R)| < |C| * 2^-123.540.

     For the approximation error in R, we have:
     sin |x| = cos2pi (R * (1 + eps))
     R = i/2^11 + X, 0 <= R < 1/4, and |eps| < 2^-126.67.
     Thus sin|x| = cos2pi(R+R*eps)
                 = cos2pi(R)-R*eps*2*pi*sin2pi(theta), theta in [R,R+R*eps]
     Since we have R < 1/4, we have cos2pi(R) >= sqrt(2)/2,
     and it follows:
     | sin|x|/cos2pi(R) - 1 | < 2*pi*R*eps/(sqrt(2)/2)
                              < pi/2*eps/sqrt(2)          [since R < 1/4]
                              < 2^-126.518.
     Adding both errors we get:
     | cos|x| - C | < |C| * 2^-123.540 + 2^-126.518 * |cos2pi(R)|
                    < |C| * 2^-123.540 + 2^-126.518 * |C| * (1 + 2^-123.540)
                    < |C| * 2^-123.367.
  */

  /* Now if is_tan=1 we compute S/C, otherwise we compute C/S. */
  if (is_tan)
    div_dint (U, Sin, Cos);
  else
    div_dint (U, Cos, Sin);

  /* Relative error on S < eps1 = 2^-122.650
     Relative error on C < eps2 = 2^-123.367
     Relative error of div_dint() < eps3 = 2^-123.67
     Total relative error < (1+eps1)*(1+eps2)*(1+eps3)-1 < 2^-121.578,
     this is less than 2^-121.578/2^-128 < 86 ulps. */

  uint64_t err = 86;
  uint64_t hi0, hi1, lo0, lo1;
  lo0 = U->lo - err;
  hi0 = U->hi - (lo0 > U->lo);
  lo1 = U->lo + err;
  hi1 = U->hi + (lo1 < U->lo);
  /* check the upper 54 bits are equal */
  if ((hi0 >> 10) != (hi1 >> 10))
    {
      static const double exceptions[2][3] = {
        /* the following has 78 identical bits after the round bit */
        {0x1.dffffffffff1fp-22, 0x1.e000000000151p-22, 0x1.fffffffffffffp-76},
        /* the following has 72 identical bits after the round bit */
        {0x1.dfffffffffc7cp-21, 0x1.e000000000546p-21, -0x1.658bcedb6e1d4p-147},
      };
      for (int j = 0; j < 2; j++)
        {
          if (__builtin_fabs (x) == exceptions[j][0])
            return (x > 0) ? exceptions[j][1] + exceptions[j][2]
              : -exceptions[j][1] - exceptions[j][2];
        }
      /* if we go here, we have a hard-to-round case, but since all hard-to-round
         cases are known and pass all tests, we are ok */
    }

  if (neg)
    U->sgn = 1 - U->sgn;

  double y = dint_tod (U);

  return y;
}

double
cr_tan (double x)
{
  b64u64_u t = {.f = x};
  int e = (t.u >> 52) & 0x7ff;

  if (__builtin_expect (e == 0x7ff, 0)) /* NaN, +Inf and -Inf. */
  {
    if ((t.u << 1) == 0x7ffull<<53) { // +/-Inf
#ifdef CORE_MATH_SUPPORT_ERRNO
      errno = EDOM;
#endif
      return x - x; // raises invalid
    }
    return x + x; // NaN
  }
  
  /* now x is a regular number */

  /* For |x| <= 0x1.d12ed0af1a27ep-27, tan(x) rounds to x (to nearest):
     we can assume x >= 0 without loss of generality since tan(-x) = -tan(x),
     we have x < tan(x) < x + x^3/3 for say 0 < x <= 1 thus
     |tan(x) - x| < x^3/3.
     Write x = c*2^e with 1/2 <= c < 1.
     Then ulp(x)/2 = 2^(e-54), and x^3/3 = c^3/3*2^(3e), thus
     x^3/3 < ulp(x)/2 rewrites as c^3/3*2^(3e) < 2^(e-54),
     or c^3*2^(2e+54) < 3 (1).
     For e <= -27, since c^3 < 1, we have c^3*2^(2e+54) < 1 < 3.
     For e=-26, (1) rewrites 4*c^3 < 3 which yields c <= 0x1.d12ed0af1a27ep-1.
  */
  uint64_t ux = t.u & 0x7fffffffffffffff;
  if (ux <= 0x3e4d12ed0af1a27eull) { // |x| <= 0x1.d12ed0af1a27ep-27
    if (x == 0)
      return x;
    // Taylor expansion of tan(x) is x + x^3/3 around zero
      /* We have underflow exactly when 0 < |x| < 2^-1022:
         for RNDU, tan(2^-1022-2^-1074) would round to 2^-1022-2^-1075
         with unbounded exponent range */
#ifdef CORE_MATH_SUPPORT_ERRNO
    if (x != 0 && __builtin_fabs (x) < 0x1p-1022)
      errno = ERANGE; // underflow
#endif
    return __builtin_fma (x, 0x1p-54, x);
  }

  double h, l, err;
  err = tan_fast (&h, &l, x);
  double left  = h + (l - err), right = h + (l + err);
  if (__builtin_expect (left == right, 1))
    return left;

  return tan_accurate (x);
}
