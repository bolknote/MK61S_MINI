#![no_std]

#[path = "../../../sdk/portable/rust/mk61_app.rs"]
mod mk61;

use core::panic::PanicInfo;

#[no_mangle]
pub extern "C" fn main() -> i32 {
    let needs = mk61::CAP_TEXT_DISPLAY | mk61::CAP_KEYBOARD;
    if !mk61::api_compatible(needs)
        || !mk61::display_clear()
        || !mk61::display_write_m8(0, 0, b"HELLO, MK61S!")
    {
        return mk61::APP_RUNTIME_ERROR;
    }
    let _ = mk61::key_wait();
    mk61::APP_OK
}

#[panic_handler]
fn panic(_: &PanicInfo) -> ! {
    loop {}
}
