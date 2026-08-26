# -*- coding: utf-8 -*-
"""r_field_drift_scan — 동일역할 2필드 드리프트 전 품목/거래처 검사 (FIELD_CANON 상시감시 도구).

목적: "같은 목적인데 2개 다른 필드"를 전 데이터 스캔해 실제 불일치 정량화 → 수렴 우선순위.
      sync 후 재실행하면 드리프트 재발 감시(제2의 접미사/561 FAIL 자동검출).
읽기전용. FIELD_CANON.md §3 사전 기반.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/NEW_ERP_1/PNC_ERP_Web/backend")
import common
cn = common._nx_tx(); cur = cn.cursor()

NX = "PARTNER_ERP_TEST3.nx."

# (역할, 조인SQL, A식, B식, 타입) — A=클린 정본, B=미러/타소스
JOINS = {
    "item": f"{NX}item i JOIN {NX}PR_M_ITEM p ON UPPER(LTRIM(RTRIM(i.item_code)))=UPPER(LTRIM(RTRIM(p.ITEM_CODE)))",
    "item_dim": f"{NX}item i JOIN {NX}bom_dim d ON UPPER(LTRIM(RTRIM(i.item_code)))=UPPER(LTRIM(RTRIM(d.item_code)))",
    "cust": f"{NX}partner n JOIN {NX}CM_M_CUST c ON UPPER(LTRIM(RTRIM(n.partner_code)))=UPPER(LTRIM(RTRIM(c.CUST_CODE)))",
}
PAIRS = [
    # 품목마스터 (nx.item 정본 vs PR_M_ITEM 미러)
    ("품명", "item", "i.item_name", "p.ITEM_DESC", "T"),
    ("매입처", "item", "i.in_cust", "p.IN_CUST_CODE", "T"),
    ("규격", "item", "i.item_spec", "p.ITEM_SPEC", "T"),
    ("생산구분", "item", "i.make_type", "p.MAKE_TYPE", "T"),
    ("단위", "item", "i.unit", "p.UNIT", "T"),
    ("재질", "item", "i.metal_gubun", "p.METAL_GUBUN", "T"),
    ("대분류", "item", "i.lgroup", "p.ITEM_LGROUP", "T"),
    ("소분류", "item", "i.sgroup", "p.ITEM_SGROUP", "T"),
    ("단가구분", "item", "i.cost_gubun", "p.COST_GUBUN", "T"),
    ("외경", "item", "i.diam", "p.ITEM_DIAM", "N"),
    ("두께", "item", "i.thick", "p.ITEM_THICK", "N"),
    ("길이", "item", "i.length", "p.ITEM_LENGTH", "N"),
    # 중량 우리축 (nx.item.net_weight vs bom_dim.fin_weight)
    ("우리중량", "item_dim", "i.net_weight", "d.fin_weight", "N"),
    # 거래처 (nx.partner 정본 vs CM_M_CUST 미러)
    ("거래처명", "cust", "n.partner_name", "c.CUST_DESC", "T"),
]


def scan(role, jk, a, b, t):
    j = JOINS[jk]
    if t == "N":
        both = f"{a} IS NOT NULL AND {b} IS NOT NULL AND (CAST({a} AS float)<>0 OR CAST({b} AS float)<>0)"
        ne = f"ABS(CAST(ISNULL({a},0) AS float)-CAST(ISNULL({b},0) AS float))>0.0005"
    else:
        both = f"LTRIM(RTRIM(ISNULL(CAST({a} AS varchar(300)),'')))<>'' AND LTRIM(RTRIM(ISNULL(CAST({b} AS varchar(300)),'')))<>''"
        ne = f"ISNULL(NULLIF(LTRIM(RTRIM(CAST({a} AS varchar(300)))),''),'~')<>ISNULL(NULLIF(LTRIM(RTRIM(CAST({b} AS varchar(300)))),''),'~')"
    sql = f"SELECT SUM(CASE WHEN {both} THEN 1 ELSE 0 END), SUM(CASE WHEN {both} AND {ne} THEN 1 ELSE 0 END) FROM {j}"
    try:
        cur.execute(sql); r = cur.fetchone()
        bo, d = r[0] or 0, r[1] or 0
        return bo, d
    except Exception as e:
        return None, str(e)[:40]


print("=== 동일역할 2필드 드리프트 전 데이터 검사 (FIELD_CANON) ===")
print("  %-10s %-24s %-22s 양쪽존재  불일치  드리프트%%" % ("역할", "정본(클린)", "미러/타소스"))
flags = []
for role, jk, a, b, t in PAIRS:
    bo, d = scan(role, jk, a, b, t)
    if bo is None:
        print("  %-10s ERR %s" % (role, d)); continue
    pct = 100.0 * d / bo if bo else 0
    mark = "  ★검토" if pct > 1 else ""
    print("  %-10s %-24s %-22s %7d %7d %7.2f%%%s" % (role, a, b, bo, d, pct, mark))
    if pct > 1:
        flags.append((role, a, b, d, pct))
print("\n★드리프트 >1%% (수렴/규명 대상):")
for f in flags:
    print("  %s: %s vs %s = %d건 (%.1f%%)" % (f[0], f[1], f[2], f[3], f[4]))
if not flags:
    print("  (없음 — 전 필드 정합)")
cn.rollback(); cn.close()
