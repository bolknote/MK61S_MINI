/* Execute the actual Pico APP against the actual M3 updater core. Only ABI
 * services, register storage and the UART physical link are substituted. */
#include "mk61_app.h"
#include "pico_uart1.h"
#include "stm3_client.h"
#include "wire.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef TEST_OLD_CLIENT
#undef S3_WIRE_VERSION
#define S3_WIRE_VERSION 1u
#endif
#include <string.h>
static uint32_t timer, fr = 16, reg;
static volatile uint32_t *mock_reg(uint32_t at) {
  if (at == 0x40054028u) {
    timer += 10;
    return &timer;
  }
  return at == 0x40038018u ? &fr : &reg;
}
#define REG(a) (*mock_reg(a))
#define main updater_main
#include "../examples/portable-apps/BIOSUPD/main.c"
#undef main
static unsigned file_size=32+2200;
static uint8_t flash_memory[65536], file[32 + 0xd400], staged[0xd400], queue[272],
    input[272];
static m3b_link link;
static unsigned queued, queue_at, input_n;
static int bootmode, legacy, uart_claims, erases, programs, fail_after,
    drop_ack, staged_ok, cancelled, passed;
static const uint8_t *model_read(void *p, uint32_t at, uint32_t n) {
  (void)p;
  assert(at >= M3B_FLASH && n <= M3B_SETTINGS - at);
  return flash_memory + (at - M3B_FLASH);
}
static int model_erase(void *p, uint32_t at) {
  (void)p;
  assert(staged_ok);
  assert(at >= M3B_APP && at <= M3B_META && !(at & 1023));
  ++erases;
  memset(flash_memory + (at - M3B_FLASH), 255, 1024);
  return 1;
}
static int model_program(void *p, uint32_t at, const uint8_t *data,
                         uint32_t n) {
  (void)p;
  assert(staged_ok);
  assert(at >= M3B_APP && n <= M3B_SETTINGS - at);
  ++programs;
  memcpy(flash_memory + (at - M3B_FLASH), data, n);
  return 1;
}
int stm3_pico_uart1_begin(stm3_pico_uart1 *u, uint32_t (*clock)(void *),
                          void *context, uint32_t peri, uint32_t rate) {
  assert(peri == 48000000 && rate == 2250000);
  u->micros = clock;
  u->context = context;
  u->ready = 1;
  ++uart_claims;
  return 1;
}
void stm3_pico_uart1_end(stm3_pico_uart1 *u) { u->ready = 0; }
uint32_t stm3_pico_uart1_micros(void *p) {
  return ((stm3_pico_uart1 *)p)->micros(0);
}
int stm3_pico_uart1_send(void *p, const uint8_t *bytes, unsigned n,
                         uint32_t timeout) {
  assert(((stm3_pico_uart1 *)p)->ready && timeout);
  queued = queue_at = 0;
  if (fail_after && programs >= fail_after)
    return 1;
  if (bootmode) {
    for (unsigned i = 0; i < n; ++i) {
      unsigned response = m3b_feed(&link, bytes[i]);
      if (response) {
        queued = response;
        memcpy(queue, link.tx, response);
      }
    }
    if (drop_ack && programs) {
      drop_ack = 0;
      queued = 0;
    }
    if (link.update.run) {
      assert(m3b_valid(&link.update));
      bootmode = 0;
    }
  } else {
    for (unsigned i = 0; i < n; ++i) {
      if (bytes[i]) {
        assert(input_n < sizeof(input));
        input[input_n++] = bytes[i];
        continue;
      }
      if (!input_n)
        continue;
      unsigned size = m3b_decode(input, input_n);
      input_n = 0;
      if (size < 12 || input[0] != S3_WIRE_VERSION)
        continue;
      assert(m3b_crc(input, size - 4) == m3b_get(input + size - 4));
      uint8_t answer[40] = {0};
      unsigned count = 4;
      unsigned op = input[1];
      uint16_t seq = (uint16_t)((unsigned)input[2] | (unsigned)input[3] << 8);
      if (op == 1) {
        m3b_put(answer + 4, 1);
        m3b_put(answer + 8, 0x70301);
        m3b_put(answer + 36, legacy ? 7 : 23);
        count = 40;
      } else if (op == M3B_ENTER) {
        assert(staged_ok && !legacy);
        assert(m3b_get(input + 8) == M3B_ENTER_MAGIC);
        bootmode = 1;
      } else
        assert(0);
      queued = m3b_packet(S3_WIRE_VERSION, (uint8_t)(op | 128), seq, answer, count, queue);
    }
  }
  return 1;
}
int stm3_pico_uart1_read(void *p, uint32_t timeout) {
  (void)p;
  (void)timeout;
  timer += 10;
  return queue_at < queued ? queue[queue_at++] : -1;
}
static uint32_t call_service(uint32_t op, uint32_t a, uint32_t b, uint32_t c,
                             void *data) {
  (void)b;
  (void)c;
  if (op == MK61_SERVICE_CAPABILITIES)
    return MK61_SERVICE_CAP_FORMAT | MK61_SERVICE_CAP_DEBUG_IO |
           MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_BUFFERS;
  if (op == MK61_SERVICE_DEBUG_WRITE) {
    fputs((char *)data, stderr);
    if (strstr((char *)data, "M3UPDATE HANDOFF"))
      passed = 1;
    return 1;
  }
  if (op == MK61_SERVICE_FILE_BYTES) {
    mk61_service_file_bytes *r = data;
    if (a == MK61_FILE_BYTES_STAT) {
      mk61_service_file_info *info = r->data;
      info->size = file_size;
      info->directory = 0;
      return 1;
    }
    if (a == MK61_FILE_BYTES_READ) {
      assert(r->offset <= file_size && r->size <= file_size - r->offset);
      memcpy(r->data, file + r->offset, r->size);
      return 1;
    }
    assert(0);
  }
  if (op == MK61_SERVICE_BUFFER) {
    mk61_service_buffer *r = data;
    if (a == MK61_BUFFER_ACQUIRE) {
      assert(r->size == (file_size-32));
      r->handle = 1;
      r->storage = MK61_BUFFER_PSRAM;
      return 1;
    }
    if (a == MK61_BUFFER_RELEASE) {
      assert(r->handle == 1);
      return 1;
    }
    assert(r->handle == 1 && r->offset <= (file_size-32) &&
           r->size <= (file_size-32) - r->offset);
    if (a == MK61_BUFFER_WRITE) {
      memcpy(staged + r->offset, r->data, r->size);
      if (r->offset + r->size == (file_size-32))
        staged_ok = 1;
      return 1;
    }
    if (a == MK61_BUFFER_READ) {
      memcpy(r->data, staged + r->offset, r->size);
      return 1;
    }
    assert(0);
  }
  assert(0);
  return 0;
}
static uint32_t clear(void) { return 1; }
static uint32_t text(uint32_t x, uint32_t y, const char *p, uint32_t n) {
  (void)x;
  (void)y;
  (void)p;
  (void)n;
  return 1;
}
static void service(void) {
  assert(queue_at == queued);
  timer += 10;
}
static void delay(uint32_t ms) { timer += ms * 1000; }
static int32_t key(void) {
  return cancelled ? MK61_APP_KEY_ESC : MK61_APP_KEY_OK;
}
static int format(char *out, uint32_t n, const char *fmt, va_list args) {
  return vsnprintf(out, n, fmt, args);
}
static const mk61_app_services services = {.magic = MK61_APP_SERVICES_MAGIC,
                                           .version = MK61_APP_SERVICES_VERSION,
                                           .struct_size =
                                               sizeof(mk61_app_services),
                                           .call = call_service,
                                           .format = format};
