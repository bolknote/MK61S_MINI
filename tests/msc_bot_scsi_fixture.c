/* Run the production class/BOT/SCSI sources against an independent USB wire
 * and a deterministic 512-byte-sector disk. No host filesystem is involved. */
#include "usbd_msc.h"
#include "msc_scsi_safety.h"
#include <stddef.h>
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)

static USBD_HandleTypeDef dev;
static struct { uint32_t left[8]; USBD_MSC_BOT_HandleTypeDef h; uint32_t right[8]; } guarded;
static USBD_MSC_BOT_HandleTypeDef *h;
static uint8_t *rx_buffer;
static uint32_t rx_length, rx_received, rx_count, tx_length, tx_count;
static uint8_t tx[MSC_MEDIA_PACKET];
static unsigned wire_error, stalls, stalled_in, stalled_out, closed, fail_open;
static unsigned init_calls, reads, writes, sync_calls;
static int8_t read_result, write_result;
static uint32_t blocks, write_cache_blocks;
static uint8_t ready, protected, sync_result;

static uint8_t disk_byte(uint32_t lba, unsigned offset) {
  return (uint8_t)(lba * 19U + offset * 73U + (offset >> 8));
}
static int8_t disk_init(void) { ++init_calls; return 0; }
static int8_t disk_read(uint8_t *buffer, uint32_t lba, uint16_t count) {
  if (!buffer || !count || count > MSC_MEDIA_PACKET/512 || lba >= blocks || count > blocks-lba) {
    wire_error = __LINE__; return -1;
  }
  ++reads;
  if (read_result) return read_result;
  for (unsigned b=0;b<count;b++) for (unsigned i=0;i<512;i++) buffer[b*512+i]=disk_byte(lba+b,i);
  return 0;
}
static int8_t disk_write(uint8_t *buffer, uint32_t lba, uint16_t count) {
  if (!buffer || !count || count > MSC_MEDIA_PACKET/512 || lba >= blocks || count > blocks-lba) {
    wire_error = __LINE__; return -1;
  }
  ++writes;
  for (unsigned b=0;b<count;b++) for (unsigned i=0;i<512;i++)
    if (buffer[b*512+i]!=disk_byte(lba+b,i)) wire_error=__LINE__;
  return write_result;
}
uint8_t MK61_VirtualFatSync(void) { ++sync_calls; return sync_result; }
uint32_t MK61_VirtualFatWriteCacheBlocks(void) { return write_cache_blocks; }

#ifdef MK61_MSC_FIXED_DISK
int8_t MK61_MSC_DiskInit(void) { return disk_init(); }
uint32_t MK61_MSC_DiskBlocks(void) { return blocks; }
int8_t MK61_MSC_DiskReady(void) { return ready ? 0 : -1; }
int8_t MK61_MSC_DiskWriteProtected(void) { return protected; }
int8_t MK61_MSC_DiskRead(uint8_t *b,uint32_t a,uint16_t n) { return disk_read(b,a,n); }
int8_t MK61_MSC_DiskWrite(uint8_t *b,uint32_t a,uint16_t n) { return disk_write(b,a,n); }
#else
static int8_t init(uint8_t lun) { if(lun)wire_error=__LINE__; return disk_init(); }
static int8_t capacity(uint8_t lun,uint32_t *n,uint16_t *s) { if(lun)wire_error=__LINE__; *n=blocks;*s=512;return 0; }
static int8_t is_ready(uint8_t lun) { if(lun)wire_error=__LINE__;return ready?0:-1; }
static int8_t is_protected(uint8_t lun) { if(lun)wire_error=__LINE__;return protected; }
static int8_t read_blocks(uint8_t lun,uint8_t *b,uint32_t a,uint16_t n) { if(lun)wire_error=__LINE__;return disk_read(b,a,n); }
static int8_t write_blocks(uint8_t lun,uint8_t *b,uint32_t a,uint16_t n) { if(lun)wire_error=__LINE__;return disk_write(b,a,n); }
static int8_t max_lun(void) { return 0; }
static int8_t inquiry[36]={0, (int8_t)0x80, 2, 2, 31, 0, 0, 0,
  'M','K','6','1','S',' ',' ',' ','P','r','o','g','r','a','m','s',
  ' ',' ',' ',' ',' ',' ',' ',' ','0','.','0','1'};
