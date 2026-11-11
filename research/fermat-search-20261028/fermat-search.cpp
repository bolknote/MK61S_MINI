// SPDX-License-Identifier: GPL-3.0-or-later
// Host-only search. No calculator firmware or floating-point screening.
#include <gmpxx.h>
#include <mpfr.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <numeric>
#include <stdexcept>
#include <string>
#include <thread>
#include <tuple>
#include <vector>

namespace {
constexpr unsigned screen_denominator = 1024;
constexpr mpfr_prec_t initial_precision = 256;
static_assert(std::atomic<bool>::is_always_lock_free,
              "The signal handler needs a lock-free stop flag");
std::atomic<bool> interrupted{false};
void interrupt_handler(int) { interrupted.store(true, std::memory_order_relaxed); }

struct Float {
    mpfr_t v;
    explicit Float(mpfr_prec_t precision = initial_precision) {
        mpfr_init2(v, precision);
        mpfr_set_zero(v, 1);
    }
    Float(const Float& other) : Float(mpfr_get_prec(other.v)) {
        mpfr_set(v, other.v, MPFR_RNDN);
    }
    Float(Float&& other) noexcept : Float(2) { mpfr_swap(v, other.v); }
    Float& operator=(Float other) noexcept { mpfr_swap(v, other.v); return *this; }
    ~Float() { mpfr_clear(v); }
};

std::string decimal(mpfr_srcptr value, unsigned places = 40, char rounding = 'N') {
    const std::string format = "%.*R" + std::string(1, rounding) + "e";
    char* buffer = nullptr;
    if (mpfr_asprintf(&buffer, format.c_str(), int(places), value) < 0)
        throw std::runtime_error("MPFR formatting failed");
    const std::string result(buffer);
    mpfr_free_str(buffer);
    return result;
}

struct Candidate {
    unsigned a, b, c, n;
    mpz_class difference, c_power;
    mutable Float low, high; // Certified bounds for abs(root(S,n)-c).

    Candidate(unsigned aa, unsigned bb, unsigned cc, unsigned nn,
              mpz_class d, mpz_class cp)
        : a(aa), b(bb), c(cc), n(nn), difference(std::move(d)),
          c_power(std::move(cp)) { refine(initial_precision); }

    auto identity() const { return std::make_tuple(n, a, b, c); }

    void refine(mpfr_prec_t precision) const {
        mpfr_set_prec(low.v, precision);
        mpfr_set_prec(high.v, precision);
        // Stable even when the error is thousands of orders below c:
        // root(S,n)-c = c * expm1(log1p((S-c^n)/c^n)/n).
        mpq_class ratio(difference, c_power);
        ratio.canonicalize();
        mpfr_set_q(low.v, ratio.get_mpq_t(), MPFR_RNDD);
        mpfr_set_q(high.v, ratio.get_mpq_t(), MPFR_RNDU);
        mpfr_log1p(low.v, low.v, MPFR_RNDD);
        mpfr_log1p(high.v, high.v, MPFR_RNDU);
        mpfr_div_ui(low.v, low.v, n, MPFR_RNDD);
        mpfr_div_ui(high.v, high.v, n, MPFR_RNDU);
        mpfr_expm1(low.v, low.v, MPFR_RNDD);
        mpfr_expm1(high.v, high.v, MPFR_RNDU);
        mpfr_mul_ui(low.v, low.v, c, MPFR_RNDD);
        mpfr_mul_ui(high.v, high.v, c, MPFR_RNDU);
        if (difference < 0) {
            Float temporary(low);
            mpfr_neg(low.v, high.v, MPFR_RNDN);
            mpfr_neg(high.v, temporary.v, MPFR_RNDN);
        }
        if (!mpfr_number_p(low.v) || !mpfr_number_p(high.v) ||
            mpfr_cmp(low.v, high.v) > 0)
            throw std::runtime_error("Invalid MPFR error interval");
        if (difference != 0 && mpfr_zero_p(low.v))
            throw std::runtime_error("Nonzero integer difference became zero");
    }