static const void *query(uint32_t id, uint32_t version) {
  assert(id == 1 && version == 2);
  return &services;
}
static const mk61_app_api api = {.magic = MK61_APP_API_MAGIC,
                                 .version = MK61_APP_API_VERSION,
                                 .struct_size = sizeof(mk61_app_api),
                                 .service = service,
                                 .delay_ms = delay,
                                 .display_clear = clear,
                                 .display_write_m8 = text,
                                 .key_wait = key,
                                 .query_service = query};
const mk61_app_api *mk61_api = &api;
uint32_t mk61_app_image_crc, mk61_app_current_kind;
static void setup(void) {
  timer = queued = queue_at = input_n = 0;
  bootmode = legacy = uart_claims = erases = programs = fail_after = drop_ack =
      staged_ok = cancelled = passed = 0;
  memset(flash_memory, 0x69, sizeof(flash_memory));
  memset(file, 0, file_size);
  for (unsigned i = 32; i < file_size; ++i)
    file[i] = (uint8_t)i;
  m3b_put(file + 32, M3B_MAILBOX);
  m3b_put(file + 36, M3B_APP + 129);
  uint32_t h[7] = {M3B_MAGIC,
                   1,
                   M3B_TARGET,
                   M3B_APP,
                   file_size - 32,
                   m3b_crc(file + 32, file_size - 32),
                   1};
  for (unsigned i = 0; i < 7; ++i)
    m3b_put(file + 4 * i, h[i]);
  m3b_put(file + 28, m3b_crc(file, 28));
  const char* package=getenv("M3U_TEST_PACKAGE");
  if(package){FILE* f=fopen(package,"rb");assert(f);assert(!fseek(f,0,SEEK_END));
    long n=ftell(f);assert(n>32&&n<=(long)sizeof(file));file_size=(unsigned)n;
    rewind(f);assert(fread(file,1,file_size,f)==file_size);fclose(f);}
  const m3b_flash f = {0, model_read, model_erase, model_program};
  m3b_link_init(&link, &f);
}
int main(void) {
  setup();
  drop_ack = 1;
  assert(updater_main() == MK61_APP_OK && passed && !uart.ready);
  assert(erases > 0 && programs > 0 &&
         !memcmp(flash_memory + 8192, file + 32, file_size - 32));
  for (unsigned i = 0; i < 8192; ++i)
    assert(flash_memory[i] == 0x69);
  for (unsigned i = 0xf800; i < 65536; ++i)
    assert(flash_memory[i] == 0x69);
  setup();
  file[50] ^= 1;
  assert(updater_main() == MK61_APP_IO_ERROR && !uart_claims && !erases);
  setup();
  legacy = 1;
  assert(updater_main() == MK61_APP_IO_ERROR && uart_claims == 1 && !erases &&
         !uart.ready);
  setup();
  cancelled = 1;
  assert(updater_main() == MK61_APP_OK && !uart_claims && !erases);
  setup();
  bootmode = 1;
  fail_after = 2;
  assert(updater_main() == MK61_APP_IO_ERROR && !m3b_valid(&link.update) &&
         !uart.ready);
  fail_after = 0;
  staged_ok = passed = 0;
  assert(updater_main() == MK61_APP_OK && passed && m3b_valid(&link.update) &&
         !uart.ready);
  puts("Pico BIOSUPD APP PASS: staged PSRAM, resident entry, ACK replay, "
       "complete readback, invalid/legacy/cancel rejection, "
       "interrupted-session recovery");
  return 0;
}
