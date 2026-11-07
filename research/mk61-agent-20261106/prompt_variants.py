"""Explicit input ablations shared by training and evaluation."""
import re


def without_public_examples(prompt):
    return re.sub(r'(?m)^Проверки:[^\n]*\n','',prompt)
