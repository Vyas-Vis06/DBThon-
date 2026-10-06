import pytest

from zeroentry import security as sec


def test_password_roundtrip_and_hash_is_not_the_password():
    h = sec.hash_password("Correct-Horse-9", rounds=4)
    assert h.startswith("$2") and "Correct-Horse-9" not in h
    assert sec.verify_password("Correct-Horse-9", h)
    assert not sec.verify_password("correct-horse-9", h)


def test_same_password_gets_different_hashes_salted():
    assert sec.hash_password("Correct-Horse-9", rounds=4) != sec.hash_password("Correct-Horse-9", rounds=4)


@pytest.mark.parametrize("bad,why", [
    ("Short1a", "at least 12"),
    ("alllowercase12345", "mix upper and lower"),
    ("ALLUPPERCASE12345", "mix upper and lower"),
    ("NoDigitsInThisOne", "digit"),
    ("Aa1" + "é" * 40, "at most 72 bytes"),
])
def test_weak_or_oversized_passwords_are_refused(bad, why):
    with pytest.raises(ValueError, match=why):
        sec.hash_password(bad, rounds=4)


def test_verify_never_raises_on_garbage_hash_or_overlong_input():
    assert sec.verify_password("Correct-Horse-9", "not-a-bcrypt-hash") is False
    assert sec.verify_password("x" * 200, sec.hash_password("Correct-Horse-9", rounds=4)) is False


def test_tokens_are_random_and_stored_only_as_hash():
    a, b = sec.new_token(), sec.new_token()
    assert a != b and len(a) >= 43
    assert sec.hash_token(a) == sec.hash_token(a) and sec.hash_token(a) != sec.hash_token(b)
    assert len(sec.hash_token(a)) == 32 and a.encode() not in sec.hash_token(a)
    assert sec.tokens_equal(a, a) and not sec.tokens_equal(a, b)


def test_sliding_window_limiter_blocks_then_recovers():
    lim = sec.SlidingWindowLimiter(max_attempts=3, window_seconds=10)
    assert [lim.allow("1.2.3.4", now=t) for t in (0, 1, 2)] == [True, True, True]
    assert lim.allow("1.2.3.4", now=3) is False
    assert lim.allow("9.9.9.9", now=3) is True          # other keys are independent
    assert lim.allow("1.2.3.4", now=11) is True         # window slid past the first hit
