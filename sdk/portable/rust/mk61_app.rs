//! Minimal `no_std` bindings for the current MK61 APP ABI.
//!
//! Ordinary and canonical System APP receive the same base API and the same
//! optional common-service table. Keep this layout append-only and in lockstep
//! with `loadable_app_api.h` and `loadable_app_services.h`.

#![allow(dead_code)]

use core::ffi::c_void;
use core::mem::size_of;
use core::ptr::null_mut;

pub const APP_ABI: u16 = 5;
pub const API_MAGIC: u32 = 0x3150_5041;
pub const API_VERSION: u16 = 1;
pub const MAX_TEXT_BYTES: u32 = 63;

pub const CAP_TIME: u32 = 1 << 0;
pub const CAP_TEXT_DISPLAY: u32 = 1 << 1;
pub const CAP_KEYBOARD: u32 = 1 << 2;
pub const CAP_LED: u32 = 1 << 3;
pub const CAP_SOUND: u32 = 1 << 4;
pub const CAP_FILES: u32 = 1 << 5;
pub const CAP_GRAPHICS: u32 = 1 << 6;
pub const CAP_KEY_STATE: u32 = 1 << 7;

pub const KIND_FOCAL: u32 = 1;
pub const KIND_TINYBASIC: u32 = 2;
pub const KIND_WBMP_VIEWER: u32 = 3;
pub const KIND_APPLICATION: u32 = 4;
pub const KIND_CHIP8: u32 = 5;
pub const KIND_MARKDOWN_VIEWER: u32 = 6;
pub const KIND_SETUP: u32 = 7;

pub const APP_OK: i32 = 0;
pub const APP_INVALID_FILE: i32 = 1;
pub const APP_UNSUPPORTED_DISPLAY: i32 = 2;
pub const APP_BUSY: i32 = 3;
pub const APP_IO_ERROR: i32 = 4;
pub const APP_RUNTIME_ERROR: i32 = 5;

pub const SERVICE_COMMON: u32 = 1;
pub const SERVICES_MAGIC: u32 = 0x3153_5953;
pub const SERVICES_VERSION: u16 = 2;

pub const SERVICE_CAP_UI: u32 = 1 << 0;
pub const SERVICE_CAP_FILES: u32 = 1 << 1;
pub const SERVICE_CAP_DIALOGS: u32 = 1 << 2;
pub const SERVICE_CAP_MEMORY: u32 = 1 << 3;
pub const SERVICE_CAP_EDITOR: u32 = 1 << 4;
pub const SERVICE_CAP_FONT: u32 = 1 << 5;
pub const SERVICE_CAP_REGISTERS: u32 = 1 << 6;
pub const SERVICE_CAP_MATH: u32 = 1 << 7;
pub const SERVICE_CAP_RUNTIME: u32 = 1 << 8;
pub const SERVICE_CAP_SETUP: u32 = 1 << 9;
pub const SERVICE_CAP_FORMAT: u32 = 1 << 10;
pub const SERVICE_CAP_UI_FONT: u32 = 1 << 11;

pub const SERVICE_DISPLAY: u32 = 1;
pub const SERVICE_KEYBOARD: u32 = 2;
pub const SERVICE_SETTINGS: u32 = 3;
pub const SERVICE_RANDOM: u32 = 4;
pub const SERVICE_MICROS: u32 = 5;
pub const SERVICE_FILE_COUNT: u32 = 6;
pub const SERVICE_FILE_ENTRY: u32 = 7;
pub const SERVICE_FILE_RESOLVE: u32 = 8;
pub const SERVICE_FILE_WRITE: u32 = 9;
pub const SERVICE_FILE_REMOVE: u32 = 10;
pub const SERVICE_FILE_CHOOSE: u32 = 11;
pub const SERVICE_FILE_SAVE_TARGET: u32 = 12;
pub const SERVICE_MEMORY_ACQUIRE: u32 = 13;
pub const SERVICE_MEMORY_RELEASE: u32 = 14;
pub const SERVICE_MEMORY_DATA: u32 = 15;
pub const SERVICE_TEXT_ROWS: u32 = 16;
pub const SERVICE_EDITOR_DRAW: u32 = 17;
pub const SERVICE_EDITOR_SCROLL: u32 = 18;
pub const SERVICE_MENU: u32 = 19;
pub const SERVICE_FONT: u32 = 20;
pub const SERVICE_REF_READ: u32 = 21;
pub const SERVICE_REF_WRITE: u32 = 22;
pub const SERVICE_FILE_EXISTS: u32 = 23;
pub const SERVICE_EDITOR_KEY: u32 = 24;
pub const SERVICE_SETUP: u32 = 25;
pub const SERVICE_CAPABILITIES: u32 = 26;
pub const SERVICE_UI_FONT: u32 = 27;

