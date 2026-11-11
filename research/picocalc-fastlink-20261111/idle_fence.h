#ifndef FL_IDLE_FENCE_H
#define FL_IDLE_FENCE_H
typedef struct {
 uint32_t waited,samples,mask,tx,rx,status,pins,raw,enable,enabled,stable;
} fl_idle_snapshot;
/* Only core0 submits keyboard I2C. Do not call an APP service while waiting.
 * Observe the real FIFO/controller/line state; require six idle observations
 * spanning >=500us. No MMIO writes or pin/peripheral acquisition here. */
static __attribute__((noinline,noclone,noipa)) int fl_i2c_idle_fence(fl_idle_snapshot *s) {
 const uint32_t start=R(0x40054028u);
 uint32_t last=start-100u,idle_since=0;
 s->samples=s->stable=0;
 for(;;) {
  const uint32_t now=R(0x40054028u);s->waited=now-start;
  if(s->waited>=20000u)return 0;
  if(now-last<100u)continue;
  last=now;++s->samples;
  s->mask=R(I2C+FL_REG_I2C_IC_INTR_MASK);s->tx=R(I2C+FL_REG_I2C_IC_TXFLR);
  s->rx=R(I2C+FL_REG_I2C_IC_RXFLR);s->status=R(I2C+FL_REG_I2C_IC_STATUS);
  s->pins=R(0xd0000004u)&0xc0u;s->raw=R(I2C+FL_REG_I2C_IC_RAW_INTR_STAT);
  s->enable=R(I2C+FL_REG_I2C_IC_ENABLE);s->enabled=R(I2C+FL_REG_I2C_IC_ENABLE_STATUS);
  if(!s->mask&&!s->tx&&!s->rx&&!(s->status&0x21u)&&s->pins==0xc0u&&
     (s->enable&1u)==(s->enabled&1u)) {
   if(!s->stable)idle_since=now;
   ++s->stable;
   if(s->stable>=6u&&now-idle_since>=500u)return 1;
  } else s->stable=0;
 }
}
#endif
