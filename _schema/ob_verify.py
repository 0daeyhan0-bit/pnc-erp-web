# -*- coding: utf-8 -*-
"""④ 검증 — 적재 후 원장 파생잔량이 목표(MAX(레거시,0))와 일치하는가 (조회 전용)"""
import sys
sys.path.insert(0, r"c:\Users\박근민\Desktop\New_ERP")
import db_client
cn = db_client.get_connection(); cur = cn.cursor()

SPECS = {
"MAT": ("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))), SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.PU_T_MAT_STOCK_WH WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,''))))""",
        """SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))), SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='MAT' AND ISNULL(MAT_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,''))))"""),
"PRD": ("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(PART_CODE,'')))), SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.PR_T_MAT_STOCK_WH WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(PART_CODE,''))))""",
        """SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))), SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='PRD' AND ISNULL(MAT_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,''))))"""),
"ASY": ("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), '', SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.SA_T_ITEM_STOCK WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))""",
        """SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), '', SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='ASY' AND ISNULL(ITEM_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))"""),
"RDY": ("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(ISNULL(PROC_GUBUN,'')))), SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.PU_T_READY_STOCK WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(ISNULL(PROC_GUBUN,''))))""",
        """SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))), SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='RDY' AND ISNULL(ITEM_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,''))))"""),
"SAG": ("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(CUST_CODE,'')))), SUM(STOCK_QTY)
             FROM PARTNER_ERP.dbo.PU_T_SAGUB_STOCK WITH(NOLOCK)
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(CUST_CODE,''))))""",
        """SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(CUST_CODE,'')))), SUM(MAINT_QTY)
             FROM nx.stock_ledger WITH(NOLOCK)
            WHERE STOCK_POINT='SAG' AND ISNULL(MAT_CODE,'')<>''
            GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), UPPER(LTRIM(RTRIM(ISNULL(CUST_CODE,''))))"""),
}

def load(sql):
    cur.execute(sql)
    return {(str(r[0] or '').strip(), str(r[1] or '').strip()): float(r[2] or 0) for r in cur.fetchall()}

print(f"{'POINT':<6}{'목표합':>16}{'원장합':>16}{'차이':>14}{'불일치키':>10}  판정")
print("-" * 74)
allok = True
for pt, (lsql, nsql) in SPECS.items():
    lv, nx = load(lsql), load(nsql)
    bad = []
    for k in set(lv) | set(nx):
        tgt = max(lv.get(k, 0.0), 0.0)
        got = nx.get(k, 0.0)
        if abs(tgt - got) > 0.0001:
            bad.append((k, tgt, got))
    tsum = sum(max(v, 0.0) for v in lv.values())
    gsum = sum(nx.values())
    ok = (len(bad) == 0)
    allok &= ok
    print(f"{pt:<6}{tsum:>16,.1f}{gsum:>16,.1f}{gsum-tsum:>+14,.1f}{len(bad):>10,}  {'OK diff0' if ok else '!! 불일치'}")
    for k, t, g in bad[:5]:
        print(f"        {k[0]:<26}{k[1]:<10} 목표 {t:>12,.1f} / 원장 {g:>12,.1f}")

print("-" * 74)
print("전체:", "★ 5개 재고점 전부 목표와 일치 (diff 0)" if allok else "!! 불일치 존재")

print()
cur.execute("""SELECT STOCK_POINT, COUNT(*), SUM(MAINT_QTY) FROM nx.stock_ledger WITH(NOLOCK)
               WHERE MAINT_TAG='OB' AND LTRIM(RTRIM(INSERT_USER_ID))='GOLIVE'
               GROUP BY STOCK_POINT ORDER BY STOCK_POINT""")
print("적재된 오프닝밸런스(원복 키: MAINT_TAG='OB' AND INSERT_USER_ID='GOLIVE'):")
for r in cur.fetchall():
    print(f"  {str(r[0]):<6}{r[1]:>7,}행{float(r[2]):>16,.1f}")
