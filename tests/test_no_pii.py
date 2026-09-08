"""Static guard: the read-only query methods must never select PII/free-text
comment columns. This greps the SQL literals in client.py rather than running
against a live DB — a regression tripwire for the next edited query, not a
runtime filter (there's nothing dynamic to filter; every query is a fixed
string)."""

from pathlib import Path

_BANNED_TOKENS = (
    "patient_identifier",
    "name_external",
    "year_of_birth",
    "sender_id",
    "receiver_id",
    "sample.comment",
    "s.comment",
    "processed_sample.comment",
    "ps.comment",
    "report_configuration_variant.comment",
    "rcv.comment",
    "report_configuration_cnv.comment",
    "rcc.comment",
    "report_configuration_sv.comment",
    "rcs.comment",
    "report_configuration_re.comment",
    "rcr.comment",
    "report_configuration_other_causal_variant.comment",
)

# variant_classification.comment/vc.comment is a deliberate exception,
# intentionally not in _BANNED_TOKENS: it's the ACMG rationale, the whole
# point of get_variant_classification.


def test_no_pii_or_comment_columns_in_queries() -> None:
    source = Path(__file__).parent.parent.joinpath("src/ngsd_api/client.py").read_text()
    for token in _BANNED_TOKENS:
        assert token not in source, f"banned column reference found in client.py: {token!r}"


if __name__ == "__main__":
    test_no_pii_or_comment_columns_in_queries()
    print("ok")
