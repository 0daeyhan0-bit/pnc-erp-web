# -*- coding: utf-8 -*-
"""자재 매입-소비 검증 (업체별 과입고 진단) — 신규.
   목적: 업체별 실제 매입입고 vs 실제 소비(가공출고·사급출고)를 "실측 자재 수불"로 펼쳐
         산 것보다 안 쓰고 남는(순증) 품목·업체를 사람이 검토하도록 투명 나열(자동 판정 아님).

   ★설계원칙(2026-08-22, 사용자 확정 — BOM 소요 추정 폐기, 실측 수불로 전환):
   - 주 신호 = 실측 자재 수불: 순증 = 매입입고 − 가공출고(tag B) − 사급출고(tag 5) ± 조정(tag 1/2).
     ※ 실측 태그(가공출고 B=실제 생산투입 소비)로 계산 → BOM 추정·변형SUB 과다전개(−2.7%잔차) 회피.
     ※ 자재재고 스냅샷(Z99990 월재고)은 SUB부품엔 재고점이 달라 부정확 → 기초/기말 대신 "순증(재고변화)"이 정확.
   - 변형코드(-3-1/-20-1)는 sub_variant_map(base_item)로 정규화, 없으면 첫 '-' 앞 base로 접어 매입↔소비 매칭.
   - 흐름유형·이상치 "플래그만" — 레거시 데이터 품목별 스파이크 많아 집계 단정 금지, 사람이 검토.
   - 조회 전용(라이브 dbo + nx.sub_variant_map), 쓰기 없음.
   매입유형=CUST_TYPE(_CT_NAME). 1차 대상=절삭-협력사('6'). 매입=PU_T_STOCK_MAINT(9/S/C/G/H)+_C(수입 P), 라이브.
   태그: 매입=9자재입고/S세트입고/H가공입고/G축관입고/C가공이동입고(+수입P) · 가공출고=B · 사급출고=5 · 조정=1,2.
"""
import time as _time
from fastapi import APIRouter, Query
from common import _conn

router = APIRouter()

_U = lambda s: (str(s).strip().upper() if s else "")
_CACHE = {}   # key=(ct,fr,to) -> (expiry, result)
_IN_TAGS = ("9", "S", "C", "G", "H")   # 확정입고(매입)


def _digits(s, n):
    k = "".join(ch for ch in str(s or "") if ch.isdigit())
    return k[-n:] if len(k) >= n else k


def _prev_ym(ym4):
    y, m = int(ym4[:2]), int(ym4[2:4]); m -= 1
    if m < 1: m = 12; y -= 1
    return f"{y:02d}{m:02d}"


