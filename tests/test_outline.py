"""B1 corpus-aware outline: doc abstracts + relevant passages feed the prompt,
source_files propagate, and abstract failures never break ingestion."""

from app.models import ParentChunk


class _StubModel:
    def __init__(self, parsed):
        self.parsed = parsed
        self.messages = None

    def call(self, messages, format=None):  # noqa: A002
        self.messages = messages
        parsed = self.parsed
        return type("R", (), {"parse": staticmethod(lambda: parsed)})


def test_outline_includes_corpus_context_and_source_files(monkeypatch, fake_db):
    import app.drafting.outline as outline_mod
    from app.stores import mongo

    mongo.documents().insert_one(
        {"_id": "d1", "session_id": "sess-1", "source_file": "letter.pdf",
         "abstract": "An appointment letter."})
    monkeypatch.setattr(
        outline_mod, "retrieve",
        lambda prompt, top_n=8, session_id=None: [
            ParentChunk(parent_id="p1", mongo_doc_id="d1", source_file="letter.pdf",
                        text="Salary is 12 LPA per annum.")])

    stub = _StubModel(outline_mod._OutlineDraft(sections=[
        outline_mod._OutlineDraft._Section(
            title="Salary", instructions="cover salary", source_files=["letter.pdf"])]))
    monkeypatch.setattr(outline_mod, "_model", lambda: stub)

    outline = outline_mod.generate_outline("job-1", "Summarize the letter", session_id="sess-1")

    user_text = str(stub.messages[1])
    assert "AVAILABLE DOCUMENTS" in user_text and "letter.pdf: An appointment letter." in user_text
    assert "RELEVANT PASSAGES" in user_text and "Salary is 12 LPA" in user_text
    assert outline.sections[0].source_files == ["letter.pdf"]


def test_outline_without_corpus_has_no_context_block(monkeypatch, fake_db):
    import app.drafting.outline as outline_mod

    stub = _StubModel(outline_mod._OutlineDraft(sections=[]))
    monkeypatch.setattr(outline_mod, "_model", lambda: stub)
    outline_mod.generate_outline("job-1", "Draft an MSA")  # no session
    assert "AVAILABLE DOCUMENTS" not in str(stub.messages[1])


def test_summarize_doc_failure_degrades_to_empty(monkeypatch):
    import app.drafting.llm as llm

    monkeypatch.setattr(llm, "_model", lambda: (_ for _ in ()).throw(RuntimeError("no key")))
    parent = ParentChunk(parent_id="p", mongo_doc_id="d", source_file="f.pdf", text="x")
    assert llm.summarize_doc([parent]) == ""
    assert llm.summarize_doc([]) == ""


def test_ingest_stores_abstract(monkeypatch, fake_db):
    import app.ingestion.pipeline as pipeline
    from app.stores import mongo

    monkeypatch.setattr(pipeline, "summarize_doc", lambda parents: "A short abstract.")
    parent = ParentChunk(parent_id="p1", mongo_doc_id="d1", source_file="f.pdf", text="x")
    pipeline._persist_truth("d1", "f.pdf", [], [parent], session_id="sess-1")
    doc = mongo.documents().find_one({"_id": "d1"})
    assert doc["abstract"] == "A short abstract." and doc["session_id"] == "sess-1"
