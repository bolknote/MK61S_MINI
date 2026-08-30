#ifndef MK61_DEVICE_IDENTITY_HPP
#define MK61_DEVICE_IDENTITY_HPP

#include "rust_types.h"

// Единственная точка преобразования 96-битной заводской метки STM32 в
// публичные идентификаторы MK61s. Полный UID остаётся внутри прошивки:
// наружу выдаются только разделённые по доменам производные значения.
namespace device_identity {

static constexpr usize PUBLIC_ID_TEXT_SIZE = 17;  // 16 hex + NUL
static constexpr usize SHORT_ID_TEXT_SIZE = 9;    // 8 hex + NUL
static constexpr usize USB_SERIAL_TEXT_SIZE = 13; // 12 hex + NUL
static constexpr usize VOLUME_ID_TEXT_SIZE = 9;   // 8 hex + NUL
static constexpr usize REPORT_TEXT_SIZE = 160;

struct Uid96 {
  u32 word0;
  u32 word1;
  u32 word2;

  constexpr bool available(void) const {
    // Electronic signature настоящего STM32 не бывает полностью нулевой.
    // Ноль служит явным и безопасным host/unsupported fallback.
    return word0 != 0 || word1 != 0 || word2 != 0;
  }
};

// На STM32 читает UID_BASE. В host/System APP окружении без UID_BASE
// возвращает недоступный {0,0,0}; чтения памяти по выдуманному адресу нет.
Uid96 read(void);

// Публичный идентификатор не является секретом или криптографической
// анонимизацией. Это стабильный хорошо перемешанный ключ экземпляра устройства.
u64 public_id(const Uid96& uid);

// FAT serial имеет отдельный домен и не является простым усечением public ID.
// При отсутствии UID сохраняется прежний детерминированный fallback.
u32 fat_volume_serial(const Uid96& uid, u32 fallback);

bool format_public_id(const Uid96& uid,
                      char out[PUBLIC_ID_TEXT_SIZE]);
bool format_short_id(const Uid96& uid,
                     char out[SHORT_ID_TEXT_SIZE]);
bool format_fat_volume_serial(const Uid96& uid, u32 fallback,
                              char out[VOLUME_ID_TEXT_SIZE]);

// Точно повторяет алгоритм USB serial закреплённого STM32duino core 2.12.0:
// восемь hex цифр (UID0 + UID2) и старшие четыре hex цифры UID1. Благодаря
// этому terminal handshake можно сверить с descriptor без патча внешнего core.
bool format_stm32duino_usb_serial(const Uid96& uid,
                                  char out[USB_SERIAL_TEXT_SIZE]);

// Машинно-читаемая строка terminal handshake. Формат версионирован и
// намеренно собирается здесь, чтобы firmware и host golden-test не могли
// незаметно разойтись. Возвращает длину без NUL либо ноль при ошибке.
usize format_report(const Uid96& uid, u32 volume_fallback, u32 build_id,
                    const char* build_profile, char* out, usize capacity);

} // namespace device_identity

#endif
