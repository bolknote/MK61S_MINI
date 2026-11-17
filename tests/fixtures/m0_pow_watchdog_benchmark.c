/* Exact-image Pico H benchmark for the production pow fallback.
 * All machine addresses are generated and verified against the sealed ELF.
 * The APP does not feed the watchdog during a timed call sequence.
 */
#include "mk61_app.h"
#include "pow_locations.h"
#include <stddef.h>
#include <stdint.h>

#define COUNT_MAX 12U
#define DIRECTORY "/MK61S-POW-WDT"
#define ABS_MASK UINT64_C(0x7FFFFFFFFFFFFFFF)
#define FINITE_END UINT64_C(0x7FF0000000000000)
#define VERSION 1U
typedef _Bool (*interval_fn)(uint64_t, uint64_t, uint64_t *);
typedef int (*exact_fn)(uint64_t, uint64_t, uint64_t *);
typedef int (*side_fn)(uint64_t, uint64_t, uint64_t);
typedef void (*feed_fn)(void);
typedef uint32_t (*clock_fn)(unsigned);

typedef struct {
    uint32_t magic, version, cases, reserved;
} InputHeader;
typedef struct {
    uint64_t x, y, lower, expected;
} Vector;
typedef struct {
    uint64_t before_us, after_us;
    uint32_t before_count, after_count, in_timing_count;
    uint32_t step512_us, step1024_us, exact_us, step4096_us, chain_us;
    uint32_t accepted, side, sys_hz_before, sys_hz_after;
    uint64_t rounded;
} Sample;
static struct {
    uint32_t magic, version, build, cases, timeout_ms, failures, first, reserved;
    Sample samples[COUNT_MAX];
} output;
_Static_assert(sizeof(InputHeader) == 16 && sizeof(Vector) == 32 && sizeof(Sample) == 72 &&
                   offsetof(__typeof__(output), samples) == 32,
               "Report wire layout");

static uint32_t word(uintptr_t address) { return *(const volatile uint32_t *)address; }

static uint64_t counter64(uintptr_t low, uintptr_t high) {
    uint32_t a, b, c;
    do {
        a = word(high);
        b = word(low);
        c = word(high);
    } while (a != c);
    return ((uint64_t)a << 32) | b;
}

static uint32_t micros(void) {
    __asm__ volatile("" ::: "memory");
    return word(UINT32_C(0x40054028)); /* TIMERAWL */
}

static uint64_t last_feed(void) { return counter64(POW_WDT_LAST_FEED, POW_WDT_LAST_FEED + 4U); }

static int check_footer(void) {
    static const uint32_t expected[] = {POW_FOOTER_WORDS};
    const volatile uint32_t *actual = (const volatile uint32_t *)(uintptr_t)POW_FW_FOOTER;
    __asm__ volatile("" : "+r"(actual));
    for (unsigned i = 0; i < sizeof(expected) / sizeof(expected[0]); ++i)
        if (actual[i] != expected[i])
            return 0;
    return 1;
}

