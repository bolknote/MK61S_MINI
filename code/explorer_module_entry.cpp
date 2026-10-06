#if defined(MK61_BUILD_EXPLORER_MODULE)

#include "explorer_ui.hpp"
#include "loadable_app_services.h"

extern "C" u32 mk61_app_initialize(const mk61_app_api* api,
                                    u32 image_crc, u32 kind) {
  if(!portable_system::bind(api, image_crc, kind)) return 1;
  return (portable_system::call(MK61_SERVICE_CAPABILITIES) &
          MK61_SERVICE_CAP_EXPLORER) != 0 ? 0 : 1;
}

extern "C" u32 mk61_app_command(u32 command, u32 a, u32 b, u32, u32) {
  if(command != (u32) loadable_module::Command::EXPLORER_SELECT ||
     a == 0 || b != sizeof(loadable_module::ExplorerSession)) return 1;
  return explorer_ui::select(
      *(loadable_module::ExplorerSession*) (usize) a) ? 0 : 1;
}

#endif
