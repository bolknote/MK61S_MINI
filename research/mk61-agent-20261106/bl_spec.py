"""Calculator values remain floating point, including INT and SIGN results.

Avoid constructing unbounded Python integer powers from an INT/SIGN subtree.
Valid ROM-domain reference expressions retain their numerical interpretation.
"""
import full_isa_math
import ar_spec
from bh_spec import value as original_value, close, normal, equal_spec


def value(expr, values, angle):
    return float(original_value(expr, values, angle))


def install():
    full_isa_math.value = value
    ar_spec.value = value
    ar_spec.close = close
