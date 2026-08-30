#include "ERM19264_UC1609.h"
#include "spi1_bus.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

// Для транспортного теста графические примитивы не нужны. Эти три определения
// дают реальному драйверу минимальную базу, не подменяя проверяемый SPI-код.
ERM19264_graphics::ERM19264_graphics(int16_t width, int16_t height)
  : WIDTH(width),
    HEIGHT(height),
    _width(width),
    _height(height),
    _cursorX(0),
    _cursorY(0),
    _textWrap(true),
    drawBitmapAddr(true) {}

LCD_rotate_e ERM19264_graphics::getRotation(void) {
  return LCD_rotate;
}

size_t ERM19264_graphics::write(uint8_t) {
  return 1;
}

namespace {

static void assert_bytes(const std::vector<uint8_t>& actual,
                         const uint8_t* expected, size_t size) {
  assert(actual.size() == size);
  assert(memcmp(actual.data(), expected, size) == 0);
}

static void assert_balanced_hardware_transaction(void) {
  assert(SPI.begin_transaction_calls == 1);
  assert(SPI.end_transaction_calls == 1);
  const spi1_arbiter::Snapshot state = spi1_bus::statistics();
  assert(state.state == spi1_arbiter::State::IDLE);
  assert(state.owner == spi1_arbiter::Owner::NONE);
  assert(state.acquisitions == state.releases);
  assert(state.failures == 0);
}

static void test_page_is_two_spi_transfers(void) {
  ERM19264_UC1609 lcd(192, 64, 1, 2, 3);
  uint8_t page[192];
  for(size_t i = 0; i < sizeof(page); i++) page[i] = (uint8_t) i;

  SPI.clear();
  lcd.LCDBuffer(0, 0, 192, 8, page);
  assert(SPI.transfers.size() == 2);
  const uint8_t address[] = {0x00, 0x10, 0xB0};
  assert_bytes(SPI.transfers[0], address, sizeof(address));
  assert_bytes(SPI.transfers[1], page, sizeof(page));
  assert_balanced_hardware_transaction();
}

static void test_full_frame_batches_every_page(void) {
  ERM19264_UC1609 lcd(192, 64, 1, 2, 3);
  uint8_t frame[192 * 8];
  for(size_t i = 0; i < sizeof(frame); i++) frame[i] = (uint8_t) (i >> 4);

  SPI.clear();
  lcd.LCDBuffer(0, 0, 192, 64, frame);
  assert(SPI.transfers.size() == 16);
  for(uint8_t page = 0; page < 8; page++) {
    const uint8_t address[] = {0x00, 0x10, (uint8_t) (0xB0U | page)};
    assert_bytes(SPI.transfers[page * 2], address, sizeof(address));
    assert_bytes(SPI.transfers[page * 2 + 1],
                 frame + (size_t) page * 192, 192);
  }
  assert_balanced_hardware_transaction();
}

static void test_clipping_preserves_source_offsets(void) {
  ERM19264_UC1609 lcd(192, 64, 1, 2, 3);
  uint8_t data[24];
  for(size_t i = 0; i < sizeof(data); i++) data[i] = (uint8_t) (0x40U + i);

  SPI.clear();
  lcd.LCDBuffer(-4, 0, 12, 8, data);
  assert(SPI.transfers.size() == 2);
  const uint8_t left_address[] = {0x00, 0x10, 0xB0};
  assert_bytes(SPI.transfers[0], left_address, sizeof(left_address));
  assert_bytes(SPI.transfers[1], data + 4, 8);

  SPI.clear();
  lcd.LCDBuffer(188, 0, 12, 8, data);
  assert(SPI.transfers.size() == 2);
  const uint8_t right_address[] = {0x0C, 0x1B, 0xB0};
  assert_bytes(SPI.transfers[0], right_address, sizeof(right_address));
  assert_bytes(SPI.transfers[1], data, 4);

  SPI.clear();
  lcd.LCDBuffer(0, -8, 12, 16, data);
  assert(SPI.transfers.size() == 2);
  assert_bytes(SPI.transfers[0], left_address, sizeof(left_address));
  assert_bytes(SPI.transfers[1], data + 12, 12);
}

static void test_progmem_bitmap_uses_the_same_bulk_path(void) {
  ERM19264_UC1609 lcd(192, 64, 1, 2, 3);
  const uint8_t bitmap[24] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
    12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
  };

