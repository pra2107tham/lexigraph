"""§4 evaluator: Tier-1 quote verification + Tier-2 batched entailment."""

from app.drafting.evaluator import evaluate_draft, extract_claims, quote_in_parent
from app.models import Citation, DraftedSection, ParentChunk

PARENT = ParentChunk(
    parent_id="p1",
    mongo_doc_id="d1",
    source_file="letter.pdf",
    text="The employee shall be paid a salary of INR 12,00,000 per annum. "
    "The notice period is sixty (60) days from written notice.",
)


def _section(text, cites):
    return DraftedSection(section_id="s1", text=text, citations=cites)


def _cite(quote, parent_id="p1"):
    return Citation(parent_id=parent_id, quote=quote, source_file="letter.pdf")


# ---- Tier 1: quote_in_parent -------------------------------------------------

def test_exact_match_normalized():
    assert quote_in_parent("salary of INR 12,00,000  per annum", PARENT.text)


def test_fuzzy_match_tolerates_typos():
    assert quote_in_parent("notice period is sixty (60) dayss from writen notice", PARENT.text)


def test_fabricated_quote_fails():
    assert not quote_in_parent("employee owns all intellectual property", PARENT.text)


# ---- claim extraction --------------------------------------------------------

def test_extract_claims_maps_marker_to_sentence():
    claims = extract_claims("Salary is 12LPA [1]. Notice is 60 days [2].", 2)
    assert claims[1] == "Salary is 12LPA ."
    assert "Notice is 60 days" in claims[2]


def test_extract_claims_ignores_out_of_range():
    assert 7 not in extract_claims("Bogus [7].", 2)


# ---- evaluate_draft ----------------------------------------------------------

def test_no_citations_fails():
    assert not evaluate_draft(_section("text", []), {}).eval_ok


def test_wrong_parent_id_is_tier1_failure():
    report = evaluate_draft(_section("Claim [1].", [_cite("salary", "ghost")]), {"p1": PARENT})
    assert not report.eval_ok
    assert report.tier1_failed[0]["reason"] == "parent_id is not a retrieved source"


def test_fabricated_quote_is_tier1_failure():
    report = evaluate_draft(_section("Claim [1].", [_cite("owns all IP")]), {"p1": PARENT})
    assert not report.eval_ok
    assert report.tier1_failed[0]["index"] == 1


def test_ratio_thresholding():
    cites = [_cite("paid a salary") for _ in range(5)]
    text = "A [1]. B [2]. C [3]. D [4]. E [5]."
    by_id = {"p1": PARENT}
    ok_4_of_5 = evaluate_draft(_section(text, cites), by_id, check=lambda p: [True, True, True, True, False])
    assert ok_4_of_5.eval_ok and ok_4_of_5.unverified == [5]
    fail_3_of_5 = evaluate_draft(_section(text, cites), by_id, check=lambda p: [True, True, True, False, False])
    assert not fail_3_of_5.eval_ok


def test_markerless_citation_unverified_but_excluded_from_ratio():
    cites = [_cite("paid a salary"), _cite("notice period")]
    report = evaluate_draft(_section("Only one claim [1].", cites), {"p1": PARENT}, check=lambda p: [True] * len(p))
    assert report.eval_ok  # ratio computed over markered claims only
    assert report.unverified == [2]
    assert report.citations[0]["verified"] == "quote_verified"
    assert report.citations[1]["verified"] == "unverified"


def test_f4_regression_multi_source_section_passes():
    """v1 judged the WHOLE section against ONE source 'alone' -> guaranteed fail.
    v2: a section citing many genuine sources passes."""
    p2 = ParentChunk(parent_id="p2", mongo_doc_id="d1", source_file="msa.pdf", text="Payment terms are Net 30 days.")
    cites = [_cite("paid a salary"), _cite("Net 30 days", "p2")]
    report = evaluate_draft(
        _section("Salary applies [1]. Payment is Net 30 [2].", cites),
        {"p1": PARENT, "p2": p2},
        check=lambda pairs: [True] * len(pairs),
    )
    assert report.eval_ok and report.unverified == []
