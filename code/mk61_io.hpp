#ifndef MK61_IO_HPP
#define MK61_IO_HPP
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <type_traits>

#if defined(ARDUINO_ARCH_STM32) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE))
#define MK61_NARROW_IO_SUPPORTED 1
#else
#define MK61_NARROW_IO_SUPPORTED 0
#endif
#if MK61_NARROW_IO_SUPPORTED && defined(USBCON) && defined(USBD_USE_CDC)
#define MK61_NARROW_USB_SERIAL_SUPPORTED 1
#else
#define MK61_NARROW_USB_SERIAL_SUPPORTED 0
#endif

namespace mk61_io {
// One shared integer formatter, with no stream state or virtual dispatch.
char* format_unsigned(char* end, uint32_t value, uint8_t base);

template<class Derived> class Output {
  Derived& output() { return static_cast<Derived&>(*this); }
public:
  size_t write(const uint8_t* bytes, size_t count) {
    size_t written = 0;
    while(written < count && output().write(bytes[written]) == 1) ++written;
    return written;
  }
  size_t write(const char* text) {
    return text ? output().write(reinterpret_cast<const uint8_t*>(text), strlen(text)) : 0;
  }
  size_t write(const char* text, size_t count) {
    return output().write(reinterpret_cast<const uint8_t*>(text), count);
  }
  size_t print(const char* text) { return write(text); }
  size_t print(char byte) { return output().write(static_cast<uint8_t>(byte)); }
  template<class T, typename std::enable_if<std::is_integral<T>::value, int>::type = 0>
  size_t print(T value, int base = 10) {
    static_assert(sizeof(T) <= sizeof(uint32_t), "use the explicit 64-bit output helper");
    uint32_t magnitude = static_cast<uint32_t>(value);
    if(base == 0) return output().write(static_cast<uint8_t>(magnitude));
    size_t sign = 0;
    if(std::is_signed<T>::value && value < 0 && base == 10) {
      sign = output().write(static_cast<uint8_t>('-'));
      magnitude = uint32_t{0} - magnitude;
    }
    char buffer[32];
    char* const end = buffer + sizeof(buffer);
    char* const first = format_unsigned(end, magnitude, static_cast<uint8_t>(base));
    return sign + output().write(reinterpret_cast<const uint8_t*>(first), static_cast<size_t>(end-first));
  }
  size_t println() { return output().write(reinterpret_cast<const uint8_t*>("\r\n"), 2); }
  template<class T, class... Format> size_t println(T value, Format... format) {
    return print(value, format...) + println();
  }
};

#if MK61_NARROW_USB_SERIAL_SUPPORTED
class UsbSerial : public Output<UsbSerial> {
public:
  void begin(uint32_t = 115200);
  void end();
  int available();
  int availableForWrite();
  int peek();
  int read();
  void flush();
  size_t write(uint8_t byte);
  size_t write(const uint8_t* bytes, size_t count);
  using Output<UsbSerial>::write;
  explicit operator bool();
};
extern UsbSerial serial;
#endif
} // namespace mk61_io
#endif