  SPI.clear();
  assert(lcd.LCDBitmap(10, 8, 12, 16, bitmap) == LCD_Success);
  assert(SPI.transfers.size() == 4);
  const uint8_t page_one[] = {0x0A, 0x10, 0xB1};
  const uint8_t page_two[] = {0x0A, 0x10, 0xB2};
  assert_bytes(SPI.transfers[0], page_one, sizeof(page_one));
  assert_bytes(SPI.transfers[1], bitmap, 12);
  assert_bytes(SPI.transfers[2], page_two, sizeof(page_two));
  assert_bytes(SPI.transfers[3], bitmap + 12, 12);
  assert_balanced_hardware_transaction();
}

static void test_goto_xy_is_a_complete_owned_transaction(void) {
  ERM19264_UC1609 lcd(192, 64, 1, 2, 3);

  SPI.clear();
  lcd.LCDGotoXY(0x2A, 5);

  assert(SPI.transfers.size() == 1);
  const uint8_t address[] = {0x0A, 0x12, 0xB5};
  assert_bytes(SPI.transfers[0], address, sizeof(address));
  assert_balanced_hardware_transaction();
}

static void test_contention_fails_closed(void) {
  ERM19264_UC1609 lcd(192, 64, 1, 2, 3);
  const uint8_t bitmap[8] = {};

  SPI.clear();
  arduino_test::clear();
  assert(spi1_bus::acquire(spi1_arbiter::Owner::FLASH_CLIENT));
  lcd.LCDGotoXY(0, 0);
  assert(SPI.transfers.empty());
  assert(SPI.begin_transaction_calls == 0);
  assert(SPI.end_transaction_calls == 0);
  assert(arduino_test::pin_writes.empty());
  spi1_arbiter::Snapshot state = spi1_bus::statistics();
  assert(state.state == spi1_arbiter::State::ERROR);
  assert(state.last_fault == spi1_arbiter::Result::CONTENTION);
  assert(state.contentions == 1);
  assert(spi1_bus::recover());

  SPI.clear();
  arduino_test::clear();
  assert(spi1_bus::acquire(spi1_arbiter::Owner::FLASH_CLIENT));
  assert(lcd.LCDBitmap(0, 0, 8, 8, bitmap) == LCD_SPIBusBusy);
  assert(SPI.transfers.empty());
  assert(SPI.begin_transaction_calls == 0);
  assert(arduino_test::pin_writes.empty());
  state = spi1_bus::statistics();
  assert(state.state == spi1_arbiter::State::ERROR);
  assert(state.contentions == 2);
  assert(spi1_bus::recover());
}

static void test_power_down_keeps_shared_spi_alive(void) {
  ERM19264_UC1609 lcd(192, 64, 1, 2, 3);

  SPI.clear();
  lcd.LCDPowerDown();

  assert(SPI.end_calls == 0);
  assert(SPI.transfers.size() == 1);
  assert_balanced_hardware_transaction();
}

static void test_software_spi_does_not_claim_spi1(void) {
  ERM19264_UC1609 lcd(192, 64, 1, 2, 3, 4, 5);
  const spi1_arbiter::Snapshot before = spi1_bus::statistics();

  SPI.clear();
  lcd.LCDGotoXY(1, 2);

  const spi1_arbiter::Snapshot after = spi1_bus::statistics();
  assert(SPI.transfers.empty());
  assert(SPI.begin_transaction_calls == 0);
  assert(after.acquisitions == before.acquisitions);
  assert(after.releases == before.releases);
  assert(after.failures == before.failures);
}

} // безымянное пространство имён

int main(void) {
  test_page_is_two_spi_transfers();
  test_full_frame_batches_every_page();
  test_clipping_preserves_source_offsets();
  test_progmem_bitmap_uses_the_same_bulk_path();
  test_goto_xy_is_a_complete_owned_transaction();
  test_power_down_keeps_shared_spi_alive();
  test_software_spi_does_not_claim_spi1();
  test_contention_fails_closed();
  printf("uc1609_transport_self_test: ok\n");
  return 0;
}
