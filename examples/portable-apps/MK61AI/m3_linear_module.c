#include "stm3_module.h"
#include "m3_linear_protocol.h"

static float vector[AI_M3_MAX_COLUMNS], lookup[128];
static uint32_t columns, received, group, rows;

static uint32_t get32(const uint8_t *p) {
  return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
         (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static void put32(uint8_t *p, uint32_t x) {
  p[0] = (uint8_t)x; p[1] = (uint8_t)(x >> 8);
  p[2] = (uint8_t)(x >> 16); p[3] = (uint8_t)(x >> 24);
}
static float load_float(const uint8_t *p) {
  union { uint32_t u; float f; } v = {get32(p)};
  return v.f;
}
static void store_float(uint8_t *p, float x) {
  union { float f; uint32_t u; } v = {x};
  put32(p, v.u);
}
static uint32_t finite(float x) {
  union { float f; uint32_t u; } v = {x};
  return (v.u & 0x7f800000u) != 0x7f800000u;
}
static float half(uint32_t h) {
  const uint32_t sign = h >> 15, exponent = (h >> 10) & 31u;
  const uint32_t mantissa = h & 1023u;
  union { uint32_t u; float f; } v;
  if (exponent) {
    v.u = ((exponent + 112u) << 23) | (mantissa << 13);
  } else {
    v.f = (float)mantissa * 0x1p-24f;
  }
  return sign ? -v.f : v.f;
}
static float plane(const float *t, const uint8_t *p) {
  float sum = 0;
  sum += t[p[0] & 15]; sum += t[16 + (p[0] >> 4)];
  sum += t[32 + (p[1] & 15)]; sum += t[48 + (p[1] >> 4)];
  sum += t[64 + (p[2] & 15)]; sum += t[80 + (p[2] >> 4)];
  sum += t[96 + (p[3] & 15)]; sum += t[112 + (p[3] >> 4)];
  return sum;
}
static uint32_t ack(stm3_job *job) {
  put32(job->output, AI_M3_MAGIC);
  put32(job->output + 4, columns); put32(job->output + 8, received);
  job->output_bytes = 12; job->progress = received;
  return STM3_DONE;
}
uint32_t module_entry(uint32_t operation, const stm3_api *api, stm3_job *job) {
  if (operation == STM3_FINI) {
    columns = received = rows = group = 0;
    return STM3_DONE;
  }
  if (operation == STM3_CANCEL) {
    columns = received = rows = group = 0;
    return STM3_DONE;
  }
  if (!api || api->abi != STM3_ABI || api->size < sizeof(*api) || !job ||
      !job->input || !job->output || job->output_capacity < 12)
    return STM3_INVALID;
  if (operation == STM3_INIT) {
    rows = group = 0;
    job->output_bytes = job->progress = 0;
    if (columns && received < columns * 4u) {
      const uint32_t n = job->input_bytes;
      if (!n || n % 4u || n > STM3_IO_CAPACITY || n > columns * 4u - received)
        return STM3_INVALID;
      /* Validate the complete chunk before changing persistent vector state. */
      for (uint32_t i = 0; i < n; i += 4)
        if (!finite(load_float(job->input + i))) return STM3_INVALID;
      for (uint32_t i = 0; i < n; i += 4)
        vector[(received + i) / 4] = load_float(job->input + i);
      received += n;
      return ack(job);
    }
    if (job->input_bytes < AI_M3_HEADER || get32(job->input) != AI_M3_MAGIC)
      return STM3_INVALID;
    const uint32_t cmd = get32(job->input + 4), nc = get32(job->input + 8);
    const uint32_t nr = get32(job->input + 12);
    if (cmd == AI_M3_PREPARE) {
      if (!nc || nc % 32u || nc > AI_M3_MAX_COLUMNS || nr ||
          job->input_bytes != AI_M3_HEADER) return STM3_INVALID;
      columns = nc; received = 0;
      return ack(job);
    }
    if (cmd != AI_M3_RUN || nc != columns || !columns ||
        received != columns * 4u || !nr || nr > AI_M3_MAX_ROWS ||
        job->input_bytes != AI_M3_HEADER + nr * (columns / 2u + columns / 16u) ||
        job->input_bytes > STM3_IO_CAPACITY) return STM3_INVALID;
    rows = nr;
    for (uint32_t r = 0; r < rows; ++r) store_float(job->output + r * 4u, 0);
    job->output_bytes = rows * 4u;
    return STM3_MORE;
  }
  if (operation != STM3_STEP || !rows || group >= columns / 32u)
    return STM3_INVALID;
  float total = 0;
  for (uint32_t quartet = 0; quartet < 8; ++quartet) {
    float *t = lookup + quartet * 16;
    t[0] = 0;
    for (uint32_t lane = 0; lane < 4; ++lane)
      for (uint32_t mask = 0; mask < (1u << lane); ++mask)
        t[mask + (1u << lane)] = t[mask] + vector[group * 32 + quartet * 4 + lane];
    total += t[15];
  }
  for (uint32_t r = 0; r < rows; ++r) {
    const uint8_t *w = job->input + AI_M3_HEADER + r * (columns / 2u + columns / 16u);
    const uint8_t *s = w + columns / 2u + group * 2u;
    const uint32_t h = (uint32_t)s[0] | (uint32_t)s[1] << 8;
    if ((h & 0x7c00u) == 0x7c00u) return STM3_INVALID;
    w += group * 16u;
    float weighted = 0;
    weighted += plane(lookup, w);
    weighted += plane(lookup, w + 4) * 2.0f;
    weighted += plane(lookup, w + 8) * 4.0f;
    weighted += plane(lookup, w + 12) * 8.0f;
    const float value = load_float(job->output + r * 4u) +
                        (weighted - 8.0f * total) * half(h);
    if (!finite(value)) return STM3_INVALID;
    store_float(job->output + r * 4u, value);
  }
  job->progress = ++group;
  return group == columns / 32u ? STM3_DONE : STM3_MORE;
}
