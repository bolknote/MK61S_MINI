#pragma once
inline constexpr int uart1=1;
bool uart_is_readable(int);
void uart_set_irq_enables(int,bool,bool);