static int profile_one(const Vector *v, Sample *out) {
    feed_fn feed = (feed_fn)(uintptr_t)POW_FEED;
    clock_fn clock_hz = (clock_fn)(uintptr_t)POW_CLOCK_HZ;
    const uint32_t first = word(POW_WDT_STATE + 8U);
    const uint32_t waiting = micros();
    do {
        mk61_api->service();
        feed();
        if (micros() - waiting > 250000U)
            return 0;
    } while (word(POW_WDT_STATE + 8U) == first);

    out->before_count = word(POW_WDT_STATE + 8U);
    out->before_us = last_feed();
    uint64_t r512 = FINITE_END, r1024 = FINITE_END, exact = v->lower;

    out->sys_hz_before = clock_hz(5U); /* clk_sys */
    if (out->sys_hz_before != 125000000U)
        return 0;
    const uint32_t begin = micros();
    const int a = ((interval_fn)(uintptr_t)POW_FIXED512)(v->x, v->y, &r512);
    const uint32_t t1 = micros();
    const int b = ((interval_fn)(uintptr_t)POW_FIXED1024)(v->x, v->y, &r1024);
    const uint32_t t2 = micros();
    const int c = ((exact_fn)(uintptr_t)POW_EXACT)(v->x, v->y, &exact);
    const uint32_t t3 = micros();
    const int r = ((side_fn)(uintptr_t)POW_BOUNDS4096)(v->x, v->y, v->lower);
    const uint32_t end = micros();

    out->in_timing_count = word(POW_WDT_STATE + 8U);
    feed();
    out->after_count = word(POW_WDT_STATE + 8U);
    out->after_us = last_feed();
    out->sys_hz_after = clock_hz(5U);
    out->step512_us = t1 - begin;
    out->step1024_us = t2 - t1;
    out->exact_us = t3 - t2;
    out->step4096_us = end - t3;
    out->chain_us = end - begin;
    out->accepted = (unsigned)a | ((unsigned)b << 1) | ((unsigned)c << 2);
    out->side = (unsigned)r;
    out->rounded = v->lower + (r > 0);

    return out->sys_hz_after == out->sys_hz_before && out->in_timing_count == out->before_count &&
           out->after_count == out->before_count + 1U && out->after_us >= out->before_us &&
           out->after_us - out->before_us >= out->chain_us &&
           out->after_us - out->before_us < (uint64_t)(output.timeout_ms * 1000U) &&
           (r == -1 || r == 1) && out->rounded == v->expected && (!a || r512 == v->expected) &&
           (!b || r1024 == v->expected) && (!c || exact == v->expected);
}

int main(void) {
    if (!check_footer() || !(word(POW_WDT_STATE) & 1U))
        return MK61_APP_RUNTIME_ERROR;
    output.timeout_ms = word(POW_WDT_STATE + 4U);
    if (output.timeout_ms != 8000U)
        return MK61_APP_RUNTIME_ERROR;
    const mk61_app_services *s = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_FILES);
    if (!s || !mk61_api->file_read || !mk61_api->file_size)
        return MK61_APP_RUNTIME_ERROR;
    mk61_service_file file = {0};
    if (s->call(MK61_SERVICE_FILE_RESOLVE, MK61_SERVICE_ROOT_ID, MK61_SERVICE_FILE_MK61_BINARY,
                (uint32_t)(uintptr_t)(DIRECTORY "/INPUT.bin"), &file))
        return MK61_APP_IO_ERROR;
    InputHeader header;
    if (mk61_api->file_read(file.id, 0, (uint8_t *)&header, sizeof(header)) != sizeof(header) ||
        header.magic != UINT32_C(0x50574937) || header.version != VERSION || header.reserved ||
        !header.cases || header.cases > COUNT_MAX ||
        mk61_api->file_size(file.id) != sizeof(header) + header.cases * sizeof(Vector))
        return MK61_APP_INVALID_FILE;
    Vector inputs[COUNT_MAX];
    if (mk61_api->file_read(file.id, sizeof(header), (uint8_t *)inputs,
                            header.cases * sizeof(Vector)) != header.cases * sizeof(Vector))
        return MK61_APP_IO_ERROR;
    for (unsigned i = 0; i < header.cases; ++i) {
        const Vector *v = &inputs[i];
        if (!v->x || v->x >= FINITE_END || (v->y & ABS_MASK) >= FINITE_END || v->lower >= FINITE_END ||
            (v->expected != v->lower && v->expected != v->lower + 1U))
            return MK61_APP_INVALID_FILE;
    }

    output.magic = UINT32_C(0x50575237);
    output.version = VERSION;
    output.build = POW_BUILD_ID;
    output.cases = header.cases;
    output.failures = 0;
    output.first = UINT32_MAX;
    output.reserved = 0;
    for (unsigned i = 0; i < header.cases; ++i) {
        if (!profile_one(&inputs[i], &output.samples[i])) {
            output.failures = 1;
            output.first = i;
            output.cases = i + 1U;
            break;
        }
    }
    mk61_service_write out = {
        "RESULT", (const uint8_t *)&output,
        (uint32_t)(offsetof(__typeof__(output), samples) + output.cases * sizeof(Sample)),
        MK61_SERVICE_INVALID_ID};
    return s->call(MK61_SERVICE_FILE_WRITE, file.parent, MK61_SERVICE_INVALID_ID,
                   MK61_SERVICE_FILE_MK61_BINARY, &out)
               ? MK61_APP_OK
               : MK61_APP_IO_ERROR;
}
