# Инструменты разработчика

Здесь находятся инструменты работы над прошивкой и штатным комплектом программ.
Пользовательские команды остаются в [`tools/`](../../tools/README.md).

| Группа | Команды |
| --- | --- |
| Математика | `certify_m0_*.py`, `generate_m0_*.py`, `generate_compact_math_*.py`, `profile_qfplib_ln_checked.py`, `select_m0_pow_refinement_corpus.py`, `vendor_m0_core_math.py` |
| VM и кеши | `measure_*.py`, `replay_vm*.py`, `model_vm_cache_packing.py`, `qualify_vm_cache_trace.py`, `language_vm_*.cpp`, `build_vm_program.py` |
| Шрифты и изображения комплекта | `generate_ui_fonts.py`, `generate_highnoon_font.py`, `generate_picocalc_game_assets.py`, `explorer_icons.py` |
| Штатные приложения и игры | `build_sheet_app.py`, `generate_eliza_doctor.py`, `elite/`, `race/`, `runner/`, `turochamp/` |
| ARM-эмуляция | `run_arm_test.py` — предварительная проверка среды и запуск тем же Python; macOS sandbox с запретом `hw.cachelinesize` отклоняется до Unicorn |
| Холодный запуск PicoCalc | `picocalc_cold_evidence.py` |

Примеры:

```sh
python3 dev/tools/explorer_icons.py --check
python3 dev/tools/generate_eliza_doctor.py --check
python3 dev/tools/runner/build.py --check
python3 dev/tools/certify_m0_trig_products.py --help
```

Исследовательский сертификат подтверждает только заявленные математические
границы. Он не включает кандидат в прошивку и не заменяет измерения на устройстве.
Готовые игры и ресурсы по-прежнему публикуются в `programs/`, а отчёты и бинарники —
в `.build/` либо в явно указанном каталоге.

Для ARM-теста используйте Python из окружения с установленным Unicorn:

```sh
python dev/tools/run_arm_test.py tests/portable_runtime_trampoline_arm_self_test.py \
  --arm-toolchain-bin /path/to/arm-gcc/bin
```

Если macOS отклоняет `hw.cachelinesize`, launcher завершится с кодом 2.
Ту же команду нужно запустить вне sandbox через штатное разрешение инструмента.
Сам launcher разрешения не повышает. Прямые штатные ARM-скрипты также
проверяют среду перед созданием эмулятора.
