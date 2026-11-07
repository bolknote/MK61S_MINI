/* Read-only warm handoff after the full image/readback path. No Flash writes.
 */
#define main unused_updater_main
#include "../examples/portable-apps/BIOSUPD/main.c"
#undef main
int main(void) {
  svc = mk61_app_get_services(
      mk61_api, MK61_SERVICE_CAP_FORMAT | MK61_SERVICE_CAP_DEBUG_IO |
                    MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_BUFFERS);
  if (!svc)
    return MK61_APP_RUNTIME_ERROR;
  int e = read_image("BIOS.M3U");
  if (e || !stm3_pico_uart1_begin(&uart, micros, 0, 48000000, 2250000))
    return MK61_APP_BUSY;
  uint8_t data[8];
  m3b_put(data, M3B_ENTER_MAGIC);
  m3b_put(data + 4, M3B_TARGET);
  e = request(1, M3B_ENTER, data, 8, 200000);
  if (!e) {
    baud(M3B_BAUD);
    e = info();
  }
  for (uint32_t at = 0; !e && at < m3b_get(image + 16);) {
    unsigned n = m3b_get(image + 16) - at;
    if (n > 240)
      n = 240;
    m3b_put(data, M3B_APP + at);
    m3b_put(data + 4, n);
    e = request(M3B_WIRE_VERSION, M3B_READ, data, 8, 1000000);
    if (!e && (!mk61_app_buffer_read(svc, image_handle, at, stage_bytes, n) ||
               reply_bytes != n || memcmp(stage_bytes, reply, n)))
      e = -34;
    at += n;
  }
  if (!e)
    e = request(M3B_WIRE_VERSION, M3B_RUN, 0, 0, 1000000);
  if (!e) {
    baud(2250000);
    uint32_t start = micros(0);
    for (unsigned i = 0; i < 12; ++i) {
      mk61_api->delay_ms(200);
      reply_bytes = 0;
      memset(reply, 0, sizeof(reply));
      e = request(1, 1, 0, 0, 100000);
      char text[256];
      mk61_app_snprintf(
          svc, text, sizeof(text),
          "M3LAUNCH i=%u ms=%lu e=%d n=%u target=%08lX flags=%08lX "
          "uart_errors=%lu cr=%08lX lcr=%08lX pins=%lu/%lu\n",
          i, (unsigned long)((micros(0) - start) / 1000), e, reply_bytes,
          (unsigned long)m3b_get(reply + 4), (unsigned long)m3b_get(reply + 32),
          (unsigned long)uart.errors, (unsigned long)REG(0x40038030u),
          (unsigned long)REG(0x4003802cu), (unsigned long)REG(0x40014044u),
          (unsigned long)REG(0x4001404cu));
      debug(text);
      if (!e && reply_bytes == 36 && m3b_get(reply + 4) == 0x70301 &&
          (m3b_get(reply + 32) & 16u))
        break;
    }
  }
  stm3_pico_uart1_end(&uart);
  mk61_app_buffer_release(svc, image_handle);
  debug(e ? "M3LAUNCH ERROR\n" : "M3LAUNCH DONE\n");
  return MK61_APP_OK;
}
