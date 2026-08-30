# -*- coding: utf-8 -*-
"""레거시 월마감(총평균법) 재현 — w_pu_stock_160.srw 원문 그대로.
   ★읽기전용. 계산 결과를 레거시 PU_T_MONTH_STOCK_WH 와 전수 대조만 한다(쓰기 없음).
   목적: 우리가 레거시 단가를 diff0 재현할 수 있는지 판정 → 회계방식 선택(A/B/C)의 근거."""
import sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\_wt_close\PNC_ERP_Web\backend")
from common import _conn

IN_TAGS  = ('3', '9', 'C', 'G', 'H', 'S', 'P', 'R')      # 자재입고
OUT_TAGS = ('1', '4', '5', '6', '8', 'A', 'B', 'J')      # 자재출고


def _rnd(x):
    """T-SQL ROUND(x,0) = 반올림(.5는 0에서 먼 쪽). Python round()는 은행가반올림이라 못 씀."""
    return math.floor(abs(x) + 0.5) * (1 if x >= 0 else -1)


def build(cur, yymm, prev_yymm, basic_override=None):
    """레거시 160 마감 재현 → {mat: dict}. basic_override 주면 그걸 기초로(체인 검증용)."""
    R = {}

    def slot(m):
        m = str(m).strip().upper()      # ★레거시는 CI 콜레이션 → GROUP BY 가 대소문자를 합친다.
        return R.setdefault(m, {"bq": 0.0, "ba": 0.0, "iq": 0.0, "ia": 0.0,
                                "oq": 0.0, "oa": 0.0, "tq": 0.0, "ta": 0.0,
                                "tc": 0.0, "oc": 0.0})

    # ── 기초(전월 기말) ─────────────────────────────────────────────
    if basic_override is not None:
        for m, (q, a) in basic_override.items():
            d = slot(m); d["bq"] += q; d["ba"] += a
    else:
        cur.execute("""SELECT a.MAT_CODE, a.STOCK_QTY, a.STOCK_AMT
                         FROM PARTNER_ERP.dbo.PU_T_MONTH_STOCK_WH a
                         JOIN PARTNER_ERP.dbo.PR_M_ITEM m ON a.MAT_CODE = m.ITEM_CODE
                        WHERE a.STOCK_YYMM = ?""", prev_yymm)
        for m, q, a in cur.fetchall():
            d = slot(m); d["bq"] += float(q or 0); d["ba"] += float(a or 0)

    # ── 자재입고 (검사 미통과 제외) ─────────────────────────────────
    cur.execute(f"""SELECT a.MAT_CODE, SUM(CAST(a.MAINT_QTY AS float)), SUM(CAST(a.MAINT_AMT AS float))
                      FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT a
                      JOIN PARTNER_ERP.dbo.PR_M_ITEM m ON a.MAT_CODE = m.ITEM_CODE
                     WHERE a.MAINT_YMD LIKE ? AND a.MAINT_QTY <> 0
                       AND a.MAINT_TAG IN ({','.join('?'*len(IN_TAGS))})
                       AND NOT (ISNULL(a.INSP_FLAG,'N') IN ('S','F') AND ISNULL(a.INSP_PROC_FLAG,'0') <> '1')
                     GROUP BY a.MAT_CODE""", yymm + '%', *IN_TAGS)
    for m, q, a in cur.fetchall():
        d = slot(m); d["iq"] += float(q or 0); d["ia"] += float(a or 0)

    # ── 수입(도입): division<>'Q' = 입고(금액=TAXPAYERS 과세표준) / 'Q' = 출고 ──
    cur.execute("""SELECT a.MAT_CODE, a.DIVISION, SUM(CAST(a.MAINT_QTY AS float)),
                          SUM(CAST(ISNULL(a.TAXPAYERS,0) AS float))
                     FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT_C a
                    WHERE a.MAINT_YMD LIKE ? AND a.WH_CUST_CODE = 'Z99990'
                    GROUP BY a.MAT_CODE, a.DIVISION""", yymm + '%')
    for m, div, q, tax in cur.fetchall():
        d = slot(m); q = float(q or 0)
        if str(div or "").strip() == 'Q':
            d["oq"] += q
        else:
            d["iq"] += q; d["ia"] += float(tax or 0)

    # ── 자재출고 ────────────────────────────────────────────────────
    cur.execute(f"""SELECT a.MAT_CODE, SUM(-CAST(a.MAINT_QTY AS float))
                      FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT a
                     WHERE a.MAINT_YMD LIKE ?
                       AND a.MAINT_TAG IN ({','.join('?'*len(OUT_TAGS))})
                     GROUP BY a.MAT_CODE""", yymm + '%', *OUT_TAGS)
    for m, q in cur.fetchall():
        slot(m)["oq"] += float(q or 0)

    # ── 생산창고 반납(T, 부호반전) · 재고조정(2) → TRANS ─────────────
    cur.execute("""SELECT a.MAT_CODE, SUM(-CAST(a.MAINT_QTY AS float))
                     FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT a
                     JOIN PARTNER_ERP.dbo.PR_M_ITEM m ON a.MAT_CODE = m.ITEM_CODE
                    WHERE a.MAINT_YMD LIKE ? AND a.MAINT_TAG = 'T' GROUP BY a.MAT_CODE""", yymm + '%')
    for m, q in cur.fetchall():
        slot(m)["tq"] += float(q or 0)
    cur.execute("""SELECT a.MAT_CODE, SUM(CAST(a.MAINT_QTY AS float))
                     FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT a
                    WHERE a.MAINT_YMD LIKE ? AND a.MAINT_TAG = '2' GROUP BY a.MAT_CODE""", yymm + '%')
    for m, q in cur.fetchall():
        slot(m)["tq"] += float(q or 0)

    # ── 소모품(ITEM_SGROUP >= '990') 제외 + 마스터에 없으면 탈락 ─────
    cur.execute("SELECT ITEM_CODE, ISNULL(ITEM_SGROUP,'') FROM PARTNER_ERP.dbo.PR_M_ITEM")
    sg = {str(r[0]).strip().upper(): str(r[1]) for r in cur.fetchall()}
    R = {m: d for m, d in R.items() if m in sg and sg[m] < '990'}
    # HAVING: 전부 0이면 제외
    R = {m: d for m, d in R.items()
         if any(abs(d[k]) > 1e-9 for k in ("bq", "ba", "iq", "ia", "oq", "oa", "tq", "ta"))}

    # ── 단가 마스터 폴백(PR_M_ITEM_COST COST_TAG='1', 원화만 1배) ────
    cur.execute("""SELECT ITEM_CODE, ITEM_COST FROM (
                     SELECT ITEM_CODE, CAST(ITEM_COST AS float) ITEM_COST,
                            ROW_NUMBER() OVER(PARTITION BY ITEM_CODE ORDER BY COST_APPLY_YMD DESC) rn
                       FROM PARTNER_ERP.dbo.PR_M_ITEM_COST
                      WHERE COST_TAG = '1' AND COST_APPLY_YMD <= ?
                        AND ISNULL(CURRENCY,'KRW') IN ('KRW','')) t WHERE rn = 1""", yymm + '99')
    mcost = {str(r[0]).strip().upper(): float(r[1] or 0) for r in cur.fetchall()}

    # ── TRANS 금액 (UPDATE 순서 그대로) ─────────────────────────────
    for m, d in R.items():
        den = d["bq"] + d["iq"]; num = d["ba"] + d["ia"]
        # U1
        if d["tq"] != 0 and d["oq"] == 0 and (d["bq"] + d["iq"] + d["tq"]) == 0:
            d["ta"] = -num
            d["tc"] = _rnd(abs(num / den)) if den != 0 else 0
        # U2
        if d["tq"] != 0 and d["tc"] == 0 and d["ta"] == 0:
            d["ta"] = _rnd(abs(num * d["tq"] / den)) * (1 if d["tq"] > 0 else -1) if den != 0 else 0
            d["tc"] = _rnd(abs(num / den)) if den != 0 else 0
        # U3
        if d["bq"] == 0 and d["iq"] == 0 and d["tq"] != 0 and d["tc"] == 0:
            d["tc"] = mcost.get(m, 0.0)
        # U4
        if d["tq"] != 0 and d["tc"] != 0 and d["ta"] == 0:
            d["ta"] = d["tc"] * d["tq"]

    # ── OUTPUT 금액 (UPDATE 순서 그대로) ────────────────────────────
    for m, d in R.items():
        den = d["bq"] + d["iq"] + d["tq"]; num = d["ba"] + d["ia"] + d["ta"]
        # V1
        if d["oq"] != 0 and (den - d["oq"]) == 0:
            d["oa"] = num
            d["oc"] = _rnd(abs(num / den)) if den != 0 else 0
        # V2
        if d["oq"] != 0 and d["oc"] == 0 and d["oa"] == 0:
            d["oa"] = _rnd(abs(num * d["oq"] / den)) * (1 if d["oq"] > 0 else -1) if den != 0 else 0
            d["oc"] = _rnd(abs(num / den)) if den != 0 else 0
        # V3
        if d["bq"] == 0 and d["iq"] == 0 and d["oq"] != 0 and d["oc"] == 0:
            d["oc"] = mcost.get(m, 0.0)
        # V4
        if d["oq"] != 0 and d["oc"] != 0 and d["oa"] == 0:
            d["oa"] = d["oc"] * d["oq"]

    # ── 기말 ────────────────────────────────────────────────────────
    for d in R.values():
        d["sq"] = d["bq"] + d["iq"] - d["oq"] + d["tq"]
        d["sa"] = d["ba"] + d["ia"] - d["oa"] + d["ta"]
        d["sc"] = math.floor(d["sa"] / d["sq"]) if d["sq"] != 0 else 0
    return R


