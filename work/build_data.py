# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
把 data/ 裡的三個 CSV 整理成網頁可以直接載入的 docs/data.js。

用法：
  uv run work/build_data.py

docs/data.js 會設定全域變數 BI_DATA，index.html 用 <script src="data.js"> 載入即可，不需要伺服器。
為了讓檔案小一點，明細列先加總，並把文字換成代碼（在對應清單裡的位置）：
  enrollment 每列：[學期, 系所, 學位別, 性別, 在學人數]
  leave      每列：[學期, 系所, 學位別, 性別, 休學原因, 學期間休學人數, 學期底休學狀態人數]
學院不放在明細列裡，用 depts[系所].college 查。
"""
import csv, json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "data.js"
DEGREES = ["學士", "碩士", "博士"]
GENDERS = ["女", "男"]
CHECK = ("114-1", 10035)  # 核對用：這個學期的在學人數合計


def read(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def main():
    mapping, enroll, leave = read("dept_mapping.csv"), read("enrollment.csv"), read("leave.csv")

    depts = [dict(name=m["dept"], college=m["college"], aliases=[a for a in m["aliases"].split(";") if a])
             for m in mapping]
    college_of = {d["name"]: d["college"] for d in depts}
    for kind, rows in (("enrollment", enroll), ("leave", leave)):
        bad = sorted({(r["dept"], r["college"]) for r in rows if college_of.get(r["dept"]) != r["college"]})
        if bad:
            sys.exit(f"❌ {kind}.csv 的系所／學院和 dept_mapping.csv 對不上：{bad[:5]}")

    semesters = sorted({r["semester"] for r in enroll + leave})
    colleges = list(dict.fromkeys(d["college"] for d in depts))
    # 休學原因依學期間休學人數由多到少排
    by_reason = defaultdict(int)
    for r in leave:
        by_reason[r["reason"]] += int(r["new_leave"])
    reasons = sorted(by_reason, key=lambda k: (-by_reason[k], k))
    reason_group = {r["reason"]: r["reason_group"] for r in leave}

    code = lambda items: {v: i for i, v in enumerate(items)}
    S, D, G, GE, R = code(semesters), code([d["name"] for d in depts]), code(DEGREES), code(GENDERS), code(reasons)

    e_sum = defaultdict(int)
    for r in enroll:
        e_sum[S[r["semester"]], D[r["dept"]], G[r["degree"]], GE[r["gender"]]] += int(r["count"])
    l_sum = defaultdict(lambda: [0, 0])
    for r in leave:
        v = l_sum[S[r["semester"]], D[r["dept"]], G[r["degree"]], GE[r["gender"]], R[r["reason"]]]
        v[0] += int(r["new_leave"])
        v[1] += int(r["on_leave_end"])

    data = dict(
        semesters=semesters,
        colleges=colleges,
        depts=depts,
        degrees=DEGREES,
        genders=GENDERS,
        reasons=[dict(name=k, group=reason_group[k]) for k in reasons],
        leaveSemesters=sorted({r["semester"] for r in leave}),
        enrollmentFields=["semester", "dept", "degree", "gender", "count"],
        leaveFields=["semester", "dept", "degree", "gender", "reason", "newLeave", "onLeaveEnd"],
        enrollment=[[*k, v] for k, v in sorted(e_sum.items())],
        leave=[[*k, *v] for k, v in sorted(l_sum.items())],
    )

    # 核對：加總前後人數一致，且指定學期的在學人數正確
    sem, expect = CHECK
    got = sum(r[-1] for r in data["enrollment"] if r[0] == S[sem])
    checks = [
        (f"{sem} 在學人數合計", got, expect),
        ("在學人數（全部學期）", sum(r[-1] for r in data["enrollment"]), sum(int(r["count"]) for r in enroll)),
        ("學期間休學人數", sum(r[-2] for r in data["leave"]), sum(int(r["new_leave"]) for r in leave)),
        ("學期底休學狀態人數", sum(r[-1] for r in data["leave"]), sum(int(r["on_leave_end"]) for r in leave)),
    ]
    for label, a, b in checks:
        print(f"{'✅' if a == b else '❌'} {label}：data.js {a}，來源 {b}")
    if any(a != b for _, a, b in checks):
        sys.exit("❌ 核對不符，沒有寫出檔案")

    OUT.parent.mkdir(exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(f"// 由 work/build_data.py 產生，請勿手動修改\nwindow.BI_DATA = {body};\n",
                   encoding="utf-8", newline="\n")
    print(f"學期 {len(semesters)}（休學資料 {len(data['leaveSemesters'])}）、學院 {len(colleges)}、系所 {len(depts)}、"
          f"休學原因 {len(reasons)}；在學 {len(enroll)} → {len(data['enrollment'])} 列，"
          f"休學 {len(leave)} → {len(data['leave'])} 列")
    print(f"已寫出 {OUT.relative_to(ROOT)}（{OUT.stat().st_size / 1024:.1f} KB）")


if __name__ == "__main__":
    main()
