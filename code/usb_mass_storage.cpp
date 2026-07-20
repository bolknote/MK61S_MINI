#include "usb_mass_storage.hpp"

#include "rust_types.h"
#include "exclusive_buffer.hpp"
#include "msc_scsi_safety.h"
#include "virtual_fat.hpp"

#include <Arduino.h>
#include <string.h>

#if defined(USBCON)

extern "C" {
#include "usbd_core.h"
#include "usbd_ctlreq.h"
#include "usbd_msc.h"
#include "usbd_msc_scsi.h"
}

#if !defined(USBD_VID) || USBD_VID == 0
#undef USBD_VID
#define USBD_VID 0x0483
#endif

namespace usb_mass_storage {

static USBD_HandleTypeDef usb_device;
static bool initialized = false;
static bool session_open = false;
static bool device_configured = false;

static bool is_initialized(void) {
  return __atomic_load_n(&initialized, __ATOMIC_ACQUIRE);
}

static void set_initialized(bool value) {
  __atomic_store_n(&initialized, value, __ATOMIC_RELEASE);
}

static void release_usb_device(void) {
  if(!device_configured) return;
  (void) USBD_DeInit(&usb_device);
  memset(&usb_device, 0, sizeof(usb_device));
  device_configured = false;
}

enum class DeferredWriteState : u8 {
  EMPTY,
  PENDING,
  PROCESSING,
  CANCELLED,
  COMPLETE_OK,
  COMPLETE_ERROR
};

struct DeferredWrite {
  u32 block_addr;
  u16 block_len;
  DeferredWriteState state;
  u8* buffer;
};

static_assert(sizeof(DeferredWrite) <= 16,
              "deferred write metadata must not contain a packet copy");

static DeferredWrite deferred_write = {};

static bool acquire_cache_buffer(void) {
#if defined(MK61_DISPLAY_UC1609)
  return exclusive_buffer::acquire(exclusive_buffer::Owner::USB_CACHE,
                                   exclusive_buffer::SIZE);
#else
  return true;
#endif
}

static bool configure_cache_buffer(void) {
#if defined(MK61_DISPLAY_UC1609)
  return virtual_fat::set_external_cache(
    exclusive_buffer::data(exclusive_buffer::Owner::USB_CACHE),
    exclusive_buffer::SIZE
  );
#else
  return virtual_fat::set_external_cache(NULL, 0);
#endif
}

static void release_cache_buffer(void) {
#if defined(MK61_DISPLAY_UC1609)
  if(exclusive_buffer::current_owner() != exclusive_buffer::Owner::USB_CACHE) return;
  exclusive_buffer::release(exclusive_buffer::Owner::USB_CACHE);
#endif
}

enum class DeferredReadState : u8 {
  EMPTY,
  PENDING,
  PROCESSING,
  CANCELLED,
  COMPLETE_OK,
  COMPLETE_ERROR
};

struct DeferredRead {
  DeferredReadState state;
  u32 block_addr;
  u16 block_len;
  u8* buffer;
};

static DeferredRead deferred_read = {DeferredReadState::EMPTY, 0, 0, NULL};

enum class DeferredSyncState : u8 {
  EMPTY,
  PENDING,
  PROCESSING,
  CANCELLED
};

static DeferredSyncState deferred_sync_state = DeferredSyncState::EMPTY;

static DeferredWriteState deferred_state(void) {
  return __atomic_load_n(&deferred_write.state, __ATOMIC_ACQUIRE);
}

static void set_deferred_state(DeferredWriteState state) {
  __atomic_store_n(&deferred_write.state, state, __ATOMIC_RELEASE);
}

static void reset_deferred_write(void) {
  DeferredWriteState expected = DeferredWriteState::PROCESSING;
  if(__atomic_compare_exchange_n(&deferred_write.state, &expected,
                                 DeferredWriteState::CANCELLED, false,
                                 __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return;
  deferred_write.block_addr = 0;
  deferred_write.block_len = 0;
  deferred_write.buffer = NULL;
  set_deferred_state(DeferredWriteState::EMPTY);
}

static DeferredReadState deferred_read_state(void) {
  return __atomic_load_n(&deferred_read.state, __ATOMIC_ACQUIRE);
}

static void set_deferred_read_state(DeferredReadState state) {
  __atomic_store_n(&deferred_read.state, state, __ATOMIC_RELEASE);
}

static void reset_deferred_read(void) {
  DeferredReadState expected = DeferredReadState::PROCESSING;
  if(__atomic_compare_exchange_n(&deferred_read.state, &expected,
                                 DeferredReadState::CANCELLED, false,
                                 __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return;
  deferred_read.block_addr = 0;
  deferred_read.block_len = 0;
  deferred_read.buffer = NULL;
  set_deferred_read_state(DeferredReadState::EMPTY);
}

static DeferredSyncState deferred_sync(void) {
  return __atomic_load_n(&deferred_sync_state, __ATOMIC_ACQUIRE);
}

static void set_deferred_sync(DeferredSyncState state) {
  __atomic_store_n(&deferred_sync_state, state, __ATOMIC_RELEASE);
}

static void reset_deferred_io(void) {
  reset_deferred_write();
  reset_deferred_read();
  DeferredSyncState expected = DeferredSyncState::PROCESSING;
  if(!__atomic_compare_exchange_n(&deferred_sync_state, &expected,
                                  DeferredSyncState::CANCELLED, false,
                                  __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
    set_deferred_sync(DeferredSyncState::EMPTY);
  }
}

static u8 string_desc[USBD_MAX_STR_DESC_SIZ];

static u8 device_desc[USB_LEN_DEV_DESC] = {
  0x12,
  USB_DESC_TYPE_DEVICE,
  0x00, 0x02,
  0x00,
  0x00,
  0x00,
  USB_MAX_EP0_SIZE,
  LOBYTE(USBD_VID), HIBYTE(USBD_VID),
  0x61, 0x61,
  0x00, 0x02,
  USBD_IDX_MFC_STR,
  USBD_IDX_PRODUCT_STR,
  USBD_IDX_SERIAL_STR,
  USBD_MAX_NUM_CONFIGURATION
};

static u8 lang_id_desc[USB_LEN_LANGID_STR_DESC] = {
  USB_LEN_LANGID_STR_DESC,
  USB_DESC_TYPE_STRING,
  0x09,
  0x04
};

static u8 serial_desc[] = {
  20,
  USB_DESC_TYPE_STRING,
  'M', 0,
  'K', 0,
  '6', 0,
  '1', 0,
  'S', 0,
  '0', 0,
  '0', 0,
  '0', 0,
  '1', 0
};

static u8* device_descriptor(USBD_SpeedTypeDef speed, u16* length) {
  (void) speed;
  *length = sizeof(device_desc);
  return device_desc;
}

static u8* lang_id_descriptor(USBD_SpeedTypeDef speed, u16* length) {
  (void) speed;
  *length = sizeof(lang_id_desc);
  return lang_id_desc;
}

static u8* string_descriptor(const char* text, u16* length) {
  USBD_GetString((u8*) text, string_desc, length);
  return string_desc;
}

static u8* manufacturer_descriptor(USBD_SpeedTypeDef speed, u16* length) {
  (void) speed;
  return string_descriptor("MK61S", length);
}

static u8* product_descriptor(USBD_SpeedTypeDef speed, u16* length) {
  (void) speed;
  return string_descriptor("MK61S FS", length);
}

static u8* serial_descriptor(USBD_SpeedTypeDef speed, u16* length) {
  (void) speed;
  *length = sizeof(serial_desc);
  return serial_desc;
}

static u8* configuration_descriptor(USBD_SpeedTypeDef speed, u16* length) {
  (void) speed;
  return string_descriptor("MK61S FS Config", length);
}

static u8* interface_descriptor(USBD_SpeedTypeDef speed, u16* length) {
  (void) speed;
  return string_descriptor("MK61S FS Interface", length);
}

static USBD_DescriptorsTypeDef descriptors = {
  device_descriptor,
  lang_id_descriptor,
  manufacturer_descriptor,
  product_descriptor,
  serial_descriptor,
  configuration_descriptor,
  interface_descriptor
#if (USBD_CLASS_USER_STRING_DESC == 1)
  , NULL
#endif
#if ((USBD_LPM_ENABLED == 1U) || (USBD_CLASS_BOS_ENABLED == 1))
  , NULL
#endif
};

static int8_t storage_init(uint8_t lun) {
  if(lun != 0) return USBD_MSC_STORAGE_ERROR;
  reset_deferred_io();
  return USBD_MSC_STORAGE_OK;
}

static int8_t storage_capacity(uint8_t lun, uint32_t* block_num, uint16_t* block_size) {
  if(lun != 0 || block_num == NULL || block_size == NULL) return USBD_MSC_STORAGE_ERROR;
  const u32 sectors = virtual_fat::sector_count();
  *block_num = sectors;
  *block_size = virtual_fat::SECTOR_SIZE;
  return 0;
}

static int8_t storage_ready(uint8_t lun) {
  if(lun != 0) return USBD_MSC_STORAGE_ERROR;
  return is_initialized() ? 0 : -1;
}

static int8_t storage_write_protected(uint8_t lun) {
  if(lun != 0) return 1;
  return 0;
}

static int8_t storage_read(uint8_t lun, uint8_t* buf, uint32_t block_addr, uint16_t block_len) {
  u32 data_len = 0;
  if(lun != 0 || buf == NULL || block_len == 0 ||
     !msc_scsi_transfer_bytes(block_len, virtual_fat::SECTOR_SIZE, &data_len) ||
     data_len > MSC_MEDIA_PACKET ||
     !msc_scsi_range_is_valid(virtual_fat::sector_count(), block_addr, block_len)) {
    return USBD_MSC_STORAGE_ERROR;
  }

  const DeferredReadState state = deferred_read_state();
  if(state == DeferredReadState::COMPLETE_OK || state == DeferredReadState::COMPLETE_ERROR) {
    if(deferred_read.block_addr != block_addr || deferred_read.block_len != block_len ||
       deferred_read.buffer != buf) {
      reset_deferred_read();
      return USBD_MSC_STORAGE_ERROR;
    }
    const int8_t result = state == DeferredReadState::COMPLETE_OK
      ? USBD_MSC_STORAGE_OK
      : USBD_MSC_STORAGE_ERROR;
    reset_deferred_read();
    return result;
  }
  if(state != DeferredReadState::EMPTY) return USBD_MSC_STORAGE_BUSY;

  deferred_read.block_addr = block_addr;
  deferred_read.block_len = block_len;
  deferred_read.buffer = buf;
  set_deferred_read_state(DeferredReadState::PENDING);
  return USBD_MSC_STORAGE_BUSY;
}

static int8_t storage_write(uint8_t lun, uint8_t* buf, uint32_t block_addr, uint16_t block_len) {
  u32 data_len = 0;
  if(lun != 0 || buf == NULL || block_len == 0 ||
     !msc_scsi_transfer_bytes(block_len, virtual_fat::SECTOR_SIZE, &data_len) ||
     data_len > MSC_MEDIA_PACKET ||
     !msc_scsi_range_is_valid(virtual_fat::sector_count(), block_addr, block_len)) {
    return USBD_MSC_STORAGE_ERROR;
  }

  const DeferredWriteState state = deferred_state();
  if(state == DeferredWriteState::COMPLETE_OK || state == DeferredWriteState::COMPLETE_ERROR) {
    if(deferred_write.block_addr != block_addr || deferred_write.block_len != block_len ||
       deferred_write.buffer != buf) {
      reset_deferred_write();
      return USBD_MSC_STORAGE_ERROR;
    }
    const int8_t result = state == DeferredWriteState::COMPLETE_OK
      ? USBD_MSC_STORAGE_OK
      : USBD_MSC_STORAGE_ERROR;
    reset_deferred_write();
    return result;
  }
  if(state != DeferredWriteState::EMPTY) return USBD_MSC_STORAGE_BUSY;

  // Обычный случай — простое копирование в ОЗУ: один полный пакет BOT размером
  // 8 КиБ помещается в кэш A00 (два пакета на UC1609), и его можно подтвердить
  // немедленно. В основной цикл, где доступ к SPI безопасен, передаётся только
  // нехватка кэша, требующая вытеснения изменённых данных.
  if(virtual_fat::try_write_cached_sectors(block_addr, buf, block_len)) {
    return USBD_MSC_STORAGE_OK;
  }

  deferred_write.block_addr = block_addr;
  deferred_write.block_len = block_len;
  // SCSI_ProcessWrite намеренно не подготавливает конечную точку OUT, пока
  // обратный вызов возвращает BUSY, поэтому пакет BOT STM32 остаётся неизменным
  // до SCSI_ContinueWrite(). Публикуем указатель последним и избегаем копирования
  // 8 КиБ.
  deferred_write.buffer = buf;
  set_deferred_state(DeferredWriteState::PENDING);
  return USBD_MSC_STORAGE_BUSY;
}

static int8_t storage_max_lun(void) {
  return 0;
}

static int8_t inquiry_data[] = {
  0x00,
  -128,
  0x02,
  0x02,
  STANDARD_INQUIRY_DATA_LEN - 5,
  0x00,
  0x00,
  0x00,
  'M', 'K', '6', '1', 'S', ' ', ' ', ' ',
  'P', 'r', 'o', 'g', 'r', 'a', 'm', 's',
  ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ',
  '0', '.', '0', '1'
};

static USBD_StorageTypeDef storage = {
  storage_init,
  storage_capacity,
  storage_ready,
  storage_write_protected,
  storage_read,
  storage_write,
  storage_max_lun,
  inquiry_data
};

static void close_session(void) {
  release_usb_device();
  if(session_open) virtual_fat::end_session();
  session_open = false;
  release_cache_buffer();
}

bool init(void) {
  if(is_initialized()) return true;
  if(!acquire_cache_buffer()) return false;
  if(session_open) {
    if(device_configured) {
      set_initialized(true);
      if(USBD_Start(&usb_device) == USBD_OK) return true;
      set_initialized(false);
      close_session();
      return false;
    }
    virtual_fat::end_session();
    session_open = false;
  }

  reset_deferred_io();
  if(!configure_cache_buffer() || !virtual_fat::reset_session()) {
    virtual_fat::end_session();
    release_cache_buffer();
    return false;
  }
  session_open = true;

  if(USBD_Init(&usb_device, &descriptors, 0) != USBD_OK) {
    virtual_fat::end_session();
    session_open = false;
    release_cache_buffer();
    return false;
  }
  device_configured = true;
  if(USBD_RegisterClass(&usb_device, USBD_MSC_CLASS) != USBD_OK) {
    release_usb_device();
    virtual_fat::end_session();
    session_open = false;
    release_cache_buffer();
    return false;
  }
  if(USBD_MSC_RegisterStorage(&usb_device, &storage) != USBD_OK) {
    release_usb_device();
    virtual_fat::end_session();
    session_open = false;
    release_cache_buffer();
    return false;
  }

  set_initialized(true);
  if(USBD_Start(&usb_device) != USBD_OK) {
    set_initialized(false);
    close_session();
    return false;
  }

  return true;
}

bool deinit(void) {
  if(!is_initialized()) {
    if(!session_open) {
      release_cache_buffer();
      return true;
    }
    const bool flushed = virtual_fat::flush_pending();
    close_session();
    return flushed;
  }
  // Сначала останавливаем USB: его прерывание работает с той же SPI-флеш-памятью,
  // а одновременный с этим сбросом обратный вызов хранилища повредил бы обе
  // передачи.
  set_initialized(false);
  (void) USBD_Stop(&usb_device);
  bool pending_ok = true;
  if(deferred_state() == DeferredWriteState::PENDING) {
    set_deferred_state(DeferredWriteState::PROCESSING);
    pending_ok = virtual_fat::write_cached_sectors(
      deferred_write.block_addr,
      deferred_write.buffer,
      deferred_write.block_len
    );
    set_deferred_state(DeferredWriteState::EMPTY);
  }
  reset_deferred_io();
  // Сохраняем завершённые транзакции хоста. Если незавершённую транзакцию
  // невозможно сбросить, явное нажатие ESC всё равно должно остановить MSC:
  // перезапуск того же сбойного BOT-сеанса оставляет в macOS фантомный диск
  // нулевого размера и делает следующее подключение невозможным. Зафиксированные
  // файлы уже сохранены; при освобождении VFAT в close_session() отбрасывается
  // только незавершённая транзакция.
  const bool flushed = virtual_fat::flush_pending();
  close_session();
  return pending_ok && flushed;
}

bool active(void) {
  return is_initialized();
}

void service(void) {
  if(!is_initialized()) return;

  if(deferred_state() == DeferredWriteState::PENDING) {
    DeferredWriteState expected = DeferredWriteState::PENDING;
    if(!__atomic_compare_exchange_n(&deferred_write.state, &expected,
                                    DeferredWriteState::PROCESSING, false,
                                    __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return;
    const bool ok = virtual_fat::write_cached_sectors(
      deferred_write.block_addr,
      deferred_write.buffer,
      deferred_write.block_len
    );
    expected = DeferredWriteState::PROCESSING;
    if(!__atomic_compare_exchange_n(&deferred_write.state, &expected,
                                    ok ? DeferredWriteState::COMPLETE_OK : DeferredWriteState::COMPLETE_ERROR,
                                    false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
      set_deferred_state(DeferredWriteState::EMPTY);
      return;
    }

    // Этот вызов повторно входит в storage_write(), где обрабатывается COMPLETE_*,
    // после чего автомат BOT подтверждает блок или возвращает хосту WRITE_FAULT.
    if(SCSI_ContinueWrite(&usb_device) < 0) reset_deferred_write();
    return;
  }

  if(deferred_read_state() == DeferredReadState::PENDING) {
    DeferredReadState expected = DeferredReadState::PENDING;
    if(!__atomic_compare_exchange_n(&deferred_read.state, &expected,
                                    DeferredReadState::PROCESSING, false,
                                    __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return;
    u8* const buffer = deferred_read.buffer;
    const u32 block_addr = deferred_read.block_addr;
    const u16 block_len = deferred_read.block_len;
    const bool ok = virtual_fat::read_sectors(
      block_addr,
      buffer,
      block_len
    );
    expected = DeferredReadState::PROCESSING;
    if(!__atomic_compare_exchange_n(&deferred_read.state, &expected,
                                    ok ? DeferredReadState::COMPLETE_OK : DeferredReadState::COMPLETE_ERROR,
                                    false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
      set_deferred_read_state(DeferredReadState::EMPTY);
      return;
    }
    if(SCSI_ContinueRead(&usb_device) < 0) reset_deferred_read();
    return;
  }

  if(deferred_sync() == DeferredSyncState::PENDING) {
    DeferredSyncState expected = DeferredSyncState::PENDING;
    if(!__atomic_compare_exchange_n(&deferred_sync_state, &expected,
                                    DeferredSyncState::PROCESSING, false,
                                    __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return;
    const bool ok = virtual_fat::flush_pending();
    expected = DeferredSyncState::PROCESSING;
    if(!__atomic_compare_exchange_n(&deferred_sync_state, &expected,
                                    DeferredSyncState::EMPTY, false,
                                    __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
      set_deferred_sync(DeferredSyncState::EMPTY);
      return;
    }
    (void) SCSI_CompleteSync(&usb_device, ok ? 1U : 0U);
  }
}

extern "C" u8 MK61_VirtualFatSync(void) {
  if(!is_initialized()) return 1U;
  DeferredSyncState expected = DeferredSyncState::EMPTY;
  if(__atomic_compare_exchange_n(&deferred_sync_state, &expected,
                                 DeferredSyncState::PENDING, false,
                                 __ATOMIC_RELEASE, __ATOMIC_ACQUIRE)) return 2U;
  return deferred_sync() == DeferredSyncState::PENDING ? 2U : 1U;
}

} // пространство имён usb_mass_storage

#else

namespace usb_mass_storage {
bool init(void) { return false; }
bool deinit(void) { return true; }
bool active(void) { return false; }
void service(void) {}
}

extern "C" u8 MK61_VirtualFatSync(void) { return 1U; }

#endif
