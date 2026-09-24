import pytest

from bewerbungdb.api import ApiError, fetch_job


@pytest.mark.parametrize("bad", ["", "../etc", "1/2", "a b", "x?y=1", "a#b", "é", "x" * 65])
def test_invalid_job_ids_rejected_before_any_request(bad):
    # ungültige Adresse: würde bei erlaubter ID einen Verbindungsfehler melden, nicht "ungültig"
    with pytest.raises(ApiError, match="ungültig"):
        fetch_job("https://invalid.invalid", bad, "k")


@pytest.mark.parametrize("ok", ["42", "c876474e3c", "AB-12_cd"])
def test_numeric_and_alphanumeric_ids_accepted(ok):
    with pytest.raises(ApiError) as e:
        fetch_job("https://invalid.invalid", ok, "k")
    assert "ungültig" not in str(e.value)  # scheitert erst bei der Verbindung, nicht an der ID
