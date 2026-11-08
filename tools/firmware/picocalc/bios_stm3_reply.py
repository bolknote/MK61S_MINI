"""Start a completed STM3 reply before returning to the BIOS foreground loop."""
from pathlib import Path


def stage_stm3_reply(source):
    path = Path(source) / "Core/Src/coproc_hal.c"
    text = path.read_text()
    old = " if(!completed_request)stm3_tick(&coproc);\n}"
    new = """ if(!completed_request)stm3_tick(&coproc);
 // Feed/STEP may have completed a reply in this turn. Start its DMA now,
 // before keyboard/RTC/PMU foreground work, without another module call.
 if(coproc.tx_at<coproc.tx_bytes && stm3_uart_tx_idle()){
  if(stm3_uart_tx_start(coproc.tx+coproc.tx_at,coproc.tx_bytes-coproc.tx_at))coproc.tx_at=coproc.tx_bytes;
 }
}"""
    if text.count(old) != 1:
        raise ValueError("STM3 immediate-reply source anchor changed")
    path.write_text(text.replace(old, new, 1))
    return {"immediate_reply_dma": True}
