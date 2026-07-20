import base64

from pi_defense.canary import detect_canary_leak


CANARY = "CANARY_TEST_ABC123"


def test_raw_leak():
    leaked, variant = detect_canary_leak(
        f"答案是 {CANARY}",
        CANARY,
    )
    assert leaked is True
    assert variant == "raw"


def test_spaced_leak():
    spaced = " ".join(CANARY)
    leaked, _ = detect_canary_leak(spaced, CANARY)
    assert leaked is True


def test_reverse_leak():
    reversed_value = CANARY[::-1]
    leaked, variant = detect_canary_leak(
        reversed_value,
        CANARY,
    )
    assert leaked is True
    assert variant == "reverse"


def test_base64_leak():
    encoded = base64.b64encode(CANARY.encode()).decode()
    leaked, variant = detect_canary_leak(
        encoded,
        CANARY,
    )
    assert leaked is True
    assert variant == "base64"


def test_no_leak():
    leaked, variant = detect_canary_leak(
        "这是一个正常输出",
        CANARY,
    )
    assert leaked is False
    assert variant is None
