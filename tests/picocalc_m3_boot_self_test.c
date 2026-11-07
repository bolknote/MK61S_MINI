#include "wire.h"
#include <stdio.h>
#include <string.h>
#ifdef M3B_ARM_TEST
void test_arm_fail(unsigned, const char *) __attribute__((noreturn));
#define CHECK(x)                                                               \
  do {                                                                         \
    if (!(x))                                                                  \
      test_arm_fail(__LINE__, #x);                                             \
  } while (0)
#else
#include <assert.h>
#define CHECK assert
#endif
static uint8_t memory[65536], image[2180], old_image[512], header[32],
    old_header[32];
static int budget = -1, mutations, partial;
static const uint8_t *read_at(void *p, uint32_t at, uint32_t n) {
  (void)p;
  CHECK(at >= M3B_FLASH && at <= M3B_SETTINGS && n <= M3B_SETTINGS - at);
  return memory + (at - M3B_FLASH);
}
static int tick(void) {
  if (budget == 0)
    return 0;
  if (budget > 0)
    --budget;
  ++mutations;
  return 1;
}
static int erase(void *p, uint32_t at) {
  (void)p;
  CHECK(!(at & 1023) && at >= M3B_APP && at <= M3B_META);
  if (!tick()) {
    if (partial)
      memset(memory + (at - M3B_FLASH), 255, 512);
    return 0;
  }
  memset(memory + (at - M3B_FLASH), 255, 1024);
  return 1;
}
static int program(void *p, uint32_t at, const uint8_t *data, uint32_t n) {
  (void)p;
  CHECK(!(at & 1) && !(n & 1) && at >= M3B_APP && n <= M3B_SETTINGS - at);
  for (unsigned i = 0; i < n; i += 2) {
    uint8_t *dst = memory + (at - M3B_FLASH) + i;
    CHECK((dst[0] & data[i]) == data[i] &&
          (dst[1] & data[i + 1]) == data[i + 1]);
    if (!tick()) {
      if (partial)
        dst[0] &= data[i];
      return 0;
    }
    dst[0] = data[i];
    dst[1] = data[i + 1];
  }
  return 1;
}
static const m3b_flash flash = {0, read_at, erase, program};
static void make_header(uint8_t *h, const uint8_t *data, unsigned n) {
  const uint32_t words[7] = {M3B_MAGIC,        1,  M3B_TARGET, M3B_APP, n,
                             m3b_crc(data, n), 123};
  for (unsigned i = 0; i < 7; ++i)
    m3b_put(h + 4 * i, words[i]);
  m3b_put(h + 28, m3b_crc(h, 28));
}
static void initial(void) {
  budget = -1;
  mutations = 0;
  memset(memory, 0x69, sizeof(memory));
  memset(memory + 8192, 255, M3B_SETTINGS - M3B_APP);
  memcpy(memory + 8192, old_image, sizeof(old_image));
  memcpy(memory + (M3B_META - M3B_FLASH), old_header, 32);
  m3b_put(memory + (M3B_META - M3B_FLASH) + 32, M3B_VALID);
}
static unsigned call(m3b_update *u, unsigned op, const uint8_t *in,
                     unsigned n) {
  uint8_t out[256];
  unsigned used = m3b_command(u, (uint8_t)op, in, n, out);
  CHECK(used >= 4 && used <= 256);
  return m3b_get(out);
}
static unsigned update(m3b_update *u) {
  unsigned e = call(u, M3B_BEGIN, header, 32);
  if (e)
    return e;
  for (unsigned at = 0; at < sizeof(image);) {
    unsigned n = sizeof(image) - at;
    if (n > M3B_CHUNK)
      n = M3B_CHUNK;
    uint8_t data[244];
    m3b_put(data, at);
    memcpy(data + 4, image + at, n);
    e = call(u, M3B_WRITE, data, n + 4);
    if (e)
      return e;
    at += n;
  }
  return call(u, M3B_COMMIT, 0, 0);
}
static void preserved(void) {
  for (unsigned i = 0; i < 8192; ++i)
    CHECK(memory[i] == 0x69);
  for (unsigned i = M3B_SETTINGS - M3B_FLASH; i < sizeof(memory); ++i)
    CHECK(memory[i] == 0x69);
}
static unsigned send(m3b_link *l, uint8_t op, uint16_t seq, const uint8_t *data,
                     unsigned n) {
  uint8_t wire[272];
  unsigned bytes = m3b_packet(M3B_WIRE_VERSION, op, seq, data, n, wire),
           reply = 0;
  CHECK(bytes);
  for (unsigned i = 0; i < bytes; ++i) {
    unsigned r = m3b_feed(l, wire[i]);
    if (r)
      reply = r;
  }
  return reply;
}
int main(int argc, char **argv) {
  (void)argc;
  (void)argv;
  for (unsigned i = 0; i < sizeof(image); ++i)
    image[i] = (uint8_t)(i * 17 + 31);
  m3b_put(image, M3B_MAILBOX);
  m3b_put(image + 4, M3B_APP + 129);
  memcpy(old_image, image, sizeof(old_image));
  old_image[20] ^= 1;
  make_header(header, image, sizeof(image));
  make_header(old_header, old_image, sizeof(old_image));
  CHECK(m3b_crc((const uint8_t *)"123456789", 9) == 0xcbf43926);
  initial();
  m3b_update u;
  m3b_init(&u, &flash);
  CHECK(m3b_valid(&u));
  CHECK(update(&u) == 0 && m3b_valid(&u));
  int all = mutations;
  CHECK(all > 1000);
  preserved();
/* Cut every erase/halfword write, including partial erase/program effects.
 * After a cold boot, only a fully valid old/new image may be launched.
 * A new full transaction must recover from every interrupted state. */
#ifdef M3B_ARM_TEST
  const int stride = all / 7;
#else
  const int stride = 1;
#endif
  for (partial = 0; partial < 2; ++partial)
    for (int cut = 0; cut <= all; cut += stride) {
      initial();
      budget = cut;
      m3b_init(&u, &flash);
      unsigned status = update(&u);
      budget = -1;
      m3b_init(&u, &flash);
      if (m3b_valid(&u)) {
        const uint8_t *h = read_at(0, M3B_META, 32);
        CHECK(m3b_get(h + 20) == m3b_get(old_header + 20) ||
              m3b_get(h + 20) == m3b_get(header + 20));
      }
      if (status)
        CHECK(status == M3B_FLASH_ERROR);
      CHECK(update(&u) == 0 && m3b_valid(&u));
      preserved();
    }
  initial();
  m3b_init(&u, &flash);
  uint8_t bad[32];
  memcpy(bad, header, 32);
  bad[8] ^= 1;
  CHECK(call(&u, M3B_BEGIN, bad, 32) == M3B_ARGUMENT && m3b_valid(&u) &&
        mutations == 0);
  CHECK(call(&u, M3B_BEGIN, header, 32) == 0);
  CHECK(call(&u, M3B_RUN, 0, 0) == M3B_STATE);
  CHECK(call(&u, M3B_COMMIT, 0, 0) == M3B_STATE);
  uint8_t data[244];
  m3b_put(data, 2);
  memcpy(data + 4, image, 240);
  CHECK(call(&u, M3B_WRITE, data, 244) == M3B_SIZE);
  m3b_put(data, 0);
  CHECK(call(&u, M3B_WRITE, data, 244) == 0);
  int count = mutations;
  CHECK(call(&u, M3B_WRITE, data, 244) == 0 && count == mutations);
  data[9] ^= 1;
  CHECK(call(&u, M3B_WRITE, data, 244) == M3B_ARGUMENT);
  data[9] ^= 1;
  m3b_put(data, M3B_SETTINGS);
  m3b_put(data + 4, 2);
  CHECK(call(&u, M3B_READ, data, 8) == M3B_SIZE);
  CHECK(update(&u) == 0);
  memory[8192 + 33] ^= 1;
  CHECK(!m3b_valid(&u));
  m3b_link l;
  initial();
  m3b_link_init(&l, &flash);
  CHECK(send(&l, M3B_BEGIN, 1, header, 32));
  count = mutations;
  CHECK(send(&l, M3B_BEGIN, 1, header, 32) && mutations == count);
  CHECK(
      !send(&l, M3B_INFO, 1, 0, 0)); /* Same sequence with different request. */
  CHECK(send(&l, M3B_INFO, 2, 0, 0));
  uint8_t wire[272];
  unsigned bytes = m3b_packet(M3B_WIRE_VERSION, M3B_BEGIN, 3, header, 32, wire);
  for (unsigned flip = 1; flip < bytes - 1; ++flip) {
    count = mutations;
    wire[flip] ^= 0x80;
    for (unsigned i = 0; i < bytes; ++i)
      (void)m3b_feed(&l, wire[i]);
    CHECK(mutations == count);
    wire[flip] ^= 0x80;
  }
  for (unsigned i = 0; i < 300; ++i)
    CHECK(!m3b_feed(&l, 1));
  CHECK(!m3b_feed(&l, 0));
  CHECK(send(&l, M3B_INFO, 4, 0, 0));
  /* Full-wire transaction and commit replay. */
  CHECK(send(&l, M3B_BEGIN, 5, header, 32));
  uint16_t seq = 6;
  for (unsigned at = 0; at < sizeof(image);) {
    unsigned n = sizeof(image) - at;
    if (n > 240)
      n = 240;
    m3b_put(data, at);
    memcpy(data + 4, image + at, n);
    CHECK(send(&l, M3B_WRITE, seq++, data, n + 4));
    at += n;
  }
  CHECK(send(&l, M3B_COMMIT, seq, 0, 0));
  count = mutations;
  CHECK(send(&l, M3B_COMMIT, seq++, 0, 0) && count == mutations);
  CHECK(m3b_valid(&l.update));
  CHECK(send(&l, M3B_RUN, seq, 0, 0) && l.update.run);
  preserved();
  printf("M3 boot PASS: %d cut points, partial erase/program, cold recovery, "
         "protected ranges, framing and replay\n",
         (all + 1) * 2);
  return 0;
}
