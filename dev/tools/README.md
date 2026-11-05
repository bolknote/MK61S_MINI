# Инструменты разработчика

Здесь находятся инструменты работы над прошивкой и штатным комплектом программ.
Пользовательские команды остаются в [`tools/`](../../tools/README.md).

| Группа | Команды |
| --- | --- |
| Математика | `certify_m0_*.py`, `generate_m0_*.py`, `generate_compact_math_*.py`, `profile_qfplib_ln_checked.py`, `select_m0_pow_refinement_corpus.py`, `vendor_m0_core_math.py` |
| VM и кеши | `measure_*.py`, `replay_vm*.py`, `model_vm_cache_packing.py`, `qualify_vm_cache_trace.py`, `language_vm_*.cpp`, `build_vm_program.py` |
| Шрифты и изображения комплекта | `generate_ui_fonts.py`, `generate_highnoon_font.py`, `generate_picocalc_game_assets.py`, `explorer_icons.py` |
| Штатные приложения и игры | `build_sheet_app.py`, `generate_eliza_doctor.py`, `elite/`, `race/`, `runner/`, `turochamp/` |
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
