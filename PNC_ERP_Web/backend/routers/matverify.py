# -*- coding: utf-8 -*-
"""자재 소요-매입 검증 (업체별 과입고 진단) — 신규.
   목적: 실적(LG리시빙)→BOM 전개 소요 vs 업체별 실제 매입입고를, 사급출고·기초재고까지 펼쳐
         "과하게 입고시킨 업체·품목"을 사람이 검토하도록 투명하게 나열(자동 판정 아님).

   ★설계원칙(2026-08-22, 사용자 확정):
   - 소요 = 검증된 CS real=1 규칙(CS_M_ITEM_BOM, CS_CALC_EXCEPT_FLAG≠1, MAKE_TYPE=1만 재귀·매입품 정지) — 리시빙 실적 구동.
     내가 nx.bom_line로 하면 평탄화·변형SUB 3배 과다전개(LME_OVERCOUNT_ROOTCAUSE). 반드시 CS BOM.
   - 변형코드(-3-1/-20-1)는 sub_variant_map(base_item)로 정규화, 없으면 첫 '-' 앞 base로 접어 매입↔소요 매칭.
   - 흐름유형·이상치 "플래그만" — 레거시 데이터 품목별 스파이크 많아 집계 단정 금지.
   - 조회 전용(라이브 dbo + nx.CS_M_ITEM_BOM), 쓰기 없음.
   매입유형=CUST_TYPE(_CT_NAME). 1차 대상=절삭-협력사('6'). 확정입고=PU_T_STOCK_MAINT(9/S/C/G/H)+_C(수입 P), 라이브.
"""
import time as _time
from fastapi import APIRouter, Query
from common import _conn

router = APIRouter()

_U = lambda s: (str(s).strip().upper() if s else "")
_CACHE = {}   # key=(ct,fr,to) -> (expiry, result). 무거운 소요전개 캐시.


def _digits(s, n):
    k = "".join(ch for ch in str(s or "") if ch.isdigit())
    return k[-n:] if len(k) >= n else k