    std::string signed_error() const {
        Float middle(mpfr_get_prec(low.v));
        mpfr_add(middle.v, low.v, high.v, MPFR_RNDN);
        mpfr_div_2ui(middle.v, middle.v, 1, MPFR_RNDN);
        if (difference < 0) mpfr_neg(middle.v, middle.v, MPFR_RNDN);
        return decimal(middle.v);
    }
};

bool better(const Candidate& a, const Candidate& b) {
    if (a.identity() == b.identity()) return false;
    if (a.n == b.n && a.c == b.c && a.difference == b.difference)
        return a.identity() < b.identity();
    for (;;) {
        if (mpfr_cmp(a.high.v, b.low.v) < 0) return true;
        if (mpfr_cmp(a.low.v, b.high.v) > 0) return false;
        if (a.difference == 0 && b.difference == 0)
            return a.identity() < b.identity();
        const mpfr_prec_t p = std::max(mpfr_get_prec(a.low.v),
                                       mpfr_get_prec(b.low.v)) * 2;
        if (p > 4096)
            throw std::runtime_error("Ranking intervals overlap at 4096 bits");
        a.refine(p);
        b.refine(p);
    }
}

struct Top {
    size_t capacity;
    std::vector<Candidate> rows;
    explicit Top(size_t count) : capacity(count) {}
    void consider(Candidate candidate) {
        if (rows.size() == capacity && !better(candidate, rows.back())) return;
        auto position = std::lower_bound(rows.begin(), rows.end(), candidate, better);
        if (position != rows.end() && position->identity() == candidate.identity()) return;
        rows.insert(position, std::move(candidate));
        if (rows.size() > capacity) rows.pop_back();
    }
};

struct Config {
    unsigned minimum = 100, maximum = 999, first_power = 3, last_power = 999;
    unsigned threads = std::min(8u, std::max(1u, std::thread::hardware_concurrency() / 2));
    unsigned count = 20;
    bool allow_trivial = false;
    std::string output = "fermat-results.csv";
};

struct Stats {
    uint64_t targets = 0, brackets = 0, passed_integer_screen = 0, qualifying = 0;
    unsigned completed = 0;
    Stats& operator+=(const Stats& b) {
        targets += b.targets; brackets += b.brackets;
        passed_integer_screen += b.passed_integer_screen;
        qualifying += b.qualifying; completed += b.completed; return *this;
    }
};

struct PowerScan {
    const Config& config;
    const unsigned n;
    Top& top;
    Stats& stats;
    std::vector<mpz_class> powers, limits;
    mpz_class delta, magnitude;
    Float epsilon;

    PowerScan(const Config& cfg, unsigned power, Top& records, Stats& counters)
        : config(cfg), n(power), top(records), stats(counters),
          powers(cfg.maximum + 1), limits(cfg.maximum + 1) {
        mpfr_set_ui(epsilon.v, 1, MPFR_RNDN);
        mpfr_div_ui(epsilon.v, epsilon.v, screen_denominator, MPFR_RNDN);
        for (unsigned x = cfg.minimum; x <= cfg.maximum; ++x) {
            mpz_ui_pow_ui(powers[x].get_mpz_t(), x, n);
            mpz_mul_ui(limits[x].get_mpz_t(), powers[x].get_mpz_t(), 2ul * n);
            mpz_cdiv_q_ui(limits[x].get_mpz_t(), limits[x].get_mpz_t(),
                          static_cast<unsigned long>(x) * screen_denominator);
        }
    }

    void evaluate(unsigned a, unsigned b, unsigned c) {
        ++stats.brackets;
        delta = powers[a] + powers[b] - powers[c];
        mpz_abs(magnitude.get_mpz_t(), delta.get_mpz_t());
        // Exact necessary condition for distance < epsilon=1/1024:
        // |S-c^n| < 2*n*epsilon*c^(n-1). See README.txt for the bound.
        if (magnitude > limits[c]) return;
        ++stats.passed_integer_screen;
        Candidate candidate(a, b, c, n, delta, powers[c]);
        if (mpfr_cmp(candidate.low.v, epsilon.v) >= 0) return;
        if (mpfr_cmp(candidate.high.v, epsilon.v) >= 0)
            throw std::runtime_error("Candidate interval intersects the screening boundary");
        ++stats.qualifying;
        top.consider(std::move(candidate));
    }

