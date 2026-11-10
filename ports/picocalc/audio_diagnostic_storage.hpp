#ifndef MK61_PICOCALC_AUDIO_DIAGNOSTIC_STORAGE_HPP
#define MK61_PICOCALC_AUDIO_DIAGNOSTIC_STORAGE_HPP
#include "audio_alarm_trace.hpp"
#include "audio_irq_entry.hpp"
#include "audio_irq_priority.hpp"
#include <new>
#include <type_traits>
namespace picocalc {
struct RemoteAudioDiagnostics {AudioIrqEntry irq;audio_stream::AudioIrqPriority priority;AudioAlarmTrace alarm;};
static_assert(std::is_trivially_copyable<RemoteAudioDiagnostics>::value);
// Mode changes happen only after the old DMA and IRQ owner have stopped.
// The original sample arrays retain their sizes and ring alignment.
union alignas(64) AudioSynthStorage {
    uint32_t samples[2][16];RemoteAudioDiagnostics remote;
    constexpr AudioSynthStorage():remote{}{}
    void begin_remote(){::new(static_cast<void*>(&remote)) RemoteAudioDiagnostics{};}
    void begin_local(){using Samples=uint32_t[2][16];::new(static_cast<void*>(&samples)) Samples;}
};
union alignas(256) RemotePwmStorage {
    uint32_t samples[64];RemoteAudioDiagnostics retained;
    constexpr RemotePwmStorage():retained{}{}
    void begin_pwm(){using Samples=uint32_t[64];::new(static_cast<void*>(&samples)) Samples;}
    void retain(const RemoteAudioDiagnostics& value){::new(static_cast<void*>(&retained)) RemoteAudioDiagnostics(value);}
};
#if defined(__ARM_ARCH_6M__)
static_assert(sizeof(RemoteAudioDiagnostics)==128 && offsetof(RemoteAudioDiagnostics,alarm)==36);
static_assert(sizeof(AudioSynthStorage)==128 && alignof(AudioSynthStorage)==64);
static_assert(sizeof(RemotePwmStorage)==256 && alignof(RemotePwmStorage)==256);
#endif
}
#endif
