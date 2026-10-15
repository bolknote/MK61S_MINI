// Compile the production foreground bridge and RAM manager. USB controller,
// disk media and display UI are mocked; prepare/unwind decisions remain real.
#include "../code/display.hpp"
#if defined(MK61_DISPLAY_UC1609)
#include "../code/menu.hpp"
// Include the real UI declaration before substituting its hardware-facing
// accessor, so the Classic close/eject path executes without a physical LCD.
struct FixtureDiskDisplay {
  void beginDiskSaving(bool) {}
  void endDiskSaving() {}
};
static FixtureDiskDisplay fixture_display;
static FixtureDiskDisplay& msc_fixture_display() { return fixture_display; }
namespace library_mk61 { bool language_is_ru() { return false; } }
#define main_lcd msc_fixture_display
#endif
#include "../code/usb_mass_storage.cpp"
#undef main_lcd
#include <stddef.h>
#define CHECK(x) do { if(!(x)) return __LINE__; } while(0)
static unsigned failure, ended, starts, stops;
static bool media_open;
static bool cancel_on_io;
static unsigned cancel_checks;
static void cancel_twice(u8* buffer) {
  if(!cancel_on_io)return;
  MK61_MSC_DiskInit();MK61_MSC_DiskInit();
  if(usb_mass_storage::MK61_MSC_DiskRead(buffer,0,1)!=USBD_MSC_STORAGE_ERROR ||
     usb_mass_storage::MK61_MSC_DiskWrite(buffer,0,1)!=USBD_MSC_STORAGE_ERROR)
    cancel_checks=0xBAD;
  else ++cancel_checks;
}
static shared_memory::Lease stage;
static virtual_fat::Diagnostic diag;
namespace virtual_fat {
u32 sector_count() { return 1024; }
bool read_sectors(u32,u8* buffer,u16) { cancel_twice(buffer);return true; }
bool try_write_cached_sectors(u32,const u8*,u16) { return false; }
bool write_cached_sectors(u32,const u8* buffer,u16) { cancel_twice((u8*)buffer);return true; }
u8 write_cache_capacity() { return 16; }
bool set_external_cache(u8*,usize) { return failure!=1; }
bool reset_session() {
  media_open=true;
  return stage.acquire_cache(shared_memory::Arena::OVERLAY,
      shared_memory::Owner::VFAT_STAGE,shared_memory::STAGE_INDEX_SIZE) && failure!=2;
}
void end_session() { ++ended;media_open=false;stage.reset(); }
CommitResult finalize_pending_result() { return failure==7?CommitResult::IO_FAILED:CommitResult::OK; }
CommitResult flush_pending_result() { return CommitResult::OK; }
const Diagnostic& diagnostic() { return diag; }
void restore_diagnostic(const Diagnostic& value) { diag=value; }
void report_startup_failure(u32 n,const char*) { diag.code=ErrorCode::PREPARE;diag.actual=n; }
}
namespace program_store {
const storage_geometry::Geometry& geometry() {
  static storage_geometry::Geometry value={};return value;
}
u16 vfat_stage_count() { return 0; }
}
namespace disk_activity { void note() {} }
namespace power_monitor { bool writes_allowed(){return true;} bool allow(Operation){return true;} }
namespace device_identity {
Uid96 read() { return {1,2,3}; }
bool format_stm32duino_usb_serial(const Uid96&,char out[USB_SERIAL_TEXT_SIZE]) { out[0]=0;return true; }
}
extern "C" {
USBD_HandleTypeDef hUSBD_Device_CDC;
uint8_t USBD_StrDesc[USBD_MAX_STR_DESC_SIZ];
USBD_StatusTypeDef USBD_Init(USBD_HandleTypeDef* d,USBD_DescriptorsTypeDef*,uint8_t) {
  memset(d,0,sizeof(*d));return failure==3?USBD_FAIL:USBD_OK;
}
USBD_StatusTypeDef USBD_RegisterClass(USBD_HandleTypeDef* d,USBD_ClassTypeDef* c) {
  d->pClass[0]=c;return failure==4?USBD_FAIL:USBD_OK;
}
USBD_StatusTypeDef USBD_Start(USBD_HandleTypeDef* d) {
  ++starts;d->dev_state=USBD_STATE_CONFIGURED;d->dev_speed=USBD_SPEED_FULL;
  if(d->pClass[0]->Init(d,0)!=USBD_OK)return USBD_FAIL;
  return failure==6?USBD_FAIL:USBD_OK;
}
USBD_StatusTypeDef USBD_Stop(USBD_HandleTypeDef* d) {
  ++stops;return d->pClass[0]? (USBD_StatusTypeDef)d->pClass[0]->DeInit(d,0):USBD_OK;
}
USBD_StatusTypeDef USBD_DeInit(USBD_HandleTypeDef* d) { return USBD_Stop(d); }
void USBD_GetString(uint8_t*,uint8_t* out,uint16_t* length) { out[0]=2;out[1]=3;*length=2; }
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef*,uint8_t,uint8_t,uint16_t) { return failure==5?USBD_FAIL:USBD_OK; }
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef*,uint8_t) { return USBD_OK; }
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef*,uint8_t) { return USBD_OK; }
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef*,uint8_t) { return USBD_OK; }
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef*,uint8_t,uint8_t*,uint32_t) { return USBD_OK; }
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef*,uint8_t,uint8_t*,uint32_t) { return USBD_OK; }
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef*,uint8_t) { return 31; }
USBD_StatusTypeDef USBD_CtlSendData(USBD_HandleTypeDef*,uint8_t*,uint32_t) { return USBD_OK; }
void USBD_CtlError(USBD_HandleTypeDef*,USBD_SetupReqTypedef*) {}
}
static int clean() {
  CHECK(!usb_mass_storage::active() && !usb_mass_storage::transport_buffer.ok());
  CHECK(!stage.ok() && !media_open && shared_memory::validate_invariants());
  CHECK(exclusive_buffer::current_owner()!=exclusive_buffer::Owner::USB_CACHE);
  CHECK(USBD_MSC.Init(&hUSBD_Device_CDC,0)==USBD_FAIL); // No dangling prepared pointer.
  return 0;
}
extern "C" int test_msc_bridge_cycles() {
  using namespace usb_mass_storage;using namespace shared_memory;
  CHECK(prepare_retained_buffers());
  const auto* heap=adjust_heap(0);const auto available=capacity(Arena::OVERLAY);
  for(unsigned cycle=0;cycle<50;++cycle) {
    CHECK(prepare() && transport_buffer.ok() && media_open);
    CHECK(prepare()); // Idempotent before USB starts.
    CHECK(init() && active() && init());
    CHECK(MK61_USBD_ClassData(&hUSBD_Device_CDC)==transport_buffer.data());
    CHECK(deinit() && deinit());
    if(int line=clean()) return line;
    CHECK(adjust_heap(0)==heap && capacity(Arena::OVERLAY)==available);
    Lease reused(Arena::OVERLAY,Owner::USB_SCREEN,available);
    CHECK(reused.ok());memset(reused.data(),0xB6,reused.size());
    CHECK(USBD_MSC.DataIn(&hUSBD_Device_CDC,1)==USBD_FAIL);
    for(usize i=0;i<reused.size();++i)CHECK(reused.data()[i]==0xB6);
  }
  CHECK(starts==50);return 0;
}
extern "C" int test_msc_bridge_failures() {
  using namespace usb_mass_storage;using namespace shared_memory;
  CHECK(prepare_retained_buffers());const auto* heap=adjust_heap(0);
  const auto available=capacity(Arena::OVERLAY);
  for(unsigned mode=1;mode<=7;++mode) {
    failure=mode;
    if(mode==7) {CHECK(init());CHECK(!deinit());}
    else CHECK(!init());
    if(int line=clean())return line;
    CHECK(adjust_heap(0)==heap && capacity(Arena::OVERLAY)==available);
    failure=0;CHECK(init() && deinit());
    if(int line=clean())return line;
  }
  return 0;
}
extern "C" int test_msc_bridge_oom() {
  using namespace usb_mass_storage;using namespace shared_memory;
  CHECK(prepare_retained_buffers());const auto available=capacity(Arena::OVERLAY);
  CHECK(available>STAGE_INDEX_SIZE+8264+8);
  const usize fill=available-STAGE_INDEX_SIZE-8264+8;
  CHECK(adjust_heap(fill));
  CHECK(!prepare());
  if(int line=clean())return line;
  CHECK(diag.actual==19);
  CHECK(adjust_heap(-i32(fill)));
  CHECK(init() && deinit());
  return clean();
}

