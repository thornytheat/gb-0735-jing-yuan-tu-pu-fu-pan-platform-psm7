from concurrent.futures import ThreadPoolExecutor

from app.manifest import canonical


def test_admission_overview_distinguishes_hold_and_admit(client):
    run_id = client.post("/api/runs", json={"sample": "qualify"}).json()["manifest"]["run_id"]
    reviews = client.get(f"/api/runs/{run_id}/admission").json()["reviews"]
    verdicts = {item["source"]: item for item in reviews}
    assert verdicts["old-probe.csv"]["verdict"] == "ADMIT"
    assert verdicts["new-probe.csv"]["verdict"] == "HOLD"
    assert all(item["decision"] is None for item in reviews)


def test_record_is_upsert_and_rerun_never_creates_a_second_decision(client):
    run_id = client.post("/api/runs", json={"sample": "qualify"}).json()["manifest"]["run_id"]
    url = f"/api/runs/{run_id}/admission/decisions"
    payload = {"wafer": "W-05", "source": "new-probe.csv", "note": "等满片"}
    first = client.post(url, json=payload)
    assert first.status_code == 201 and first.json()["created"] is True
    second = client.post(url, json=payload)
    body = second.json()
    assert second.status_code == 201 and body["created"] is False
    assert body["decision"]["note"] == "等满片"
    # 重跑同一批次后再次形成结论，仍然只有一份
    client.post(f"/api/runs/{run_id}/rerun")
    third = client.post(url, json=payload).json()
    assert third["created"] is False
    stored = [item for item in client.get(f"/api/runs/{run_id}/admission").json()["reviews"]
              if item["source"] == "new-probe.csv"][0]["decision"]
    assert stored is not None and stored["state"] == "current"
    rows = client.app.state.runs.store.list_admission(run_id)
    assert len(rows) == 1


def test_stored_decision_goes_stale_once_reference_evidence_changes(client):
    run_id = client.post("/api/runs", json={"sample": "qualify"}).json()["manifest"]["run_id"]
    base = f"/api/runs/{run_id}"
    client.post(base + "/admission/decisions", json={"wafer": "W-05", "source": "new-probe.csv"})
    review = client.get(base + "/admission/review",
                        params={"wafer": "W-05", "source": "new-probe.csv"}).json()
    assert review["decision"]["state"] == "current"
    # 直接篡改归档快照中的参照行，模拟证据变化
    store = client.app.state.runs.store
    manifest, snapshot, pinned = store.get(run_id)
    for row in snapshot["rows"]:
        if row.get("source") == "new-probe.csv" and row.get("bucket") == "accepted":
            row["raw"] = [*row["raw"], "changed"]
            break
    with store.connect() as connection:
        connection.execute("UPDATE wafer_runs SET snapshot = ? WHERE run_id = ?",
                           (canonical(snapshot), run_id))
    stale = client.get(base + "/admission/review",
                       params={"wafer": "W-05", "source": "new-probe.csv"}).json()
    assert stale["decision"]["state"] == "stale"
    assert stale["evidence_sha256"] != stale["decision"]["evidence_sha256"]


def test_recomputing_after_stale_evidence_supersedes_without_duplicate(client):
    run_id = client.post("/api/runs", json={"sample": "qualify"}).json()["manifest"]["run_id"]
    base = f"/api/runs/{run_id}"
    payload = {"wafer": "W-05", "source": "new-probe.csv"}
    client.post(base + "/admission/decisions", json=payload)
    store = client.app.state.runs.store
    manifest, snapshot, pinned = store.get(run_id)
    original_hash = next(iter(store.list_admission(run_id)))["evidence_sha256"]
    for row in snapshot["rows"]:
        if row.get("source") == "new-probe.csv" and row.get("bucket") == "accepted":
            row["raw"] = [*row["raw"], "changed"]
            break
    with store.connect() as connection:
        connection.execute("UPDATE wafer_runs SET snapshot = ? WHERE run_id = ?",
                           (canonical(snapshot), run_id))
    reply = client.post(base + "/admission/decisions", json=payload).json()
    assert reply["created"] is False and reply["superseded"] is True
    decisions = store.list_admission(run_id)
    assert len(decisions) == 1 and decisions[0]["evidence_sha256"] != original_hash
    refreshed = client.get(base + "/admission/review",
                           params={"wafer": "W-05", "source": "new-probe.csv"}).json()
    assert refreshed["decision"]["state"] == "current"


def test_admission_evidence_keeps_machine_raw_coordinates(client):
    run_id = client.post("/api/runs", json={"sample": "qualify"}).json()["manifest"]["run_id"]
    review = client.get(f"/api/runs/{run_id}/admission/review",
                        params={"wafer": "W-05", "source": "new-probe.csv"}).json()
    row = review["checks"]["coverage"]["evidence"][0]
    assert row["fields"]["x"] and row["fields"]["y"]
    assert row["transform"]["canonical"]
    # 坐标对表接口同样能按图档查回旧/新机台的原始坐标
    coordinates = client.get(f"/api/runs/{run_id}/coordinates").json()["rows"]
    sources = {row["source"] for row in coordinates}
    assert {"old-probe.csv", "new-probe.csv"} <= sources


def test_admission_page_renders_with_native_controls(client):
    response = client.get("/admission")
    assert response.status_code == 200
    assert "<h1>入批裁决</h1>" in response.text
    assert 'id="admission-rows"' in response.text and 'id="admission-evidence"' in response.text


def test_admission_validation_rejects_unknown_source(client):
    run_id = client.post("/api/runs", json={"sample": "qualify"}).json()["manifest"]["run_id"]
    response = client.post(f"/api/runs/{run_id}/admission/decisions",
                           json={"wafer": "W-05", "source": "nope.csv"})
    assert response.status_code == 404 and response.json()["code"] == "SOURCE_NOT_FOUND"


def test_parallel_decisions_commit_one_row(client):
    run_id = client.post("/api/runs", json={"sample": "qualify"}).json()["manifest"]["run_id"]
    service = client.app.state.admission
    store = client.app.state.runs.store
    _, snapshot, _ = store.get(run_id)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _: service.record(run_id, snapshot, "W-05", "new-probe.csv"), range(4)))
    assert sum(item["created"] for item in results) == 1
    assert len(store.list_admission(run_id)) == 1
