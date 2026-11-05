# Общие внутренние модули

Этот каталог используется пользовательскими сборщиками, CI и тестами:

- `program_collection.py`, `program-catalog.json`, `program-capabilities.json`,
  `write-program-capabilities.ps1` — подбор, экспорт и безопасное обновление
  программ для конкретной сборки; [контракт](../../doc/design/Program-bundle-installation.md);
- `m8_codec.py` — кодек файловых/терминальных данных M8;
- `build_mk61_module_pack.sh` — сборка нативного упаковщика APP;
- `build_vm_program.cpp`, `vm_program_builder.hpp` — сборка исследовательских VM-образов;
- `seal-firmware*`, `.mk61-firmware-seal/`, `seal_picocalc.py` — запечатывание и проверка прошивок;
- `release-contract.json`, `release_contract.py`, `release-contract.ps1` — закреплённые зависимости, профили, бюджеты и отчёты релизных сборок.

Это внутренние зависимости, а не дополнительные пользовательские лаунчеры.
Публичные команды описаны в [`tools/README.md`](../../tools/README.md).

Для разработчиков и CI:

```sh
python3 dev/lib/release_contract.py validate
python3 dev/lib/release_contract.py profiles
```

При добавлении профиля меняется единый `release-contract.json`. Матрицы сборок
и проверяющие инструменты читают его напрямую; лимиты не дублируются в документации.
Исторические результаты не переписываются при перемещении исходных инструментов.