static USBD_StorageTypeDef storage={init,capacity,is_ready,is_protected,read_blocks,write_blocks,max_lun,inquiry};
#endif

USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *d,uint8_t ep,uint8_t type,uint16_t size) {
  (void)d;if((ep!=0x81 && ep!=1)||type!=USBD_EP_TYPE_BULK||size!=64)wire_error=__LINE__;
  if (fail_open && --fail_open==0) return USBD_FAIL;
  return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *d,uint8_t ep) { (void)d;(void)ep;++closed;return 0; }
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef *d,uint8_t ep) { (void)d;(void)ep;return 0; }
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef *d,uint8_t ep) {
  (void)d;++stalls;if(ep==0x81)stalled_in=1;else if(ep==1)stalled_out=1;else wire_error=__LINE__;return 0;
}
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef *d,uint8_t ep) {
  (void)d;if(ep==0x81)stalled_in=0;else if(ep==1)stalled_out=0;else wire_error=__LINE__;return 0;
}
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *d,uint8_t ep,uint8_t *b,uint32_t size) {
  (void)d;if(ep!=0x81 || size>sizeof(tx) || (!b && size)) {wire_error=__LINE__;return USBD_FAIL;}
  for(unsigned i=0;i<size;i++) { tx[i]=b[i]; }
  tx_length=size;++tx_count;return 0;
}
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *d,uint8_t ep,uint8_t *b,uint32_t size) {
  (void)d;if(ep!=1 || !b || size>MSC_MEDIA_PACKET) {wire_error=__LINE__;return USBD_FAIL;}
  rx_buffer=b;rx_length=size;++rx_count;return 0;
}
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *d,uint8_t ep) { (void)d;if(ep!=1)wire_error=__LINE__;return rx_received; }
static uint32_t control_length, control_errors;
static uint8_t control[64];
USBD_StatusTypeDef USBD_CtlSendData(USBD_HandleTypeDef *d,uint8_t *b,uint32_t n) {
  (void)d;if(n>sizeof(control))return USBD_FAIL;control_length=n;for(unsigned i=0;i<n;i++)control[i]=b[i];return 0;
}
void USBD_CtlError(USBD_HandleTypeDef *d,USBD_SetupReqTypedef *r) { (void)d;(void)r;++control_errors; }

