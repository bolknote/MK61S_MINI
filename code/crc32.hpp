#ifndef MK61_CRC32_HPP
#define MK61_CRC32_HPP

#include "rust_types.h"

#include <string.h>

#if defined(ARDUINO_ARCH_STM32)
  #include "Arduino.h"
#endif

#if defined(MK61_CRC32_FORCE_SOFTWARE)
  #define MK61_CRC32_STM32_BACKEND 0
  #define MK61_CRC32_STM32_EMULATED 0
#elif defined(MK61_CRC32_EMULATE_STM32)
  #define MK61_CRC32_STM32_BACKEND 1
  #define MK61_CRC32_STM32_EMULATED 1
#elif defined(__ARM_ARCH_7EM__) && \
      (defined(STM32F401xC) || defined(STM32F401xE) || \
       defined(STM32F411xE))
  #define MK61_CRC32_STM32_BACKEND 1
  #define MK61_CRC32_STM32_EMULATED 0
#else
  #define MK61_CRC32_STM32_BACKEND 0
  #define MK61_CRC32_STM32_EMULATED 0
#endif

namespace mk61_crc32 {

static constexpr u32 INITIAL_STATE = 0xFFFFFFFFUL;
static constexpr u32 REFLECTED_POLYNOMIAL = 0xEDB88320UL;
static constexpr u32 STM32_POLYNOMIAL = 0x04C11DB7UL;

inline u32 update_byte(u32 state, u8 value) {
  state ^= value;
  for(u8 bit = 0; bit < 8; bit++) {
    state = (state & 1U) != 0
        ? (state >> 1) ^ REFLECTED_POLYNOMIAL : state >> 1;
  }
  return state;
}

inline u32 extend(u32 state, const u8* data, usize size) {
  if(data == nullptr && size != 0) return state;
  for(usize index = 0; index < size; index++) {
    state = update_byte(state, data[index]);
  }
  return state;
}

inline u32 finish(u32 state) {
  return state ^ INITIAL_STATE;
}

namespace detail {

struct ArbitrationState {
  bool busy;
  u32 acquisitions;
  u32 fallbacks;
};

inline ArbitrationState& arbitration_state(void) {
  static ArbitrationState value = {};
  return value;
}

inline void increment(u32& value) {
  if(value != 0xFFFFFFFFUL) value++;
}

inline u32 enter_critical(void) {
#if (defined(__arm__) || defined(__thumb__)) && MK61_CRC32_STM32_BACKEND
  u32 primask = 0;
  __asm__ volatile (
      "mrs %0, primask\n"
      "cpsid i"
      : "=r" (primask) :: "memory");
  return primask;
#else
  return 0;
#endif
}

inline void leave_critical(u32 primask) {
#if (defined(__arm__) || defined(__thumb__)) && MK61_CRC32_STM32_BACKEND
  if((primask & 1U) == 0) {
    __asm__ volatile ("cpsie i" ::: "memory");
  }
#else
  (void) primask;
#endif
}

inline bool acquire_hardware(void) {
#if MK61_CRC32_STM32_BACKEND
  const u32 primask = enter_critical();
  ArbitrationState& state = arbitration_state();
  const bool acquired = !state.busy;
  if(acquired) {
    state.busy = true;
    increment(state.acquisitions);
  } else {
    increment(state.fallbacks);
  }
  leave_critical(primask);
  return acquired;
#else
  return false;
#endif
}

inline void release_hardware(void) {
#if MK61_CRC32_STM32_BACKEND
  const u32 primask = enter_critical();
  arbitration_state().busy = false;
  leave_critical(primask);
#endif
}

inline u32 reverse_bits_portable(u32 value) {
  value = ((value & 0x55555555UL) << 1) |
          ((value >> 1) & 0x55555555UL);
  value = ((value & 0x33333333UL) << 2) |
          ((value >> 2) & 0x33333333UL);
  value = ((value & 0x0F0F0F0FUL) << 4) |
          ((value >> 4) & 0x0F0F0F0FUL);
  value = ((value & 0x00FF00FFUL) << 8) |
          ((value >> 8) & 0x00FF00FFUL);
  return (value << 16) | (value >> 16);
}

inline u32 reverse_bits(u32 value) {
#if MK61_CRC32_STM32_BACKEND && !MK61_CRC32_STM32_EMULATED
  return __RBIT(value);
#else
  return reverse_bits_portable(value);
#endif
}

#if MK61_CRC32_STM32_EMULATED
inline u32& emulated_state(void) {
  static u32 value = INITIAL_STATE;
  return value;
}

inline u32 emulate_stm32_word(u32 state, u32 value) {
  state ^= value;
  for(u8 bit = 0; bit < 32; bit++) {
    state = (state & 0x80000000UL) != 0
        ? (state << 1) ^ STM32_POLYNOMIAL : state << 1;
  }
  return state;
}
#endif

} // namespace detail

// F401/F411 имеют один глобальный CRC-блок с фиксированным полиномом и
// 32-битным входом. Первый живой Context арендует регистр, а вложенный или
// прервавший его Context автоматически продолжает программно. Критическая
// секция защищает только флаг владения; сами длинные вычисления IRQ не держат.
class Context {
  public:
    Context(void)
      : software_state_(INITIAL_STATE), result_(0), pending_{},
        pending_size_(0), finalized_(false),
        used_hardware_(detail::acquire_hardware()),
        owns_hardware_(used_hardware_)
    {
#if MK61_CRC32_STM32_EMULATED
      if(owns_hardware_) detail::emulated_state() = INITIAL_STATE;
#elif MK61_CRC32_STM32_BACKEND
      if(owns_hardware_) {
        RCC->AHB1ENR |= RCC_AHB1ENR_CRCEN;
        (void) RCC->AHB1ENR;
        CRC->CR = CRC_CR_RESET;
      }
#endif
    }

