#ifndef MK61_PICOCALC_FRAME_SCHEDULE_HPP
#define MK61_PICOCALC_FRAME_SCHEDULE_HPP
#include <cstdint>
namespace picocalc {
// Start-to-start cadence. A slow frame is followed by the newest state as
// soon as the LCD is free; missed frames are never queued or replayed.
struct FrameSchedule {
    static constexpr uint32_t INTERVAL_US=20000;
    static uint64_t next(uint64_t started) { return started+INTERVAL_US; }
};
}
#endif
