# /// script
# requires-python = ">=3.10"
# dependencies = ["xlrd"]
# ///
"""
把 114-1 在學生人數統計表（.xls）的第一個工作表，轉成整齊的 CSV。

用法：
  uv run work/etl_enrollment.py

輸出 work/enrollment_114-1.csv（UTF-8 with BOM），每列是「系所 × 學制 × 性別」。
"""
import csv, re, sys
from os.path import commonprefix
from pathlib import Path
import xlrd

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "東華大學統計資料" / "在學人數統計表"
OUT = ROOT / "work" / "enrollment_114-1.csv"
SEM = "114-1"

# 區段標題列（例如「碩專班 合計3」）→ 學制。碩專班區段的學制別欄是空的，所以學制一律看區段標題。
SECTION = {"博士班": "博士班", "碩士班": "碩士班", "碩專班": "碩士在職專班", "學士班": "學士班"}
C_COLLEGE, C_DEPT, C_GROUP = 1, 2, 3

clean = lambda v: re.sub(r"\s+", "", str(v))
strip_note = lambda s: re.sub(r"[（(].*?[)）]", "", s).strip()
num = lambda v: int(v) if v != "" else 0


def merged_lookup(sh, col):
    """回傳 {列: 合併範圍第一列}，只看指定欄的直向合併。"""
    top = {}
    for r0, r1, c0, c1 in sh.merged_cells:
        if c0 <= col < c1:
            for r in range(r0, r1):
                top[r] = r0
    return top


def main():
    src = sorted(SRC_DIR.glob(f"{SEM}*.xls"))
    if len(src) != 1:
        sys.exit(f"找不到唯一的 {SEM} .xls：{src}")
    sh = xlrd.open_workbook(src[0], formatting_info=True).sheet_by_index(0)
    cell = lambda r, c: clean(sh.cell_value(r, c))

    # 「總計」底下的女、男欄
    hdr = next(r for r in range(sh.nrows) if "總計" in sh.row_values(r)[1:])
    c_total = sh.row_values(hdr).index("總計")
    sub = [clean(v) for v in sh.row_values(hdr + 1)]
    c_f, c_m = sub.index("女", c_total), sub.index("男", c_total)

    dept_top = merged_lookup(sh, C_DEPT)

    # 先收集資料列，學院往下填滿
    rows, program, college = [], None, ""
    for r in range(hdr + 2, sh.nrows):
        head = cell(r, 0)
        if head.startswith("備註"):
            break
        m = re.match(r"(.+?)合計\d*$", head)
        if m:
            program = SECTION[m.group(1)]
            continue
        if head.startswith("總計") or program is None or not cell(r, C_GROUP):
            continue
        college = strip_note(cell(r, C_COLLEGE)) or college
        rows.append(dict(r=r, program=program, college=college, dept=cell(r, C_DEPT),
                         group=cell(r, C_GROUP), f=num(sh.cell_value(r, c_f)), m=num(sh.cell_value(r, c_m))))

    # 系所往下填滿。系所格空白又不在任何合併範圍內的列，是報表合併範圍畫歪了：
    # 分組名稱和下一列比較像，就歸到下一個系所（114-1 物理學系博士班的第一個分組）。
    for i, row in enumerate(rows):
        if row["dept"]:
            continue
        prev = rows[i - 1]
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        same = lambda o: len(commonprefix([row["group"], o["group"]]))
        orphan = row["r"] not in dept_top
        if (orphan and nxt and nxt["dept"] and nxt["program"] == row["program"]
                and same(nxt) >= 2 and same(nxt) > same(prev)):
            row["dept"] = nxt["dept"]
        else:
            row["dept"] = prev["dept"]

    # 同一系所、同一學制的多個分組加總
    agg = {}
    for row in rows:
        key = (row["college"], row["dept"], row["program"])
        f, m = agg.get(key, (0, 0))
        agg[key] = (f + row["f"], m + row["m"])

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["college", "dept_raw", "program_raw", "gender", "count"])
        for (college, dept, program), (f, m) in agg.items():
            w.writerow([college, dept, program, "女", f])
            w.writerow([college, dept, program, "男", m])
    total = sum(f + m for f, m in agg.values())
    print(f"讀取 {src[0].name}：{len(rows)} 個資料列 → {len(agg) * 2} 列，總人數 {total}")
    print(f"已寫出 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
