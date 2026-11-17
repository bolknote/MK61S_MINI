/* Call the sealed production functions directly to exercise all pow stages. */
#include "mk61_app.h"
#include "pow_total_locations.h"
#include <stddef.h>
#include <stdint.h>
#define DIR "/MK61S-POW-EXACT"

typedef _Bool (*interval_fn)(uint64_t, uint64_t, uint64_t *);
typedef int (*exact_fn)(uint64_t, uint64_t, uint64_t *);
typedef int (*side_fn)(uint64_t, uint64_t, uint64_t);
typedef uint64_t (*round_fn)(uint64_t, uint64_t, uint64_t);
typedef uint32_t (*clock_fn)(unsigned);
typedef void (*feed_fn)(void);

typedef struct {
    uint64_t x, y, lower, expected;
    uint32_t full, pad;
} Case;

typedef struct {
    uint32_t prefix_us, tail_us, elapsed_us, prior_reloads, entry_reloads, after_reloads;
    uint32_t max_gap_ms, last_feed_age_us, announced_hz, finish_hz;
    uint32_t caller_stack_bytes, reserved;
    uint64_t returned;
} Sample;

_Static_assert(sizeof(Case) == 40 && sizeof(Sample) == 56, "Benchmark wire layout");

static struct {
    uint32_t tag, build, count, timeout_ms, fail, pad;
    Sample samples[4];
} report;

static uint32_t word(uintptr_t address) { return *(const volatile uint32_t *)address; }

static uint32_t micros(void) {
    __asm__ volatile("" ::: "memory");
    return word(UINT32_C(0x40054028)); /* TIMERAWL */
}

static int footer_ok(void) {
    const uint32_t expected[] = {POW_FOOTER_WORDS};
    const volatile uint32_t *actual = (const volatile uint32_t *)(uintptr_t)POW_FW_FOOTER;
    __asm__ volatile("" : "+r"(actual));
    for (unsigned i = 0; i < sizeof(expected) / sizeof(*expected); ++i)
        if (actual[i] != expected[i])
            return 0;
    return 1;
}

static int evaluate(const Case *input, Sample *out) {
    feed_fn feed = (feed_fn)(uintptr_t)POW_FEED;
    clock_fn clock_hz = (clock_fn)(uintptr_t)POW_CLOCK;
    const uint64_t x = input->x, y = input->y, lower = input->lower, want = input->expected;
    const uint32_t old_count = word(POW_WATCHDOG + 8U);
    const uint32_t start_wait = micros();
    while (word(POW_WATCHDOG + 8U) == old_count) {
        mk61_api->service();
        feed();
        if (micros() - start_wait > 250000U)
            return 0;
    }
    out->announced_hz = clock_hz(5);
    out->prior_reloads = word(POW_WATCHDOG + 8U);
    const uint32_t begin = micros();
    uint64_t lower512 = UINT64_C(0x7ff0000000000000), lower1024 = lower512, exact = lower;
    int a = 0, b = 0, c = 0, side = 0;
    if (input->full) {
        a = ((interval_fn)(uintptr_t)POW_512)(x, y, &lower512);
        b = ((interval_fn)(uintptr_t)POW_1024)(x, y, &lower1024);
        c = ((exact_fn)(uintptr_t)POW_EXACT)(x, y, &exact);
        side = ((side_fn)(uintptr_t)POW_4096)(x, y, lower);
    }
    const uint32_t tail_begin = micros();
    out->entry_reloads = word(POW_WATCHDOG + 8U);
    uint32_t stack;
    __asm__ volatile("mrs %0, msp" : "=r"(stack));
    out->caller_stack_bytes = POW_STACK_TOP - stack;
    if (input->full) {
        out->returned = ((round_fn)(uintptr_t)POW_FINAL)(x, y, lower);
    } else {
        const int relation = ((side_fn)(uintptr_t)POW_STREAM)(x, y, lower);
        if (relation != 1 && relation != -1)
            return 0;
        out->returned = lower + (relation > 0);
    }
    const uint32_t end = micros();
    out->last_feed_age_us = end - word(POW_LAST_FEED);
    out->after_reloads = word(POW_WATCHDOG + 8U);
    out->max_gap_ms = word(POW_WATCHDOG + 12U);
    feed();
    out->finish_hz = clock_hz(5);
    out->prefix_us = tail_begin - begin;
    out->tail_us = end - tail_begin;
    out->elapsed_us = end - begin;
    return out->returned == want && (!a || lower512 == want) && (!b || lower1024 == want) &&
           (!c || exact == want) && (!input->full || side == (want > lower ? 1 : -1)) &&
           out->announced_hz == 125000000U && out->finish_hz == out->announced_hz &&
           out->entry_reloads == out->prior_reloads && out->last_feed_age_us < 8000000U &&
           out->max_gap_ms < 8000U && out->caller_stack_bytes <= (32768U - 20480U) &&
           (out->tail_us < 30000U || out->after_reloads > out->entry_reloads);
}

int main(void) {
    if (!footer_ok() || !(word(POW_WATCHDOG) & 1U) || word(POW_WATCHDOG + 4U) != 8000U)
        return MK61_APP_RUNTIME_ERROR;
    const mk61_app_services *files = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_FILES);
    mk61_service_file input = {0};
    if (!files ||
        files->call(MK61_SERVICE_FILE_RESOLVE, MK61_SERVICE_ROOT_ID, MK61_SERVICE_FILE_MK61_BINARY,
                    (uint32_t)(uintptr_t)(DIR "/INPUT.bin"), &input))
        return MK61_APP_IO_ERROR;
    Case entries[4];
    if (mk61_api->file_size(input.id) != sizeof(entries) ||
        mk61_api->file_read(input.id, 0, (uint8_t *)entries, sizeof(entries)) != sizeof(entries))
        return MK61_APP_INVALID_FILE;
    report.tag = UINT32_C(0x544f5731);
    report.build = POW_BUILD_ID;
    report.count = 4;
    report.timeout_ms = 8000;
    for (unsigned i = 0; i < 4; ++i) {
        if (!evaluate(&entries[i], &report.samples[i])) {
            report.fail = i + 1;
            break;
        }
    }
    mk61_service_write out = {"RESULT", (const uint8_t *)&report, sizeof(report),
                              MK61_SERVICE_INVALID_ID};
    return files->call(MK61_SERVICE_FILE_WRITE, input.parent, MK61_SERVICE_INVALID_ID,
                       MK61_SERVICE_FILE_MK61_BINARY, &out)
               ? MK61_APP_OK
               : MK61_APP_IO_ERROR;
}
