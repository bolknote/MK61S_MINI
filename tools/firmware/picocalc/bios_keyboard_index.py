"""Invert keyboard slots per scan while preserving physical read and event order."""
from pathlib import Path
import hashlib
import re

def stage_keyboard_index(source):
    p = Path(source) / 'Core/Src/keyboard.c'
    original = p.read_bytes()
    if hashlib.sha256(original).hexdigest() != '7625b6ca934d9d413ba9f1f2a0b03de80fed61c665fc75659ff0605e309207ae':
        raise ValueError('Archived keyboard source changed; review the index transformation')
    s = original.decode().replace('\r\n', '\n')
    helper = """/* The foreground scan owns keys_list. Invert its ten slots once, while
 * preserving every GPIO read, state callback and uptime call in scan order. */
static void key_index_build(uint8_t slots[NUM_OF_ROWS*NUM_OF_COLS+12]) {
    for(unsigned k=0;k<NUM_OF_ROWS*NUM_OF_COLS+12;++k)slots[k]=UINT8_MAX;
    for(unsigned i=0;i<KEY_LIST_SIZE;++i) {
        const uintptr_t p=(uintptr_t)keys_list[i].p_entry;
        const uintptr_t matrix=(uintptr_t)kbd_entries,buttons=(uintptr_t)btn_entries;
        unsigned key;
        if(p>=matrix && p-matrix<sizeof(kbd_entries) && (p-matrix)%sizeof(struct entry)==0)
            key=(unsigned)((p-matrix)/sizeof(struct entry));
        else if(p>=buttons && p-buttons<sizeof(btn_entries) && (p-buttons)%sizeof(struct entry)==0)
            key=NUM_OF_ROWS*NUM_OF_COLS+(unsigned)((p-buttons)/sizeof(struct entry));
        else continue;
        if(slots[key]==UINT8_MAX)slots[key]=(uint8_t)i;
    }
}

"""
    s = s.replace('void keyboard_process(void) {', helper + 'void keyboard_process(void) {')
    needle = '\t\tlast_process_time = uptime_ms();'
    assert s.count(needle) == 1
    s = s.replace(needle, needle + '\n        uint8_t key_slots[NUM_OF_ROWS*NUM_OF_COLS+12];\n        key_index_build(key_slots);')
    start = s.index('\t\t\t\tconst int32_t key_idx')
    mid = s.index('\t\t\tio_matrix[c] = col_value;', start)
    end = s.index('\n\t\t\tio_matrix[8]', mid)
    a = s[start:mid]
    b = s[mid:end]
    pat = '\\t{4}int32_t list_idx = -1;\\n\\t{4}for \\(int32_t i = 0; i < KEY_LIST_SIZE; \\+\\+i\\) \\{.*?\\n\\t{4}\\}'
    a, count = re.subn(pat, '                const uint8_t indexed=key_slots[key_idx];\n                int32_t list_idx=indexed<KEY_LIST_SIZE &&\n                    keys_list[indexed].p_entry==&((const struct entry*)kbd_entries)[key_idx]?indexed:-1;', a, count=1, flags=re.S)
    assert count == 1
    old = '\t\t\t\t\tnext_item_state(&keys_list[list_idx], pressed);'
    assert a.count(old) == 1
    a = a.replace(old, old + '\n                    if(!keys_list[list_idx].p_entry)key_slots[key_idx]=UINT8_MAX;')
    old = '\t\t\t\t\tkeys_list[i].p_entry = &((const struct entry*)kbd_entries)[key_idx];'
    assert a.count(old) == 1
    a = a.replace(old, old + '\n                    key_slots[key_idx]=(uint8_t)i;')
    pat = '\\t{4}int8_t list_idx = -1;\\n\\t{4}for \\(int8_t i = 0; i < KEY_LIST_SIZE; \\+\\+i\\) \\{.*?\\n\\t{4}\\}'
    b, count = re.subn(pat, '                const unsigned button_key=NUM_OF_ROWS*NUM_OF_COLS+b;\n                const uint8_t indexed=key_slots[button_key];\n                int8_t list_idx=indexed<KEY_LIST_SIZE &&\n                    keys_list[indexed].p_entry==&((const struct entry*)btn_entries)[b]?indexed:-1;', b, count=1, flags=re.S)
    assert count == 1
    old = '\t\t\t\t\tnext_item_state(&keys_list[list_idx], pressed);'
    assert b.count(old) == 1
    b = b.replace(old, old + '\n                    if(!keys_list[list_idx].p_entry)key_slots[button_key]=UINT8_MAX;')
    old = '\t\t\t\t\tkeys_list[i].p_entry = &((const struct entry*)btn_entries)[b];'
    assert b.count(old) == 1
    b = b.replace(old, old + '\n                    key_slots[button_key]=(uint8_t)i;')
    s = s[:start] + a + b + s[end:]
    result = ('#include <stdint.h>\n' + s).encode()
    if hashlib.sha256(result).hexdigest() != 'f6dc61f828dc8e168ab7c01ea978269d0df2cb1763fcc07cdf25b85605482afb':
        raise ValueError('Indexed keyboard output differs from tested source')
    p.write_bytes(result)
    return {'keyboard_index_slots': 68, 'keyboard_index_persistent_RAM_bytes': 0, 'keyboard_GPIO_reads_per_scan': 152}