extern "C" int test_msc_bridge_pending_cancel() {
  using namespace usb_mass_storage;using namespace shared_memory;
  CHECK(prepare_retained_buffers());const auto available=capacity(Arena::OVERLAY);
  for(unsigned request=0;request<3;++request) {
    CHECK(init());
    auto* handle=(USBD_MSC_BOT_HandleTypeDef*)MK61_USBD_ClassData(&hUSBD_Device_CDC);
    if(request==0)CHECK(MK61_MSC_DiskRead(handle->bot_data,0,1)==USBD_MSC_STORAGE_BUSY);
    else if(request==1)CHECK(MK61_MSC_DiskWrite(handle->bot_data,0,1)==USBD_MSC_STORAGE_BUSY);
    else CHECK(MK61_VirtualFatSync()==2);
    CHECK(deinit());
    if(int line=clean())return line;
    CHECK(deferred_read.buffer==nullptr && deferred_write.buffer==nullptr);
    CHECK(deferred_state()==DeferredWriteState::EMPTY && deferred_read_state()==DeferredReadState::EMPTY && deferred_sync()==DeferredSyncState::EMPTY);
    Lease reused(Arena::OVERLAY,Owner::USB_SCREEN,available);
    CHECK(reused.ok());memset(reused.data(),0x71,reused.size());
    service(); // An idle main loop cannot resume cancelled disk work.
    CHECK(SCSI_ContinueRead(&hUSBD_Device_CDC)<0 && SCSI_ContinueWrite(&hUSBD_Device_CDC)<0 && SCSI_CompleteSync(&hUSBD_Device_CDC,1)<0);
    for(usize i=0;i<reused.size();++i)CHECK(reused.data()[i]==0x71);
  }
  // Reentrant teardown while a foreground operation is processing refuses
  // to free its packet. After that operation returns, close may retry.
  CHECK(init());set_deferred_state(DeferredWriteState::PROCESSING);
  CHECK(!deinit() && transport_buffer.ok());
  CHECK(deferred_state()==DeferredWriteState::CANCELLED && diag.actual==20);
  set_deferred_state(DeferredWriteState::EMPTY);
  CHECK(deinit());return clean();
}

extern "C" int test_msc_bridge_reset_during_io() {
  using namespace usb_mass_storage;
  for(unsigned request=0;request<2;++request) {
    CHECK(init());auto* h=(USBD_MSC_BOT_HandleTypeDef*)MK61_USBD_ClassData(&hUSBD_Device_CDC);
    if(request==0)CHECK(MK61_MSC_DiskRead(h->bot_data,0,1)==USBD_MSC_STORAGE_BUSY);
    else CHECK(MK61_MSC_DiskWrite(h->bot_data,0,1)==USBD_MSC_STORAGE_BUSY);
    cancel_on_io=true;service();cancel_on_io=false;
    CHECK(cancel_checks==request+1);
    CHECK(deferred_state()==DeferredWriteState::EMPTY && deferred_read_state()==DeferredReadState::EMPTY);
    CHECK(deinit());if(int line=clean())return line;
  }
  return 0;
}
