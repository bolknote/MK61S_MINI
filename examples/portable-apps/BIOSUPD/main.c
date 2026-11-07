/* Pico H only. Stage the complete physical file before taking M3 offline. */
#include "mk61_app.h"
#include "pico_uart1.h"
#include "wire.h"
#include <string.h>
#ifndef REG
#define REG(a) (*(volatile uint32_t *)(uintptr_t)(a))
#endif
static const mk61_app_services *svc;
static stm3_pico_uart1 uart;
static uint8_t image[M3B_HEADER], stage_bytes[4096], tx[272], rx[272],
    reply[256];
static uint32_t image_handle;
static uint16_t sequence;
static unsigned reply_bytes;
static uint32_t micros(void *p) {
  (void)p;
  return REG(0x40054028u);
}
static void debug(const char *p) {
  svc->call(MK61_SERVICE_DEBUG_WRITE, (uint32_t)strlen(p), 0, 0, (void *)p);
}
static void show(const char *text) {
  mk61_api->display_clear();
  mk61_api->display_write_m8(0, 0, "BIOS M3 / PicoCalc", 17);
  mk61_api->display_write_m8(0, 2, text, (uint32_t)strlen(text));
  mk61_api->service();
}
static void baud(uint32_t rate) {
  while (REG(0x40038018u) & 8u)
    mk61_api->service();
  REG(0x40038030u) = 0;
  REG(0x4003802cu) = 0;
  /* Rounded UART divisor in units of 1/64, PERI fixed at 48 MHz. */
  const uint32_t divisor = (192000000u + rate / 2) / rate;
  REG(0x40038024u) = divisor / 64;
  REG(0x40038028u) = divisor % 64;
  REG(0x4003802cu) = 0x70;
  REG(0x40038030u) = 0x301;
  while (!(REG(0x40038018u) & 16u))
    (void)REG(0x40038000u);
  REG(0x40038004u) = 0;
}
static int request(uint8_t version, uint8_t op, const uint8_t *data, unsigned n,
                   uint32_t timeout) {
  const uint16_t seq = ++sequence;
  const unsigned bytes = m3b_packet(version, op, seq, data, n, tx);
  if (!bytes)
    return -10;
  for (unsigned attempt = 0; attempt < 3; ++attempt) {
    /* A 32-byte FIFO fills in ~142 us at 2.25 Mbaud. UI service may
     * present an LCD frame: yield only BEFORE sending, never inside RX.
     * Each exchange is bounded to <=2 s, below the 8 s Pico watchdog. */
    mk61_api->service();
    if (!stm3_pico_uart1_send(&uart, tx, bytes, 100000))
      return -11;
    unsigned count = 0, overflow = 0;
    const uint32_t start = micros(0);
    while ((uint32_t)(micros(0) - start) < timeout) {
      const int c = stm3_pico_uart1_read(&uart, 1000);
      if (c < 0)
        continue;
      if (c) {
        if (count < sizeof(rx))
          rx[count++] = (uint8_t)c;
        else
          overflow = 1;
        continue;
      }
      if (!count && !overflow)
        continue;
      const unsigned size = overflow ? 0 : m3b_decode(rx, count);
      count = overflow = 0;
      if (size < 16 || rx[0] != version || rx[1] != (op | 128) ||
          rx[2] != (uint8_t)seq || rx[3] != (uint8_t)(seq >> 8) || rx[6] ||
          rx[7])
        continue;
      const unsigned payload = (unsigned)rx[4] | (unsigned)rx[5] << 8;
      if (payload < 4 || payload > 256 || size != 12 + payload ||
          m3b_get(rx + size - 4) != m3b_crc(rx, size - 4))
        continue;
      const unsigned status = m3b_get(rx + 8);
      if (status)
        return (int)status;
      reply_bytes = payload - 4;
      memcpy(reply, rx + 12, reply_bytes);
      return 0;
    }
  }
  return -12;
}
static int info(void) {
  int e = request(M3B_WIRE_VERSION, M3B_INFO, 0, 0, 1000000);
  if (!e &&
      (reply_bytes != 40 || m3b_get(reply) != 1 ||
       m3b_get(reply + 4) != M3B_TARGET || m3b_get(reply + 8) != M3B_APP ||
       m3b_get(reply + 12) != M3B_LIMIT || m3b_get(reply + 16) != M3B_META))
    return -13;
  return e;
}
static int file_call(unsigned op, const char *path, void *data, unsigned at,
                     unsigned size) {
  mk61_service_file_bytes r = {path, data, at, size};
  return (int)svc->call(MK61_SERVICE_FILE_BYTES, op, 0, sizeof(r), &r);
}
static int read_image(const char *path) {
  mk61_service_file_info stat;
  if (!file_call(MK61_FILE_BYTES_STAT, path, &stat, 0, sizeof(stat)) ||
      stat.directory || stat.size < 40 || stat.size > M3B_LIMIT + M3B_HEADER)
    return -20;
  if (!file_call(MK61_FILE_BYTES_READ, path, image, 0, 32) ||
      !m3b_header_ok(image) || stat.size != 32 + m3b_get(image + 16))
    return -22;
  const uint32_t size = m3b_get(image + 16);
  mk61_service_buffer buffer;
  if (!mk61_app_buffer_acquire(svc, size, MK61_BUFFER_BLOCK, &buffer))
    return -23;
  image_handle = buffer.handle;
  uint32_t crc = ~0u;
  for (uint32_t at = 0; at < size;) {
    unsigned n = size - at;
    if (n > sizeof(stage_bytes))
      n = sizeof(stage_bytes);
    if (!file_call(MK61_FILE_BYTES_READ, path, stage_bytes, 32 + at, n))
      return -21;
    if (!at && !m3b_vectors_ok(stage_bytes, size))
      return -22;
    crc = m3b_crc_step(crc, stage_bytes, n);
    if (!mk61_app_buffer_write(svc, image_handle, at, stage_bytes, n))
      return -24;
    at += n;
    mk61_api->service();
  }
  if ((~crc) != m3b_get(image + 20))
    return -22;
  return 0;
}
static int install(void) {
  if (!stm3_pico_uart1_begin(&uart, micros, 0, 48000000, 2250000))
    return -30;
  baud(2250000);
  int error = request(1, 1, 0, 0, 100000);
  if (!error) {
    if (reply_bytes != 36 || m3b_get(reply) != 1 ||
        m3b_get(reply + 4) != 0x70301 || m3b_get(reply + 16) != 0 ||
        !(m3b_get(reply + 32) & 16u)) {
      error = -31;
      goto done;
    }
    uint8_t enter[8];
    m3b_put(enter, M3B_ENTER_MAGIC);
    m3b_put(enter + 4, M3B_TARGET);
    error = request(1, M3B_ENTER, enter, 8, 100000);
    if (error > 0)
      goto done;
  }
  /* Recovery may already be running at the slow baud. An ACK lost on the
   * resident-to-loader transition is also resolved by a validated INFO. */
  baud(M3B_BAUD);
  error = info();
  if (error)
    goto done;
  const uint32_t boot_crc = m3b_get(reply + 36), size = m3b_get(image + 16);
  char text[128];
  mk61_app_snprintf(svc, text, sizeof(text),
                    "M3UPDATE BEGIN bytes=%lu crc=%08lX boot_crc=%08lX\n",
                    (unsigned long)size, (unsigned long)m3b_get(image + 20),
                    (unsigned long)boot_crc);
  debug(text);
  show("Updating... keep power on");
  error = request(M3B_WIRE_VERSION, M3B_BEGIN, image, 32, 2000000);
  if (error)
    goto done;
  for (uint32_t at = 0; at < size;) {
    uint8_t data[244];
    unsigned n = size - at;
    if (n > 240)
      n = 240;
    m3b_put(data, at);
    if (!mk61_app_buffer_read(svc, image_handle, at, data + 4, n)) {
      error = -24;
      goto done;
    }
    error = request(M3B_WIRE_VERSION, M3B_WRITE, data, n + 4, 300000);
    if (error)
      goto done;
    at += n;
    if (reply_bytes != 4 || m3b_get(reply) != at) {
      error = -32;
      goto done;
    }
    if (at % 3840 == 0) {
      mk61_app_snprintf(svc, text, sizeof(text),
                        "M3UPDATE PROGRESS bytes=%lu\n", (unsigned long)at);
      debug(text);
    }
  }
  error = request(M3B_WIRE_VERSION, M3B_COMMIT, 0, 0, 2000000);
  if (error)
    goto done;
  error = info();
  if (error)
    goto done;
  if (!m3b_get(reply + 20) || m3b_get(reply + 24) != size ||
      m3b_get(reply + 28) != m3b_get(image + 20) ||
      m3b_get(reply + 36) != boot_crc) {
    error = -33;
    goto done;
  }
  /* Read back the complete programmed body through the independent READ path.
   */
  for (uint32_t at = 0; at < size;) {
    uint8_t data[8];
    unsigned n = size - at;
    if (n > 240)
      n = 240;
    m3b_put(data, M3B_APP + at);
    m3b_put(data + 4, n);
    error = request(M3B_WIRE_VERSION, M3B_READ, data, 8, 300000);
    if (error)
      goto done;
    if (!mk61_app_buffer_read(svc, image_handle, at, stage_bytes, n)) {
      error = -24;
      goto done;
    }
    if (reply_bytes != n || memcmp(reply, stage_bytes, n)) {
      error = -34;
      goto done;
    }
    at += n;
  }
  error = request(M3B_WIRE_VERSION, M3B_RUN, 0, 0, 1000000);

done:
  stm3_pico_uart1_end(&uart);
  return error;
}
static uint32_t run(const char *path) {
  svc = mk61_app_get_services(
      mk61_api, MK61_SERVICE_CAP_FORMAT | MK61_SERVICE_CAP_DEBUG_IO |
                    MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_BUFFERS);
  if (!svc)
    return MK61_APP_RUNTIME_ERROR;
  show("Checking BIOS.M3U...");
  int error = read_image(path);
  if (!error) {
    show("Enter: update    Esc: cancel");
    for (;;) {
      int key = mk61_api->key_wait();
      if (key == MK61_APP_KEY_ESC) {
        mk61_app_buffer_release(svc, image_handle);
        image_handle = 0;
        return MK61_APP_OK;
      }
      if (key == MK61_APP_KEY_OK)
        break;
    }
    error = install();
  }
  if (image_handle) {
    mk61_app_buffer_release(svc, image_handle);
    image_handle = 0;
  }
  char text[96];
  mk61_app_snprintf(svc, text, sizeof(text), "M3UPDATE %s code=%d\n",
                    error ? "FAIL" : "HANDOFF", error);
  debug(text);
  if (!error)
    return MK61_APP_OK;
  show(error == -31 ? "M3 loader required / busy."
                    : "Update failed. Retry BIOSUPD.");
  /* UART boot recovery can be driven through USB while the physical
   * keyboard is temporarily unavailable. */
  mk61_api->key_wait();
  return MK61_APP_IO_ERROR;
}

int main(void) { return (int)run("BIOS.M3U"); }
uint32_t mk61_app_open_file(uint32_t id) {
  svc = mk61_app_get_services(
      mk61_api, MK61_SERVICE_CAP_FORMAT | MK61_SERVICE_CAP_DEBUG_IO |
                    MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_BUFFERS);
  if (!svc)
    return MK61_APP_RUNTIME_ERROR;
  char path[256];
  if (!file_call(MK61_FILE_BYTES_PATH, 0, path, id, sizeof(path)))
    return MK61_APP_INVALID_FILE;
  return run(path);
}