def _build(ct, fr, to):
    """ct=CUST_TYPE(예 '6'), fr/to=YYMMDD. 품목별 진단 dict 계산(캐시)."""
    cn = _conn(); cu = cn.cursor()
    try:
        # 1) 대상 매입유형 매입(확정입고+수입) — 업체×자재
        cu.execute(f"""SELECT UPPER(LTRIM(RTRIM(t.mat))) mat, t.cc, MAX(t.cnm) cnm, SUM(t.q) q, SUM(t.amt) amt FROM (
            SELECT a.MAT_CODE mat, a.CUST_CODE cc, c.CUST_DESC cnm, CONVERT(float,ISNULL(a.MAINT_QTY,0)) q, CONVERT(float,ISNULL(a.MAINT_AMT,0)) amt
              FROM dbo.PU_T_STOCK_MAINT a JOIN dbo.CM_M_CUST c ON a.CUST_CODE=c.CUST_CODE
              WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG IN ('9','S','C','G','H') AND c.CUST_TYPE=?
            UNION ALL
            SELECT a.MAT_CODE, a.CUST_CODE, c.CUST_DESC, CONVERT(float,ISNULL(a.MAINT_QTY,0)), CONVERT(float,ISNULL(a.MAINT_AMT,0))
              FROM dbo.PU_T_STOCK_MAINT_C a JOIN dbo.CM_M_CUST c ON a.CUST_CODE=c.CUST_CODE
              WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.DIVISION='P' AND c.CUST_TYPE=?
            ) t GROUP BY UPPER(LTRIM(RTRIM(t.mat))), t.cc""", fr, to, ct, fr, to, ct)
        buy_rows = [(_U(r[0]), str(r[1]).strip(), r[2], float(r[3] or 0), float(r[4] or 0)) for r in cu.fetchall()]
        buyset = set(m for m, cc, cnm, q, a in buy_rows)

        # 2) MAKE_TYPE (재귀 게이트: '1'=제작=재귀, else 정지)
        cu.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), ISNULL(MAKE_TYPE,'') FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM")
        mk = {_U(a): str(b).strip() for a, b in cu.fetchall()}

        # 3) CS BOM (CS_CALC_EXCEPT_FLAG≠1) 부모→[(자식,use_qty)]
        ch = {}
        cu.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))),UPPER(LTRIM(RTRIM(MAT_CODE))),ISNULL(USE_QTY,0) FROM PARTNER_ERP_TEST3.nx.CS_M_ITEM_BOM WHERE ISNULL(CS_CALC_EXCEPT_FLAG,'0')<>'1'")
        for p, c2, q in cu.fetchall():
            ch.setdefault(_U(p), []).append((_U(c2), float(q or 0)))

        # 4) 리시빙 실적(demand) — C+R 전부(R=반품아닌 다른구분)
        cu.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it, SUM(CONVERT(float,ISNULL(RECV_QTY,0))) q FROM dbo.SA_T_LG_RECEIVING_DTL WHERE RECEIVING_YMD BETWEEN ? AND ? GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))", fr, to)
        recv_rows = [(_U(r[0]), float(r[1] or 0)) for r in cu.fetchall()]
        recv_direct = {m: q for m, q in recv_rows}   # 리시빙 직접(직납 판정용)

        # 5) 소요 전개(CS real=1: 매입품/비제작 정지, 제작품 재귀). 단위전개 memo.
        import sys as _sys
        _sys.setrecursionlimit(100000)
        stop = lambda n: (n in buyset) or (mk.get(n, "") != "1")
        memo = {}

        def unit(item):
            if item in memo:
                return memo[item]
            memo[item] = {}
            acc = {}
            for c2, uq in ch.get(item, []):
                if uq <= 0:
                    continue
                if stop(c2):
                    acc[c2] = acc.get(c2, 0.0) + uq
                else:
                    for k, v in unit(c2).items():
                        acc[k] = acc.get(k, 0.0) + v * uq
            memo[item] = acc
            return acc

        soyo = {}
        for S, Q in recv_rows:
            if stop(S):
                soyo[S] = soyo.get(S, 0.0) + Q          # 우리가 사서 출하(직납/외주완성)
            else:
                for k, v in unit(S).items():
                    soyo[k] = soyo.get(k, 0.0) + Q * v

        # 6) 사급출고(tag5) — 그 자재가 우리 재고서 나간 것(전 거래처)
        cu.execute("SELECT UPPER(LTRIM(RTRIM(MAT_CODE))) m, SUM(-CONVERT(float,ISNULL(MAINT_QTY,0))) FROM dbo.PU_T_STOCK_MAINT WHERE MAINT_YMD BETWEEN ? AND ? AND MAINT_TAG='5' GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))", fr, to)
        sagub = {_U(r[0]): float(r[1] or 0) for r in cu.fetchall()}

        # 7) 기초재고(조회 시작월 직전월말 자재재고) — 자재창고 Z99990 월재고
        begym = _prev_ym(fr[:4])
        cu.execute("SELECT UPPER(LTRIM(RTRIM(mat_code))) m, SUM(CONVERT(float,ISNULL(stock_qty,0))) FROM dbo.PU_T_MONTH_STOCK_WH WHERE cust_code='Z99990' AND STOCK_YYMM=? GROUP BY UPPER(LTRIM(RTRIM(mat_code)))", begym)
        beg = {_U(r[0]): float(r[1] or 0) for r in cu.fetchall()}

        # 8) 변형코드 정규화 맵(sub_variant_map base_item; 없으면 첫 '-' 앞)
        v2b = {}
        cu.execute("SELECT UPPER(LTRIM(RTRIM(variant_item))),UPPER(LTRIM(RTRIM(base_item))) FROM PARTNER_ERP_TEST3.nx.sub_variant_map")
        for v, b in cu.fetchall():
            if _U(v) and _U(b):
                v2b[_U(v)] = _U(b)

        def base(m):
            if m in v2b:
                return v2b[m]
            return m.split("-")[0] if "-" in m else m

        # 9) base로 접어 매입(업체별)·소요·사급·기초·리시빙 결합
        items = {}   # base -> dict
        def _it(k):
            return items.setdefault(k, {"item": k, "beg": 0.0, "buy_q": 0.0, "buy_amt": 0.0,
                                        "soyo": 0.0, "sagub": 0.0, "recv": 0.0,
                                        "vendors": {}, "raw_codes": set()})
        for m, cc, cnm, q, a in buy_rows:
            k = base(m); d = _it(k)
            d["buy_q"] += q; d["buy_amt"] += a; d["raw_codes"].add(m)
            v = d["vendors"].setdefault(cc, {"code": cc, "name": cnm, "q": 0.0, "amt": 0.0})
            v["q"] += q; v["amt"] += a
        # soyo/sagub/beg/recv를 base로 접어 합산(매입 base에만 귀속)
        def _fold(src, key):
            for m, val in src.items():
                k = base(m)
                if k in items:
                    items[k][key] += val
        _fold(soyo, "soyo"); _fold(sagub, "sagub"); _fold(beg, "beg"); _fold(recv_direct, "recv")

        # 품명
        cu.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), MAX(item_name) FROM PARTNER_ERP_TEST3.nx.item GROUP BY UPPER(LTRIM(RTRIM(item_code)))")
        nm = {_U(a): b for a, b in cu.fetchall()}

        # 10) 흐름유형·플래그·검토후보 산출
        out = []
        for k, d in items.items():
            bq, sq, og, be, rv = d["buy_q"], d["soyo"], d["sagub"], d["beg"], d["recv"]
            up = d["buy_amt"] / bq if bq else 0.0
            end = be + bq - sq - og                       # 기말(참고)
            cand = bq - max(sq, og)                        # 검토후보: 매입 − max(소요,사급출고) (이중차감 회피)
            # 흐름유형
            if og > 0 and abs(og - sq) / max(sq, 1) < 0.3 and abs(og - bq) / max(bq, 1) < 0.5:
                flow = "서포터(사급출고형)"
            elif rv > 0 and abs(rv - sq) / max(sq, 1) < 0.1:
                flow = "직납"
            elif len(d["vendors"]) > 1:
                flow = "다업체소싱"
            else:
                flow = "컴포넌트"
            flags = []
            if sq == 0 and og == 0:
                flags.append("소요없음")
            if og > bq * 1.05:
                flags.append("사급>매입")
            if sq > 0 and bq / max(sq, 1) > 3 and og == 0:
                flags.append("매입≫소요")
            if end < -max(bq, sq) * 0.1:
                flags.append("기말음수")
            out.append({
                "item": k, "name": nm.get(k, ""),
                "beg": round(be), "buy_q": round(bq), "buy_amt": round(d["buy_amt"]),
                "soyo": round(sq), "sagub_out": round(og), "recv": round(rv),
                "end": round(end), "cand_over": round(cand * up),
                "flow": flow, "flags": flags,
                "vendors": sorted(d["vendors"].values(), key=lambda x: -x["amt"]),
                "n_codes": len(d["raw_codes"]),
            })
        out.sort(key=lambda x: -x["cand_over"])
        return {"ct": ct, "fr": fr, "to": to, "begym": begym, "count": len(out), "rows": out}
    finally:
        cn.close()


def _prev_ym(ym4):
    y, m = int(ym4[:2]), int(ym4[2:4])
    m -= 1
    if m < 1:
        m = 12; y -= 1
    return f"{y:02d}{m:02d}"


@router.get("/api/matverify/coop")
def matverify_coop(ct: str = Query("6"), ym_from: str = Query(""), ym_to: str = Query(""), nocache: str = Query("")):
    """매입유형(ct=CUST_TYPE, 기본6=절삭-협력사)별 소요-매입 검증 진단. 기간 YYMM(월). 기본=2601~당월."""
    fr = (_digits(ym_from, 4) or "2601") + "01"
    to = (_digits(ym_to, 4) or _digits(_cur_ym(), 4)) + "99"
    key = (ct, fr, to)
    now = _time.time()
    if not str(nocache).strip():
        hit = _CACHE.get(key)
        if hit and hit[0] > now:
            return hit[1]
    res = _build(ct, fr, to)
    _CACHE[key] = (now + 600, res)
    return res


def _cur_ym():
    cn = _conn(); cu = cn.cursor()
    try:
        cu.execute("SELECT FORMAT(GETDATE(),'yyMM')")
        return cu.fetchone()[0]
    finally:
        cn.close()