def compare(cur, yymm, R, label):
    cur.execute("""SELECT MAT_CODE, CAST(STOCK_QTY AS float), CAST(STOCK_AMT AS float), CAST(STOCK_COST AS float)
                     FROM PARTNER_ERP.dbo.PU_T_MONTH_STOCK_WH WHERE STOCK_YYMM = ?""", yymm)
    L = {str(r[0]).strip().upper(): (float(r[1] or 0), float(r[2] or 0), float(r[3] or 0)) for r in cur.fetchall()}
    common = set(R) & set(L)
    qok = sum(1 for m in common if abs(R[m]["sq"] - L[m][0]) < 0.001)
    aok = sum(1 for m in common if abs(R[m]["sa"] - L[m][1]) < 1.0)
    cok = sum(1 for m in common if abs(R[m]["sc"] - L[m][2]) < 0.01)
    print(f"\n=== {label} ===")
    print(f"  재현 {len(R):,} · 레거시 {len(L):,} · 공통 {len(common):,}"
          f" · 재현만 {len(set(R)-set(L))} · 레거시만 {len(set(L)-set(R))}")
    print(f"  수량 {qok:,}/{len(common):,} ({qok/len(common)*100:.2f}%)"
          f" · 금액 {aok:,} ({aok/len(common)*100:.2f}%)"
          f" · 단가 {cok:,} ({cok/len(common)*100:.2f}%)")
    bad = sorted((m for m in common if abs(R[m]["sc"] - L[m][2]) >= 0.01),
                 key=lambda m: -abs(R[m]["sq"] * (R[m]["sc"] - L[m][2])))[:6]
    if bad:
        print("  단가 불일치 상위(금액영향순)")
        for m in bad:
            d = R[m]
            print(f"    {m:22s} 잔량 재현 {d['sq']:10,.0f}/레거시 {L[m][0]:10,.0f}"
                  f" · 단가 재현 {d['sc']:10,.0f}/레거시 {L[m][2]:10,.0f}")
    return common, L