pub type Millis = unsafe extern "C" fn() -> u32;
pub type Service = unsafe extern "C" fn();
pub type Delay = unsafe extern "C" fn(u32);
pub type Dimension = unsafe extern "C" fn() -> u32;
pub type Clear = unsafe extern "C" fn() -> u32;
pub type Write = unsafe extern "C" fn(u32, u32, *const u8, u32) -> u32;
pub type KeyPoll = unsafe extern "C" fn() -> i32;
pub type KeyWait = unsafe extern "C" fn() -> i32;
pub type LedSet = unsafe extern "C" fn(u32);
pub type LedBlink = unsafe extern "C" fn(u32, u32, u32) -> u32;
pub type Beep = unsafe extern "C" fn(u32, u32, u32) -> u32;
pub type SoundStop = unsafe extern "C" fn();
pub type FileSize = unsafe extern "C" fn(u32) -> u32;
pub type FileRead = unsafe extern "C" fn(u32, u32, *mut u8, u32) -> u32;
pub type GraphicsValue = unsafe extern "C" fn() -> u32;
pub type GraphicsPresent = unsafe extern "C" fn(*const u8, u32) -> u32;
pub type GraphicsEnd = unsafe extern "C" fn();
pub type KeyPressed = unsafe extern "C" fn(i32) -> u32;
pub type QueryService = unsafe extern "C" fn(u32, u32) -> *const c_void;

#[repr(C)]
pub struct AppApi {
    pub magic: u32,
    pub version: u16,
    pub struct_size: u16,
    pub capabilities: u32,
    pub millis_ms: Option<Millis>,
    pub service: Option<Service>,
    pub delay_ms: Option<Delay>,
    pub display_columns: Option<Dimension>,
    pub display_rows: Option<Dimension>,
    pub display_clear: Option<Clear>,
    pub display_write_utf8: Option<Write>,
    pub key_poll: Option<KeyPoll>,
    pub key_wait: Option<KeyWait>,
    pub led_set: Option<LedSet>,
    pub led_blink: Option<LedBlink>,
    pub beep: Option<Beep>,
    pub sound_stop: Option<SoundStop>,
    pub file_size: Option<FileSize>,
    pub file_read: Option<FileRead>,
    pub graphics_available: Option<GraphicsValue>,
    pub graphics_width: Option<GraphicsValue>,
    pub graphics_height: Option<GraphicsValue>,
    pub graphics_revision: Option<GraphicsValue>,
    pub graphics_begin: Option<GraphicsValue>,
    pub graphics_present: Option<GraphicsPresent>,
    pub graphics_end: Option<GraphicsEnd>,
    pub key_pressed: Option<KeyPressed>,
    pub query_service: Option<QueryService>,
}

pub type ServiceCall = unsafe extern "C" fn(u32, u32, u32, u32, *mut c_void) -> u32;
pub type ServiceMath = unsafe extern "C" fn(u32, f64, f64) -> f64;
pub type RuntimeFunction = unsafe extern "C" fn();

