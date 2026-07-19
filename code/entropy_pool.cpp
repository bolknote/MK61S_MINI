#include "entropy_pool.hpp"

#include <Arduino.h>

#include "mk61emu_core.h"

namespace entropy_pool {
namespace {

static constexpr u16 TARGET_ENTROPY_BITS = 64;
static constexpr u16 MAX_STARTUP_SAMPLES = 1024;
static constexpr usize DOMAIN_COUNT = 3;

static u64 pool_state = 0x6A09E667F3BCC909ULL;
static u64 stream_state[DOMAIN_COUNT];
static u64 event_counter;
static u16 raw_sample_count;
static u8 extracted_bit_count;
static u8 first_pair_bit;
static bool have_first_pair_bit;
static bool collection_started;
static bool adc_resolution_owned;
static bool streams_ready;
static bool calculator_enhanced;

static u64 avalanche(u64 value) {
  value ^= value >> 30;
  value *= 0xBF58476D1CE4E5B9ULL;
  value ^= value >> 27;
  value *= 0x94D049BB133111EBULL;
  return value ^ (value >> 31);
}

static void absorb(u64 value) {
  event_counter++;
  const u64 event = avalanche(value + event_counter * 0x9E3779B97F4A7C15ULL);
  pool_state = avalanche(pool_state ^ event);

  if(!streams_ready) return;
  for(usize domain = 0; domain < DOMAIN_COUNT; domain++) {
    stream_state[domain] ^= avalanche(event + (domain + 1U) * 0xD1B54A32D192ED03ULL);
  }
}

static void initialize_streams(void) {
  if(streams_ready) return;
  absorb(((u64) micros() << 32) ^ millis() ^ 0x53545245414DULL);
  for(usize domain = 0; domain < DOMAIN_COUNT; domain++) {
    stream_state[domain] = avalanche(pool_state ^ ((domain + 1U) * 0xD1B54A32D192ED03ULL));
  }
  streams_ready = true;
}

static void sample_adc(void) {
  if(!collection_started || raw_sample_count >= MAX_STARTUP_SAMPLES) return;

  const u16 value = (u16) analogRead(AVBAT);
  const u32 timestamp = micros();
  raw_sample_count++;
  absorb(((u64) value << 48) ^ ((u64) timestamp << 16) ^ raw_sample_count);

  const u8 bit = value & 1U;
  if(!have_first_pair_bit) {
    first_pair_bit = bit;
    have_first_pair_bit = true;
    return;
  }

  have_first_pair_bit = false;
  if(first_pair_bit == bit) return;

  // Von Neumann debiasing: 01 -> 0, 10 -> 1.
  const u8 extracted = first_pair_bit == 1U ? 1U : 0U;
  if(extracted_bit_count < TARGET_ENTROPY_BITS) extracted_bit_count++;
  absorb(0x564E000000000000ULL ^ ((u64) extracted_bit_count << 8) ^ extracted);
}

static u64 calculator_seed_material(void) {
  const u64 high = next_u32(Domain::CALCULATOR);
  return (high << 32) | next_u32(Domain::CALCULATOR);
}

} // namespace

void begin(void) {
  if(collection_started) return;

  pool_state = 0x6A09E667F3BCC909ULL;
  event_counter = 0;
  raw_sample_count = 0;
  extracted_bit_count = 0;
  have_first_pair_bit = false;
  streams_ready = false;
  calculator_enhanced = false;
  collection_started = true;

  absorb(((u64) micros() << 32) ^ millis() ^ 0x424F4F54ULL);
#if defined(UID_BASE)
  const volatile u32* const uid = reinterpret_cast<const volatile u32*>(UID_BASE);
  absorb(((u64) uid[0] << 32) | uid[1]);
  absorb(((u64) uid[2] << 32) ^ 0x554944ULL);
#endif

  analogReadResolution(12);
  adc_resolution_owned = true;
  (void) analogRead(AVBAT); // discard the first internal-mux settling sample
}

void poll_startup(void) {
  if(!collection_started) begin();
  if(extracted_bit_count >= TARGET_ENTROPY_BITS) return;
  sample_adc();
}

void finish_startup(void) {
  if(!collection_started) begin();
  while(extracted_bit_count < TARGET_ENTROPY_BITS && raw_sample_count < MAX_STARTUP_SAMPLES) {
    sample_adc();
  }

  absorb(((u64) micros() << 32) ^ raw_sample_count ^ ((u64) extracted_bit_count << 16));
  if(adc_resolution_owned) {
    analogReadResolution(ADC_RESOLUTION);
    adc_resolution_owned = false;
  }
  initialize_streams();
}

void note_rtc_snapshot(u8 snapshot_index, u64 calendar_material, u64 phase_material) {
  if(!collection_started) begin();
  const u64 index = snapshot_index;
  absorb(calendar_material ^ 0x5254432D43414C00ULL ^ index); // "RTC-CAL"
  absorb(phase_material ^ 0x5254432D50485300ULL ^ index);    // "RTC-PHS"
}

void note_key(u8 keycode, u32 timestamp_us) {
  if(!collection_started) begin();
  absorb(((u64) timestamp_us << 32) ^ ((u64) keycode << 16) ^ micros());

  if(calculator_enhanced && core_61::random_seed_enabled()) {
    core_61::update_random_seed(((u64) timestamp_us << 32) ^ calculator_seed_material());
  }
}

u32 next_u32(Domain domain) {
  initialize_streams();
  usize index = (usize) domain;
  if(index >= DOMAIN_COUNT) index = 0;

  stream_state[index] += 0x9E3779B97F4A7C15ULL;
  const u64 value = avalanche(stream_state[index]);
  return (u32) (value ^ (value >> 32));
}

void configure_calculator(bool enhanced) {
  calculator_enhanced = enhanced;
  if(!enhanced) {
    core_61::configure_random_seed(false, 1);
    return;
  }

  core_61::configure_random_seed(true, calculator_seed_material());
}

u16 startup_raw_samples(void) {
  return raw_sample_count;
}

u8 startup_entropy_bits(void) {
  return extracted_bit_count;
}

} // namespace entropy_pool
