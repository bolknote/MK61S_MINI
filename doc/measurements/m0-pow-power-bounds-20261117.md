# RP2040 pow rounding by bounded power products, 2026-11-17

After the directed 512-bit and 1,024-bit passes, the midpoint step
uses the adjacent encodings from the final enclosure. The existing
bounded exact comparison runs first. The new RP2040 stage applies
when that comparison has no answer. For positive exponent `p/q` it
compares `abs(x)^p` with `m^q`, where `m` is the exact midpoint. For
negative exponent it compares their product with one and reverses the
side. Zero, subnormal and overflow boundaries share the existing midpoint
decoder. The result sign is restored by the existing rescue entry point.

The power products use a 4,096-bit normalized lower significand and a
signed 128-bit scale. Each multiplication rounds downward. With
`N` factors, expanding the expression tree gives at most `N-1` local
rounding losses. Each relative loss is strictly below `2^(1-P)` for
significand precision `P`. Bernoulli's inequality and
`1/(1-z) <= 1+2*z` for `z <= 1/2` bound the upper significand by the
lower significand plus `4*(N-1)` units. An exact result needs zero
allowance. This construction proves the decision whenever the endpoints
identify the side. Equal exact endpoints use the parity of the lower
encoding for RNE.

After the existing tiny and huge exponent rules, `q <= 2^116`.
The combined exponentiation work takes at most 169 full-width products
and 11,128,832 16-bit multiply-accumulates, including the multiplications
by the original four-word factor. The relative interval width is below
`2^-3976`. The tested Pico H build used 119,896 bytes of static RAM and
a 1,805,072-byte Flash image.
[Rational certificate](../../dev/tools/certify_m0_pow_power_bounds.py)

| Check | Result |
| --- | --- |
| Native normalized multiply and upper-bound packing | 3,000 products and 1,000 bounds matched exact integers |
| Native directed MPFR side checks | 2,362 at 256 bits and 346 at 4,096 bits, all correct |
| Narrow test at 128 bits | 15 undecided results in 2,362 checks, zero incorrect decisions |
| Linked Pico H comparator with factory BootROM in Unicorn | Seven cases matched MPFR, including both tie parities |
| Input reaching the full-product bound | 146,215,403 guest instructions, 2,300 bytes of callee stack |
| Forced ARM rescue | 19/19 correct, each entered the new stage, 5,944 bytes of stack at the worst observed point |
| Existing exact stage with a forced interval hint | 19/19 correct |
| Public ARM pow numerical regression | 20,395 results matched directed MPFR |
| Committed exp inputs in ARM emulation | All 22 groups matched the earlier instruction counts, and the two broad modeled XIP miss rates matched |

The input with the largest exercised workload uses the largest subnormal
base and a negative exponent with 53 numerator bits and denominator
`2^116`. It exercises 169 full-width products and 52 four-word products.
The benchmark reports guest instructions and stack usage. The follow-up on
[physical PicoCalc](m0-pow-watchdog-20261117.md) measured 1.620 s in the
4,096-bit stage and a 2.294 s watchdog gap across the forced chain.

If the last stage is still undecided, the two directed enclosures overlap.
For a product with `n` leaves at precision `P`, its upper endpoint is at
most `1 + (4*(n-1)+1)*2^(1-P)` times its lower endpoint, including the
possible upward renormalization. Let `A = abs(x)^p` and `B = m^q` for
the positive exponent case. Overlap bounds both `A/B` and `B/A` by the
product of the two endpoint ratios. For a negative exponent the same
argument bounds `A*B` and its reciprocal using the combined enclosure.
Taking logarithms, applying `ln(1+t) <= t`, and dividing by `q` bounds
`abs(y*ln(abs(x)) - ln(m))` strictly below `4*(abs(y)+1)*2^-4095`.
The largest active `abs(y)` is `2^63 - 1024`, so the gap must be
strictly below `2^-4030`.

Two multiplicatively dependent dyadic bases are integer powers of a
common dyadic `g` with odd coefficient below `2^54`, up to inversion.
The nonzero distance of `ln(g)` from zero is at least `2^-54`. For
`g` between one half and two this follows from
`abs(ln(g)) >= abs(g-1)/max(1,g)` and the numerator and denominator
bounded by `2^54` near one. Outside that range use `ln(2)`. A nonzero
dependent gap is at least `2^-54/q >= 2^-170`, so it separates. At a
positive exact tie with nontrivial odd coefficients, the odd parts of
the two bases are `C^q` and `C^p` for an odd `C >= 3`. Then `q <= 32`
and both powers are exact at 4,096 bits. At other ties all odd parts
are one and the comparison uses the exact binary scales.

