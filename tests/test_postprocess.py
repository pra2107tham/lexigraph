"""§3 post-processor: UUID stripping, title dedupe, marker renumbering."""

from app.drafting.postprocess import clean_section
from app.models import Citation

U1 = "9a1f0c2e-1234-4abc-8def-000000000001"
U2 = "9a1f0c2e-1234-4abc-8def-000000000002"


def _cites(n):
    return [Citation(parent_id=f"p{i}", quote=f"q{i}", source_file=f"f{i}.pdf") for i in range(1, n + 1)]


def test_strips_uuid_tokens_all_shapes():
    text = f"Salary is due monthly [{U1}]. Notice period ({U2}) applies. [parent_id: {U1}] End."
    out, _ = clean_section(text, "Terms", [])
    assert U1 not in out and U2 not in out
    assert "Salary is due monthly ." in out  # prose kept


def test_strips_duplicated_leading_title():
    for head in ["## Salary Terms", "**Salary Terms**", "salary terms"]:
        out, _ = clean_section(f"{head}\nBody text.", "Salary Terms", [])
        assert out == "Body text."


def test_keeps_non_title_first_line():
    out, _ = clean_section("Payment obligations vary.\nMore.", "Salary Terms", [])
    assert out.startswith("Payment obligations vary.")


def test_renumbers_markers_and_reorders_citations():
    cites = _cites(3)
    out, ordered = clean_section("A [3] then B [1] then A again [3].", "T", cites)
    assert out == "A [1] then B [2] then A again [1]."
    # citation 3 first, then 1; unreferenced 2 kept at tail
    assert [c.parent_id for c in ordered] == ["p3", "p1", "p2"]


def test_out_of_range_markers_removed():
    out, ordered = clean_section("Claim [1] and bogus [7].", "T", _cites(1))
    assert out == "Claim [1] and bogus ."
    assert len(ordered) == 1


def test_idempotent_on_clean_text():
    cites = _cites(2)
    text = "Fine prose [1] with markers [2]."
    once = clean_section(text, "T", cites)
    again = clean_section(once[0], "T", once[1])
    assert again[0] == once[0]
    assert [c.parent_id for c in again[1]] == [c.parent_id for c in once[1]]
