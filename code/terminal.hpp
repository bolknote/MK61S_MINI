#ifndef TERMINAL_CLASS
#define TERMINAL_CLASS

#include "config.h"
#include "rust_types.h"
#include "program_store.hpp"
#include "storage_path.hpp"
#include "m61_ansi.hpp"
#include "m61_print.hpp"
#include "shared_memory.hpp"
#include "lcd_gui.hpp"
#include "terminal_core.hpp"
#include "terminal_command_ids.hpp"
#include "terminal_line_editor.hpp"
#include "terminal_protocol.hpp"
#include "power_monitor.hpp"
#include "rtc_clock.hpp"
#include "dwt_profiler.hpp"
#include "crash_dump.hpp"
#include "mpu_guard.hpp"
#include "independent_watchdog.hpp"

namespace read_benchmark { struct Summary; }

static constexpr usize MAX_INPUT_CHAR = terminal_core::INPUT_CAPACITY;

class class_terminal {
  private:
    enum class mnemo_type {ISA_61, ISA_CLASSIC};
    static constexpr usize MAX_LEN_CLASSIC_MNEMO = 8; // максимальная длинна классической инструкции

    isize   AT;
    u8      pending_confirmation_cmd;
    isize   nSlot;
    bool    input_overflow;
    char    pending_save_name[program_store::NAME_SIZE];
    u16     pending_save_parent_id;
    u16     current_directory;
    bool    file_upload_active;
    u16     file_upload_size;
    u16     file_upload_received;
    u32     file_upload_checksum;
    u32     file_upload_checksum_state;
    storage_path::FileTarget file_upload_target;

    static m61_ansi::SavedCursor print_saved_cursor;

    // Буфер строки один на прошивку (одна реализация): экземпляров терминала два
    // (интерактивный и скриптовый m61), но раньше из-за слияния weak-методов
    // линкером реально использовалась одна копия, вторая была мёртвым грузом.
    static u8 input_buffer[MAX_INPUT_CHAR];

    static constexpr u16 FILE_UPLOAD_STAGE_BLOCKS =
        (program_store::MAX_APP_FILE_SIZE +
         program_store::VFAT_STAGE_BLOCK_SIZE - 1U) /
        program_store::VFAT_STAGE_BLOCK_SIZE;
    // Диапазон терминального C5-upload отделён от USB LBA.
    static constexpr u32 FILE_UPLOAD_STAGE_FIRST_KEY =
        program_store::VFAT_STAGE_KEY_MAX - 127U;
    static constexpr usize FILE_UPLOAD_WORKSPACE_SIZE =
        program_store::VFAT_STAGE_BLOCK_SIZE +
        (usize) FILE_UPLOAD_STAGE_BLOCKS * sizeof(u32);

    // ====== История команд: байтовое кольцо + каталог записей ======
    // Каталог хранит позицию и длину каждой записи, поэтому доступ по номеру
    // (стрелки вверх/вниз) O(1) и нет сдвигов памяти при вытеснении старых.
    static constexpr u16 HISTORY_TEXT_SIZE = 256;
    static constexpr u8  HISTORY_DEPTH     = 8;

    // static: серийный ввод ведёт только интерактивный экземпляр,
    // держать копию истории в каждом экземпляре (script_terminal) - потеря ОЗУ.
    static char  hist_text[HISTORY_TEXT_SIZE];
    static u16   hist_start[HISTORY_DEPTH];
    static u8    hist_length[HISTORY_DEPTH];
    static u8    hist_head;                    // номер самой старой записи в каталоге
    static u8    hist_count;
    static u16   hist_used;                    // занято байт в текстовом кольце
    static u16   hist_write;                   // позиция записи в текстовом кольце
    static i8    hist_nav;                     // -1 - не в истории, 0 - самая новая
    static terminal_line_editor::EscapeDecoder escape_decoder;
    static u8    prev_terminator;              // съедание второго символа пары CRLF
    static u8    saved_line[MAX_INPUT_CHAR];   // строка, редактируемая до входа в историю
    static usize saved_len;
    static usize saved_cursor;

    void history_drop_oldest(void);

    void history_entry_read(u8 slot, u8* out);

