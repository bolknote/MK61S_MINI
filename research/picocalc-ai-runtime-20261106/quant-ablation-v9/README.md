# Q4 × INT16 и покомпонентная проверка

Изолированный кандидат для Flourish-3M `harness-debug-v3/selected-budget/active-best/step1500`. [Полный отчёт](../../../doc/measurements/picocalc-ai-quant-ablation-20261107.md) описывает выбор профиля, ограничения и аппаратный тест.

Результат: INT16 сохранил каждый базовый успех на 1175 проверках, уменьшил steady workspace с 20 880 до 15 120 байт. В коротком SRAM-тесте на M0+ при 125 МГц скорость практически равна INT8, около 6× быстрее LUT для 384 столбцов. Это не измерение полной модели. Основной runtime/прошивка не переключены. Lifecycle теста имеет HOLD из-за FS4 при возврате UI; отдельный C5 подтвердил закрытый foreground без crash. Численные 18 записей сохранены и проверены отдельно.

- `source/` — общий исследовательский backend для всех ablation-профилей.
- `candidate/source/` — компактный backend и развёрнутый Q4 × INT16 dot. `candidate.patch` сравнивает его с замороженным SWAR-v5, не с текущим общим рабочим деревом.
- `metrics-*.json`, `metrics.csv`, `metric-*.json` — метрики и фиксированные токены/цели, включая полный русский диагностический выход.
- `candidate/paired-report.json`, `candidate/run-*/results.jsonl.gz` — функциональный аудит. Архивы lossless; исходные SHA находятся в `archives.json`.
- `weight-grid-report.json`, `weight-metrics.json`, `huffman-report.json` — LNS/APoT и реальный row-indexed Huffman.
- `hil/` — исторические single-use фазы и receipts. **Не переигрывать** эти аппаратные фазы. `hardware-summary.json` разделяет numeric PASS и lifecycle HOLD.
- `arm/app/QKERNEL.APP` и `arm/a16-dot32.asm` — проверенная тестовая APP и листинг. ARM payload уже выполнен однократно; штатный harness он не заменяет.

Воспроизведение на HOST, без USB:

```sh
python3 research/picocalc-ai-runtime-20261106/quant-ablation-v9/replay.py \
  --workdir /tmp/picocalc-quant-v9-replay \
  --model-dir .build/mk61ai/quant-ablation-v9/model
```

Требуются Python, clang/clang++ и фиксированные `model.mka`, `model-nibble.mka` из `external-model.json`. Для `--metrics` дополнительно нужен numpy в выбранном Python. Каталог workdir должен отсутствовать. По умолчанию пересобираются оба backend, проверяются 48 000 строк с int64 oracle и ASan/UBSan, 65 контрольных генераций и границы областей памяти. `--metrics both` повторяет все calibration и заранее выбранные audit-профили; `--functional` повторяет по 1175 случаев для LUT, INT16 и INT16+FP32 head. Это может занять несколько минут.

`publication-manifest.json` — итоговый inventory, а не притворный pre-run seal. Настоящие предшествовавшие прогонам `metric-manifest.json` и `candidate/qualification-manifest.json` сохранены отдельно. Скрипты исторического orchestration могут ссылаться на исходный `.build`; поддерживаемый вход для повторения HOST-проверки — `replay.py`.
