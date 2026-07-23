# Примеры загружаемых APP

Каждое приложение лежит в отдельном каталоге и описывается manifest-файлом
`app.mk61`. Пример `HELLO` собирается вместе с точной F401 resident-прошивкой:

```bash
./tools/build_f401_bundle.sh \
  --profile mini-v3-a00 \
  --app-manifest examples/loadable-apps/HELLO/app.mk61
```

В результате появится `Apps/HELLO.APP`. Пример использует только версионную
таблицу `loadable_app::Api`, полученную через `argument0`, и не импортирует
внутренние C++-символы resident.

Manifest можно проверить без компиляции:

```bash
./tools/build_f401_bundle.sh --check-app-manifests \
  --app-manifest examples/loadable-apps/HELLO/app.mk61
```

Полное описание manifest, API v1, установки и ограничений доверенного
нативного кода: `doc/src/MK61s-mini-APP.md`.
