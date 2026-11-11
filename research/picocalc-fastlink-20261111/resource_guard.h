#ifndef FL_RESOURCE_GUARD_H
#define FL_RESOURCE_GUARD_H
/* native_pins.h supplies register offsets extracted from the pinned RP2040
 * SDK hardware/regs/pio.h. Raw INTR includes ordinary TXNFULL and is not an
 * ownership indication; check the four enable/force registers instead. */
static __attribute__((noinline,noclone,noipa)) int fl_pio_resources_free(unsigned sm) {
 if(sm>=4)return 0;
 const uint32_t mask=(1u<<sm)|(1u<<(4+sm))|(1u<<(8+sm));
 const uint32_t enabled=R(PIO+FL_REG_PIO_IRQ0_INTE)|R(PIO+FL_REG_PIO_IRQ0_INTF)|
                        R(PIO+FL_REG_PIO_IRQ1_INTE)|R(PIO+FL_REG_PIO_IRQ1_INTF);
 return !(R(PIO)&(1u<<sm))&&!(enabled&mask);
}
#endif