The 4,096-bit stage can still decline for a nonzero cancelling gap
below `2^-4030` between independent bases. The explicit separation
estimate in the prior analysis and the published searches for selected
exponents do not exclude that case across binary64. The RP2040 code now
handles further overlap with an exact comparison of integer powers.
[Final rounding decision](m0-pow-final-20261117.md)
[Prior separation analysis](m0-math-followup-20261114.md#host-results),
[CORE-MATH coverage](https://core-math.gitlabpages.inria.fr/worst.html)

## Проверка универсальной границы точности

Практическая верхняя граница задержки полного `pow` остаётся недоказанной.
Точное сравнение после 8 192 бит гарантирует завершение, но его число
пересчётов зависит от полных коэффициентов степеней. Чтобы ограничиться
нынешней последней ступенью для всех входов, достаточно доказать
`abs(y*ln(x)-ln(m)) >= 2^-8126` для независимых основания и середины
округления. Ничьи и зависимые основания уже покрыты отдельно.

Сертификат теперь проверяет специализацию следствия 2 Лорана с точной
рациональной арифметикой. После сокращения `abs(y)=p/q` выполняется
`p+q <= 2^116+2^53-1`. Высота каждого рационального основания и его
обратного, а также модуль логарифма меньше 746. При `log(A1)=log(A2)=746`
нормированный коэффициент равен `b'=(p+q)/746`. Неравенство
`ln(1+t)<=t`, нижняя граница `ln(746)>9*ln(2)+234/629` и рациональное
ограждение `ln(2)` дают `max(ln(b')+0.38,30,1)<75`. Таким образом,
модуль ненулевой формы `p*ln(x)-q*ln(m)` не меньше
`exp(-17.9*75^2*746^2) = exp(-56034204750)`.
Приведение оснований к числам больше единицы инвертированием сохраняет
высоты. При отсутствии вычитания ненулевые логарифмы ограничены снизу
отдельной элементарной оценкой.
[Теорема и таблица констант](https://www.impan.pl/shop/en/publication/transaction/download/product/82485)

После деления на `q` получается строгая нижняя граница
`2^-80840269429` для ненулевого логарифмического расстояния. Из ограждения
степеней следует достаточная точность **80 840 269 504 бита**, округлённая
вверх до 16-битных разрядов. Одна такая мантисса заняла бы
10 105 033 688 байт. Эта достаточная точность превышает возможности
PicoCalc. Оценка допускает гораздо меньшую фактически необходимую
точность и не устанавливает существование входа, требующего указанного
объёма памяти. Код прошивки продолжает использовать ступень на 8 192
бита и точное сравнение.

Опубликованный поиск CORE-MATH покрывает специальные подмножества
`pow`. В статье об алгоритме последняя ступень также допускает отказ
на неизвестном трудном входе. Полного сертификата расстояния для
оставшейся области эти результаты не дают.
[Описание покрытия](https://core-math.gitlabpages.inria.fr/worst.html),
[алгоритм pow, раздел IV](https://arith2023.arithsymposium.org/papers/Towards%20a%20Correctly-Rounded%20and%20Fast%20Power%20Function%20in%20Binary64%20Arithmetic.pdf)

Для общей практической границы времени требуется более сильная
оценка расстояния на всём оставшемся диапазоне либо алгоритм точного
сравнения с подходящей границей работы. Замеры на PicoCalc и конечные
корпуса MPFR подтверждают отдельные вызовы и диапазоны. Универсального
сертификата в текущей реализации нет.

```sh
python3 -B dev/tools/certify_m0_pow_power_bounds.py --json /tmp/m0-pow-power-bounds.json
```

Поле `uniform_precision_bound` содержит точные параметры расчёта и
`practical_uniform_latency_established=false`.

Дальнейшее [сужение оставшейся области](m0-pow-residual-domain-20261117.md)
исключает все основания `x=2^e` при `q>=2^100`: точный рациональный
перебор доказывает разделение уже при 128 битах и завершение первой
512-битной ступени. Там же установлены ограничения на середины при
малых показателях и передача одной границы в обычной rescue-цепочке.
Для остальных входов универсальная практическая граница остаётся
недоказанной.

Уточнённая [оценка в окрестности единицы](m0-pow-close-one-20261117.md)
доказывает достаточность 8032 бит, когда основание и середина лежат
в `[1-2^-37,1+2^-37]`. В частности, это закрывает все показатели
`abs(y)<=1/2` при `abs(x-1)<=2^-37` существующей ступенью на 8192 битах.