static int begin(void) {
  (void)USBD_MSC.DeInit(&dev,0);
  memset(&dev,0,sizeof(dev));memset(&guarded,0xa5,sizeof(guarded));
  dev.dev_state=USBD_STATE_CONFIGURED;dev.dev_speed=USBD_SPEED_FULL;
  dev.pClass[0]=(USBD_ClassTypeDef*)&USBD_MSC;
  ready=1;protected=sync_result=0;blocks=4096;write_cache_blocks=16;
  wire_error=stalls=stalled_in=stalled_out=closed=fail_open=0;
  reads=writes=sync_calls=init_calls=0;read_result=write_result=0;
  tx_length=rx_length=rx_received=tx_count=rx_count=0;
  control_errors=control_length=0;
#if defined(STM32F411xE)
  CHECK(MK61_MSC_SetPreparedHandle(&guarded.h,sizeof(guarded.h))==1);
#endif
#ifndef MK61_MSC_FIXED_DISK
  CHECK(USBD_MSC_RegisterStorage(&dev,&storage)==USBD_OK);
#endif
  CHECK(USBD_MSC.Init(&dev,0)==USBD_OK);
  h=(USBD_MSC_BOT_HandleTypeDef*)dev.pClassDataCmsit[0];
  CHECK(h && h->bot_state==USBD_BOT_IDLE && rx_length==31 && init_calls==1);
  return 0;
}
static void put32(uint8_t *p,uint32_t n) { p[0]=n>>24;p[1]=n>>16;p[2]=n>>8;p[3]=n; }
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3]; }
static uint32_t getle(const uint8_t *p) { return (uint32_t)p[3]<<24|(uint32_t)p[2]<<16|(uint32_t)p[1]<<8|p[0]; }
static void cbw(uint8_t op,uint8_t flags,uint32_t bytes) {
  memset(&h->cbw,0,sizeof(h->cbw));h->cbw.dSignature=0x43425355;h->cbw.dTag=0x836192a5;
  h->cbw.dDataLength=bytes;h->cbw.bmFlags=flags;h->cbw.CB[0]=op;
  h->cbw.bCBLength=(op==0x9e || op==0x91)?16:(op>=0xa0?12:(op>=0x20?10:6));
  rx_received=31;tx_count=0;tx_length=0;
}
static void submit(void) { if(USBD_MSC.DataOut(&dev,1)!=USBD_OK)wire_error=__LINE__; }
static void ack(void) { if(USBD_MSC.DataIn(&dev,1)!=USBD_OK)wire_error=__LINE__; }
static void clear(uint8_t ep) {
  USBD_SetupReqTypedef r={0x02,USB_REQ_CLEAR_FEATURE,USB_FEATURE_EP_HALT,ep,0};
  (void)USBD_LL_ClearStallEP(&dev,ep);(void)USBD_MSC.Setup(&dev,&r);
}
static int csw(unsigned status,uint32_t residue) {
  CHECK(!wire_error && tx_length==13 && getle(tx)==0x53425355 && getle(tx+4)==0x836192a5);
  CHECK(tx[12]==status && getle(tx+8)==residue && h->bot_state==USBD_BOT_IDLE);
  CHECK(status==2 ? h->bot_status==USBD_BOT_STATUS_ERROR : rx_length==31);
  for(unsigned i=0;i<8;i++)CHECK(guarded.left[i]==0xa5a5a5a5 && guarded.right[i]==0xa5a5a5a5);
  return 0;
}
#define BEGIN() do { int line=begin(); if(line)return line; } while(0)
#define CSW(s,r) do { int line=csw(s,r);if(line)return line; } while(0)

