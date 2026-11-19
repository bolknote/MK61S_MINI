// Certify pow midpoint separation when both odd significands are powers of one small odd integer.
#include <gmpxx.h>
#include <mpfr.h>

#include <algorithm>
#include <cstdint>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
constexpr unsigned GridBits = 320;
constexpr unsigned ExponentDenominatorBits = 116;
constexpr unsigned CoefficientBits = 122;
constexpr unsigned First = 3;
constexpr unsigned Stop = (1U << 27) + 1;

struct Euclid {
    const mpz_class unit = mpz_class(1) << GridBits;
    const mpz_class cap = (mpz_class(1) << CoefficientBits) - 1;
    mpz_class previous, remainder, next, quotient;
    mpz_class previous_denominator, denominator, next_denominator;

    // Consecutive convergents are unimodular and have opposite errors.
    // With q_i <= cap < q_(i+1), the error at q_i is minimal among q<=cap.
    const mpz_class& min_residue(const mpz_class& logarithm) {
        previous = unit;
        mpz_fdiv_r_2exp(remainder.get_mpz_t(), logarithm.get_mpz_t(), GridBits);
        previous_denominator = 0;
        denominator = 1;
        while (remainder != 0) {
            mpz_fdiv_qr(quotient.get_mpz_t(), next.get_mpz_t(), previous.get_mpz_t(), remainder.get_mpz_t());
            next_denominator = previous_denominator;
            mpz_addmul(next_denominator.get_mpz_t(), quotient.get_mpz_t(), denominator.get_mpz_t());
            if (next_denominator > cap) break;
            previous.swap(remainder);
            remainder.swap(next);
            previous_denominator.swap(denominator);
            denominator.swap(next_denominator);
        }
        return remainder;
    }
};

struct Logarithm {
    mpfr_t argument, bound;
    mpz_class lower, upper;

    Logarithm() {
        mpfr_init2(argument, 32);
        mpfr_init2(bound, GridBits + 32);
    }

    ~Logarithm() {
        mpfr_clear(argument);
        mpfr_clear(bound);
        mpfr_free_cache2(MPFR_FREE_LOCAL_CACHE);
    }

    bool enclose(unsigned base) {
        mpfr_set_ui(argument, base, MPFR_RNDN);
        mpfr_log2(bound, argument, MPFR_RNDD);
        mpfr_mul_2ui(bound, bound, GridBits, MPFR_RNDD);
        mpfr_get_z(lower.get_mpz_t(), bound, MPFR_RNDD);
        mpfr_log2(bound, argument, MPFR_RNDU);
        mpfr_mul_2ui(bound, bound, GridBits, MPFR_RNDU);
        mpfr_get_z(upper.get_mpz_t(), bound, MPFR_RNDU);
        return upper >= lower && upper - lower <= 2;
    }
};

struct Result {
    mpz_class minimum, denominator;
    unsigned root = 0;
    unsigned checked = 0;
    bool verified = true;
};

void verify(unsigned first, unsigned stop, Result& result) {
    Logarithm logarithm;
    Euclid euclid;
    mpz_class gap;
    for (unsigned d = first; d < stop; d += 2) {
        if (!logarithm.enclose(d)) {
            result = {0, 0, d, result.checked, false};
            return;
        }
        gap = euclid.min_residue(logarithm.lower);
        gap -= (logarithm.upper - logarithm.lower) * euclid.cap;
        if (gap <= 0) {
            result = {gap, euclid.denominator, d, result.checked, false};
            return;
        }
        if (!result.root || gap < result.minimum) {
            result.minimum = gap;
            result.denominator = euclid.denominator;
            result.root = d;
        }
        ++result.checked;
    }
}

unsigned parse(const char* value) {
    std::size_t used = 0;
    const std::string text(value);
    const auto result = std::stoul(text, &used, 0);
    if (used != text.size() || result > Stop) throw std::invalid_argument("invalid unsigned argument");
    return unsigned(result);
}

int run(unsigned workers, unsigned first, unsigned stop) {
    if (first < First || stop > Stop || !(first & stop & 1) || first >= stop) {
        throw std::invalid_argument("expected an odd half-open subrange of [3, 2^27+1)");
    }
    const unsigned count = (stop - first) / 2;
    if (!workers || workers > count) throw std::invalid_argument("invalid worker count");
    if (workers > 1 && !mpfr_buildopt_tls_p()) throw std::runtime_error("MPFR needs TLS for multiple workers");

    std::vector<Result> results(workers);
    std::vector<std::thread> threads;
    threads.reserve(workers);
    try {
        for (unsigned i = 0; i < workers; ++i) {
            const unsigned lo = first + 2 * (std::uint64_t(i) * count / workers);
            const unsigned hi = first + 2 * (std::uint64_t(i+1) * count / workers);
            threads.emplace_back(verify, lo, hi, std::ref(results[i]));
        }
    } catch (...) {
        for (auto& thread : threads) thread.join();
        throw;
    }
    for (auto& thread : threads) thread.join();

    const Result* least = &results[0];
    unsigned checked = 0;
    for (const auto& result : results) {
        checked += result.checked;
        if (!result.verified || (least->verified && result.minimum < least->minimum)) least = &result;
    }
    const bool proven = least->verified && checked == count;
    const bool full = first == First && stop == Stop;
    const unsigned gap_bits = proven ? GridBits + 1 - mpz_sizeinbase(least->minimum.get_mpz_t(), 2) : 0;
    std::cout << "{\"status\":\"" << (proven ? (full ? "PASS_COMMON_ODD_ROOT" : "VERIFIED_RANGE") : "INCOMPLETE")
              << "\",\"first\":" << first << ",\"stop\":" << stop << ",\"roots_checked\":" << checked
              << ",\"coefficient_bits\":" << CoefficientBits << ",\"grid_bits\":" << GridBits
              << ",\"least_root\":" << least->root << ",\"min_grid_units\":\"" << least->minimum
              << "\",\"convergent_denominator\":\"" << least->denominator
              << "\",\"strict_log_gap_bits\":" << (proven ? gap_bits + ExponentDenominatorBits + 1 : 0)
              << ",\"mpfr\":\"" << mpfr_get_version() << "\"}\n";
    return proven ? 0 : 1;
}
}

int main(int argc, char** argv) {
    try {
        if (argc == 2) return run(parse(argv[1]), First, Stop);
        if (argc == 4) return run(parse(argv[1]), parse(argv[2]), parse(argv[3]));
        throw std::invalid_argument("usage: certify_common_odd_root WORKERS [FIRST STOP]");
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