    bool history_entry_equals(u8 slot, const u8* line, usize len);

    void history_add(const u8* line, usize len);

    void history_print(void);

    void print_prompt(void);

    void move_terminal_cursor(char direction, usize columns);

    usize input_columns(usize begin, usize end) const;

    void redraw_input_line(void);

    void history_recall(i8 nav);

    void history_key_up(void);

    void history_key_down(void);

    void editor_move_left(void);

    void editor_move_right(void);

    void editor_move_home(void);

    void editor_move_end(void);

    void editor_backspace(void);

    void editor_delete_forward(void);

    bool editor_insert(u8 byte);

    void editor_key(terminal_line_editor::Key key);

    void print_help(void);

#if MK61_CRASH_DUMP_SUPPORTED
    static void print_crash_usage(void);

    terminal_protocol::Result show_crash_dump(void);

    terminal_protocol::Result save_crash_dump(const char* path);

    terminal_protocol::Result exec_crash(void);
#endif

#if MK61_MPU_GUARD_SUPPORTED
    static void print_mpu_usage(void);

    terminal_protocol::Result show_mpu_status(void);

    terminal_protocol::Result exec_mpu(void);
#endif

#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED
    static const char* watchdog_state_name(u32 state);

    static void print_watchdog_usage(void);

    terminal_protocol::Result show_watchdog_status(void);

    terminal_protocol::Result exec_watchdog(void);
#endif

    static void print_memory_snapshot(shared_memory::Arena arena);

    terminal_protocol::Result exec_memory(void);

    static void print_display_status(void);

    static void print_display_usage(void);

#if defined(MK61_OLED1602_WS0010)
    static void display_test_text(void);

    static void display_test_map(u8 page);

    static void display_test_alphabet(u8 page);

    static void display_test_symbols(void);

    static void make_display_ddram(u8 cells[lcd_display::ROWS]
                                            [lcd_display::DDRAM_COLS]);

    static void display_test_cgram(void);

    static terminal_protocol::Result display_test_graphics(u8 pattern);

#if MK61_WS0010_GRAPHICS_PROFILE_QUALIFIED && \
    MK61_WS0010_GRAPHICS_100X16
    static terminal_protocol::Result display_test_graphics_readback(
        u8 pattern);
#endif
#endif

    terminal_protocol::Result exec_display(void);

    static const char* power_state_name(
        const power_monitor::Snapshot& snapshot);

    static void print_power_status(void);

#if MK61_ENABLE_ANALOG_REPORT
    static void print_analog_status(void);
#endif

#if MK61_DWT_PROFILER_SUPPORTED
#if MK61_ENABLE_PROFILE_SAVE
    class ProfileReportBuilder;
#endif

    static void print_u64(u64 value);

    static void print_profile_statistics(void);

#if MK61_ENABLE_PROFILE_SAVE
    static u16 build_profile_report(u8* output, usize capacity);

    terminal_protocol::Result save_profile_report(const char* path);
#endif

    terminal_protocol::Result exec_profile(void);
#endif

    terminal_protocol::Result script_action(terminal_protocol::ResultKind action, const char* args);

    bool input_can_append(void) const;

    void list_mk61_code_page(void);

    void dump_mk61_code_page(void);

    char* ISA_61_code(u8 opcode, char* text);

    char* ISA_CLASSIC_61_code(u8 opcode, char* text);

    void output_version(void);

    terminal_protocol::Result exec_identity(void);

#if MK61_ENABLE_READ_BENCHMARKS
    void print_benchmark_pass(u8 pass, u32 elapsed_us, u32 crc);

    terminal_protocol::Result print_benchmark_summary(
        const char* kind, u32 bytes,
        const read_benchmark::Summary& summary);

    terminal_protocol::Result benchmark_file(const char* cursor);

    terminal_protocol::Result benchmark_flash(const char* cursor);

    terminal_protocol::Result benchmark_random(const char* cursor);

    terminal_protocol::Result exec_benchmark(void);
#endif

    terminal_protocol::Result exec_date(void);

#if MK61_ENABLE_RTC_ALARM_TERMINAL
    static char alarm_id_letter(rtc_clock::AlarmId id);

    static void print_two_digits(u8 value);

