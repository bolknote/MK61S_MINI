/* Correctly-rounded power function for two binary64 values.

Copyright (c) 2022-2025 CERN and Inria
Authors: Tom Hubrecht and Paul Zimmermann

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

/* For reference, the files in this directory were copied from the private
   git repository gitlab.inria.fr:zimmerma/core-math-power.git, branch
   two_step, revision f153eb68, before edition in the CORE-MATH git
   repository. */

/* References:
   [1] Note on FastTwoSum with Directed Rounding, Paul Zimmermann,
       https://hal.inria.fr/hal-03798376/, 2022.
   [2] An efficient rounding boundary test for pow(x,y) in double precision,
       Christoph Lauter, Vincent Lefèvre,
       https://hal-ens-lyon.archives-ouvertes.fr/ensl-00169409, 2007.
   [3] Arrondi correct de fonctions mathématiques, Fonctions univariées et
       bivariées, certification et automatisation, Christoph Quirin Lauter,
       PhD thesis, 2008, in french,
       http://www.ens-lyon.fr/LIP/Pub/Rapports/PhD/PhD2008/PhD2008-07.pdf
   [4] An efficient rounding boundary test for pow(x,y) in double precision,
       Christoph Lauter, Vincent Lefèvre, IEEE Transactions on Computers,
       volume 58, number 2, 197-207, 2009.
   [5] Towards a correctly-rounded and fast power function in binary64
       arithmetic, Tom Hubrecht, Claude-Pierre Jeannerod, Paul Zimmermann,
       ARITH 2023 - 30th IEEE Symposium on Computer Arithmetic, 2023.
       Detailed version (with full proofs) available at
       https://inria.hal.science/hal-04159652.
   [6] On Ziv's rounding test, F. De Dinechin, C. Lauter, J.-M. Muller,
       S. Torres, ACM Trans. Math. Soft., volume 39, number 3, 2013.

   This code corresponds to reference [5].       
*/

// Shared without changes from cr_pow: integer phases and final guard.
  uint64_t rd; // used in the 2nd and 3rd phases

// Second iteration of rounding
#if ENABLE_ZIV2 > 0
  dint64_t X, Y;
  dint_fromd (&X, x); /* exact: |x| = 2^(X->ex-63) * X->hi (X->lo = 0) */
  dint_fromd (&Y, y); /* exact: |y| = 2^(Y->ex-63) * Y->hi (Y->lo = 0) */

  X.sgn = 0x0; /* force the sign of X to +1 */

  dint64_t R;
  log_2 (&R, &X); /* relative error bounded by 2^-122.88 */

  mul_dint_21 (&R, &R, &Y);
  /* The rounding error of mul_dint_21() is bounded by 2 ulps, which is at most
     2*2^-127 in terms of relative error. Thus the relative error on R is
     bounded by (1+e1)*(1+e2)-1 with e1=2^-122.88 and e2=2*2^-127,
     which gives: R = y*log|x| * (1+eps1) with |eps1| < 2^-122.72 */

  exp_2 (&R, &R); /* relative error < 2^-121.70:
                     R = exp(R_in) * (1+eps2) with |eps2| < 2^-121.70 */

  /* We thus have R = |x|^y * exp(y*log|x|*eps1) * (1+eps2).
     Since y*log|x| < 744.45, we have |y*log|x|*eps1| < 744.45*2^-122.72
     < eps3 = 2^-113.179 thus the relative error is bounded by
     exp(eps3)*(1+eps2)-1 < 2^-113.17.
     This corresponds to an error of at most 2^-113.17*2^128 < 29126 ulps. */

  /* Remark: since eps3 = 2^-113.179, it would suffice to get about 113 bits
     of accuracy in exp_2(). We tried to reduce the degree of the minimax
     polynomial in q_2() from 7 to 6, or to use only 64 bits for the degree-3
     coefficient, but in both cases the accuracy was too small. */

  // Rounding test

  // 2^R.ex <= R < 2^(R.ex+1)

  /* case R < 2^-1075: underflow case */
  if (R.ex < -1075) {
#ifdef CORE_MATH_SUPPORT_ERRNO
    errno = ERANGE; // underflow
#endif
    return 0.5 * (s * 0x1p-1074);
  }

  if (R.ex < -1022) { /* subnormal case */
    // for x^y = 2^-1022, we can have R < 2^-1022 here

    /* -1075 <= R.ex <= -1023 thus 2^-1075 <= R < 2^-1022 */
    uint64_t ex = -(1022 + R.ex); /* 1 <= ex <= 53 */
    // the significand has to be shifted right by ex bits
    uint64_t m = R.lo >> (10 + ex) | R.hi << (54 - ex);

    /* We always have underflow when ex >= 2. However for ex=1,
       where 2^-1023 <= R < 2^-1022, we might not have underflow
       for rounding up if R >= 2^-1022 - 2^-1075, and for rounding
       to nearest for R >= 2^-1022 - 2^-1076. */

    /* In principle, the bound 28 which holds for the normal case below
       should be replaced by ceil(28/2^ex) since the relative error bound
       is the same as for the normal case, but since the round bit is 'shifted'
       by 'ex' bits to the left, we get 'ex' extra bits after the round bit.
       Since ex>=1 we replace 28 by 14. */

    rd = m + 14 > (2*14);

  } else {
#define ERR_BND_2 28
    uint64_t lo = R.lo >> 10 | R.hi << 54;
    /* lo contains the 64 bits after the round bit */
    rd = lo + ERR_BND_2 > (2*ERR_BND_2);
    /* The value 28 comes from floor(29126/2^10): rd is 0 when lo <= 28 or
       lo >= 2^64 - 28, which means that the approximation R is at distance
       < 29*2^10 = 29696 ulps of a rounding boundary */
  }

  R.sgn = s == -1.0;

  if (rd)
    // dint_tod should deal with underflow/overflow/errno issues
    return dint_tod (&R, exact);

