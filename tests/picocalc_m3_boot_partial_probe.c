/* Private HIL fixture. Deliberately leave an incomplete BIOS, then qualify
 * recovery using the production BIOSUPD.APP. Never package this on user SD. */
#ifndef M3_BOOT_PARTIAL_HIL
#error Build only for an explicitly assigned M3 update/recovery hardware phase
#endif
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
    return MK61_APP_IO_ERROR;
  uint8_t data[244];
  m3b_put(data, M3B_ENTER_MAGIC);
  m3b_put(data + 4, M3B_TARGET);
  e = request(1, M3B_ENTER, data, 8, 200000);
  if (!e) {
    baud(M3B_BAUD);
    e = info();
  }
  uint32_t before = e ? 0 : m3b_get(reply + 36);
  if (!e)
    e = request(M3B_WIRE_VERSION, M3B_BEGIN, image, 32, 2000000);
  if (!e && !mk61_app_buffer_read(svc, image_handle, 0, data + 4, 240))
    e = -24;
  if (!e) {
    m3b_put(data, 0);
    e = request(M3B_WIRE_VERSION, M3B_WRITE, data, 244, 500000);
  }
  if (!e)
    e = info();
  if (!e && (m3b_get(reply + 20) != 0 || m3b_get(reply + 32) != 240 ||
             m3b_get(reply + 36) != before))
    e = -40;
  stm3_pico_uart1_end(&uart);
  mk61_app_buffer_release(svc, image_handle);
  char message[128];
  mk61_app_snprintf(
      svc, message, sizeof(message),
      "M3PARTIAL %s code=%d received=240 valid=0 boot_crc=%08lX\n",
      e ? "FAIL" : "PASS", e, (unsigned long)before);
  debug(message);
  return e ? MK61_APP_IO_ERROR : MK61_APP_OK;
}