    static void print_alarm_line(rtc_clock::AlarmId id);

    static void print_alarm_status(void);

    terminal_protocol::Result exec_alarm(void);
#endif

    static u16 file_capacity(program_store::ProgramType type);

    void cancel_file_upload(void);

    static bool read_staged_file_upload(void* context, u32 offset,
                                        u8* output, usize size);

    terminal_protocol::Result file_transfer_error(const char* code);

    terminal_protocol::Result exec_fs_get(void);

    terminal_protocol::Result exec_fs_put(void);

    void DumpRegisters(void);

    void Dump1302(void);

    void  print_address_as_MK61(usize addr);

  public:
    struct InputResult {
      i32 key;
      bool line_complete;
    };

    usize recive_pos;
    usize input_cursor;

    constexpr class_terminal(void)
      : AT(0), pending_confirmation_cmd(CMD_UNKNOWN), nSlot(-1),
        input_overflow(false), pending_save_name{},
        pending_save_parent_id(program_store::ROOT_ID),
        current_directory(program_store::ROOT_ID), file_upload_active(false),
        file_upload_size(0), file_upload_received(0),
        file_upload_checksum(0), file_upload_checksum_state(0),
        file_upload_target{}, recive_pos(0), input_cursor(0) {}

    void reset_command_state(void);

    // История и редактор строки общие (static): сбрасываются только при
    // старте интерактивного терминала, скриптовый init их не трогает.
    void reset_line_editor(void);

    void  init(void);

    void init_script(void);

    terminal_protocol::Result execute_script_line(const char* line,
                                                   bool trap_mode = false);

    void  echo_mk61_stack(void);

    void  echo_ISA_61(void);

    void pub_mk61_code_page(void);

    void  lasm_mk61_code_page(mnemo_type type);

    bool GetHexString(const char* args);

    void  PutHexString(void);

    bool Assembler(void);

    void  flash_map_list(void);

    terminal_protocol::Result command_to_kbd(bool script_mode);

    bool scancode_to_kbd(i32& out);

    static bool value_fits_mk61(double value);

    bool write_register_value(u8 reg, const char* args);

    bool write_stack_value(const char* args);

    // Аргументы команды: всё после первого слова строки ввода.
    const char* command_args(void);

    // Список неотрицательных чисел через запятую и/или пробелы.
    isize parse_u32_list(const char* p, u32* out, usize max_count);

    // led 1 | led 0 | led 1,500,0,500,1 - состояния и паузы (ms), асинхронно.
    bool exec_led(void);

    // beep 4000,100 | beep 4000,100,0,50,2000,200 - пары частота(Hz),длительность(ms);
    // частота 0 - пауза. Воспроизведение асинхронное.
    bool exec_beep(void);

    // Значение индикаторного формата "-1.2345678 -99" -> double.
    // Нечисловые сегменты (ERROR, L/C/E на индикаторе) - отказ.
    static bool parse_mk_display_value(const char* v, double& out);

    static bool operand_delimiter(char c);

    // Операнд условия if: x,y,z,t,x1 (стек), r0..re (rf в расширенном режиме)
    // или числовой литерал (1.25e-2, -5, ...).
    static bool parse_if_operand(const char*& p, double& out);

    // if <операнд><op><операнд> <команда> - команда выполняется при истинном
    // условии. В m61-скриптах вместе с "run :метка" даёт условные переходы.
    struct PrintRenderContext {
      m61_ansi::Writer* writer;
    };

    static bool screen_put_byte(u8 x, u8 y, u8 value, void* user_data);

    static bool screen_clear(void* user_data);

    static bool print_byte(u8 value, void* user_data);

    static bool print_text(const char* text, PrintRenderContext& context);

    static bool print_number_text(const char text[15],
                                  m61_print::ValueFormat format,
                                  PrintRenderContext& context);

    static bool print_value(const m61_print::ValueRef& value, void* user_data);

    bool exec_print(bool script_mode);

    terminal_protocol::Result exec_if(bool script_mode, bool trap_mode);

    terminal_protocol::Result execute(bool script_mode = false,
                                      bool trap_mode = false);

    InputResult input_handler(u8 rx_char);

    i32 serial_input_handler();

};

#endif
