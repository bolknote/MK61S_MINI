use core::mem::size_of;

pub const API_MAGIC: u32 = 0x3150_5041;
pub const API_VERSION: u16 = 1;
pub const CAP_TEXT_DISPLAY: u32 = 1 << 1;
pub const CAP_KEYBOARD: u32 = 1 << 2;
pub const APP_OK: i32 = 0;
pub const APP_RUNTIME_ERROR: i32 = 5;

type Clear = unsafe extern "C" fn() -> u32;
type Write = unsafe extern "C" fn(u32, u32, *const u8, u32) -> u32;
type Wait = unsafe extern "C" fn() -> i32;

#[repr(C)]
struct AppApi {
    magic: u32,
    version: u16,
    struct_size: u16,
    capabilities: u32,
    _before_display: [usize; 5],
    display_clear: Option<Clear>,
    display_write_utf8: Option<Write>,
    _key_poll: usize,
    key_wait: Option<Wait>,
}

unsafe extern "C" {
    static mk61_api: *const AppApi;
}

fn api() -> Option<&'static AppApi> {
    unsafe { mk61_api.as_ref() }
}

pub fn api_compatible(required_capabilities: u32) -> bool {
    let Some(api) = api() else { return false };
    api.magic == API_MAGIC
        && api.version == API_VERSION
        && api.struct_size >= size_of::<AppApi>() as u16
        && api.capabilities & required_capabilities == required_capabilities
}

pub fn display_clear() -> bool {
    let Some(callback) = api().and_then(|value| value.display_clear) else {
        return false;
    };
    unsafe { callback() != 0 }
}

pub fn display_write_utf8(column: u32, row: u32, text: &[u8]) -> bool {
    let Some(callback) = api().and_then(|value| value.display_write_utf8) else {
        return false;
    };
    unsafe { callback(column, row, text.as_ptr(), text.len() as u32) != 0 }
}

pub fn key_wait() -> Option<i32> {
    let callback = api()?.key_wait?;
    Some(unsafe { callback() })
}