int test_msc_commands(void) {
  BEGIN();
  cbw(0,0,0);submit();CSW(0,0);
  cbw(0,0x80,0);submit();CSW(0,0);
  cbw(0x12,0x80,96);h->cbw.CB[4]=96;submit();
  CHECK(tx_length==36 && tx[0]==0 && tx[1]==0x80 && tx[4]==31);
  static const char text[]="MK61S   Programs        0.01";
  for(unsigned i=0;i<sizeof(text)-1;i++)CHECK(tx[8+i]==(uint8_t)text[i]);
  ack();CSW(0,60);
  for(unsigned page=0;page<2;page++) {
    cbw(0x12,0x80,32);h->cbw.CB[1]=1;h->cbw.CB[2]=page?0x80:0;h->cbw.CB[4]=32;submit();
    CHECK(tx_length==(page?8U:6U) && tx[1]==(page?0x80:0));ack();CSW(0,32-(page?8:6));
  }
  cbw(0x25,0x80,8);submit();CHECK(tx_length==8 && get32(tx)==4095 && get32(tx+4)==512);ack();CSW(0,0);
  cbw(0x9e,0x80,64);h->cbw.CB[1]=0x10;put32(h->cbw.CB+10,64);submit();
  CHECK(tx_length==32 && get32(tx)==0 && get32(tx+4)==4095 && get32(tx+8)==512);ack();CSW(0,32);
  for(unsigned ten=0;ten<2;ten++) {
    cbw(ten?0x5a:0x1a,0x80,64);h->cbw.CB[2]=0x3f;h->cbw.CB[ten?8:4]=64;submit();
    unsigned header=ten?8:4;CHECK(tx_length==header+32 && tx[header]==8 && tx[header+2]==4);
    CHECK(tx[header+20]==0x1b && tx[header+23]==1);ack();CSW(0,64-header-32);
  }
  cbw(0xff,0,0);submit();
#ifdef MK61_MSC_FIXED_DISK
  CSW(1,0);
#else
  CHECK(stalled_in && stalled_out);clear(0x81);CHECK(stalled_in && stalled_out);
#endif
  return 0;
}
int test_msc_streams(void) {
  for(unsigned twelve=0;twelve<2;twelve++) {
    BEGIN();cbw(twelve?0xa8:0x28,0x80,35*512);put32(h->cbw.CB+2,73);
    if(twelve)put32(h->cbw.CB+6,35);else h->cbw.CB[8]=35;
    /* Capacity need not have been requested before READ. */
#ifndef MK61_MSC_FIXED_DISK
    h->scsi_blk_nbr=blocks;h->scsi_blk_size=512;
#endif
    submit();unsigned received=0;
    while(tx_length!=13) {
      CHECK(tx_length && tx_length<=MSC_MEDIA_PACKET && tx_length%512==0);
      for(unsigned i=0;i<tx_length;i++)CHECK(tx[i]==disk_byte(73+(received+i)/512,(received+i)%512));
      received+=tx_length;CHECK(received<=35*512);ack();
    }
    CHECK(received==35*512);CSW(0,0);
    cbw(twelve?0xaa:0x2a,0,35*512);put32(h->cbw.CB+2,91);
    if(twelve)put32(h->cbw.CB+6,35);else h->cbw.CB[8]=35;
    write_cache_blocks=3;submit();unsigned sent=0;
    while(rx_length!=31) {
      CHECK(rx_length && rx_length<=3*512 && rx_length<=MSC_MEDIA_PACKET && rx_length%512==0);
      unsigned n=rx_length;for(unsigned i=0;i<n;i++)rx_buffer[i]=disk_byte(91+(sent+i)/512,(sent+i)%512);
      rx_received=n;submit();sent+=n;CHECK(sent<=35*512);
    }
    CHECK(sent==35*512);CSW(0,0);CHECK(reads && writes && !wire_error);
  }
  return 0;
}
int test_msc_deferred(void) {
  BEGIN();cbw(0x25,0x80,8);submit();ack();CSW(0,0);
  cbw(0x28,0x80,512);h->cbw.CB[8]=1;read_result=USBD_MSC_STORAGE_BUSY;submit();
  CHECK(h->bot_state==USBD_BOT_DATA_IN && !tx_count);read_result=0;
  CHECK(SCSI_ContinueRead(&dev)==0 && tx_length==512);ack();CSW(0,0);
  cbw(0x2a,0,512);h->cbw.CB[8]=1;submit();
  for(unsigned i=0;i<512;i++) { rx_buffer[i]=disk_byte(0,i); }
  rx_received=512;
  write_result=USBD_MSC_STORAGE_BUSY;unsigned before=rx_count;submit();
  CHECK(h->bot_state==USBD_BOT_DATA_OUT && rx_count==before && !tx_count);
  write_result=0;CHECK(SCSI_ContinueWrite(&dev)==0);CSW(0,0);
  cbw(0x2a,0,512);h->cbw.CB[8]=1;submit();
  for(unsigned i=0;i<512;i++) {rx_buffer[i]=disk_byte(0,i);}
  rx_received=512;write_result=USBD_MSC_STORAGE_BUSY;submit();write_result=-1;
  CHECK(SCSI_ContinueWrite(&dev)<0);CSW(1,512);clear(1);
  cbw(0x28,0x80,512);h->cbw.CB[8]=1;read_result=USBD_MSC_STORAGE_BUSY;submit();
  read_result=-1;CHECK(SCSI_ContinueRead(&dev)<0);
#ifdef MK61_MSC_FIXED_DISK
  CHECK(stalled_in && h->bot_state==USBD_BOT_WAIT_CLEAR);clear(0x81);
#endif
  CSW(1,512);
  cbw(0x35,0,0);sync_result=2;submit();CHECK(h->bot_state==USBD_BOT_DEFERRED && !tx_count);
  CHECK(SCSI_CompleteSync(&dev,1)==0);CSW(0,0);
  cbw(0x1b,0,0);h->cbw.CB[4]=2;submit();CHECK(h->host_eject_latched && h->bot_state==USBD_BOT_DEFERRED);
  CHECK(SCSI_CompleteSync(&dev,0)<0 && h->host_eject_latched);CSW(1,0);
  cbw(0x1e,0,0);submit();CSW(0,0);CHECK(h->host_eject_latched);
  cbw(0x1b,0,0);h->cbw.CB[4]=1;submit();CSW(0,0);CHECK(!h->host_eject_latched);
  return 0;
}
int test_msc_recovery(void) {
  BEGIN();uint16_t length=0;const uint8_t *descriptor=USBD_MSC.GetFSConfigDescriptor(&length);
  CHECK(length==32 && descriptor[4]==1 && descriptor[11]==0 && descriptor[12]==0);
  CHECK(descriptor[14]==8 && descriptor[15]==6 && descriptor[16]==0x50);
  CHECK(descriptor[20]==0x81 && descriptor[22]==64 && descriptor[23]==0);
  CHECK(descriptor[27]==1 && descriptor[29]==64 && descriptor[30]==0);
  cbw(0,0,0);h->cbw.dSignature=0;submit();CHECK(stalled_in && stalled_out && !tx_count);
  clear(0x81);CHECK(stalled_in && stalled_out && !tx_count);
  USBD_SetupReqTypedef reset={0x21,0xff,0,0,0};
  CHECK(USBD_MSC.Setup(&dev,&reset)==USBD_OK && init_calls==2);
  clear(0x81);clear(1);cbw(0,0,0);submit();CSW(0,0);
  const uint8_t bad_luns[]={1,15,16,255};
  for(unsigned i=0;i<sizeof(bad_luns);i++) {
    BEGIN();cbw(0,0,0);h->cbw.bLUN=bad_luns[i];submit();CHECK(stalled_in && stalled_out && !tx_count);
  }
  for(unsigned i=0;i<4;i++) {
    BEGIN();cbw(0,0,0);rx_received=(uint32_t[]){0,30,32,64}[i];submit();CHECK(stalled_in && stalled_out && !tx_count);
  }
  for(unsigned i=0;i<4;i++) {
    BEGIN();cbw(0,0,0);h->cbw.bCBLength=(uint8_t[]){0,17,32,255}[i];submit();CHECK(stalled_in && stalled_out && !tx_count);
  }
  BEGIN();USBD_SetupReqTypedef r={0xa1,0xfe,0,0,1};CHECK(USBD_MSC.Setup(&dev,&r)==0 && control_length==1 && control[0]==0);
  r.wIndex=0xffff;CHECK(USBD_MSC.Setup(&dev,&r)==USBD_FAIL && control_errors);
  r=(USBD_SetupReqTypedef){0x81,USB_REQ_GET_INTERFACE,0,0,1};CHECK(USBD_MSC.Setup(&dev,&r)==0 && control_length==1 && control[0]==0);
  CHECK(USBD_MSC.DataIn(&dev,2)==USBD_FAIL && USBD_MSC.DataOut(&dev,0)==USBD_FAIL);
  CHECK(!wire_error);return 0;
}