    bool run() {
        mpz_class twice, target;
        for (unsigned b = config.minimum; b <= config.maximum; ++b) {
            if (interrupted) return false;
            twice = powers[b] * 2;
            const unsigned first_c = b + (config.allow_trivial ? 0 : 1);
            for (unsigned c = first_c; c <= config.maximum; ++c) {
                ++stats.targets;
                if (powers[c] > twice) {
                    // All possible roots for this b are below c. The closest
                    // remaining pair is a=b, and larger c can only be farther.
                    evaluate(b, b, c);
                    break;
                }
                target = powers[c] - powers[b];
                unsigned lo = config.minimum, hi = b + 1;
                while (lo < hi) {
                    const unsigned mid = lo + (hi - lo) / 2;
                    if (powers[mid] < target) lo = mid + 1;
                    else hi = mid;
                }
                if (lo <= b) evaluate(lo, b, c);
                if (lo > config.minimum) evaluate(lo - 1, b, c);
            }
        }
        ++stats.completed;
        return true;
    }
};

Candidate probe(unsigned a, unsigned b, unsigned n, unsigned c) {
    mpz_class ap, bp, cp;
    mpz_ui_pow_ui(ap.get_mpz_t(), a, n);
    mpz_ui_pow_ui(bp.get_mpz_t(), b, n);
    mpz_ui_pow_ui(cp.get_mpz_t(), c, n);
    return Candidate(a, b, c, n, ap + bp - cp, cp);
}

void print_candidate(const Candidate& row, unsigned rank) {
    std::cout << rank << ". " << row.a << '^' << row.n << " + " << row.b
              << '^' << row.n << " ~= " << row.c << '^' << row.n
              << "  root-c=" << row.signed_error() << '\n';
}

void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(std::string("Self-test failed: ") + message);
}

void self_test() {
    struct Fixture { unsigned a,b,n,c; const char* low; const char* high; bool negative; };
    const Fixture fixtures[] = {
        {3987,4365,12,4472,"7.059290738213529240e-9","7.059290738213529243e-9",false},
        {1782,1841,12,1922,"4.413277459708867162e-8","4.413277459708867164e-8",true},
        {6727,6984,24,7084,"1.774402449373805732e-8","1.774402449373805735e-8",true}
    };
    for (const auto& f : fixtures) {
        Candidate c = probe(f.a, f.b, f.n, f.c);
        Float low, high;
        mpfr_set_str(low.v, f.low, 10, MPFR_RNDD);
        mpfr_set_str(high.v, f.high, 10, MPFR_RNDU);
        require(mpfr_cmp(c.low.v, low.v) > 0 && mpfr_cmp(c.high.v, high.v) < 0,
                "published examples disagree with high-precision bounds");
        require((c.difference < 0) == f.negative, "wrong sign");
    }
    Candidate tiny = probe(100,999,999,999);
    require(mpfr_sgn(tiny.low.v) > 0, "dominated term incorrectly became zero");
    Config cfg;
    cfg.minimum=130; cfg.maximum=180; cfg.first_power=cfg.last_power=3;
    cfg.threads=1; cfg.count=8;
    Top fast(cfg.count), oracle(cfg.count);
    Stats stats;
    PowerScan scanner(cfg,3,fast,stats);
    require(scanner.run(), "small search interrupted");
    Float root, distance, epsilon;
    mpfr_set_ui(epsilon.v,1,MPFR_RNDN);
    mpfr_div_ui(epsilon.v,epsilon.v,screen_denominator,MPFR_RNDN);
    // Independent exhaustive oracle: every a,b,c; direct MPFR root and
    // subtraction, with no integer screening or a-bracket reduction.
    for(unsigned a=cfg.minimum;a<=cfg.maximum;++a)
        for(unsigned b=a;b<=cfg.maximum;++b)
            for(unsigned c=b+1;c<=cfg.maximum;++c) {
                mpz_class sum=scanner.powers[a]+scanner.powers[b];
                mpfr_set_z(root.v,sum.get_mpz_t(),MPFR_RNDN);
                mpfr_rootn_ui(root.v,root.v,3,MPFR_RNDN);
                mpfr_sub_ui(distance.v,root.v,c,MPFR_RNDN);
                mpfr_abs(distance.v,distance.v,MPFR_RNDN);
                if(mpfr_cmp(distance.v,epsilon.v)<0)
                    oracle.consider(probe(a,b,3,c));
            }
    require(!oracle.rows.empty(), "empty exhaustive oracle");
    require(oracle.rows.size()==fast.rows.size(), "wrong candidate count");
    for(size_t i=0;i<oracle.rows.size();++i)
        require(oracle.rows[i].identity()==fast.rows[i].identity(),
                "optimized search differs from exhaustive oracle");
    Config four;
    four.minimum=3980; four.maximum=4480; four.count=20;
    Top four_top(four.count);
    Stats four_stats;
    PowerScan four_scan(four,12,four_top,four_stats);
    require(four_scan.run(), "four-digit search interrupted");
    require(std::any_of(four_top.rows.begin(),four_top.rows.end(),
                       [](const Candidate& c) {
                           return c.a==3987 && c.b==4365 && c.c==4472 && c.n==12;
                       }), "four-digit scan omitted the Homer example");
    // This cube miss has an exact integer power difference of -1.
    require(probe(135,138,3,172).difference == -1, "integer power arithmetic");
    std::cout << "PASS: three article examples; nonzero error near 10^-999; "
                 "exact -1 power difference; reduced search vs exhaustive oracle; "
                 "four-digit scan includes the Homer example.\n";
}

