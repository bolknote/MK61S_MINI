#ifndef MK61_PICOCALC_AUDIO_STREAM_HPP
#define MK61_PICOCALC_AUDIO_STREAM_HPP
#include "loadable_app_services.h"
#include "audio_alarm_trace.hpp"
namespace picocalc::audio_stream {
bool active();
void close();
bool key_click();
void stop_key_click();
struct KeyClickStatistics { uint32_t started,completed;bool active; };
KeyClickStatistics key_click_statistics();
// DMA synthesis is an opt-in hardware candidate. Blocks are16 samples
// (640us at25kHz); two queued blocks add at most1.28ms of buffering.
struct RefillStatistics { uint32_t max_us,late_stage,head_before,head_after,filled,core,priority,restored,irq_pc,irq_context,irq_dispatch_us,irq_entry_pc; };
struct SynthStatistics { bool dma;uint32_t blocks,underruns;bool coprocessor;uint32_t fallbacks;RefillStatistics refill; };
SynthStatistics synth_statistics();
struct AlarmStatistics { AudioAlarmTrace::Snapshot snapshot;uint32_t start_before,start_after,start_fraction,mask; };
AlarmStatistics alarm_statistics();
void report_alarm_trace();
uint32_t call(uint32_t operation,mk61_service_audio* request,unsigned master_volume);
uint32_t synth(const mk61_service_audio_synth& request,unsigned master_volume);
uint32_t psg(const mk61_service_audio_psg& request,unsigned master_volume,bool remote_only=false,
             const mk61_service_audio_psg_config* config=nullptr);
void poll(); // Core0: complete a failed coprocessor stream's local fallback.
}
#endif
