/* Execute the production EP0 engine with an independent fake transport. */
#include <usbd_core.h>
#include <usbd_ctlreq.h>
#include <usbd_ioreq.h>
#include <cdc_queue.h>
#include "stm32f4_usbd_desc.h"
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
static USBD_HandleTypeDef dev;
static uint32_t tx_size, rx_size, tx_count, rx_count, stalls, address;
static uint8_t *tx_data, *rx_data;
static unsigned setup_calls, rx_ready, tx_ready, in_calls, out_calls;
static uint8_t config[67] = {9, 2, 67, 0, 2, 1};
static uint8_t* configuration(uint16_t* length) { *length=sizeof(config); return config; }
static uint8_t init(USBD_HandleTypeDef* d, uint8_t n) {
  (void)n; d->ep_in[1].is_used=d->ep_out[1].is_used=1;
  d->ep_in[1].maxpacket=d->ep_out[1].maxpacket=64; return USBD_OK;
}
static uint8_t deinit(USBD_HandleTypeDef* d, uint8_t n) {
  (void)n; d->ep_in[1].is_used=d->ep_out[1].is_used=0; return USBD_OK;
}
static uint8_t setup(USBD_HandleTypeDef* d, USBD_SetupReqTypedef* r) {
  (void)d; (void)r; ++setup_calls; return USBD_OK;
}
static uint8_t received(USBD_HandleTypeDef* d) { (void)d; ++rx_ready; return 0; }
static uint8_t sent(USBD_HandleTypeDef* d) { (void)d; ++tx_ready; return 0; }
static uint8_t data_in(USBD_HandleTypeDef* d, uint8_t ep) { (void)d; (void)ep; ++in_calls; return 0; }
static uint8_t data_out(USBD_HandleTypeDef* d, uint8_t ep) { (void)d; (void)ep; ++out_calls; return 0; }
static USBD_ClassTypeDef cls={init,deinit,setup,sent,received,data_in,data_out,
                            0,0,0,0,configuration,0,0};
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef* d) { (void)d; return 0; }
USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef* d) { (void)d; return 0; }
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef* d) { (void)d; return 0; }
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef* d) { (void)d; return 0; }
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef* d,uint8_t ep,uint8_t type,uint16_t size) {
  (void)d;(void)ep;(void)type;(void)size;return 0;
}
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef* d,uint8_t ep) { (void)d;(void)ep;++stalls;return 0; }
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef* d,uint8_t ep) { (void)d;(void)ep;return 0; }
uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef* d,uint8_t ep) { (void)d;(void)ep;return 0; }
USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef* d,uint8_t value) { (void)d;address=value;return 0; }
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef* d,uint8_t ep,uint8_t* b,uint32_t size) {
  (void)d;(void)ep;tx_data=b;tx_size=size;++tx_count;return 0;
}
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef* d,uint8_t ep,uint8_t* b,uint32_t size) {
  (void)d;(void)ep;rx_data=b;rx_size=size;++rx_count;return 0;
}
static void request(uint8_t bm,uint8_t req,uint16_t value,uint16_t index,uint16_t length) {
  uint8_t raw[]={bm,req,value,value>>8,index,index>>8,length,length>>8};
  USBD_LL_SetupStage(&dev,raw);
}
int test_control(void) {
  CHECK(USBD_Init(&dev,(USBD_DescriptorsTypeDef*)&mk61_usb_descriptors,0)==0);
  CHECK(USBD_RegisterClass(&dev,&cls)==0); CHECK(USBD_LL_Reset(&dev)==0);
  CHECK(dev.dev_state==USBD_STATE_DEFAULT && dev.ep_in[0].maxpacket==64);
  request(0x80,6,0x100,0,18);CHECK(tx_size==18 && tx_data[0]==18 && tx_data[4]==2);
  request(0,5,7,0,0);CHECK(address==7 && dev.dev_state==USBD_STATE_ADDRESSED);
  request(0,9,1,0,0);CHECK(dev.dev_state==USBD_STATE_CONFIGURED);
  for(unsigned i=0;i<2;i++) { unsigned before=setup_calls;
    request(0x21,0x22,0,i,0);CHECK(setup_calls==before+1);
  }
  unsigned before=setup_calls;request(0x21,0x22,0,2,0);CHECK(setup_calls==before);
  config[4]=1;request(0x21,0x22,0,1,0);CHECK(setup_calls==before);config[4]=2;
  const uint16_t bad[]={4,15,0x84,0x8f,0x100,0x70,0xffff};
  for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++) {
    unsigned previous=stalls;request(0x82,0,0,bad[i],2);CHECK(stalls>previous);
  }
  CHECK(USBD_CoreFindEP(&dev,0x81)==0 && USBD_CoreFindEP(&dev,0x82)==255);
  request(0x80,6,0x200,0,200);CHECK(tx_size==67);
  CHECK(USBD_LL_DataInStage(&dev,0,config+64)==0 && tx_size==3 && tx_data==config+64);
  CHECK(USBD_LL_DataInStage(&dev,0,config+67)==0 && dev.ep0_state==USBD_EP0_STATUS_OUT);
  dev.ep0_data_len=200;USBD_CtlSendData(&dev,config,64);before=tx_count;
  USBD_LL_DataInStage(&dev,0,config+64);CHECK(tx_count==before+1 && tx_size==0);
  USBD_LL_DataInStage(&dev,0,config+64);CHECK(dev.ep0_state==USBD_EP0_STATUS_OUT);
  static uint8_t data[130];before=rx_ready;USBD_CtlPrepareRx(&dev,data,130);
  CHECK(rx_size==130);USBD_LL_DataOutStage(&dev,0,data+64);CHECK(rx_size==64 && rx_data==data+64);
  USBD_LL_DataOutStage(&dev,0,data+128);CHECK(rx_size==2 && rx_data==data+128 && rx_ready==before);
  USBD_LL_DataOutStage(&dev,0,data+130);CHECK(rx_ready==before+1 && tx_size==0 && dev.ep0_state==USBD_EP0_STATUS_IN);
  USBD_LL_DataInStage(&dev,1,0);USBD_LL_DataOutStage(&dev,1,0);CHECK(in_calls==1 && out_calls==1);
  CHECK(USBD_LL_DataInStage(&dev,4,0)==USBD_FAIL && USBD_LL_DataOutStage(&dev,255,0)==USBD_FAIL);
  USBD_LL_Suspend(&dev);USBD_LL_Suspend(&dev);CHECK(dev.dev_state==USBD_STATE_SUSPENDED);
  USBD_LL_DataInStage(&dev,1,0);CHECK(in_calls==1);
  USBD_LL_Resume(&dev);CHECK(dev.dev_state==USBD_STATE_CONFIGURED);
  dev.dev_remote_wakeup=dev.dev_test_mode=1;USBD_LL_Reset(&dev);
  CHECK(!dev.dev_config && !dev.dev_remote_wakeup && !dev.dev_test_mode);
  CHECK(dev.dev_state==USBD_STATE_DEFAULT && !dev.ep_in[1].is_used);
  USBD_Stop(&dev);USBD_DeInit(&dev);CHECK(dev.pDesc==0 && dev.pConfDesc==0);
  return 0;
}
int test_descriptors(void) {
  uint16_t length;uint8_t* b;
  const USBD_DescriptorsTypeDef* d=&mk61_usb_descriptors;
  b=d->GetLangIDStrDescriptor(USBD_SPEED_FULL,&length);CHECK(length==4 && b[2]==9 && b[3]==4);
  b=d->GetSerialStrDescriptor(USBD_SPEED_FULL,&length);CHECK(length==26);
  const char* expected="2068336B4731";
  for(unsigned i=0;i<12;i++) CHECK(b[2+2*i]==expected[i] && b[3+2*i]==0);
  b=d->GetProductStrDescriptor(USBD_SPEED_FULL,&length);CHECK(length<=64 && b[0]==length);
  b=d->GetManufacturerStrDescriptor(USBD_SPEED_FULL,&length);CHECK(length==38 && b[2]=='S');
  b=d->GetConfigurationStrDescriptor(USBD_SPEED_FULL,&length);CHECK(length<=64);
  b=d->GetInterfaceStrDescriptor(USBD_SPEED_FULL,&length);CHECK(length<=64);
  struct {uint8_t left[8],out[64],right[8];} guard;
  static uint8_t text[400];memset(&guard,0xa5,sizeof(guard));memset(text,'x',399);
  USBD_GetString(text,guard.out,&length);CHECK(length==64 && guard.out[0]==64);
  for(unsigned i=0;i<8;i++) CHECK(guard.left[i]==0xa5 && guard.right[i]==0xa5);
  for(unsigned i=2;i<64;i+=2) CHECK(guard.out[i]=='x' && !guard.out[i+1]);
  text[0]=0;USBD_GetString(text,guard.out,&length);CHECK(length==2);
  return 0;
}
static uint32_t rng=0x315a98e7;
static uint32_t random32(void) {rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
int test_queues(void) {
  CDC_TransmitQueue_TypeDef tx;CDC_ReceiveQueue_TypeDef rx;
  CDC_TransmitQueue_Init(&tx);CDC_ReceiveQueue_Init(&rx);
  unsigned produced=0,consumed=0;uint8_t input[128];
  for(unsigned round=0;round<20000;round++) {
    unsigned size=random32()%128;unsigned available=CDC_TransmitQueue_WriteSize(&tx);
    if(size>available)size=available;
    for(unsigned i=0;i<size;i++)input[i]=(uint8_t)(produced+i);
    CDC_TransmitQueue_Enqueue(&tx,input,size);produced+=size;
    CHECK(CDC_TransmitQueue_ReadSize(&tx)==(int)(produced-consumed));
    if(random32()&1) {
      uint16_t count;uint8_t* b=CDC_TransmitQueue_ReadBlock(&tx,&count);
      CHECK(count<=produced-consumed && b>=tx.buffer && b+count<=tx.buffer+128);
      for(unsigned i=0;i<count;i++) CHECK(b[i]==(uint8_t)(consumed+i));
      consumed+=count;CDC_TransmitQueue_CommitRead(&tx);
    }
  }
  produced=consumed=0;
  for(unsigned round=0;round<30000;round++) {
    uint8_t* b=CDC_ReceiveQueue_ReserveBlock(&rx);
    if(b) {
      unsigned size=random32()%65;CHECK(b>=rx.buffer && b+64<=rx.buffer+192);
      for(unsigned i=0;i<size;i++)b[i]=(uint8_t)(produced+i);
      CDC_ReceiveQueue_CommitBlock(&rx,size);produced+=size;
    }
    CHECK(CDC_ReceiveQueue_ReadSize(&rx)==(int)(produced-consumed));
    unsigned read=random32()%90;
    if(random32()&1) {
      while(read-- && consumed<produced) {
        CHECK(CDC_ReceiveQueue_Peek(&rx)==(uint8_t)consumed);
        CHECK(CDC_ReceiveQueue_Dequeue(&rx)==(uint8_t)consumed);++consumed;
      }
    } else if(random32()&1) {
      unsigned n=CDC_ReceiveQueue_Read(&rx,input,read);CHECK(n<=read && n<=produced-consumed);
      for(unsigned i=0;i<n;i++) { CHECK(input[i]==(uint8_t)(consumed+i)); }
      consumed+=n;
    } else {
      uint16_t fetched;uint8_t terminator=(uint8_t)(consumed+13);
      bool found=CDC_ReceiveQueue_ReadUntil(&rx,terminator,input,read,&fetched);
      CHECK(fetched<=read && (unsigned)fetched+found<=produced-consumed);
      for(unsigned i=0;i<fetched;i++)CHECK(input[i]==(uint8_t)(consumed+i));
      if(found)CHECK((uint8_t)(consumed+fetched)==terminator);
      consumed+=fetched+found;
    }
    CHECK(produced-consumed<192);
    if(produced==consumed) CHECK(CDC_ReceiveQueue_Dequeue(&rx)==-1);
  }
  return 0;
}
