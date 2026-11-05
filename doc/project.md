# История и участники MK61S


Проект вырос из [эмулятора МК-61s Vitasam](https://web.archive.org/web/20231130170055/https://gitlab.com/vitasam/mk61s/).
Ядро основано на работе [Феликса Лазарева](https://github.com/fixelsan/emu145)
и сохраняет особенности исходной «Электроники МК-61», включая её «ЕГГОГ».

Первоначальная цель mini — бюджетное устройство, которое можно повторить
с обычным паяльником и начальными навыками пайки. Плата ограничена размером
10×10 см и использует готовую BlackPill. Корпус mini V3 имеет размеры
99×99×19 мм; эти размеры относятся именно к mini.

![mini V3 в сборе](../img/mk-61s-mini-c.jpg)

[Описание mini](MK61s-mini-Documentation.pdf),
[сборка](MK61s-mini-Assembly.pdf),
[прошивка](MK61s-mini-Programming.pdf),
[OLED WS0010](src/MK61s-mini-WS0010.md),
[статья о проекте](https://habr.com/ru/articles/860226/),
[видео сборки FANJET](https://www.youtube.com/watch?v=JBStgbfmuOs),
[плата в Open Source Hardware Lab](https://oshwlab.com/un7fgo/mk61s_v1_copy_copy_copy_copy).

Участники проекта:

- [Digitalinvitro](https://github.com/digitalinvitro) — программный код.
- [Vitasam](https://github.com/vitasam) — программный код.
- [UN7FGO](http://gengen.ru/) — схема, печатная плата и документация.
- [Bolknote](https://github.com/bolknote/) — программный код: файловая система
  и Проводник, терминал и M61, языки и редакторы, APP, шрифты и графический
  интерфейс, порт PicoCalc.