#[repr(C)]
pub struct ServiceKeyboard {
    pub cx: u8,
    pub bx: u8,
    pub mul: u8,
    pub div: u8,
    pub power: u8,
    pub xy: u8,
    pub add: u8,
    pub sub: u8,
    pub neg: u8,
    pub dot: u8,
    pub digit: [u8; 10],
    pub pp: u8,
    pub bp: u8,
    pub x_to_p: u8,
    pub p_to_x: u8,
    pub run: u8,
    pub ret: u8,
    pub frw: u8,
    pub bkw: u8,
    pub k: u8,
    pub alpha: u8,
    pub degree: u8,
    pub grade: u8,
    pub radian: u8,
    pub user: u8,
    pub save: u8,
    pub load: u8,
    pub left: u8,
    pub right: u8,
    pub ok: u8,
    pub esc: u8,
    pub shg_left: u8,
    pub shg_right: u8,
}

#[repr(C)]
pub struct AppServices {
    pub magic: u32,
    pub version: u16,
    pub struct_size: u16,
    pub keyboard_mapping: *const ServiceKeyboard,
    pub call: Option<ServiceCall>,
    pub math: Option<ServiceMath>,
    // C's variadic va_list bridge is intentionally opaque in Rust. Rust APP
    // can use their own integer formatting or a tiny C wrapper if needed.
    pub format: usize,
    pub runtime: *const RuntimeFunction,
}

#[cfg(target_pointer_width = "32")]
const _: [(); 108] = [(); size_of::<AppApi>()];
#[cfg(target_pointer_width = "32")]
const _: [(); 104] = [(); core::mem::offset_of!(AppApi, query_service)];
#[cfg(target_pointer_width = "32")]
const _: [(); 28] = [(); size_of::<AppServices>()];

unsafe extern "C" {
    static mut mk61_api: *const AppApi;
    static mut mk61_app_image_crc: u32;
    static mut mk61_app_current_kind: u32;
}

pub fn api() -> Option<&'static AppApi> {
    let pointer = unsafe { mk61_api };
    unsafe { pointer.as_ref() }
}

pub fn image_crc() -> u32 {
    unsafe { mk61_app_image_crc }
}

pub fn current_kind() -> u32 {
    unsafe { mk61_app_current_kind }
}

pub fn api_compatible(required_capabilities: u32) -> bool {
    let Some(api) = api() else { return false };
    api.magic == API_MAGIC
        && api.version == API_VERSION
        && api.struct_size >= size_of::<AppApi>() as u16
        && api.capabilities & required_capabilities == required_capabilities
}

pub fn common_services(required_capabilities: u32) -> Option<&'static AppServices> {
    if !api_compatible(0) {
        return None;
    }
    let query = api()?.query_service?;
    let services = unsafe {
        (query(SERVICE_COMMON, u32::from(SERVICES_VERSION)) as *const AppServices).as_ref()?
    };
    if services.magic != SERVICES_MAGIC
        || services.version != SERVICES_VERSION
        || services.struct_size < size_of::<AppServices>() as u16
    {
        return None;
    }
    let call = services.call?;
    if required_capabilities != 0
        && unsafe { call(SERVICE_CAPABILITIES, 0, 0, 0, null_mut()) } & required_capabilities
            != required_capabilities
    {
        return None;
    }
    Some(services)
}

pub fn service_call(
    services: &AppServices,
    operation: u32,
    a: u32,
    b: u32,
    c: u32,
    payload: *mut c_void,
) -> Option<u32> {
    let callback = services.call?;
    Some(unsafe { callback(operation, a, b, c, payload) })
}

pub fn service_math(services: &AppServices, operation: u32, x: f64, y: f64) -> Option<f64> {
    let callback = services.math?;
    Some(unsafe { callback(operation, x, y) })
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

pub fn key_poll() -> Option<i32> {
    let callback = api()?.key_poll?;
    Some(unsafe { callback() })
}

pub fn key_wait() -> Option<i32> {
    let callback = api()?.key_wait?;
    Some(unsafe { callback() })
}
