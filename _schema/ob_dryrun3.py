# -*- coding: utf-8 -*-
"""②-3 드라이런 최종안 — 목표잔액 = MAX(레거시, 0)  (대표 지시 2026-09-06)
   조회 전용. INSERT 없음.

   조정수량 = 목표잔액 − 원장파생잔액
     · 레거시가 음수면 목표는 0 (음수 재고를 웹에 복제하지 않는다)
     · 레거시 0인데 원장에 값이 있으면 목표 0 → 마이너스 조정으로 눌러 0
"""
import sys, csv, os
sys.path.insert(0, r"c:\Users\박근민\Desktop\New_ERP")
import db_client

OUT = r"C:\Users\박근민\AppData\Local\Temp\claude\c--Users-----Desktop-NEW-ERP-1--schema\0d811a39-bd77-4b27-83f9-16f3733d6289\scratchpad"
cn = db_client.get_connection(); cur = cn.cursor()

SPECS = {
"MAT": ("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))), SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.PU_T_MAT_STOCK_WH WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,''))))""",
        """SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))), SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='MAT' AND ISNULL(MAT_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,''))))""",
        ("mat_code","gagong_proc_code")),
"PRD": ("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(PART_CODE,'')))), SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.PR_T_MAT_STOCK_WH WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(PART_CODE,''))))""",
        """SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))), SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='PRD' AND ISNULL(MAT_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,''))))""",
        ("mat_code","part_code")),
"ASY": ("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), '', SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.SA_T_ITEM_STOCK WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))""",
        """SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), '', SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='ASY' AND ISNULL(ITEM_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))""",
        ("item_code","-")),
"RDY": ("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(ISNULL(PROC_GUBUN,'')))), SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.PU_T_READY_STOCK WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(ISNULL(PROC_GUBUN,''))))""",
        """SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))), SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='RDY' AND ISNULL(ITEM_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,''))))""",
        ("item_code","proc_gubun")),
"SAG": ("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(CUST_CODE,'')))), SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.PU_T_SAGUB_STOCK WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(CUST_CODE,''))))""",
        """SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(CUST_CODE,'')))), SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='SAG' AND ISNULL(MAT_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(CUST_CODE,''))))""",
        ("mat_code","cust_code")),
}

def load(sql):
    cur.execute(sql)
    return {(str(r[0] or '').strip(), str(r[1] or '').strip()): float(r[2] or 0) for r in cur.fetchall()}

print(f"{'POINT':<6}{'조정행':>8}{'레거시원값':>15}{'목표(음수0)':>15}{'원장현재':>15}{'조정합':>15}{'음수→0':>8}")
print("-" * 82)
tot = 0; tadj = 0.0
for pt, (lsql, nsql, klab) in SPECS.items():
    lv, nx = load(lsql), load(nsql)
    rows = []; nneg = 0
    for k in sorted(set(lv) | set(nx)):
        raw = lv.get(k, 0.0)
        tgt = raw if raw > 0 else 0.0          # ★음수는 0으로
        if raw < 0: nneg += 1
        n = nx.get(k, 0.0)
        d = round(tgt - n, 4)
        if abs(d) > 0.0001:
            rows.append((k[0], k[1], raw, tgt, n, d))
    dsum = sum(r[5] for r in rows)
    print(f"{pt:<6}{len(rows):>8,}{sum(lv.values()):>15,.1f}"
          f"{sum(max(v,0.0) for v in lv.values()):>15,.1f}{sum(nx.values()):>15,.1f}{dsum:>15,.1f}{nneg:>8,}")
    with open(os.path.join(OUT, f"ob3_{pt}.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([klab[0], klab[1], "legacy_raw", "target_qty", "ledger_qty", "adjust_qty"])
        w.writerows(rows)
    tot += len(rows); tadj += dsum
print("-" * 82)
print(f"{'합계':<6}{tot:>8,}{'':>15}{'':>15}{'':>15}{tadj:>15,.1f}")