#ifdef MK61_MSC_FIXED_DISK
/* Independent table from USB BOT 1.0 section 6.7: Hn/Hi/Ho against Dn/Di/Do.
 * It specifies wire observations and persistent writes, not implementation
 * helper results. Case 13 is deliberately received but never persisted. */
int test_msc_bot_matrix(void) {
  static const struct {uint8_t op,flags;uint16_t host;uint8_t status;uint16_t residue;} cases[]={
    {0,0,0,0,0}, {0x28,0,0,2,0}, {0x2a,0x80,0,2,0},
    {0,0x80,64,0,64}, {0x28,0x80,1024,0,512}, {0x28,0x80,512,0,0},
    {0x28,0x80,256,2,0}, {0x2a,0x80,512,2,512},
    {0,0,64,0,64}, {0x28,0,512,2,512},
    {0x2a,0,1024,0,512}, {0x2a,0,512,0,0}, {0x2a,0,256,2,0}
  };
  for(unsigned c=0;c<sizeof(cases)/sizeof(*cases);c++) {
    BEGIN();cbw(cases[c].op,cases[c].flags,cases[c].host);h->cbw.CB[8]=1;submit();
    if(h->bot_state==USBD_BOT_DATA_OUT) {
      CHECK(rx_length==512 || (c==12 && rx_length==256));
      for(unsigned i=0;i<rx_length;i++)rx_buffer[i]=disk_byte(0,i);
      rx_received=rx_length;submit();
    } else if(h->bot_state==USBD_BOT_LAST_DATA_IN) {
      CHECK(tx_length==(c==6?256U:512U));
      for(unsigned i=0;i<tx_length;i++)CHECK(tx[i]==disk_byte(0,i));
      ack();
    }
    if(h->bot_state==USBD_BOT_WAIT_CLEAR) {CHECK(stalled_in);clear(0x81);}
    CSW(cases[c].status,cases[c].residue);
    CHECK(writes==((c==10 || c==11)?1U:0U));
    if(cases[c].status==2) {
      unsigned before=rx_count;ack();CHECK(stalled_in && stalled_out);
      clear(0x81);CHECK(stalled_in && stalled_out && rx_count==before);
      USBD_SetupReqTypedef reset={0x21,0xff,0,0,0};
      CHECK(USBD_MSC.Setup(&dev,&reset)==0 && stalled_in && stalled_out && rx_count==before);
      clear(0x81);clear(0x81);CHECK(rx_count==before);
      clear(1);CHECK(rx_count==before+1 && rx_length==31 && !stalled_in && !stalled_out);
      cbw(0,0,0);submit();CSW(0,0);
    }
  }
  return 0;
}
int test_msc_bounds(void) {
  BEGIN();
  /* Invalid CDB lengths must not make out-of-length bytes into an I/O request. */
  const uint8_t ops[]={0,3,0x12,0x1a,0x1b,0x1e,0x23,0x25,0x28,0x2a,0x2f,0x35,0x5a,0x91,0x9e,0xa8,0xaa};
  for(unsigned i=0;i<sizeof(ops);i++) {
    BEGIN();cbw(ops[i],0,0);memset(h->cbw.CB+1,0xff,15);h->cbw.bCBLength=1;submit();
    CSW(1,0);CHECK(!reads && !writes && !sync_calls);
  }
  /* A valid wrapper with a truncated OUT packet may not persist its stale tail. */
  BEGIN();cbw(0x2a,0,512);h->cbw.CB[8]=1;submit();
  memset(rx_buffer,0xa5,512);rx_received=63;submit();CHECK(!writes);CSW(2,512);
  BEGIN();blocks=31;cbw(0x25,0x80,8);submit();CHECK(get32(tx)==30 && get32(tx+4)==512);ack();CSW(0,0);
  blocks=19;cbw(0x23,0x80,12);h->cbw.CB[8]=12;submit();
  CHECK(tx_length==12 && tx[3]==8 && get32(tx+4)==19 && tx[8]==2 && tx[10]==2);ack();CSW(0,0);
  for(unsigned write=0;write<2;write++) {
    cbw(write?0x2a:0x28,write?0:0x80,512);put32(h->cbw.CB+2,19);h->cbw.CB[8]=1;submit();
    if(stalled_in) { clear(0x81); }
    CSW(1,512);if(stalled_out) { clear(1); }
    CHECK(!reads && !writes);
    cbw(write?0xaa:0xa8,0,0);put32(h->cbw.CB+2,19);submit();CSW(0,0);
  }
  cbw(0x28,0x80,512);put32(h->cbw.CB+2,0xffffffff);h->cbw.CB[8]=1;submit();clear(0x81);CSW(1,512);CHECK(!reads);
  BEGIN();blocks=0xffffffff;cbw(0xa8,0x80,512);put32(h->cbw.CB+6,0x800000);submit();clear(0x81);CSW(1,512);CHECK(!reads);
  BEGIN();write_cache_blocks=0;cbw(0x2a,0,512);h->cbw.CB[8]=1;submit();CHECK(!writes);CSW(1,512);
  BEGIN();protected=1;cbw(0x2a,0,512);h->cbw.CB[8]=1;submit();CSW(1,512);CHECK(!writes);
  cbw(3,0x80,18);h->cbw.CB[4]=18;submit();CHECK(tx_length==18 && tx[2]==NOT_READY && tx[12]==WRITE_PROTECTED && tx[13]==0 && tx[7]==10);ack();CSW(0,0);
  return 0;
}
int test_msc_pages_eject(void) {
  BEGIN();
  const uint8_t pages[]={6,0xc8,0x08};
  for(unsigned i=0;i<sizeof(pages);i++) {
    cbw(0x1a,0x80,64);h->cbw.CB[2]=pages[i];h->cbw.CB[3]=(i==2);h->cbw.CB[4]=64;submit();
    CHECK(stalled_in && !tx_count);clear(0x81);CSW(1,64);
    cbw(3,0x80,18);h->cbw.CB[4]=18;submit();
    CHECK(tx[2]==ILLEGAL_REQUEST && tx[12]==(i==1?SAVING_PARAMETERS_NOT_SUPPORTED:INVALID_FIELED_IN_COMMAND));ack();CSW(0,0);
  }
  protected=1;cbw(0x5a,0x80,40);h->cbw.CB[2]=0x3f;h->cbw.CB[8]=40;submit();
  CHECK(tx_length==40 && tx[3]==0x80 && tx[10]==4 && tx[31]==1);ack();CSW(0,0);
  cbw(0x5a,0x80,40);h->cbw.CB[2]=0x7f;h->cbw.CB[8]=40;submit();
  CHECK(tx[10]==0 && tx[31]==0);ack();CSW(0,0);
  cbw(0x12,0,0);submit();CSW(0,0);
  cbw(0x1e,0,0);h->cbw.CB[4]=1;submit();CSW(0,0);
  cbw(0x1b,0,0);h->cbw.CB[4]=2;submit();CSW(1,0);CHECK(!h->host_eject_latched && !sync_calls);
  cbw(0x1e,0,0);submit();CSW(0,0);
  cbw(0x91,0,0);sync_result=2;submit();CHECK(h->bot_state==USBD_BOT_DEFERRED && sync_calls==1);
  CHECK(SCSI_CompleteSync(&dev,1)==0);CSW(0,0);
  cbw(0x1b,0,0);h->cbw.CB[4]=2;submit();CHECK(h->host_eject_latched && h->bot_state==USBD_BOT_DEFERRED);
  CHECK(SCSI_CompleteSync(&dev,1)==0 && h->scsi_medium_state==SCSI_MEDIUM_EJECTED);CSW(0,0);
  cbw(0,0,0);submit();CSW(1,0);
  cbw(0x2a,0,512);h->cbw.CB[8]=1;submit();CSW(1,512);CHECK(!writes);
  return 0;
}
int test_msc_lifetime(void) {
  BEGIN();cbw(0x28,0x80,512);h->cbw.CB[8]=1;read_result=1;submit();CHECK(!tx_count && reads==1);
  USBD_SetupReqTypedef reset={0x21,0xff,0,0,0};
  unsigned before=rx_count;CHECK(USBD_MSC.Setup(&dev,&reset)==0 && init_calls==2 && rx_count==before);
  CHECK(SCSI_ContinueRead(&dev)<0 && reads==1);clear(0x81);clear(1);
  cbw(0x2a,0,512);h->cbw.CB[8]=1;submit();
  for(unsigned i=0;i<512;i++) {rx_buffer[i]=disk_byte(0,i);}
  rx_received=512;write_result=1;submit();CHECK(writes==1 && h->bot_state==USBD_BOT_DATA_OUT);
  CHECK(USBD_MSC.Setup(&dev,&reset)==0 && init_calls==3);CHECK(SCSI_ContinueWrite(&dev)<0 && writes==1);
  clear(0x81);clear(1);cbw(0x35,0,0);sync_result=2;submit();CHECK(h->bot_state==USBD_BOT_DEFERRED);
  CHECK(USBD_MSC.Setup(&dev,&reset)==0 && init_calls==4);CHECK(SCSI_CompleteSync(&dev,1)<0);
  CHECK(USBD_MSC.DeInit(&dev,0)==0 && !dev.pClassDataCmsit[0] && !dev.pClassData);
  CHECK(SCSI_ContinueRead(&dev)<0 && SCSI_ContinueWrite(&dev)<0 && SCSI_CompleteSync(&dev,1)<0);
  CHECK(!dev.ep_in[1].is_used && !dev.ep_out[1].is_used);
  for(unsigned fail=1;fail<3;fail++) {
    fail_open=fail;CHECK(USBD_MSC.Init(&dev,0)==USBD_FAIL);
    CHECK(!dev.pClassDataCmsit[0] && !dev.pClassData && !dev.ep_out[1].is_used && !dev.ep_in[1].is_used);
  }
  CHECK(USBD_MSC.Init(&dev,0)==0);
#if defined(STM32F411xE)
  CHECK(!MK61_MSC_SetPreparedHandle(NULL,sizeof(guarded.h)));
  CHECK(!MK61_MSC_SetPreparedHandle((uint8_t*)&guarded.h+1,sizeof(guarded.h)));
  CHECK(!MK61_MSC_SetPreparedHandle(&guarded.h,sizeof(guarded.h)+4));
  CHECK(!MK61_MSC_SetPreparedHandle(guarded.left,sizeof(guarded.h)));
#endif
  USBD_SetupReqTypedef r={0xa1,0xfe,0,1,1};CHECK(USBD_MSC.Setup(&dev,&r)==USBD_FAIL);
  dev.classId=1;CHECK(USBD_MSC.Init(&dev,0)==USBD_FAIL && USBD_MSC.DataIn(&dev,1)==USBD_FAIL);dev.classId=0;
  CHECK(!wire_error);return 0;
}
int test_msc_sense(void) {
  BEGIN();
  for(unsigned i=1;i<=10;i++)SCSI_SenseCode(&dev,i,0x50+i);
  for(unsigned i=8;i<=11;i++) {
    cbw(3,0x80,18);h->cbw.CB[4]=18;submit();
    CHECK(tx_length==18 && tx[2]==(i<=10?i:0) && tx[12]==(i<=10?0x50+i:0) && tx[13]==0);
    ack();CSW(0,0);
  }
  USBD_ClassTypeDef dummy={0};dev.pClass[0]=&dummy;
  CHECK(SCSI_ContinueRead(&dev)<0 && SCSI_ContinueWrite(&dev)<0 && SCSI_CompleteSync(&dev,1)<0);
  SCSI_SenseCode(&dev,1,1);CHECK(!wire_error);
  dev.pClass[0]=(USBD_ClassTypeDef*)&USBD_MSC;
  CHECK(SCSI_ContinueRead(NULL)<0 && SCSI_ContinueWrite(NULL)<0 && SCSI_CompleteSync(NULL,1)<0);
  return 0;
}
static uint32_t random_state=0x91827364;
static uint32_t random32(void) {random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
int test_msc_random(void) {
  static const uint8_t ops[]={0,3,0x12,0x1a,0x1b,0x1e,0x23,0x25,0x28,0x2a,0x2f,0x35,0x5a,0x91,0x9e,0xa8,0xaa,0xff};
  for(unsigned round=0;round<4000;round++) {
    BEGIN();cbw(ops[random32()%sizeof(ops)],random32()&0x80,random32()%65537);
    for(unsigned i=1;i<16;i++)h->cbw.CB[i]=random32();
    h->cbw.bCBLength=1+random32()%16;submit();
    CHECK(!wire_error && tx_length<=MSC_MEDIA_PACKET && rx_length<=MSC_MEDIA_PACKET && !writes);
    for(unsigned i=0;i<8;i++)CHECK(guarded.left[i]==0xa5a5a5a5 && guarded.right[i]==0xa5a5a5a5);
  }
  return 0;
}
#endif
