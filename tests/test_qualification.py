import pytest

from app.modules.intake.catalog import load_sample
from app.modules.qualification.evaluate import evaluate
from app.modules.runs.pipeline import calculate


@pytest.fixture(scope="module")
def snapshot():
    return calculate(load_sample("qualify"))


def test_full_reference_old_machine_admits_with_symmetric_edge_evidence(snapshot):
    review = evaluate(snapshot, "W-05", "old-probe.csv")
    assert review["verdict"] == "ADMIT"
    coverage = review["checks"]["coverage"]
    assert coverage["status"] == "FULL" and coverage["missing"] == []
    assert coverage["covered"] == coverage["active"] == 45
    edge = review["checks"]["edge_void"]
    assert edge["status"] == "PASS" and edge["unpaired"] == [] and edge["paired"]
    assert review["checks"]["measurement"]["status"] == "PASS"


def test_half_run_new_machine_holds_and_lists_every_position_without_evidence(snapshot):
    review = evaluate(snapshot, "W-05", "new-probe.csv")
    assert review["verdict"] == "HOLD"
    coverage = review["checks"]["coverage"]
    assert coverage["status"] == "PARTIAL" and coverage["covered"] == 19
    assert len(coverage["missing"]) == 26
    assert all(point["x"] < 1 for point in coverage["missing"])
    assert review["checks"]["edge_void"]["status"] == "UNVERIFIED"


def test_every_check_cites_original_rows_with_raw_and_canonical_coordinates(snapshot):
    review = evaluate(snapshot, "W-05", "old-probe.csv")
    rows = review["checks"]["coverage"]["evidence"]
    assert rows and all(row["source"] == "old-probe.csv" for row in rows)
    first = rows[0]
    assert {"line", "end_line", "raw", "fields", "transform"} <= set(first)
    assert first["fields"]["x"] and first["fields"]["y"]
    assert first["transform"]["canonical"]
    edge_rows = review["checks"]["edge_void"]["evidence"]
    assert {row["code"] for row in edge_rows} == {"EDGE_EXCLUSION", "NOTCH_VOID"}


def test_evidence_hash_changes_when_reference_rows_change(snapshot):
    before = evaluate(snapshot, "W-05", "new-probe.csv")["evidence_sha256"]
    altered = dict(snapshot)
    altered_rows = [dict(row) for row in snapshot["rows"]]
    for row in altered_rows:
        if row.get("source") == "new-probe.csv" and row.get("bucket") == "accepted":
            row["raw"] = [*row["raw"], "tampered"]
            break
    altered["rows"] = altered_rows
    after = evaluate(altered, "W-05", "new-probe.csv")["evidence_sha256"]
    assert after != before


def test_geometry_isolation_is_not_a_measurement_failure(snapshot):
    review = evaluate(snapshot, "W-05", "old-probe.csv")
    assert review["checks"]["measurement"]["issues"] == []
    assert {row["code"] for row in review["checks"]["edge_void"]["evidence"]} <= {"EDGE_EXCLUSION", "NOTCH_VOID"}


def test_unknown_wafer_and_source_raise_explicit_errors(snapshot):
    from app.errors import ReviewError
    with pytest.raises(ReviewError) as wafer_error:
        evaluate(snapshot, "W-99", "old-probe.csv")
    assert wafer_error.value.code == "WAFER_NOT_FOUND"
    with pytest.raises(ReviewError) as source_error:
        evaluate(snapshot, "W-05", "missing.csv")
    assert source_error.value.code == "SOURCE_NOT_FOUND"


def test_measurement_isolation_or_asymmetric_edge_forces_reject(snapshot):
    # 拆掉旧机台的一条边缘隔离行，制造左右不成对
    broken = dict(snapshot)
    broken["rows"] = [row for row in snapshot["rows"]
                      if not (row.get("source") == "old-probe.csv" and row.get("code") == "EDGE_EXCLUSION"
                              and tuple(row["transform"]["canonical"]) == (5, 0))]
    review = evaluate(broken, "W-05", "old-probe.csv")
    assert review["verdict"] == "REJECT"
    assert review["checks"]["edge_void"]["status"] == "FAIL"
    assert any(item["x"] == -5 for item in review["checks"]["edge_void"]["unpaired"])


def test_no_evidence_at_all_is_reject_rather_than_hold():
    snapshot = calculate(load_sample("qualify"))
    emptied = dict(snapshot)
    emptied["rows"] = [row for row in snapshot["rows"] if row.get("source") != "new-probe.csv"]
    review = evaluate(emptied, "W-05", "new-probe.csv")
    assert review["checks"]["coverage"]["status"] == "NONE"
    assert review["verdict"] == "REJECT"
