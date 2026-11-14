"""Product barcodes: EAN-13, UPC-A and EAN-8 (the GTIN family).

normalize_barcode() is used both when saving a product and when looking one
up, so a barcode is always stored and searched in the same form:

- spaces are removed, then only the digits 0 to 9 are allowed;
- it must be 13 digits (EAN-13), 12 (UPC-A) or 8 (EAN-8);
- the last digit (the check digit) must match the others;
- a UPC-A is stored as the EAN-13 it is equivalent to, by adding a leading 0,
  so scanning "036000291452" and "0036000291452" finds the same product.
"""

import re

# Only the ASCII digits 0 to 9. (str.isdigit() would also accept other
# characters that count as digits, such as "²" or Arabic-Indic numerals.)
DIGITS_ONLY = re.compile(r"[0-9]+")

EAN_13_LENGTH = 13
UPC_A_LENGTH = 12
EAN_8_LENGTH = 8
VALID_LENGTHS = (EAN_13_LENGTH, UPC_A_LENGTH, EAN_8_LENGTH)

# Longer than any barcode, but short enough to reject junk before looking at it
MAX_INPUT_LENGTH = 32


class InvalidBarcode(ValueError):
    """The barcode can't be accepted. The message says why, for the client to show."""


def gtin_check_digit(digits_without_check: str) -> int:
    """The check digit that should follow these digits.

    EAN-13, UPC-A and EAN-8 all use the same rule. Example, for the EAN-13
    6150000000013, whose first 12 digits are 615000000001:

    1. Start from the RIGHT-hand end of the digits (the one next to where
       the check digit goes) and give the digits weights 3, 1, 3, 1, ...
       Starting from the right means the rule works for every length.

           digits:   6 1 5 0 0 0 0 0 0 0 0 1
           weights:  1 3 1 3 1 3 1 3 1 3 1 3   (read right to left: 3, 1, 3, ...)

    2. Multiply each digit by its weight and add everything up:
           6x1 + 1x3 + 5x1 + 0 + ... + 0 + 1x3 = 6 + 3 + 5 + 3 = 17

    3. The check digit is whatever brings that total up to the next
       multiple of 10: 17 + 3 = 20, so the check digit is 3.
       (10 - 17 % 10) % 10 = (10 - 7) % 10 = 3. The final "% 10" turns a
       result of 10 into 0, for totals that are already a multiple of 10.

    The weights are why a single mistyped digit, or two neighbouring digits
    swapped, almost always gives a different check digit and is caught.
    """
    total = 0
    for position_from_right, digit in enumerate(reversed(digits_without_check)):
        weight = 3 if position_from_right % 2 == 0 else 1
        total += int(digit) * weight
    return (10 - total % 10) % 10


def normalize_barcode(raw: str) -> str:
    """Validate a scanned or typed barcode and return the form it is stored in.

    Raises InvalidBarcode with a message that never repeats the whole input.
    """
    if len(raw) > MAX_INPUT_LENGTH:
        raise InvalidBarcode("A barcode is 8, 12 or 13 digits long")

    # Remove spaces (and tabs or newlines a scanner may add) anywhere in it
    code = "".join(raw.split())

    if not DIGITS_ONLY.fullmatch(code):
        raise InvalidBarcode("A barcode may only contain the digits 0 to 9")
    if len(code) not in VALID_LENGTHS:
        raise InvalidBarcode(f"A barcode must be 13 digits (EAN-13), 12 (UPC-A) or 8 (EAN-8); this one has {len(code)}")

    expected = gtin_check_digit(code[:-1])
    given = int(code[-1])
    if given != expected:
        raise InvalidBarcode(
            f"The check digit (the last digit) is wrong: it should be {expected}, not {given}. "
            "Check the barcode for a mistyped or swapped digit."
        )

    if len(code) == UPC_A_LENGTH:
        # A UPC-A is an EAN-13 that starts with 0. Adding the 0 doesn't change
        # the check digit: it gets weight 1 and adds nothing to the total.
        return "0" + code
    return code
