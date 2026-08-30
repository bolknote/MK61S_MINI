#include <cassert>
#include <cstring>
#include <iostream>
#include <set>

#include "device_identity.hpp"

static void test_unsupported_fallback(void) {
  const device_identity::Uid96 unavailable = {0, 0, 0};
  char text[device_identity::PUBLIC_ID_TEXT_SIZE];
  assert(!unavailable.available());
  assert(device_identity::public_id(unavailable) == 0);
  assert(!device_identity::format_public_id(unavailable, text));
  assert(text[0] == 0);
  assert(device_identity::fat_volume_serial(
      unavailable, 0xC5123456U) == 0xC5123456U);
}

static void test_golden_identity(void) {
  const device_identity::Uid96 uid = {
    0x12345678U, 0x9ABCDEF0U, 0x0FEDCBA9U
  };
  char public_text[device_identity::PUBLIC_ID_TEXT_SIZE];
  char short_text[device_identity::SHORT_ID_TEXT_SIZE];
  char usb_text[device_identity::USB_SERIAL_TEXT_SIZE];
  char volume_text[device_identity::VOLUME_ID_TEXT_SIZE];

  assert(device_identity::format_public_id(uid, public_text));
  assert(device_identity::format_short_id(uid, short_text));
  assert(device_identity::format_stm32duino_usb_serial(uid, usb_text));
  assert(device_identity::format_fat_volume_serial(
      uid, 0xC5000000U, volume_text));

  // Значения зафиксируют endian, домены и совместимость с USB core.
  assert(std::strcmp(public_text, "52D9F3AFF9DA156B") == 0);
  assert(std::strcmp(short_text, "F9DA156B") == 0);
  assert(std::strcmp(usb_text, "222222219ABC") == 0);
  assert(std::strcmp(volume_text, "827BA469") == 0);
  assert(std::strncmp(public_text + 8, volume_text, 8) != 0);

  char report[device_identity::REPORT_TEXT_SIZE];
  const usize report_length = device_identity::format_report(
      uid, 0xC5000000U, 0x12345678U, "mini-v3-a00",
      report, sizeof(report));
  assert(report_length == std::strlen(report));
  assert(std::strcmp(
      report,
      "MK61 ID v=1 public=52D9F3AFF9DA156B short=F9DA156B "
      "usb=222222219ABC volume=827BA469 build=12345678 "
      "profile=mini-v3-a00") == 0);

  char too_small[16];
  assert(device_identity::format_report(
      uid, 0, 0, "mini-v3-a00", too_small, sizeof(too_small)) == 0);
  assert(device_identity::format_report(
      uid, 0, 0, "bad profile", report, sizeof(report)) == 0);
}

static void test_usb_serial_wraparound(void) {
  // Сумма UID0+UID2 вправе переполниться в ноль; STM32duino всё равно
  // публикует корректные 12 hex цифр, и handshake обязан их повторить.
  const device_identity::Uid96 uid = {
    0xFFFFFFFFU, 0x12345678U, 0x00000001U
  };
  char usb_text[device_identity::USB_SERIAL_TEXT_SIZE];
  assert(device_identity::format_stm32duino_usb_serial(uid, usb_text));
  assert(std::strcmp(usb_text, "000000001234") == 0);
}

static void test_small_collision_corpus(void) {
  std::set<u64> public_ids;
  std::set<u32> volume_ids;
  for(u32 index = 1; index <= 4096; index++) {
    const device_identity::Uid96 uid = {
      0x002A0000U + index,
      0x36384720U ^ (index * 0x9E3779B9U),
      0x12340000U + index * 17U
    };
    const u64 public_value = device_identity::public_id(uid);
    const u32 volume_value = device_identity::fat_volume_serial(uid, 0);
    assert(public_value != 0 && volume_value != 0);
    assert(public_ids.insert(public_value).second);
    assert(volume_ids.insert(volume_value).second);
  }
}

int main(void) {
  test_unsupported_fallback();
  test_golden_identity();
  test_usb_serial_wraparound();
  test_small_collision_corpus();
  std::cout << "device_identity_self_test: ok\n";
  return 0;
}
