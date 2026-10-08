/* Fixed frame fixtures for the real resident USB Screen pipeline.
 * Digits 0..5 select bitmaps, 6 selects text through the normal renderer.
 * No timers animate the image during a measured batch. */
#include "mk61_app.h"
#if defined(PACKBITS_QUALIFIED_CALLBACKS)
#include "packbits_profile_callbacks.h"
#endif

static uint8_t frame[192 * 64 / 8];
static unsigned selected_kind;

static void bitmap(unsigned kind) {
  uint32_t random = 0x61F411U;
  for(unsigned i = 0; i < sizeof(frame); ++i) {
    if(kind == 0) frame[i] = 0;
    else if(kind == 1) frame[i] = i % 192 == 95 ? 255 : 0;
    else if(kind == 2) frame[i] = i % 32 < 16 ? 0 : (uint8_t)(i % 7 + 1);
    else if(kind == 3) {
      random ^= random << 13; random ^= random >> 17; random ^= random << 5;
      frame[i] = (uint8_t)random;
    } else if(kind == 4) frame[i] = i & 1 ? 255 : 0;
    else frame[i] = 255;
  }
}

int main(void) {
  if(!mk61_app_api_compatible(mk61_api, sizeof(*mk61_api),
      MK61_APP_CAP_TIME | MK61_APP_CAP_GRAPHICS | MK61_APP_CAP_KEYBOARD |
      MK61_APP_CAP_TEXT_DISPLAY)) return MK61_APP_RUNTIME_ERROR;
  unsigned previous = 99;
#if defined(PACKBITS_QUALIFIED_CALLBACKS)
  const profile_callbacks* profiler = qualified_profiler();
  if(!profiler) return MK61_APP_RUNTIME_ERROR;
#endif
  int graphical = 0;
  for(;;) {
    if(selected_kind != previous) {
      if(selected_kind == 6) {
        if(graphical) mk61_api->graphics_end();
        graphical = 0;
        mk61_api->display_clear();
        static const char* const lines[] = {
          "PACKBITS BENCH", "0123456789 + - *", "BASIC FOCAL VM", "FRAME 192x64"
        };
        for(unsigned row = 0; row < 4 && row < mk61_api->display_rows(); ++row) {
          unsigned size = 0;
          while(lines[row][size]) ++size;
          mk61_api->display_write_m8(0, row, lines[row], size);
        }
      } else {
        if(!graphical && !mk61_api->graphics_begin()) return MK61_APP_RUNTIME_ERROR;
        graphical = 1;
        bitmap(selected_kind);
        if(!mk61_api->graphics_present(frame, sizeof(frame))) return MK61_APP_RUNTIME_ERROR;
      }
      previous = selected_kind;
    }
    const int key = mk61_api->key_poll();
    if(key == MK61_APP_KEY_ESC) break;
    if(key >= MK61_APP_KEY_DIGIT_0 && key <= MK61_APP_KEY_DIGIT_6)
      selected_kind = (unsigned)(key - MK61_APP_KEY_DIGIT_0);
#if defined(PACKBITS_QUALIFIED_CALLBACKS)
    if(key == MK61_APP_KEY_DIGIT_7) (void)profiler->start();
    if(key == MK61_APP_KEY_DIGIT_8) profiler->stop();
#endif
    mk61_api->delay_ms(1);
  }
  if(graphical) mk61_api->graphics_end();
  return MK61_APP_OK;
}
