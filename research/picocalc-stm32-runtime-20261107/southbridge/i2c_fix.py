"""Minimal source delta against the pinned Southbridge; no device access."""
def once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new, 1)

def patch_callbacks(text):
    text=once(text,'#include "i2cs.h"','#include "i2cs.h"\n#include "i2cs_recovery.h"')
    text=once(text,'enum i2cs_state i2cs_state = I2CS_STATE_IDLE;',
              'volatile enum i2cs_state i2cs_state = I2CS_STATE_IDLE;\nvolatile uint8_t i2cs_recover_required;\nstatic volatile uint8_t i2cs_selection_ready;')
    text=once(text,'uint32_t i2cs_rearm_counter = 0;',
              'volatile uint32_t i2cs_rearm_counter = 0;')
    text=once(text,'\t\t\tif (i2cs_state == I2CS_STATE_IDLE) {',
              '\t\t\t/* A new write address replaces an incomplete selection. */\n\t\t\t{\n\t\t\t\ti2cs_selection_ready = 0;')
    text=once(text,'if (i2cs_state == I2CS_STATE_REG_REQUEST || i2cs_state == I2CS_STATE_REG_RECEIVE)',
              'if (i2cs_state == I2CS_STATE_REG_RECEIVE && i2cs_selection_ready)')
    text=once(text,'reg == REG_ID_INT_CFG ||',
              'reg == REG_ID_INT_CFG ||\n\t\t\t\t\treg == REG_ID_RTC_CFG ||')
    text=once(text,'\t\t\t\tHAL_I2C_Slave_Seq_Receive_IT(hi2c, i2cs_r_buff + 1, bytes_needed, I2C_NEXT_FRAME);\n\t\t\t}\n\t\t}',
              '\t\t\t\tif (bytes_needed)\n\t\t\t\t\tHAL_I2C_Slave_Seq_Receive_IT(hi2c, i2cs_r_buff + 1, bytes_needed, I2C_NEXT_FRAME);\n\t\t\t} else {\n\t\t\t\ti2cs_selection_ready = 1;\n\t\t\t}\n\t\t} else if (i2cs_state == I2CS_STATE_REG_RECEIVE) {\n\t\t\t/* The complete payload, rather than an old buffer, is valid. */\n\t\t\ti2cs_selection_ready = 1;\n\t\t}')
    tail='\t\t\t\ti2cs_rearm_counter = uptime_ms();\n\t\t\t}\n\t\t}\n\t}\n}'
    fallback='''\t\t\t\ti2cs_rearm_counter = uptime_ms();
\t\t\t} else {
\t\t\t\t/* No complete selection (including after the 1s rearm). Reply with
\t\t\t\t * an empty key event; never pop FIFO or replay a stale write. */
\t\t\t\ti2cs_w_buff[0] = i2cs_w_buff[1] = 0;
\t\t\t\ti2cs_w_len = 2;
\t\t\t\ti2cs_w_idx = 0;
\t\t\t\ti2cs_state = I2CS_STATE_REG_ANSWER;
\t\t\t\tHAL_I2C_Slave_Seq_Transmit_IT(hi2c, i2cs_w_buff, 2, I2C_LAST_FRAME);
\t\t\t\ti2cs_rearm_counter = uptime_ms();
\t\t\t}
\t\t}
\t}
}'''
    text=once(text,tail,fallback)
    return text.replace('HAL_I2C_Slave_Seq_Receive_IT(', 'i2cs_receive(').replace(
                        'HAL_I2C_Slave_Seq_Transmit_IT(', 'i2cs_transmit(')

def patch_header(text):
    text=once(text,'extern enum i2cs_state i2cs_state;',
              'extern volatile enum i2cs_state i2cs_state;')
    return once(text,'extern uint32_t i2cs_rearm_counter;',
                'extern volatile uint32_t i2cs_rearm_counter;')

def patch_main(text):
    # Include the deferred flag; recovery must clear FSM before re-enabling
    # IRQs, otherwise a newly received address could be erased after reset.
    text=once(text,'#include "i2cs.h"','#include "i2cs.h"\n#include "i2cs_recovery.h"')
    text=once(text,'if ((i2cs_state != I2CS_STATE_IDLE &&',
                   'if (i2cs_recover_required || (i2cs_state != I2CS_STATE_IDLE &&')
    return once(text,'\t\t\tHAL_Interface_I2C1_reset();\n\t\t\ti2cs_state = I2CS_STATE_IDLE;',
                     '\t\t\ti2cs_recover_required = 0;\n\t\t\ti2cs_state = I2CS_STATE_IDLE;\n\t\t\tHAL_Interface_I2C1_reset();')
