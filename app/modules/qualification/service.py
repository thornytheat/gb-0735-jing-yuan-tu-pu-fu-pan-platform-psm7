from datetime import datetime, timezone

from app.modules.qualification.evaluate import evaluate


def _stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stored_view(store_decision, current_hash):
    if store_decision is None:
        return None
    view = dict(store_decision)
    view["state"] = "current" if store_decision["evidence_sha256"] == current_hash else "stale"
    return view


class AdmissionService:
    def __init__(self, store):
        self.store = store

    def review(self, run_id, snapshot, wafer, source):
        """重算当前归档下的结论，并回挂同一机台已归档结论（若已失效则标记 stale）。"""
        result = evaluate(snapshot, wafer, source)
        stored = self.store.get_admission(run_id, wafer, source)
        return {**result, "decision": _stored_view(stored, result["evidence_sha256"])}

    def record(self, run_id, snapshot, wafer, source, note=None):
        """形成（或覆盖重算）结论。同批次同机台同晶圆只保留一份，重跑不新增第二份。"""
        result = evaluate(snapshot, wafer, source)
        stored = self.store.get_admission(run_id, wafer, source)
        superseded = bool(stored and stored["evidence_sha256"] != result["evidence_sha256"])
        decision = {**result, "note": (note or "").strip() or None,
                    "run_id": run_id, "recorded_at": _stamp()}
        created = self.store.put_admission(decision)
        return {"decision": decision, "created": created, "superseded": superseded}

    def listing(self, run_id, snapshot):
        stored = {(item["wafer"], item["source"]): item for item in self.store.list_admission(run_id)}
        reviews = []
        for wafer in snapshot["masks"]:
            for record in snapshot["transforms"]:
                source = record["name"]
                result = evaluate(snapshot, wafer, source)
                reviews.append({**result, "decision": _stored_view(stored.get((wafer, source)),
                                                                   result["evidence_sha256"])})
        return reviews
