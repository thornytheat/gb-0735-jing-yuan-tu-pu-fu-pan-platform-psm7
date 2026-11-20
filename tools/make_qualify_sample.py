"""生成入批裁决演示样例 sample_data/qualify.*。

旧机台 old-probe.csv 跑完整片参照晶圆 W-05（含对称的边缘带与缺口行）；
新机台 new-probe.csv 只跑完东半片（x >= 1），边缘与缺口均无证据。
两个来源使用不同原点、轴向与镜像，机台原始坐标在归档中逐行保留。
本脚本仅为样例造数工具，业务代码不依赖它。
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sample_data"

RADIUS = 5
EDGE = 1
NOTCH_DEPTH = 2
NOTCH_HALF_WIDTH = 1

OLD_SOURCE = {"name": "old-probe.csv", "origin_x": 120, "origin_y": 340,
              "notch": "N", "x_left": False, "y_down": True, "mirror": False}
NEW_SOURCE = {"name": "new-probe.csv", "origin_x": 700, "origin_y": 880,
              "notch": "E", "x_left": False, "y_down": True, "mirror": True}

VECTOR = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
TURNS = {(0, -1): 0, (-1, 0): 1, (0, 1): 2, (1, 0): 3}


def position(x, y):
    r2 = x * x + y * y
    if max(abs(x), abs(y)) > RADIUS or r2 > RADIUS * RADIUS:
        return "OUTSIDE_DISC"
    if NOTCH_DEPTH and y <= -RADIUS + NOTCH_DEPTH and abs(x) <= NOTCH_HALF_WIDTH:
        return "NOTCH_VOID"
    if r2 > (RADIUS - EDGE) ** 2:
        return "EDGE_EXCLUSION"
    return "ACTIVE"


def inverse_raw(source, cx, cy):
    """normalize() 的逆运算：由标准坐标反推机台原始坐标。"""
    nx, ny = VECTOR[source["notch"]]
    turns = TURNS[(-nx if source["mirror"] else nx, ny)]
    mx, my = cx, cy
    for _ in range(turns):  # 反向旋转（顺时针）
        mx, my = my, -mx
    dx = -mx if source["mirror"] else mx
    dy = my
    raw_x = source["origin_x"] + dx * (-1 if source["x_left"] else 1)
    raw_y = source["origin_y"] + dy * (-1 if source["y_down"] else 1)
    return raw_x, raw_y


def write_probe(source, points):
    path = OUT / source["name"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["wafer", "x", "y", "attempt", "result", "bin", "note"])
        for cx, cy in points:
            raw_x, raw_y = inverse_raw(source, cx, cy)
            writer.writerow(["W-05", raw_x, raw_y, 1, "PASS", 1, ""])
    return len(points)


def main():
    grid = [(x, y) for y in range(RADIUS, -RADIUS - 1, -1) for x in range(-RADIUS, RADIUS + 1)]
    active = [p for p in grid if position(*p) == "ACTIVE"]
    edge = [p for p in grid if position(*p) == "EDGE_EXCLUSION"]
    notch = [p for p in grid if position(*p) == "NOTCH_VOID"]

    # 旧机台：整片有效位 + 左右成对的边缘带行 + 缺口行（含左右对称位）
    old_edge = [p for p in edge if p in {(5, 0), (-5, 0), (4, 3), (-4, 3), (3, 4), (-3, 4), (0, 5)}]
    old_points = active + old_edge + notch
    old_count = write_probe(OLD_SOURCE, old_points)

    # 新机台：只跑东半片有效位，边缘与缺口留空
    new_points = [p for p in active if p[0] >= 1]
    new_count = write_probe(NEW_SOURCE, new_points)

    contract = {
        "sample": "qualify",
        "label": "入批参照半片样例",
        "lot": "FT26-Q05",
        "sources": [
            {**OLD_SOURCE, "records": old_count},
            {**NEW_SOURCE, "records": new_count},
        ],
        "wafers": [{
            "wafer": "W-05", "radius": RADIUS, "edge": EDGE,
            "notch_depth": NOTCH_DEPTH, "notch_half_width": NOTCH_HALF_WIDTH,
        }],
        "ledger": [],
    }
    (OUT / "qualify.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"active": len(active), "edge": len(edge), "notch": len(notch),
                      "old_records": old_count, "new_records": new_count,
                      "east_half_active": len(new_points)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