#if ENABLE_EXACT > 0
  // Detect rounding boundary cases
  double e;

  if (exact_pow (&e, x0, y, &R, exact))
    return e;
#endif /* ENABLE_EXACT */
#endif /* ENABLE_ZIV2 */

  /* Note: exact and midpoint cases should be filtered by
     exact_pow() above, and should not enter the 2nd iteration.
     Thus check.sh might fail when POW_ITERATION | 2 == 0
     or POW_ITERATION | 4 == 0. */

#if ENABLE_ZIV3
  // Hard to round cases
  qint64_t qX, qY;
  qint_fromd (&qX, x); /* exact */
  qint_fromd (&qY, y); /* exact */

  qX.sgn = 0x0; /* force the sign of X to +1 */

  qint64_t qR;
  log_3 (&qR, &qX); /* relative error bounded by 2^-250.74 */

  mul_qint_41 (&qR, &qR, &qY);
  /* The rounding error of mul_qint_41() is bounded by 2 ulps, which is at most
     2*2^-255 in terms of relative error. Thus the relative error on qR is
     bounded by (1+e1)*(1+e2)-1 with e1=2^-250.74 and e2=2*2^-255,
     which gives a relative error less than 2^-250.59:
     qR = y*log|x| * (1+eps1) with |eps1| < 2^-250.59 */

  qint64_t qZ;
  exp_3 (&qZ, &qR); /* relative error < 2^-241.10:
                       qZ = exp(qR) * (1+eps2) with |eps2| < 2^-241.10 */

  /* We thus have qZ = |x|^y * exp(y*log|x|*eps1) * (1+eps2).
     Since y*log|x| < 744.45, we have |y*log|x|*eps1| < 744.45*2^-250.59
     < eps3 = 2^-241.049 thus the relative error is bounded by
     exp(eps3)*(1+eps2)-1 < 2^-240.07.
     This corresponds to an error of at most 2^-240.07*2^256 < 62433 ulps. */

  /* extra rounding test */
#define ERR_BND_3 60 /* floor(62433/2^10) */
  uint64_t r1 = qZ.hh << 54 | qZ.hl >> 10;
  uint64_t r2 = qZ.hl << 54 | qZ.lh >> 10;
  uint64_t r3 = qZ.lh << 54 | qZ.ll >> 10;
  rd = !((r1 == 0 && r2 == 0 && r3 <= ERR_BND_3) ||
         (~r1 == 0 && ~r2 == 0 && r3 + (2*ERR_BND_3) <= ERR_BND_3));

  if (rd)
  {
    qZ.sgn = s == -1.0;
    qZ.ll = qZ.ll & (~0ull << 10);

    return qint_tod (&qZ);
  }

  /* We can end up here for x^y very close to 1. For |qR| < 2^-55,
     we have 1-2^-54 < exp(qR) < 1+2^-53, thus exp(qR) rounds either
     to nextbelow(1), to 1 or to nextabove(1). */
  if (qR.ex < -56) /* the upper limb h of qR encodes h/2^63, thus a number
                      in [1, 2) */
    return (qR.sgn == 0x0) ? 1.0 + 0x1p-100 : 1.0 - 0x1p-100;

  printf ("Unexpected worst-case found.\n");
  printf ("Please report to core-math@inria.fr:\n");
  printf ("Worst-case of pow found: x,y=%la,%la\n", x, y);
  exit (1);

#else
  return -0.0;
#endif /* ENABLE_ZIV3 */