    ~Context(void) {
      release_hardware();
    }

    Context(const Context&) = delete;
    Context& operator=(const Context&) = delete;

    bool update(const u8* data, usize size) {
      if(finalized_ || (data == nullptr && size != 0)) return false;
#if MK61_CRC32_STM32_BACKEND
      if(owns_hardware_) {
        while(size != 0 && pending_size_ != 0) {
          pending_[pending_size_++] = *data++;
          size--;
          if(pending_size_ == sizeof(pending_)) {
            feed_pending_word();
          }
        }
        while(size >= sizeof(pending_)) {
          u32 word = 0;
          memcpy(&word, data, sizeof(word));
          feed_word(word);
          data += sizeof(word);
          size -= sizeof(word);
        }
        while(size-- != 0) pending_[pending_size_++] = *data++;
      } else {
        software_state_ = extend(software_state_, data, size);
      }
#else
      software_state_ = extend(software_state_, data, size);
#endif
      return true;
    }

    bool update_byte(u8 value) {
      if(finalized_) return false;
#if MK61_CRC32_STM32_BACKEND
      if(owns_hardware_) {
        pending_[pending_size_++] = value;
        if(pending_size_ == sizeof(pending_)) feed_pending_word();
      } else {
        software_state_ = mk61_crc32::update_byte(software_state_, value);
      }
#else
      software_state_ = mk61_crc32::update_byte(software_state_, value);
#endif
      return true;
    }

    u32 finish(void) {
      if(finalized_) return result_;
#if MK61_CRC32_STM32_BACKEND
      u32 state = owns_hardware_
          ? hardware_state() : software_state_;
      if(owns_hardware_) state = extend(state, pending_, pending_size_);
#else
      const u32 state = software_state_;
#endif
      result_ = mk61_crc32::finish(state);
      finalized_ = true;
      release_hardware();
      return result_;
    }

    bool using_hardware(void) const {
      return used_hardware_;
    }

  private:
    void feed_pending_word(void) {
      u32 word = 0;
      memcpy(&word, pending_, sizeof(word));
      feed_word(word);
      pending_size_ = 0;
    }

    void feed_word(u32 word) {
      const u32 reflected = detail::reverse_bits(word);
#if MK61_CRC32_STM32_EMULATED
      detail::emulated_state() =
          detail::emulate_stm32_word(detail::emulated_state(), reflected);
#elif MK61_CRC32_STM32_BACKEND
      CRC->DR = reflected;
#else
      (void) reflected;
#endif
    }

    u32 hardware_state(void) const {
#if MK61_CRC32_STM32_EMULATED
      return detail::reverse_bits(detail::emulated_state());
#elif MK61_CRC32_STM32_BACKEND
      return detail::reverse_bits(CRC->DR);
#else
      return INITIAL_STATE;
#endif
    }

    u32 software_state_;
    u32 result_;
    u8 pending_[4];
    u8 pending_size_;
    bool finalized_;
    bool used_hardware_;
    bool owns_hardware_;

    void release_hardware(void) {
      if(!owns_hardware_) return;
      detail::release_hardware();
      owns_hardware_ = false;
    }
};

struct ArbitrationSnapshot {
  bool supported;
  bool busy;
  u32 hardware_acquisitions;
  u32 software_fallbacks;
};

inline ArbitrationSnapshot arbitration_statistics(void) {
  const detail::ArbitrationState& state = detail::arbitration_state();
  const ArbitrationSnapshot result = {
    MK61_CRC32_STM32_BACKEND != 0,
    state.busy,
    state.acquisitions,
    state.fallbacks
  };
  return result;
}

inline void reset_arbitration_statistics(void) {
  detail::ArbitrationState& state = detail::arbitration_state();
  state.acquisitions = 0;
  state.fallbacks = 0;
}

inline u32 calculate(const u8* data, usize size) {
  Context context;
  (void) context.update(data, size);
  return context.finish();
}

inline bool hardware_backend_available(void) {
  return MK61_CRC32_STM32_BACKEND != 0;
}

} // namespace mk61_crc32

#endif
