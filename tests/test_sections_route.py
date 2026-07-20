"""GET /jobs/{id}/sections serves legacy UUID-soup rows clean (read-time repair)."""

UUID = "9a1f0c2e-1234-4abc-8def-00000000aaaa"


def test_legacy_row_served_clean(client, fake_db):
    from app.stores import mongo

    job_id = "job-1"
    sec_id = "sec-1"
    mongo.jobs().insert_one(
        {
            "_id": job_id,
            "status": "done",
            "document": "x",
            "outline": {"sections": [{"section_id": sec_id, "title": "Salary Terms"}]},
        }
    )
    mongo.drafted_sections().insert_one(
        {
            "job_id": job_id,
            "section_id": sec_id,
            "title": "Salary Terms",
            "text": f"## Salary Terms\nPay is monthly [{UUID}]. Backed claim [1].",
            "citations": [{"parent_id": "p1", "quote": "paid monthly"}],
            "needs_review": False,
        }
    )

    res = client.get(f"/jobs/{job_id}/sections")
    assert res.status_code == 200
    sec = res.json()["sections"][0]
    assert UUID not in sec["text"]
    assert not sec["text"].startswith("## Salary Terms")
    assert sec["text"].endswith("Backed claim [1].")
    # legacy citations parse with the new optional fields defaulted
    assert sec["citations"][0]["source_file"] == ""
    assert sec["citations"][0]["verified"] is None
