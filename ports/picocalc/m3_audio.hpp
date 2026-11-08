#ifndef MK61_PICOCALC_M3_AUDIO_HPP
#define MK61_PICOCALC_M3_AUDIO_HPP
#include "loadable_app_services.h"
namespace picocalc::m3_audio {
struct Statistics {
    bool active;int error;uint32_t blocks,samples,underruns,max_slice,requests,uart_errors,unload_failures;
    uint32_t max_render_us,starve_stage,starve_request_us;int32_t starve_ahead;
    bool profile_valid;
    uint32_t render_samples,render_jobs,render_slices,max_job_us,render_max_slice_us;
    uint64_t render_us;
    uint32_t min_block_us,late_blocks,ready_polls,prime_us,min_queued;
    bool inline_input;
    uint32_t transport_flags,inline_requests,stream_write_requests,tx_bytes,rx_bytes;
    uint64_t block_us;
    uint32_t max_service_gap_us;
    uint32_t max_idle_gap_us,max_pump_us,max_step_us,max_tx_us;
};
#if defined(PICO_ON_DEVICE) || defined(MK61_TEST_M3_AUDIO_BACKEND)
// Open/close/poll belong to core0. service and duty run only on core1.
bool open(const mk61_service_audio_psg&,unsigned gain);
void close();
void service();
bool transport_active();
uint32_t duty(void*);
bool failed();
void fault(int error);
Statistics statistics();
#else
inline bool open(const mk61_service_audio_psg&,unsigned){return false;}
inline void close(){}
inline void service(){}
inline bool transport_active(){return false;}
inline uint32_t duty(void*){return 0x00800080u;}
inline bool failed(){return false;}
inline void fault(int){}
inline Statistics statistics(){return {};}
#endif
}
#endif