def _build(ct, fr, to):
    """ct=CUST_TYPE, fr/to=YYMMDD. 업체별 실측 수불 진단 dict."""
    cn = _conn(); cu = cn.cursor()
    try:
        # 1) 매입입고 업체×자재 (확정입고 9/S/C/G/H + 수입 _C P)
        cu.execute("""SELECT UPPER(LTRIM(RTRIM(t.mat))) mat, t.cc, MAX(t.cnm) cnm, SUM(t.q) q, SUM(t.amt) amt, SUM(t.imp) imp FROM (
            SELECT a.MAT_CODE mat, a.CUST_CODE cc, c.CUST_DESC cnm, CONVERT(float,ISNULL(a.MAINT_QTY,0)) q, CONVERT(float,ISNULL(a.MAINT_AMT,0)) amt, CONVERT(float,0) imp
              FROM dbo.PU_T_STOCK_MAINT a JOIN dbo.CM_M_CUST c ON a.CUST_CODE=c.CUST_CODE
              WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG IN ('9','S','C','G','H') AND c.CUST_TYPE=?
            UNION ALL
            SELECT a.MAT_CODE, a.CUST_CODE, c.CUST_DESC, CONVERT(float,ISNULL(a.MAINT_QTY,0)), CONVERT(float,ISNULL(a.MAINT_AMT,0)), CONVERT(float,ISNULL(a.MAINT_QTY,0))
              FROM dbo.PU_T_STOCK_MAINT_C a JOIN dbo.CM_M_CUST c ON a.CUST_CODE=c.CUST_CODE
              WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.DIVISION='P' AND c.CUST_TYPE=?
            ) t GROUP BY UPPER(LTRIM(RTRIM(t.mat))), t.cc""", fr, to, ct, fr, to, ct)
        buy_rows = [(_U(r[0]), str(r[1]).strip(), r[2], float(r[3] or 0), float(r[4] or 0), float(r[5] or 0)) for r in cu.fetchall()]

        # 2) 소비·조정·순이동 — ★전 코드 스캔(변형코드 포함) 후 base 집계해야 정확.
        #    (소비가 매입코드와 다른 변형코드로 잡히므로 type6-매입코드 스코프 금지.)
        #    가공출고(B)·사급출고(5)·조정(1,2)·전업체매입(9SHGC)·순이동(tag≠3). CASE 집계, GROUP BY mat.
        cu.execute("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))) mat,
            SUM(CASE WHEN MAINT_TAG='B' THEN -CONVERT(float,ISNULL(MAINT_QTY,0)) ELSE 0 END) gagong,
            SUM(CASE WHEN MAINT_TAG='5' THEN -CONVERT(float,ISNULL(MAINT_QTY,0)) ELSE 0 END) sagub,
            SUM(CASE WHEN MAINT_TAG IN ('1','2') THEN CONVERT(float,ISNULL(MAINT_QTY,0)) ELSE 0 END) adj,
            SUM(CASE WHEN MAINT_TAG IN ('9','S','C','G','H') THEN CONVERT(float,ISNULL(MAINT_QTY,0)) ELSE 0 END) ipgo_all,
            SUM(CASE WHEN MAINT_TAG='3' THEN 0 ELSE CONVERT(float,ISNULL(MAINT_QTY,0)) END) netmv
          FROM dbo.PU_T_STOCK_MAINT WHERE MAINT_YMD BETWEEN ? AND ?
          GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))""", fr, to)
        mv = {}
        for mat, gag, sag, adj, ipgo, netmv in cu.fetchall():
            mv[_U(mat)] = {"gagong": float(gag or 0), "sagub": float(sag or 0), "adj": float(adj or 0),
                           "ipgo_all": float(ipgo or 0), "netmv": float(netmv or 0)}
        # 전업체 수입(_C, DIVISION=P) — 순이동에 합산
        cu.execute("SELECT UPPER(LTRIM(RTRIM(MAT_CODE))) mat, SUM(CONVERT(float,ISNULL(MAINT_QTY,0))) q FROM dbo.PU_T_STOCK_MAINT_C WHERE MAINT_YMD BETWEEN ? AND ? AND DIVISION='P' GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))", fr, to)
        imp_all = {_U(r[0]): float(r[1] or 0) for r in cu.fetchall()}

        # 3) 리시빙(참고) — 이 품번이 LG로 직접 나간 실적
        cu.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it, SUM(CONVERT(float,ISNULL(RECV_QTY,0))) q FROM dbo.SA_T_LG_RECEIVING_DTL WHERE RECEIVING_YMD BETWEEN ? AND ? GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))", fr, to)
        recv = {_U(r[0]): float(r[1] or 0) for r in cu.fetchall()}

        # 4) 변형코드 정규화(sub_variant_map base_item; 없으면 첫 '-' 앞)
        v2b = {}
        cu.execute("SELECT UPPER(LTRIM(RTRIM(variant_item))),UPPER(LTRIM(RTRIM(base_item))) FROM PARTNER_ERP_TEST3.nx.sub_variant_map")
        for v, b in cu.fetchall():
            if _U(v) and _U(b): v2b[_U(v)] = _U(b)
        def base(m):
            # sub_variant_map(검증) 우선. ★'-SUB'(체결 SUB=별개 품목, 조달변형 아님)은 병합 금지(서포터 루프 오병합 방지).
            #   그 외 숫자 조달경로 접미사(-3-1/-4-2/-20-1 등)는 첫 '-' 앞 base로 접음.
            if m in v2b: return v2b[m]
            if m.endswith("-SUB") or "_S" in m: return m
            return m.split("-")[0] if "-" in m else m

        # 5) base로 접어 결합. ★items 키(base)는 type6 매입 있는 것만(buy_rows 기준). 소비/순이동은 전 변형코드에서 base로 합산.
        items = {}
        def _it(k): return items.setdefault(k, {"item": k, "buy_q": 0.0, "buy_amt": 0.0,   # buy_q=type6 매입(업체분)
                                                 "buy_all": 0.0, "gagong": 0.0, "sagub": 0.0, "adj": 0.0, "netmv": 0.0,
                                                 "recv": 0.0, "vendors": {}, "raw_codes": set()})
        for mat, cc, cnm, q, amt, imp in buy_rows:
            k = base(mat); d = _it(k)
            d["buy_q"] += q; d["buy_amt"] += amt; d["raw_codes"].add(mat)
            v = d["vendors"].setdefault(cc, {"code": cc, "name": cnm, "q": 0.0, "amt": 0.0})
            v["q"] += q; v["amt"] += amt
        for mat, d0 in mv.items():                     # 전 변형코드 소비/이동 → base
            k = base(mat)
            if k in items:
                items[k]["gagong"] += d0["gagong"]; items[k]["sagub"] += d0["sagub"]
                items[k]["adj"] += d0["adj"]; items[k]["buy_all"] += d0["ipgo_all"]; items[k]["netmv"] += d0["netmv"]
        for mat, q in imp_all.items():                 # 전업체 수입 → base(총매입·순증)
            k = base(mat)
            if k in items: items[k]["buy_all"] += q; items[k]["netmv"] += q
        for mat, q in recv.items():
            k = base(mat)
            if k in items: items[k]["recv"] += q

        # 품명
        cu.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), MAX(item_name) FROM PARTNER_ERP_TEST3.nx.item GROUP BY UPPER(LTRIM(RTRIM(item_code)))")
        nm = {_U(a): b for a, b in cu.fetchall()}

        # 6) 순증·흐름·플래그. ★순증=순이동(netmv, 전코드 전태그≠3)=진짜 재고변화. 총매입=전업체 매입(base).
        out = []
        for k, d in items.items():
            buy6, buyall, gag, sag, adj, rv = d["buy_q"], d["buy_all"], d["gagong"], d["sagub"], d["adj"], d["recv"]
            up = d["buy_amt"] / buy6 if buy6 else 0.0
            net = d["netmv"]                          # 순증(재고변화, 전코드 순이동)
            consume = gag + sag
            # ★단가 신뢰성 가드: 소량매입(buy6<10)이면 단가 스파이크(예 "수불정산" 2개→13B) → 순증액 산정 제외
            unreliable = buy6 < 10 or up <= 0
            # 흐름유형
            if sag > buyall * 0.3: flow = "사급재출고형"
            elif rv > buyall * 0.3: flow = "직납"
            elif len(d["vendors"]) > 1: flow = "다업체소싱"
            else: flow = "컴포넌트(가공소비)"
            net_amt = 0 if unreliable else round(net * up)
            flags = []
            if unreliable and abs(net) > 100: flags.append("단가불명")
            if consume <= 0 and buyall > 0: flags.append("소비없음")
            if (not unreliable) and net > 0 and net > buyall * 0.2 and net_amt > 3_000_000: flags.append("순증과다")
            if sag > buyall * 1.05: flags.append("사급>매입")
            out.append({
                "item": k, "name": nm.get(k, ""),
                "buy_q": round(buy6), "buy_amt": round(d["buy_amt"]), "buy_all": round(buyall),
                "gagong": round(gag), "sagub": round(sag), "adj": round(adj),
                "consume": round(consume), "net": round(net), "net_amt": net_amt,
                "recv": round(rv), "flow": flow, "flags": flags,
                "vendors": sorted(d["vendors"].values(), key=lambda x: -x["amt"]),
                "n_codes": len(d["raw_codes"]),
            })
        out.sort(key=lambda x: -x["net_amt"])
        return {"ct": ct, "fr": fr, "to": to, "count": len(out), "rows": out}
    finally:
        cn.close()


def _cur_ym():
    cn = _conn(); cu = cn.cursor()
    try:
        cu.execute("SELECT FORMAT(GETDATE(),'yyMM')"); return cu.fetchone()[0]
    finally:
        cn.close()


@router.get("/api/matverify/coop")
def matverify_coop(ct: str = Query("6"), ym_from: str = Query(""), ym_to: str = Query(""), nocache: str = Query("")):
    """매입유형(ct=CUST_TYPE, 기본6=절삭-협력사)별 매입-소비 실측 수불 진단. 기간 YYMM. 기본=2601~당월."""
    fr = (_digits(ym_from, 4) or "2601") + "01"
    to = (_digits(ym_to, 4) or _digits(_cur_ym(), 4)) + "99"
    key = (ct, fr, to); now = _time.time()
    if not str(nocache).strip():
        hit = _CACHE.get(key)
        if hit and hit[0] > now: return hit[1]
    res = _build(ct, fr, to)
    _CACHE[key] = (now + 600, res)
    return res
