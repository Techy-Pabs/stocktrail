"""Unit tests for app/core/barcodes.py: no database or API needed."""

import pytest

from app.core.barcodes import InvalidBarcode, gtin_check_digit, normalize_barcode

# Real, published examples of each kind (from the GS1 and Wikipedia write-ups),
# used only to prove the check digit maths. The API docs use made-up 615 codes.
PUBLISHED = {
    "ean13": "4006381333931",
    "ean13_isbn": "9780306406157",
    "upca": "036000291452",
    "ean8": "96385074",
}


@pytest.mark.parametrize("code", PUBLISHED.values(), ids=PUBLISHED.keys())
def test_check_digit_matches_published_barcodes(code):
    assert gtin_check_digit(code[:-1]) == int(code[-1])


@pytest.mark.parametrize(
    "digits, expected",
    [
        ("615000000001", 3),  # the worked example in gtin_check_digit's docstring
        ("615000000002", 0),  # total already a multiple of 10: check digit 0, not 10
        ("6150000", 6),  # EAN-8 length
        ("61500000001", 3),  # UPC-A length
    ],
)
def test_check_digit_examples(digits, expected):
    assert gtin_check_digit(digits) == expected


@pytest.mark.parametrize(
    "code",
    ["6150000000013", "6150000000020", "4006381333931", "9780306406157"],
)
def test_valid_ean13_is_stored_as_given(code):
    assert normalize_barcode(code) == code


@pytest.mark.parametrize("code", ["61500006", "96385074"])
def test_valid_ean8_is_stored_as_given(code):
    assert normalize_barcode(code) == code


@pytest.mark.parametrize("code", ["615000000013", "036000291452"])
def test_upca_is_stored_as_ean13_with_a_leading_zero(code):
    assert normalize_barcode(code) == "0" + code


def test_upca_and_its_ean13_form_normalize_to_the_same_value():
    assert normalize_barcode("036000291452") == normalize_barcode("0036000291452") == "0036000291452"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("615 0000 000013", "6150000000013"),
        ("  6150000000013  ", "6150000000013"),
        ("6150000000013\n", "6150000000013"),  # a scanner's trailing newline
        ("6150 0006", "61500006"),
        ("0 36000 29145 2", "0036000291452"),
    ],
)
def test_spaces_are_stripped(raw, expected):
    assert normalize_barcode(raw) == expected


@pytest.mark.parametrize(
    "code",
    ["615000000001X", "ABCDEFGHIJKLM", "6150-0000-0001", "615000000001.3", "+615000000013", "６１５００００６"],
    ids=["letter", "letters", "dashes", "dot", "plus", "full-width-digits"],
)
def test_anything_but_ascii_digits_is_rejected(code):
    with pytest.raises(InvalidBarcode, match="only contain the digits 0 to 9"):
        normalize_barcode(code)


@pytest.mark.parametrize("length", [1, 7, 9, 10, 11, 14, 20])
def test_other_lengths_are_rejected(length):
    with pytest.raises(InvalidBarcode, match=f"this one has {length}"):
        normalize_barcode("6" * length)


def test_empty_and_whitespace_only_are_rejected():
    for raw in ("", "   "):
        with pytest.raises(InvalidBarcode):
            normalize_barcode(raw)


def test_very_long_input_is_rejected_before_parsing():
    with pytest.raises(InvalidBarcode, match="8, 12 or 13 digits long"):
        normalize_barcode("6" * 1000)


@pytest.mark.parametrize(
    "code, should_be, was",
    [
        ("6150000000014", 3, 4),  # EAN-13
        ("615000000010", 3, 0),  # UPC-A
        ("61500007", 6, 7),  # EAN-8
    ],
)
def test_wrong_check_digit_message_names_the_right_digit(code, should_be, was):
    with pytest.raises(InvalidBarcode) as error:
        normalize_barcode(code)

    message = str(error.value)
    assert f"should be {should_be}, not {was}" in message
    assert "check digit" in message
    assert code not in message  # the whole input is never repeated back


def test_swapped_neighbouring_digits_are_caught():
    # 6150000000013 with its 12th and 13th digits swapped
    with pytest.raises(InvalidBarcode, match="check digit"):
        normalize_barcode("6150000000031")