cn = _conn(); cur = cn.cursor()
for yymm, prev in (('2606', '2605'), ('2607', '2606')):
    R = build(cur, yymm, prev)
    compare(cur, yymm, R, f"레거시 총평균 재현 {yymm} (기초=레거시 {prev} 저장값)")

# ── 잔차 분류 ────────────────────────────────────────────────────────
print("\n\n########## 잔차 분류 ##########")
for yymm, prev in (('2606', '2605'), ('2607', '2606')):
    R = build(cur, yymm, prev)
    cur.execute("""SELECT MAT_CODE, CAST(STOCK_QTY AS float), CAST(STOCK_AMT AS float), CAST(STOCK_COST AS float)
                     FROM PARTNER_ERP.dbo.PU_T_MONTH_STOCK_WH WHERE STOCK_YYMM = ?""", yymm)
    L = {str(r[0]).strip().upper(): (float(r[1] or 0), float(r[2] or 0), float(r[3] or 0)) for r in cur.fetchall()}
    common = set(R) & set(L)
    bad = [m for m in common if abs(R[m]["sc"] - L[m][2]) >= 0.01]
    cat = {"±1원 반올림": 0, "±10원 이내": 0, "레거시 단가0(우리는 값)": 0,
           "우리 단가0(레거시는 값)": 0, "수량도 불일치": 0, "그외 실질차": 0}
    other = []
    for m in bad:
        dq = abs(R[m]["sq"] - L[m][0]) >= 0.001
        dc = abs(R[m]["sc"] - L[m][2])
        if dq:                      cat["수량도 불일치"] += 1
        elif L[m][2] == 0:          cat["레거시 단가0(우리는 값)"] += 1
        elif R[m]["sc"] == 0:       cat["우리 단가0(레거시는 값)"] += 1
        elif dc <= 1.0:             cat["±1원 반올림"] += 1
        elif dc <= 10.0:            cat["±10원 이내"] += 1
        else:                       cat["그외 실질차"] += 1; other.append(m)
    print(f"\n[{yymm}] 단가 불일치 {len(bad)}건 / 공통 {len(common):,}건 "
          f"({(len(common)-len(bad))/len(common)*100:.2f}% 일치)")
    for k, v in cat.items():
        if v: print(f"    {k:24s} {v:4d}건")
    if other:
        print(f"    ▸ '그외 실질차' 전체 {len(other)}건:")
        for m in sorted(other, key=lambda x: -abs(R[x]['sq']*(R[x]['sc']-L[x][2])))[:10]:
            print(f"       {m:24s} 잔량 {R[m]['sq']:9,.0f} · 재현 {R[m]['sc']:9,.0f} · 레거시 {L[m][2]:9,.0f}")
