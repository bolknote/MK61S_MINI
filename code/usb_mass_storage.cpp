#include "usb_mass_storage.hpp"

#include "rust_types.h"
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

static bool is_initialized(void) {
  return __atomic_load_n(&initialized, __ATOMIC_ACQUIRE);
}

static void set_initialized(bool value) {
  __atomic_store_n(&initialized, value, __ATOMIC_RELEASE);
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
  DeferredWriteState state;
  u32 block_addr;
  u16 block_len;
  u8 data[MSC_MEDIA_PACKET];
};

static DeferredWrite deferred_write = {DeferredWriteState::EMPTY, 0, 0, {0}};

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
  (void) lun;
  reset_deferred_io();
  return USBD_MSC_STORAGE_OK;
}

static int8_t storage_capacity(uint8_t lun, uint32_t* block_num, uint16_t* block_size) {
  (void) lun;
  const u32 sectors = virtual_fat::sector_count();
  *block_num = sectors;
  *block_size = virtual_fat::SECTOR_SIZE;
  return 0;
}

static int8_t storage_ready(uint8_t lun) {
  (void) lun;
  return is_initialized() ? 0 : -1;
}

static int8_t storage_write_protected(uint8_t lun) {
  (void) lun;
  return 0;
}

static int8_t storage_read(uint8_t lun, uint8_t* buf, uint32_t block_addr, uint16_t block_len) {
  (void) lun;
  const u32 data_len = (u32) block_len * virtual_fat::SECTOR_SIZE;
  if(buf == NULL || block_len == 0 || data_len > MSC_MEDIA_PACKET) return USBD_MSC_STORAGE_ERROR;

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
  (void) lun;
  const u32 data_len = (u32) block_len * virtual_fat::SECTOR_SIZE;
  if(buf == NULL || block_len == 0 || data_len > sizeof(deferred_write.data)) return USBD_MSC_STORAGE_ERROR;

  const DeferredWriteState state = deferred_state();
  if(state == DeferredWriteState::COMPLETE_OK || state == DeferredWriteState::COMPLETE_ERROR) {
    if(deferred_write.block_addr != block_addr || deferred_write.block_len != block_len) {
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

  memcpy(deferred_write.data, buf, data_len);
  deferred_write.block_addr = block_addr;
  deferred_write.block_len = block_len;
  // Publish the state last: service() must never observe a half-copied block.
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

bool init(void) {
  if(is_initialized()) return true;
  if(session_open) {
    set_initialized(true);
    if(USBD_Start(&usb_device) == USBD_OK) return true;
    set_initialized(false);
    return false;
  }

  reset_deferred_io();
  if(!virtual_fat::reset_session()) return false;
  session_open = true;

  if(USBD_Init(&usb_device, &descriptors, 0) != USBD_OK) {
    virtual_fat::end_session();
    session_open = false;
    return false;
  }
  if(USBD_RegisterClass(&usb_device, USBD_MSC_CLASS) != USBD_OK) {
    (void) USBD_DeInit(&usb_device);
    memset(&usb_device, 0, sizeof(usb_device));
    virtual_fat::end_session();
    session_open = false;
    return false;
  }
  if(USBD_MSC_RegisterStorage(&usb_device, &storage) != USBD_OK) {
    (void) USBD_DeInit(&usb_device);
    memset(&usb_device, 0, sizeof(usb_device));
    virtual_fat::end_session();
    session_open = false;
    return false;
  }

  set_initialized(true);
  if(USBD_Start(&usb_device) != USBD_OK) {
    set_initialized(false);
    (void) USBD_DeInit(&usb_device);
    memset(&usb_device, 0, sizeof(usb_device));
    virtual_fat::end_session();
    session_open = false;
    return false;
  }

  return true;
}

bool deinit(void) {
  if(!is_initialized()) {
    if(!session_open) return true;
    if(!virtual_fat::flush_pending()) return false;
    virtual_fat::end_session();
    session_open = false;
    return true;
  }
  // Stop USB first: its interrupt drives the same SPI flash, and a storage
  // callback racing this flush would corrupt both transfers.
  set_initialized(false);
  (void) USBD_Stop(&usb_device);
  if(deferred_state() == DeferredWriteState::PENDING) {
    set_deferred_state(DeferredWriteState::PROCESSING);
    (void) virtual_fat::write_sectors(deferred_write.block_addr, deferred_write.data, deferred_write.block_len);
    set_deferred_state(DeferredWriteState::EMPTY);
  }
  reset_deferred_io();
  // Persist queued writes/deletes even when the host never ejected cleanly.
  if(!virtual_fat::flush_pending()) {
    // Keep the session and reconnect the device. Discarding the language
    // workspace here would lose writes that the host has already submitted.
    set_initialized(true);
    if(USBD_Start(&usb_device) != USBD_OK) set_initialized(false);
    return false;
  }
  (void) USBD_DeInit(&usb_device);
  memset(&usb_device, 0, sizeof(usb_device));
  virtual_fat::end_session();
  session_open = false;
  return true;
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
    const bool ok = virtual_fat::write_sectors(
      deferred_write.block_addr,
      deferred_write.data,
      deferred_write.block_len
    );
    expected = DeferredWriteState::PROCESSING;
    if(!__atomic_compare_exchange_n(&deferred_write.state, &expected,
                                    ok ? DeferredWriteState::COMPLETE_OK : DeferredWriteState::COMPLETE_ERROR,
                                    false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
      set_deferred_state(DeferredWriteState::EMPTY);
      return;
    }

    // This re-enters storage_write(), which consumes COMPLETE_* and lets the BOT
    // state machine acknowledge the block or return WRITE_FAULT to the host.
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

} // namespace usb_mass_storage

#else

namespace usb_mass_storage {
bool init(void) { return false; }
bool deinit(void) { return true; }
bool active(void) { return false; }
void service(void) {}
}

extern "C" u8 MK61_VirtualFatSync(void) { return 1U; }

#endif
