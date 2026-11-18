#include "native_eabi_m0_pow_log_side.inc"
#include <climits>
#include <mpfr.h>

extern "C" int log_side(uint64_t x, uint64_t y, uint64_t lower) {
  return m0_pow_log_side::side(x, y, lower);
}

extern "C" unsigned logarithm_error(uint64_t coefficient, int exponent) {
  static_assert(ULONG_MAX >= UINT64_MAX, "64-bit Unix MPFR host");
  using namespace m0_pow_log_side;
  Big approximation;
  absolute_log(approximation, coefficient, exponent);
  mpfr_t input, endpoint;
  mpfr_inits2(Precision+64, input, endpoint, (mpfr_ptr) nullptr);
  mpfr_set_ui(input, coefficient, MPFR_RNDN);
  mpfr_mul_2si(input, input, exponent, MPFR_RNDN);
  const bool inverse = mpfr_cmp_ui(input,1)<0;
  mpz_t integer, difference;
  mpz_inits(integer,difference,(mpz_ptr) nullptr);
  mpz_import(integer, Words+5, -1, sizeof(Word), 0, 0, approximation.word);
  unsigned error = 0;
  const mpfr_rnd_t directions[] = {MPFR_RNDD, MPFR_RNDU};
  for(auto rounding : directions) {
    const auto direction = inverse ? (rounding==MPFR_RNDD ? MPFR_RNDU : MPFR_RNDD) : rounding;
    mpfr_log(endpoint,input,direction);
    mpfr_abs(endpoint,endpoint,MPFR_RNDN);
    mpfr_mul_2ui(endpoint,endpoint,Precision,MPFR_RNDN);
    mpfr_get_z(difference,endpoint,rounding);
    mpz_sub(difference,difference,integer);
    mpz_abs(difference,difference);
    const unsigned delta = mpz_fits_uint_p(difference) ? unsigned(mpz_get_ui(difference)) : UINT_MAX;
    if(delta>error) error=delta;
  }
  mpz_clears(integer,difference,(mpz_ptr) nullptr);
  mpfr_clears(input,endpoint,(mpfr_ptr) nullptr);
  return error;
}
