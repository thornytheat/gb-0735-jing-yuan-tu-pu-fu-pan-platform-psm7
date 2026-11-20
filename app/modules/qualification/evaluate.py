"""入批裁决：按机台图档来源对参照晶圆形成能否入批的结论。

结论只来自当前归档快照中的参照证据：
- 覆盖核查：参照晶圆的有效位上，该机台留下了多少有效测值、哪些格位没有证据；
- 边缘空位核查：边缘保留带与缺口空位的证据是否关于 X=0 左右成对，防整幅左右翻；
- 测值质量：该机台被隔离的非几何类异常行。

每条判据都回挂快照中的原始行（含机台原始坐标与标准坐标），结论附带证据哈希，
证据一旦变化即可识别为失效。
"""
from decimal import Decimal, ROUND_HALF_UP

from app.errors import ReviewError
from app.manifest import canonical, digest
from app.modules.intake.contract import Geometry
from app.modules.mask.geometry import position

GEOMETRY_CODES = {"OUT_OF_GRID", "OUTSIDE_DISC", "EDGE_EXCLUSION", "NOTCH_VOID"}
EDGE_CODES = {"EDGE_EXCLUSION", "NOTCH_VOID"}
VALID_EVIDENCE_BUCKETS = {"accepted", "duplicate"}
CHECK_ORDER = ("coverage", "edge_void", "measurement")


def _percent(numerator, denominator):
    if denominator == 0:
        return None
    return str((Decimal(numerator) * 100 / Decimal(denominator)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def evidence_hash(snapshot, wafer, source):
    """对该机台在本参照晶圆上的全部原始行与几何参数取摘要。"""
    geometry = snapshot["masks"][wafer]["geometry"]
    rows = [row for row in snapshot["rows"] if row["source"] == source
            and row.get("wafer") in (None, wafer)]
    return digest(canonical([geometry, rows]).encode())


def _source_rows(snapshot, wafer, source):
    return [row for row in snapshot["rows"] if row["source"] == source and row.get("wafer") == wafer]


def _coverage(snapshot, wafer, geometry_model, rows):
    mask = snapshot["masks"][wafer]
    active = {(x, y) for x, y, reason in mask["cells"] if reason == "ACTIVE"}
    by_position = {}
    for row in rows:
        if "transform" not in row or row["bucket"] not in VALID_EVIDENCE_BUCKETS:
            continue
        point = tuple(row["transform"]["canonical"])
        if point in active:
            by_position.setdefault(point, []).append(row)
    covered = set(by_position)
    missing = sorted(active - covered)
    status = "FULL" if covered == active else "NONE" if not covered else "PARTIAL"
    return {
        "status": status,
        "active": len(active),
        "covered": len(covered),
        "coverage_pct": _percent(len(covered), len(active)),
        "missing": [{"x": x, "y": y} for x, y in missing],
        "evidence": [row for point in sorted(covered) for row in by_position[point]],
    }


def _edge_void(snapshot, wafer, geometry_model, rows):
    """边缘空位左右镜像核查：(x, y) 的对称位 (-x, y) 必须同码且有同机台证据。"""
    geo_rows = [row for row in rows if row.get("code") in EDGE_CODES and "transform" in row]
    by_position = {}
    for row in geo_rows:
        by_position.setdefault(tuple(row["transform"]["canonical"]), []).append(row)
    paired, unpaired = [], []
    for point, point_rows in sorted(by_position.items()):
        x, y = point
        mirror = (-x, y)
        same_class = position(geometry_model, *mirror) == point_rows[0]["code"]
        has_counterpart = mirror in by_position
        item = {"x": x, "y": y, "code": point_rows[0]["code"],
                "mirror_x": mirror[0], "mirror_y": mirror[1], "evidence": point_rows}
        if x == 0 or (same_class and has_counterpart):
            paired.append(item)
        else:
            unpaired.append(item)
    if not geo_rows:
        status = "UNVERIFIED"
    elif unpaired:
        status = "FAIL"
    else:
        status = "PASS"
    return {"status": status, "paired": paired, "unpaired": unpaired,
            "evidence": geo_rows}


def _measurement(rows):
    issues = [row for row in rows if row["bucket"] == "isolated" and row["code"] not in GEOMETRY_CODES]
    return {"status": "FAIL" if issues else "PASS", "issues": issues,
            "evidence": issues}


def _verdict(checks):
    if checks["measurement"]["status"] == "FAIL" or checks["edge_void"]["status"] == "FAIL" \
            or checks["coverage"]["status"] == "NONE":
        return "REJECT"
    if checks["coverage"]["status"] != "FULL" or checks["edge_void"]["status"] != "PASS":
        return "HOLD"
    return "ADMIT"


def evaluate(snapshot, wafer, source):
    if wafer not in snapshot["masks"]:
        raise ReviewError("WAFER_NOT_FOUND", "此批次无对应晶圆", 404)
    if not any(record["name"] == source for record in snapshot["transforms"]):
        raise ReviewError("SOURCE_NOT_FOUND", "此批次无对应图档", 404)
    geometry_model = Geometry.model_validate(snapshot["masks"][wafer]["geometry"])
    rows = _source_rows(snapshot, wafer, source)
    checks = {
        "coverage": _coverage(snapshot, wafer, geometry_model, rows),
        "edge_void": _edge_void(snapshot, wafer, geometry_model, rows),
        "measurement": _measurement(rows),
    }
    verdict = _verdict(checks)
    return {"wafer": wafer, "source": source, "verdict": verdict,
            "evidence_sha256": evidence_hash(snapshot, wafer, source),
            "checks": checks, "check_order": list(CHECK_ORDER)}