unsigned number(const std::string& text) {
    size_t used=0;
    unsigned long long value=std::stoull(text,&used);
    if(used!=text.size() || text.empty() || text[0]=='-' || value>1000000)
        throw std::runtime_error("Invalid integer: "+text);
    return static_cast<unsigned>(value);
}

void help() {
    std::cout <<
        "Search (a^n+b^n)^(1/n) near an integer c. Defaults: 100<=a<=b<c<=999, 3<=n<=999.\n"
        "Only errors below 1/1024 are ranked. All screening uses exact GMP integers.\n"
        "Usage: fermat-search [options]\n"
        "  --min N --max N          Range of a, b AND c (default 100..999)\n"
        "                             Allowed range: 2..9999\n"
        "  --min-power N --max-power N  Exponents, inclusive (default 3..999)\n"
        "  --threads N              Worker count (default up to half the CPU, max 8)\n"
        "  --top N                  Number of results (default 20)\n"
        "  --output PATH            CSV file (default fermat-results.csv)\n"
        "  --allow-trivial          Also allow c=b; dominated terms will win\n"
        "  --probe A B N C          Evaluate one expression at high precision\n"
        "  --self-test              Run arithmetic and exhaustive-oracle checks\n"
        "Ctrl-C stops gracefully and saves PARTIAL results.\n";
}

void write_results(const Config& cfg, const Top& top, const Stats& stats,
                   bool complete, double seconds) {
    std::ofstream file(cfg.output, std::ios::trunc);
    if(!file) throw std::runtime_error("Cannot write "+cfg.output);
    file << "# status=" << (complete?"COMPLETE":"PARTIAL")
         << "; a,b,c=" << cfg.minimum << ".." << cfg.maximum
         << "; n=" << cfg.first_power << ".." << cfg.last_power
         << "; allow_c_equal_b=" << cfg.allow_trivial
         << "; abs_error_limit=1/1024; completed_exponents=" << stats.completed
         << "; seconds=" << seconds << '\n';
    file << "rank,a,b,c,power,root_minus_c,abs_error_lower,abs_error_upper,gcd\n";
    unsigned rank=0;
    for(const auto& c:top.rows) {
        file << ++rank << ',' << c.a << ',' << c.b << ',' << c.c << ',' << c.n
             << ',' << c.signed_error() << ',' << decimal(c.low.v,40,'D')
             << ',' << decimal(c.high.v,40,'U') << ','
             << std::gcd(std::gcd(c.a,c.b),c.c) << '\n';
    }
    file.close();
    if(!file) throw std::runtime_error("Failed to finish "+cfg.output);
}
} // namespace

