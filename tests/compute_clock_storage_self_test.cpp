#include <cassert>
#include <cstdint>
#include <cstdio>
using u8=uint8_t;
#include "compute_clock_storage.inc"
int main() {
  static_assert(sizeof(SettingsFlags)==1 && sizeof(SoundSettings)==1);
  assert(stored_compute_clock_profile(normalize_settings_flags(255),normalize_sound_settings(255))==0);
  // Run the actual packed storage helpers and erased-value normalizers.
  // Profile4 crosses the old 2-bit boundary, without changing either record
  // byte's size or overwriting independent settings.
  for(u8 profile=0;profile<5;++profile)for(u8 volume=0;volume<=10;++volume)
    for(u8 rows=0;rows<4;++rows)for(u8 speed=0;speed<2;++speed) {
      SettingsFlags flags(0xE5);flags.bits.speed_mode=speed;
      SoundSettings sound; sound.bits.volume=volume;sound.bits.display_rows_mode=rows;
      const u8 other=flags.raw&~0x10U;
      set_stored_compute_clock_profile(flags,sound,profile);
      flags=normalize_settings_flags(flags.raw);sound=normalize_sound_settings(sound.raw);
      assert(stored_compute_clock_profile(flags,sound)==profile);
      assert((flags.raw&~0x10U)==other && flags.bits.speed_mode==speed);
      assert(sound.bits.volume==volume && sound.bits.display_rows_mode==rows);
    }
  std::puts("Compute settings: all five profiles, packed high bit, erased defaults, speed/volume/rows independent PASS");
}
