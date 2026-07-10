![GitHub](https://img.shields.io/badge/github-%23121011.svg?style=for-the-badge&logo=github&logoColor=white)
![C](https://img.shields.io/badge/c-%2300599C.svg?style=for-the-badge&logo=c&logoColor=white) 
![C++](https://img.shields.io/badge/c++-%2300599C.svg?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![Arduino](https://img.shields.io/badge/-Arduino-00979D?style=for-the-badge&logo=Arduino&logoColor=white)


# MK61S_MINI

Развитие проекта эмулятора МК-61s - <a href="https://web.archive.org/web/20231130170055/https://gitlab.com/vitasam/mk61s/">gitlab.com/vitasam/mk61s</a>

Основной задачей было, получение бюджетного варианта, легкого в повторении всеми желающими. В связи с чем, печатная плата была ограничена размером 10х10 сантиметров. В качестве микроконтроллера используется готовая отладочная плата "BlackPill". Для сборки устройства не требуется паяльная станция или специфичное оборудование. Навыков пайки начинающего радиолюбителя и паяльника из поднебесной, будет достаточно.

Ну и дополнительно, хотелось создать аппаратную платформу, пригодную для реализации других эмуляторов программируемых микрокалькуляторов или вычислительных систем.

Обсуждение проекта и просто общение любителей программируемых микрокалькуляторов, происходит в группе в Телеграм - https://t.me/mk61s

Программный код проекта основан на работе Феликса Лазарева (https://github.com/fixelsan/emu145), в связи с чем ни один "ЕГГОГ" не пострадал и участники проекта могут во всей красе насладиться особенностями работы микрокалькуляторов "Электроника МК-61".

Для снижения порога входа в проект, исходный код предоставлен для среды разработки Arduino IDE.
Для предложенного исходного кода сформированы также бинарные файлы, которые можно найти в соответствующей папке проекта.

Разработка ведется творческим коллективом, в составе:
- Digitalinvitro (https://github.com/digitalinvitro) - программный код
- Vitasam - (https://github.com/vitasam) программный код
- UN7FGO (http://gengen.ru/) - схема, печатная плата и документация

На данный момент, актуальной является 3-я версия печатной платы устройства, гербер-файлы которой размещены в соответствующем разделе. 

Устройство в сборе, имеет габариты 99х99х19 мм, но никто не мешает "доработать его напильником" и сделать значительно тоньше. Все возможности для этого имеются.

![3-я версия устройства в сборе](https://github.com/UN7FGO/MK61S_MINI/blob/main/img/mk-61s-mini-c.jpg)

**Более подробное описание проекта:**  
https://github.com/UN7FGO/MK61S_MINI/blob/main/doc/MK61s-mini-Documentation.pdf

**Инструкция по сборке:**  
https://github.com/UN7FGO/MK61S_MINI/blob/main/doc/MK61s-mini-Assembly.pdf

**Инструкция по прошивке микроконтроллера, "для чайников":**  
https://github.com/UN7FGO/MK61S_MINI/blob/main/doc/MK61s-mini-Programming.pdf

**Инструкция по работе с Терминалом:**  
https://github.com/UN7FGO/MK61S_MINI/blob/main/doc/MK61s-mini-Terminal.pdf

**Инструкция по работе с БЕЙСИКом:**<br>
https://github.com/UN7FGO/MK61S_MINI/blob/main/doc/MK61s-mini-BASIC.pdf

**Литературное творчество о Проекте:** - https://habr.com/ru/articles/860226/

**Видеоинструкция по сборке от Виталия (FANJET)** - https://www.youtube.com/watch?v=JBStgbfmuOs

Желающие поправить проект "под себя", могут это сделать на Open Source Hardware Lab - <a href="https://oshwlab.com/un7fgo/mk61s_v1_copy_copy_copy_copy"> ЗДЕСЬ </a>

## Проверка исходного кода

Host-тесты требуют `clang++` с поддержкой C++17 и запускаются одной командой:

```bash
tests/run_all_tests.sh
```

Для дополнительной проверки границ памяти и неопределённого поведения:

```bash
MK61_TEST_SANITIZERS=1 tests/run_all_tests.sh
```

Тестовый набор проверяет BASIC, FOCAL, TinyBASIC, математический CORE-бэкенд,
эксклюзивное владение общими runtime/scratch-буферами, Virtual FAT и реальное
устройство `program_store` через модель SPI flash с инъекцией ошибок записи и
повреждения каталога.

Референсная сборка прошивки использует STM32 Arduino Core `2.12.0`,
`LiquidCrystal 1.0.7` и `SPIMemory 3.4.0`. Точная матрица плат и дисплеев
зафиксирована в [release workflow](.github/workflows/firmware-release.yml).

73!

![](https://komarev.com/ghpvc/?username=MK61s-mini)