int main(int argc,char** argv) {
    try {
        Config cfg;
        for(int i=1;i<argc;++i) {
            const std::string option=argv[i];
            if(option=="--help" || option=="-h") {help();return 0;}
            if(option=="--self-test") {self_test();return 0;}
            if(option=="--allow-trivial") {cfg.allow_trivial=true;continue;}
            if(option=="--probe") {
                if(i+4>=argc) throw std::runtime_error("--probe needs A B N C");
                unsigned a=number(argv[++i]),b=number(argv[++i]);
                unsigned n=number(argv[++i]),c=number(argv[++i]);
                if(!a||!b||!c||n<3||n>999)
                    throw std::runtime_error("Probe needs positive bases and 3<=n<=999");
                Candidate row=probe(a,b,n,c); print_candidate(row,1);
                std::cout << "abs_error in [" << decimal(row.low.v,50,'D') << ", "
                          << decimal(row.high.v,50,'U') << "]\n";
                return 0;
            }
            if(i+1>=argc) throw std::runtime_error("Missing value after "+option);
            const std::string value=argv[++i];
            if(option=="--output") cfg.output=value;
            else if(option=="--min") cfg.minimum=number(value);
            else if(option=="--max") cfg.maximum=number(value);
            else if(option=="--min-power") cfg.first_power=number(value);
            else if(option=="--max-power") cfg.last_power=number(value);
            else if(option=="--threads") cfg.threads=number(value);
            else if(option=="--top") cfg.count=number(value);
            else throw std::runtime_error("Unknown option: "+option);
        }
        if(cfg.minimum<2 || cfg.maximum>9999 || cfg.minimum>cfg.maximum ||
           cfg.first_power<3 || cfg.last_power>999 || cfg.first_power>cfg.last_power ||
           cfg.threads<1 || cfg.threads>256 || cfg.count<1 || cfg.count>1000)
            throw std::runtime_error("Invalid range; use --help");
        if(cfg.threads>1 && !mpfr_buildopt_tls_p())
            throw std::runtime_error("MPFR lacks thread-local storage; use --threads 1");
        const unsigned requested=cfg.last_power-cfg.first_power+1;
        cfg.threads=std::min(cfg.threads,requested);
        std::signal(SIGINT,interrupt_handler);
        std::signal(SIGTERM,interrupt_handler);
        std::cout << "a,b,c=" << cfg.minimum << ".." << cfg.maximum
                  << "; n=" << cfg.first_power << ".." << cfg.last_power
                  << "; c" << (cfg.allow_trivial?">=b":">b")
                  << "; threads=" << cfg.threads << "; GMP " << gmp_version
                  << "; MPFR " << mpfr_get_version() << '\n';
        std::cout.flush();
        const auto start=std::chrono::steady_clock::now();
        std::atomic<unsigned> next{cfg.first_power},done{0},finished{0};
        std::atomic<bool> failed{false};
        std::mutex failure_mutex;
        std::string failure;
        std::vector<Top> partial;
        std::vector<Stats> counters(cfg.threads);
        for(unsigned i=0;i<cfg.threads;++i) partial.emplace_back(cfg.count);
        std::vector<std::thread> workers;
        for(unsigned id=0;id<cfg.threads;++id) workers.emplace_back([&,id] {
            try {
                while(!interrupted && !failed.load()) {
                    unsigned n=next.fetch_add(1);
                    if(n>cfg.last_power) break;
                    PowerScan scan(cfg,n,partial[id],counters[id]);
                    if(scan.run()) done.fetch_add(1);
                }
                mpfr_free_cache();
            } catch(const std::exception& e) {
                std::lock_guard<std::mutex> lock(failure_mutex);
                failure=e.what();failed=true;
            }
            finished.fetch_add(1);
        });
        while(finished.load()<cfg.threads) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
            if(finished.load()<cfg.threads)
                std::cerr << "Completed exponents: " << done.load() << '/' << requested << '\n';
        }
        for(auto& worker:workers) worker.join();
        if(failed) throw std::runtime_error(failure);
        Top top(cfg.count); Stats stats;
        for(unsigned i=0;i<cfg.threads;++i) {
            stats+=counters[i];
            for(auto& candidate:partial[i].rows) top.consider(std::move(candidate));
        }
        const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        const bool complete=done.load()==requested;
        write_results(cfg,top,stats,complete,seconds);
        std::cout << (complete?"COMPLETE":"PARTIAL") << ": " << stats.completed
                  << '/' << requested << " exponents; " << stats.targets << " (b,c) targets; "
                  << stats.brackets << " bracketing triples; " << stats.qualifying
                  << " with abs(error)<1/1024; " << std::fixed << std::setprecision(2)
                  << seconds << " seconds\n";
        unsigned rank=0;for(const auto& row:top.rows) print_candidate(row,++rank);
        std::cout << "Saved: " << cfg.output << '\n';
        return complete?0:130;
    } catch(const std::exception& e) {
        std::cerr << "Error: " << e.what() << '\n';return 1;
    }
}
