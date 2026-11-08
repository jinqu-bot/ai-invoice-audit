"""A 复盘的回归：演示污染、来源误导、202 查询竞态及任务启动失败。"""
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.services import db, history, jobs, store
from test_rules import make_fields, make_extraction
from test_contract import make_png

client = TestClient(app)


def test_mock_and_model_same_number_are_isolated_across_restart():
    fields = make_fields(invoice_number="44190582")
    mock = make_extraction(fields)
    model = mock.model_copy(update={"provider": "openai-compat"})
    a = store.build_batch("B-MOCK", [("a.png", "i1", mock)])
    db.close()
    b = store.build_batch("B-MODEL", [("b.png", "i2", model)])
    assert a.cards[0]["verdict"] == b.cards[0]["verdict"] == "pass"
    assert history.find("44190582")["source"] == "mock-vlm"
    assert history.find("44190582", source="openai-compat")["source"] == "openai-compat"
    c = store.build_batch("B-MODEL2", [("b.png", "i2", model)])
    assert "R1" in c.cards[0]["hit_rule_codes"]
    assert "已报销" not in c.cards[0]["headline"]
    hit = c.details[c.cards[0]["invoice_id"]]["hit_rules"][0]
    assert hit["evidence"]["employee"] == "未登记"


def test_seed_never_rejects_model_invoice():
    ext = make_extraction(make_fields(invoice_number="66472890"))
    ext.provider = "openai-compat"
    batch = store.build_batch("B-SEED", [("a.png", "i", ext)])
    assert "R1" not in batch.cards[0]["hit_rule_codes"]
    assert history.find("66472890")["source"] == "fixture"


def test_legacy_unknown_is_preserved_but_quarantined():
    db.execute("INSERT INTO reimbursements (invoice_number, employee) VALUES (?,?)", ("old-number", "报销人"))
    assert history.find("old-number", source="openai-compat") is None
    assert history.find("old-number") is None
    assert db.one("SELECT * FROM reimbursements WHERE invoice_number='old-number'")
    row = db.one("SELECT * FROM audit_history WHERE invoice_number='old-number'")
    assert row["source"] == "legacy-unknown"
    assert row["employee"] == "未登记"


def test_legacy_mock_stays_mock_even_after_configuration_changes(monkeypatch):
    ext = make_extraction()
    batch = store.build_batch("B-OLD", [("a.png", "i", ext)])
    invoice_id = batch.cards[0]["invoice_id"]
    db.execute("INSERT INTO reimbursements (invoice_number,invoice_id,employee) VALUES (?,?,?)",
               ("legacy-mock", invoice_id, "报销人"))
    monkeypatch.setattr(settings, "vlm_api_key", "test-only")
    monkeypatch.setattr(settings, "vlm_base_url", "http://invalid.local")
    assert history.find("legacy-mock", source="openai-compat") is None
    assert history.find("legacy-mock")["source"] == "mock-vlm"
    payload = batch.details[invoice_id]
    payload.pop("provider")
    db.execute("UPDATE invoices SET payload_json=? WHERE invoice_id=?", (db.dumps(payload), invoice_id))
    assert client.get(f"/api/invoices/{invoice_id}").json()["provider"] == "mock-vlm"


def test_sources_on_api_routes(monkeypatch):
    monkeypatch.setattr(settings, "vlm_api_key", "")
    assert client.get("/api/health").json()["recognition_provider"] == "mock-vlm"
    batch = store.build_batch("B-SOURCE", [("a.png", "i", make_extraction())])
    data = client.get("/api/batches/B-SOURCE/results").json()
    assert data["batch"]["provider"] == data["items"][0]["provider"] == "mock-vlm"
    iid = batch.cards[0]["invoice_id"]
    assert client.get(f"/api/invoices/{iid}").json()["provider"] == "mock-vlm"
    demo = client.post("/api/batches?demo=true").json()
    data = client.get(f"/api/batches/{demo['batch_id']}/results").json()
    assert all(i["provider"] == "fixture" for i in data["items"])
    assert client.get(f"/api/invoices/{data['items'][0]['invoice_id']}").json()["provider"] == "fixture"


def test_batch_exists_before_worker_starts(monkeypatch):
    held = []
    monkeypatch.setattr(jobs, "start_job", lambda task: held.append(task))
    response = client.post("/api/batches", files={"files": ("a.png", make_png(), "image/png")})
    try:
        assert response.status_code == 202
        bid = response.json()["batch_id"]
        result = client.get(f"/api/batches/{bid}/results")
        assert result.status_code == 200
        assert result.json()["batch"]["status"] == "processing"
        assert result.json()["batch"]["invoice_count"] == 1
    finally:
        for task in held: task.close()


def test_worker_start_failure_is_terminal(monkeypatch):
    def fail(task):
        raise RuntimeError("cannot start thread")
    monkeypatch.setattr(jobs, "start_job", fail)
    response = client.post("/api/batches", files={"files": ("a.png", make_png(), "image/png")})
    bid = response.json()["batch_id"]
    assert response.json()["status"] == "failed"
    result = client.get(f"/api/batches/{bid}/results").json()
    assert result["batch"]["status"] == "failed"
    assert result["failures"][0]["code"] == "START_FAILED"
    assert jobs.get(bid).finished
