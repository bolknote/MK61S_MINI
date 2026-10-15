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
static unsigned init_calls, deinit_calls, address_calls, clear_calls, event_clock, setup_event, tx_event;
static uint8_t init_failure, setup_failure, in_halts, out_halts;
static uint8_t config[67] = {9, 2, 67, 0, 2, 1};
static uint8_t* configuration(uint16_t* length) { *length=sizeof(config); return config; }
static uint8_t init(USBD_HandleTypeDef* d, uint8_t n) {
  (void)n; ++init_calls; in_halts=out_halts=0; d->ep_in[1].is_used=d->ep_out[1].is_used=1;
  d->ep_in[1].maxpacket=d->ep_out[1].maxpacket=64; return init_failure ? USBD_FAIL : USBD_OK;
}
static uint8_t deinit(USBD_HandleTypeDef* d, uint8_t n) {
  (void)n; ++deinit_calls; d->ep_in[1].is_used=d->ep_out[1].is_used=0; return USBD_OK;
}
static uint8_t setup(USBD_HandleTypeDef* d, USBD_SetupReqTypedef* r) {
  (void)d; (void)r; ++setup_calls; setup_event=++event_clock; return setup_failure ? USBD_FAIL : USBD_OK;
}
static uint8_t received(USBD_HandleTypeDef* d) { (void)d; ++rx_ready; return 0; }
static uint8_t sent(USBD_HandleTypeDef* d) { (void)d; ++tx_ready; return 0; }
static uint8_t data_in(USBD_HandleTypeDef* d, uint8_t ep) { (void)d; (void)ep; ++in_calls; return 0; }
static uint8_t data_out(USBD_HandleTypeDef* d, uint8_t ep) { (void)d; (void)ep; ++out_calls; return 0; }
static USBD_ClassTypeDef cls={.Init=init,.DeInit=deinit,.Setup=setup,
  .EP0_TxSent=sent,.EP0_RxReady=received,.DataIn=data_in,.DataOut=data_out,
  .GetFSConfigDescriptor=configuration};
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef* d) { (void)d; return 0; }
USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef* d) { (void)d; return 0; }
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef* d) { (void)d; return 0; }
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef* d) { (void)d; return 0; }
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef* d,uint8_t ep,uint8_t type,uint16_t size) {
  (void)d;(void)ep;(void)type;(void)size;return 0;
}
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef* d,uint8_t ep) {
  (void)d;++stalls;if(ep&0x80)in_halts|=1U<<(ep&15);else out_halts|=1U<<(ep&15);return 0;
}
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef* d,uint8_t ep) {
  (void)d;++clear_calls;if(ep&0x80)in_halts&=~(1U<<(ep&15));else out_halts&=~(1U<<(ep&15));return 0;
}
uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef* d,uint8_t ep) { (void)d;return ((ep&0x80?in_halts:out_halts)>>(ep&15))&1U; }
USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef* d,uint8_t value) { (void)d;++address_calls;address=value;return 0; }
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef* d,uint8_t ep,uint8_t* b,uint32_t size) {
  (void)d;(void)ep;tx_event=++event_clock;tx_data=b;tx_size=size;++tx_count;return 0;
}
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef* d,uint8_t ep,uint8_t* b,uint32_t size) {
  (void)d;(void)ep;rx_data=b;rx_size=size;++rx_count;return 0;
}
static USBD_StatusTypeDef request(uint8_t bm,uint8_t req,uint16_t value,uint16_t index,uint16_t length) {
  uint8_t raw[]={bm,req,value,value>>8,index,index>>8,length,length>>8};
  return USBD_LL_SetupStage(&dev,raw);
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
int test_compact_state_boundaries(void) {
#if MK61_USB_COMPACT_STATE
  struct {
    uint8_t left[8];
    USBD_HandleTypeDef device;
    uint8_t right[8];
  } guarded;
  memset(&guarded,0xA5,sizeof(guarded));
  USBD_HandleTypeDef *d=&guarded.device;
  CHECK(USBD_Init(d,(USBD_DescriptorsTypeDef*)&mk61_usb_descriptors,0)==USBD_OK);
  CHECK(USBD_RegisterClass(d,&cls)==USBD_OK && USBD_LL_Reset(d)==USBD_OK);
  /* Independent persistent counters must retain more than 16 bits. */
  CHECK(USBD_CtlSendData(d,config,0x10040U)==USBD_OK);
  CHECK(d->control_in.total_length==0x10040U && d->control_in.rem_length==0x10040U);
  CHECK(USBD_CtlPrepareRx(d,config,0x20080U)==USBD_OK);
  CHECK(d->control_out.total_length==0x20080U && d->control_out.rem_length==0x20080U);
  CHECK(d->control_in.total_length==0x10040U && d->control_in.rem_length==0x10040U);
  MK61_USBD_SetClassData(d,config);CHECK(d->pClassDataCmsit[0]==config && MK61_USBD_ClassData(d)==config);
  MK61_USBD_SetClassData(d,NULL);CHECK(d->pClassDataCmsit[0]==NULL && MK61_USBD_ClassData(d)==NULL);
  d->dev_config=1;d->dev_state=USBD_STATE_CONFIGURED;
  USBD_SetupReqTypedef r={0x80,USB_REQ_GET_STATUS,0,0,2};
  CHECK(USBD_StdDevReq(d,&r)==USBD_OK && tx_size==2);
  CHECK(tx_data==(uint8_t*)&d->dev_config_status && tx_data[0]==1 && tx_data[1]==0);
  CHECK(d->dev_config==1 && d->dev_speed==USBD_SPEED_FULL && d->dev_state==USBD_STATE_CONFIGURED);
  d->ep_in[1].status=0xFFFF;d->ep_in[1].maxpacket=64;d->ep_in[1].is_used=1;
  r.bmRequest=0x82;r.wIndex=0x81;
  CHECK(USBD_StdEPReq(d,&r)==USBD_OK && tx_size==2);
  CHECK(tx_data==(uint8_t*)&d->ep_in[1].status && tx_data[0]==0 && tx_data[1]==0);
  CHECK(d->ep_in[1].maxpacket==64 && d->ep_in[1].is_used==1);
  for(unsigned i=0;i<8;i++) CHECK(guarded.left[i]==0xA5 && guarded.right[i]==0xA5);
#endif
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

/* Wire-level expectations from USB 2.0 chapter 9, not a second dispatcher.
 * Rejected requests cannot ACK a write or change the selected configuration.
 */
static int configured(void) {
  CHECK(USBD_Init(&dev,(USBD_DescriptorsTypeDef*)&mk61_usb_descriptors,0)==USBD_OK);
  CHECK(USBD_RegisterClass(&dev,&cls)==USBD_OK);
  CHECK(USBD_LL_Reset(&dev)==USBD_OK);
  CHECK(request(0,USB_REQ_SET_ADDRESS,7,0,0)==USBD_OK);
  CHECK(request(0,USB_REQ_SET_CONFIGURATION,1,0,0)==USBD_OK);
  return 0;
}
int test_ep0_requests(void) {
  CHECK(configured()==0);
  static const struct {uint8_t bm,request;uint16_t value,index,length;} bad[]={
    {0x80,5,8,0,0},{0,5,128,0,0},{0,5,8,1,0},{0,5,8,0,1},
    {0x80,9,0,0,0},{0,9,2,0,0},{0,9,0x101,0,0},{0,9,0,1,0},{0,9,0,0,1},
    {0,8,0,0,1},{0x80,8,1,0,1},{0x80,8,0,1,1},{0x80,8,0,0,2},
    {0,0,0,0,2},{0x80,0,1,0,2},{0x80,0,0,1,2},{0x80,0,0,0,1},
    {0x40,0,0,0,0},{0x20,0,0,0,0},{0xC0,0,0,0,2},{0x60,0,0,0,0},
    {0,3,1,0,0},{0,1,1,0,0},{0,3,2,0x100,0}, /* unadvertised RW, HS test */
    {0x80,6,0x101,0,18},{0x80,6,0x100,1,18},{0x80,6,0x201,0,9},
    {0x80,6,0x200,1,9},{0x80,6,0x306,0x409,64},{0x80,6,0x600,0,10},
    {0x80,6,0x700,0,9},{0x80,6,0xF00,0,5},{0,6,0x100,0,18},
    {0x81,0,0,2,2},{0x81,0,0,0x100,2},{0xC1,0,0,0,2},
    {0x82,0,0,0x82,2},{0x82,0,0,0x101,2},{0x82,0,1,0x81,2},
    {0x82,0,0,0x81,1},{0x02,3,1,0x81,0},{0x02,1,0,0x81,1},
    {0x02,3,0,0,0},{0x02,1,0,0x80,0},{0xA2,0,0,0x81,2},
    {0xC2,0,0,0x81,2},{0x02,3,0,0x82,0},{0x02,1,0,0x82,0}
  };
  for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++) {
    unsigned a=address_calls,t=tx_count,c=clear_calls,setup_before=setup_calls,stalls_before=stalls;
    CHECK(request(bad[i].bm,bad[i].request,bad[i].value,bad[i].index,bad[i].length)==USBD_FAIL);
    CHECK(stalls>stalls_before && tx_count==t && address_calls==a && clear_calls==c);
    CHECK(setup_calls==setup_before && dev.dev_state==USBD_STATE_CONFIGURED && dev.dev_config==1);
  }
  request(0x80,0,0,0,2);CHECK(tx_size==2 && tx_data[0]==1 && tx_data[1]==0);
  request(0x80,8,0,0,1);CHECK(tx_size==1 && tx_data[0]==1);
  unsigned t=tx_count,s=setup_calls;
  CHECK(request(0x21,0x22,3,0,0)==USBD_OK && setup_calls==s+1 && tx_count==t+1 && tx_size==0);
  setup_failure=1;t=tx_count;s=stalls;
  CHECK(request(0x21,0x22,0,0,0)==USBD_FAIL && tx_count==t && stalls>s);
  setup_failure=0;
  CHECK(request(0,9,0,0,0)==USBD_OK && dev.dev_state==USBD_STATE_ADDRESSED && dev.dev_config==0);
  s=setup_calls;t=tx_count;CHECK(request(0x21,0x22,0,0,0)==USBD_FAIL && setup_calls==s && tx_count==t);
  request(0x80,8,0,0,1);CHECK(tx_size==1 && tx_data[0]==0);
  request(0x82,0,0,0,2);CHECK(tx_size==2 && tx_data[0]==0 && tx_data[1]==0);
  s=stalls;CHECK(request(0x82,0,0,0x81,2)==USBD_FAIL && stalls>s);
  CHECK(request(0,5,0,0,0)==USBD_OK && dev.dev_state==USBD_STATE_DEFAULT);
  CHECK(request(0,9,1,0,0)==USBD_FAIL && dev.dev_state==USBD_STATE_DEFAULT);
  return 0;
}
int test_ep0_configuration_failure(void) {
  CHECK(configured()==0);CHECK(init_calls==1);
  in_halts=2;out_halts=2;
  CHECK(request(0,9,1,0,0)==USBD_OK && init_calls==2 && deinit_calls>=1);
  CHECK(in_halts==0 && out_halts==0 && dev.dev_state==USBD_STATE_CONFIGURED);
  CHECK(request(0,9,0,0,0)==USBD_OK && dev.dev_config==0 && !dev.ep_in[1].is_used);
  unsigned t=tx_count,deinits=deinit_calls;
  init_failure=1;
  CHECK(request(0,9,1,0,0)==USBD_FAIL && tx_count==t && deinit_calls==deinits+1);
  CHECK(dev.dev_config==0 && dev.dev_state==USBD_STATE_ADDRESSED && !dev.ep_in[1].is_used && !dev.ep_out[1].is_used);
  init_failure=0;
  CHECK(request(0,9,1,0,0)==USBD_OK && dev.dev_state==USBD_STATE_CONFIGURED);
  return 0;
}
int test_ep0_halt_recovery(void) {
  CHECK(configured()==0);
  for(unsigned mode=1;mode<=2;mode++) {
    config[4]=mode;
    for(unsigned dir=0;dir<=0x80;dir+=0x80) {
      uint16_t ep=dir|1;unsigned before=setup_calls,t=tx_count;
      CHECK(request(2,3,0,ep,0)==USBD_OK && tx_count==t+1 && tx_size==0);
      CHECK(request(0x82,0,0,ep,2)==USBD_OK && tx_size==2 && tx_data[0]==1 && tx_data[1]==0);
      CHECK(request(2,1,0,ep,0)==USBD_OK && tx_size==0);
      CHECK(setup_calls==before+(mode==1) && (mode!=1 || setup_event<tx_event));
      CHECK(request(0x82,0,0,ep,2)==USBD_OK && tx_data[0]==0);
    }
  }
  config[4]=1;setup_failure=1;unsigned t=tx_count;
  CHECK(request(2,1,0,0x81,0)==USBD_FAIL && tx_count==t);
  return 0;
}
int test_ep0_descriptor_lengths(void) {
  CHECK(configured()==0);
  static const uint16_t lengths[]={0,1,2,8,9,18,63,64,65,67,255,65535};
  for(unsigned i=0;i<sizeof(lengths)/sizeof(*lengths);i++) {
    uint16_t len=lengths[i];
    CHECK(request(0x80,6,0x200,0,len)==USBD_OK && tx_size==(len<67?len:67));
    CHECK(config[0]==9 && config[1]==2 && config[2]==67 && config[3]==0);
    CHECK(request(0x80,6,0x100,0,len)==USBD_OK && tx_size==(len<18?len:18));
    for(unsigned string=0;string<=5;string++) {
      CHECK(request(0x80,6,0x300|string,string?0x409:0,len)==USBD_OK);
      CHECK(tx_size<=len && tx_size<=64);
      if(tx_size) CHECK(tx_data[1]==3);
    }
  }
  USBD_DescriptorsTypeDef missing=mk61_usb_descriptors;missing.GetProductStrDescriptor=NULL;dev.pDesc=&missing;
  unsigned t=tx_count;CHECK(request(0x80,6,0x302,0x409,64)==USBD_FAIL && tx_count==t);
  return 0;
}
int test_ep0_indices(void) {
  CHECK(configured()==0);
  // Every invalid endpoint wIndex: neither array indexing nor a HALT mutation.
  for(uint32_t index=0;index<=65535;index++) {
    if(index==0 || index==0x80 || index==1 || index==0x81) continue;
    unsigned before=tx_count,c=clear_calls,s=setup_calls;
    CHECK(request(0x82,0,0,index,2)==USBD_FAIL);
    CHECK(tx_count==before && clear_calls==c && setup_calls==s);
  }
  for(uint32_t index=2;index<=65535;index++) {
    unsigned before=setup_calls,t=tx_count;
    CHECK(request(0x21,0x22,0,index,0)==USBD_FAIL && setup_calls==before && tx_count==t);
  }
  return 0;
}
