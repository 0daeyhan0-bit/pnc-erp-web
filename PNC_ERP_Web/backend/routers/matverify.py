# -*- coding: utf-8 -*-
"""자재 매입-소비 검증 (업체별 과입고 진단) — 신규. 정본 문서 _schema/MATVERIFY_DESIGN.md.
   목적: 국내/해외(수입) 협력사가 실적 대비 과하게 매입(입고)시킨 품목·업체를 실측 자재수불로 검증.
         수입은 리드타임 때문에 과매입 경향(확인 필요), 국내 협력사도 같이.

   ★모델 = 실측 자재 수불 (BOM 소요 추정 폐기):
     순증(재고변화) = 매입입고 − 가공출고(tag B=실소비) − 사급출고(5) ± 조정(1,2)  [전 공급원]
     순증 크게 양수 = 산 것보다 안 쓰고 재고로 쌓임 = 과입고 후보.
   태그: 매입=9/S/C/G/H (+수입=PU_T_STOCK_MAINT_C DIVISION='P') · 가공출고=B · 사급출고=5 · 조정=1,2.
   ★공급원 분해: 국내 협력사(CUST_TYPE→_CT_NAME) + 수입(_C, XINXIANG/AUDY/FONE THAI 등) + 기타(비협력 집계).
     매입유형(ct)=필터(그 유형 매입 있는 품목). ct='IMP'=수입 전용 뷰.
   ★변형코드: sub_variant_map(base_item) 정규화, 없으면 첫 '-' 앞. 단 '-SUB'(체결SUB=별품목)·'_S'는 병합 금지.
   ★레거시 데이터 튐 → 집계 단정 금지, 이상치 플래그만(사람 검토). 단가불명 가드(소량매입 스파이크 제외).
   조회 전용(라이브 dbo + nx.sub_variant_map), 쓰기 없음.
"""
import time as _time
from fastapi import APIRouter, Query
from common import _conn

router = APIRouter()

_U = lambda s: (str(s).strip().upper() if s else "")
_CACHE = {}   # key=(ct,fr,to) -> (expiry, result)
_CT_NAME = {'1': '유상사급부품', '4': '절삭원자재', '5': '설치원자재', '6': '절삭협력', '7': '절삭부자재', '8': '설치부자재', '9': '소모품', 'A': '이지링크'}
# 비자재 pseudo-코드 제외(소급/샘플/금형비/수불정산 등). ★한글시작+키워드만 제외 → 실자재(영숫자시작 -삼화·동BODY 등) 보호.
_NONMAT_KW = ('샘플', '소급', '금형', '교육', '수불정산', '견본', '폐기', '불용', '시험', 'TEST', '정산')
def _is_nonmat(code):
    c = _U(code)
    if not c: return True
    if c[0].isascii(): return False        # 영숫자 시작 = 정상 품번(거래처접미사 포함) 유지
    return any(k in c for k in _NONMAT_KW)  # 한글 시작 pseudo-코드 중 키워드만 제외


def _digits(s, n):
    k = "".join(ch for ch in str(s or "") if ch.isdigit())
    return k[-n:] if len(k) >= n else k


def _build(ct, fr, to):
    """ct=CUST_TYPE(6=절삭협력…) 또는 'IMP'(수입). fr/to=YYMMDD. 업체별 실측 수불 진단 dict."""
    cn = _conn(); cu = cn.cursor()
    try:
        # 0) 변형코드 정규화
        v2b = {}
        cu.execute("SELECT UPPER(LTRIM(RTRIM(variant_item))),UPPER(LTRIM(RTRIM(base_item))) FROM PARTNER_ERP_TEST3.nx.sub_variant_map")
        for a, b in cu.fetchall():
            if _U(a) and _U(b): v2b[_U(a)] = _U(b)

        def base(m):
            if m in v2b: return v2b[m]
            if m.endswith("-SUB") or "_S" in m: return m
            if "-" in m:
                b = m.split("-")[0]
                if len(b) >= 8: return b       # 실제 품번 base(11자리 등)만 접음. 짧은 접두어(PNC 등) 오병합 방지.
            return m

        # 1) 전 공급처: 국내 PU 매입 by (mat,cust,type) [9/S/C/G/H] + 수입 _C by (mat,cust)
        sup = []   # (mat, code, name, ctype, kind, q, amt)
        cu.execute("""SELECT UPPER(LTRIM(RTRIM(a.MAT_CODE))), a.CUST_CODE, MAX(c.CUST_DESC), MAX(ISNULL(c.CUST_TYPE,'')),
              SUM(CONVERT(float,ISNULL(a.MAINT_QTY,0))), SUM(CONVERT(float,ISNULL(a.MAINT_AMT,0)))
            FROM dbo.PU_T_STOCK_MAINT a JOIN dbo.CM_M_CUST c ON a.CUST_CODE=c.CUST_CODE
            WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG IN ('9','S','C','G','H')
            GROUP BY UPPER(LTRIM(RTRIM(a.MAT_CODE))), a.CUST_CODE""", fr, to)
        for m, cc, cnm, cty, q, amt in cu.fetchall():
            sup.append((_U(m), str(cc).strip(), cnm, str(cty or "").strip(), "협력", float(q or 0), float(amt or 0)))
        cu.execute("""SELECT UPPER(LTRIM(RTRIM(a.MAT_CODE))), a.CUST_CODE, MAX(ISNULL(c.CUST_DESC,a.CUST_CODE)),
              SUM(CONVERT(float,ISNULL(a.MAINT_QTY,0))), SUM(CONVERT(float,ISNULL(a.MAINT_AMT*ISNULL(a.EXCHANGE_RATE,1),0)))
            FROM dbo.PU_T_STOCK_MAINT_C a LEFT JOIN dbo.CM_M_CUST c ON a.CUST_CODE=c.CUST_CODE
            WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.DIVISION='P'
            GROUP BY UPPER(LTRIM(RTRIM(a.MAT_CODE))), a.CUST_CODE""", fr, to)
        for m, cc, cnm, q, amt in cu.fetchall():
            sup.append((_U(m), str(cc).strip(), cnm, "IMP", "수입", float(q or 0), float(amt or 0)))

        # 2) 대상 base = 선택 유형(ct) 공급이 있는 base
        def is_prim(kind, cty):
            return (kind == "수입") if ct == "IMP" else (cty == ct)
        prim_bases = set(base(m) for m, cc, cnm, cty, kind, q, amt in sup if q > 0 and is_prim(kind, cty) and not _is_nonmat(base(m)))

        # 3) 소비·조정·순이동 broad (전 코드, PU) → base 집계
        cu.execute("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))) mat,
            SUM(CASE WHEN MAINT_TAG='B' THEN -CONVERT(float,ISNULL(MAINT_QTY,0)) ELSE 0 END) gagong,
            SUM(CASE WHEN MAINT_TAG='5' THEN -CONVERT(float,ISNULL(MAINT_QTY,0)) ELSE 0 END) sagub,
            SUM(CASE WHEN MAINT_TAG IN ('1','2') THEN CONVERT(float,ISNULL(MAINT_QTY,0)) ELSE 0 END) adj,
            SUM(CASE WHEN MAINT_TAG='3' THEN 0 ELSE CONVERT(float,ISNULL(MAINT_QTY,0)) END) netmv
          FROM dbo.PU_T_STOCK_MAINT WHERE MAINT_YMD BETWEEN ? AND ? GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))""", fr, to)
        mv = {_U(r[0]): {"gagong": float(r[1] or 0), "sagub": float(r[2] or 0), "adj": float(r[3] or 0), "netmv": float(r[4] or 0)} for r in cu.fetchall()}
        # (참고) 전이동 누적 재고(≤to): PU 전 태그 + 수입(_C). — 실재고 표시엔 안 씀(정본=자재일마감 사용). 내부 참고만.
        cu.execute("SELECT UPPER(LTRIM(RTRIM(MAT_CODE))) mat, SUM(CONVERT(float,ISNULL(MAINT_QTY,0))) q FROM dbo.PU_T_STOCK_MAINT WHERE MAINT_YMD <= ? GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))", to)
        stock_cum = {_U(r[0]): float(r[1] or 0) for r in cu.fetchall()}
        cu.execute("SELECT UPPER(LTRIM(RTRIM(MAT_CODE))) mat, SUM(CONVERT(float,ISNULL(MAINT_QTY,0))) q FROM dbo.PU_T_STOCK_MAINT_C WHERE MAINT_YMD <= ? AND DIVISION='P' GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))", to)
        for r in cu.fetchall():
            m = _U(r[0]); stock_cum[m] = stock_cum.get(m, 0.0) + float(r[1] or 0)
        # ★정본재고 = 자재일마감(이동평균) nx.mat_stock_daily. 실재고=정본기말(≤to)·기초=정본기초(<fr).
        #   ※matverify는 스냅샷을 저장하지 않고 정본을 조회만(read-only). 정확코드→base 폴딩. 미커버=정본이 추적 안 하는 품목.
        off_end, off_beg, off_cov = {}, {}, set()
        cu.execute("""SELECT mat_code, stock_qty FROM (
              SELECT UPPER(LTRIM(RTRIM(mat_code))) mat_code, CONVERT(float,ISNULL(stock_qty,0)) stock_qty,
                     ROW_NUMBER() OVER (PARTITION BY UPPER(LTRIM(RTRIM(mat_code))) ORDER BY ymd DESC) rn
              FROM PARTNER_ERP_TEST3.nx.mat_stock_daily WHERE ymd <= ?) t WHERE rn=1""", to)
        for mc, q in cu.fetchall():
            off_end[_U(mc)] = float(q or 0); off_cov.add(_U(mc))
        cu.execute("""SELECT mat_code, stock_qty FROM (
              SELECT UPPER(LTRIM(RTRIM(mat_code))) mat_code, CONVERT(float,ISNULL(stock_qty,0)) stock_qty,
                     ROW_NUMBER() OVER (PARTITION BY UPPER(LTRIM(RTRIM(mat_code))) ORDER BY ymd DESC) rn
              FROM PARTNER_ERP_TEST3.nx.mat_stock_daily WHERE ymd < ?) t WHERE rn=1""", fr)
        for mc, q in cu.fetchall():
            off_beg[_U(mc)] = float(q or 0)
        # 수입(_C)은 netmv(PU)에 없음 → 순증에 별도 가산
        imp_net = {}
        for m, cc, cnm, cty, kind, q, amt in sup:
            if kind == "수입": imp_net[m] = imp_net.get(m, 0.0) + q

        # 4) 리시빙(참고)
        cu.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), SUM(CONVERT(float,ISNULL(RECV_QTY,0))) FROM dbo.SA_T_LG_RECEIVING_DTL WHERE RECEIVING_YMD BETWEEN ? AND ? GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))", fr, to)
        recv = {_U(r[0]): float(r[1] or 0) for r in cu.fetchall()}

        # 5) items 조립 (prim_bases만). vendors=전 공급처(유형태그). buy_all=Σ공급, prim=선택유형 공급(단가/업체매입).
        items = {}
        def _it(k): return items.setdefault(k, {"item": k, "buy_all": 0.0, "prim_q": 0.0, "prim_amt": 0.0,
                                                 "gagong": 0.0, "sagub": 0.0, "adj": 0.0, "netmv": 0.0, "recv": 0.0,
                                                 "stock": 0.0, "off_end": 0.0, "off_beg": 0.0, "off_cov": False,
                                                 "vendors": {}, "raw_codes": set()})
        for m, cc, cnm, cty, kind, q, amt in sup:
            k = base(m)
            if k not in prim_bases or q == 0: continue
            d = _it(k); d["buy_all"] += q; d["raw_codes"].add(m)
            tname = "수입" if kind == "수입" else _CT_NAME.get(cty, cty or "기타")
            vk = kind + ":" + cc
            v = d["vendors"].setdefault(vk, {"code": cc, "name": cnm, "type": cty, "tname": tname, "kind": kind, "q": 0.0, "amt": 0.0})
            v["q"] += q; v["amt"] += amt
            if is_prim(kind, cty): d["prim_q"] += q; d["prim_amt"] += amt
        for m, d0 in mv.items():
            k = base(m)
            if k in items:
                items[k]["gagong"] += d0["gagong"]; items[k]["sagub"] += d0["sagub"]
                items[k]["adj"] += d0["adj"]; items[k]["netmv"] += d0["netmv"]
        for m, q in imp_net.items():
            k = base(m)
            if k in items: items[k]["netmv"] += q      # 수입 인플로우 → 순증
        for m, q in recv.items():
            k = base(m)
            if k in items: items[k]["recv"] += q
        for m, q in stock_cum.items():                 # (참고) 전이동 누적, PU — 표시 안 함
            k = base(m)
            if k in items: items[k]["stock"] += q
        for m, q in off_end.items():                    # ★정본기말(자재일마감) → 실재고
            k = base(m)
            if k in items: items[k]["off_end"] += q; items[k]["off_cov"] = True
        for m, q in off_beg.items():                    # ★정본기초(자재일마감) → 기초
            k = base(m)
            if k in items: items[k]["off_beg"] += q

        # 품명
        cu.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), MAX(item_name) FROM PARTNER_ERP_TEST3.nx.item GROUP BY UPPER(LTRIM(RTRIM(item_code)))")
        nm = {_U(a): b for a, b in cu.fetchall()}

        # 6) 순증·흐름·플래그
        out = []
        for k, d in items.items():
            prim, buyall = d["prim_q"], d["buy_all"]           # 협력사(선택), 총매입
            other = buyall - prim                              # 타협력사(그 외 공급처)
            gag_all, sag, adj, rv, stock = d["gagong"], d["sagub"], d["adj"], d["recv"], d["stock"]
            jiknap = min(rv, gag_all) if gag_all > 0 else 0.0  # 직납(리시빙分, 가공출고 내에서 분리 → 이중차감 없음)
            gagong = gag_all - jiknap                          # 가공(순소비)
            up = d["prim_amt"] / prim if prim else 0.0
            net = d["netmv"]                                   # 순증 = 총매입 − 가공 − 사급 − 직납 + 조정 (전 공급원)
            consume = gag_all + sag
            imp_q = sum(v["q"] for v in d["vendors"].values() if v["kind"] == "수입")
            unreliable = prim < 10 or up <= 0
            if sag > buyall * 0.3: flow = "사급재출고형"
            elif jiknap > buyall * 0.3: flow = "직납"
            elif imp_q > buyall * 0.3: flow = "수입주도"
            elif len(d["vendors"]) > 1: flow = "다업체소싱"
            else: flow = "컴포넌트(가공소비)"
            net_amt = 0 if unreliable else round(net * up)
            # ★정본재고(자재일마감). 미커버=정본이 이 품목을 추적 안 함 → 실재고 확인 불가(빈값).
            cov = d["off_cov"]
            off_e = d["off_end"] if cov else None      # 실재고(정본기말)
            off_b = d["off_beg"] if cov else None       # 기초(정본기초)
            off_chg = (off_e - off_b) if cov else None  # 정본 재고증감(=기말−기초)
            flags = []
            if unreliable and abs(net) > 100: flags.append("단가불명")
            if consume <= 0 and buyall > 0: flags.append("소비없음")
            big = (not unreliable) and net > 0 and net > buyall * 0.2 and net_amt > 3_000_000
            if big: flags.append("순증과다")
            # ★순증만큼 정본재고가 실제로 늘었는지 대조: big인데 정본증감이 순증에 크게 못 미침 = 과매입 미실현(통과/타창고)
            if big and cov and off_chg is not None and off_chg < net * 0.5: flags.append("재고미확인")
            if big and not cov: flags.append("정본미커버")   # 정본(자재일마감)이 추적 안 함 → 실재고 대조 불가
            if cov and off_e is not None and off_e < -100: flags.append("재고음수")   # 정본재고 음수=데이터 이상
            if sag > buyall * 1.05: flags.append("사급>매입")
            out.append({
                "item": k, "name": nm.get(k, ""),
                "beg": (round(off_b) if off_b is not None else None),   # 기초(정본기초, 자재일마감)
                "buy_q": round(prim), "buy_amt": round(d["prim_amt"]), "buy_all": round(buyall), "other_q": round(other),
                "gagong": round(gagong), "jiknap": round(jiknap), "sagub": round(sag), "adj": round(adj),
                "consume": round(consume), "net": round(net), "net_amt": net_amt,
                "stock": (round(off_e) if off_e is not None else None),   # 실재고(정본기말, 자재일마감)
                "off_chg": (round(off_chg) if off_chg is not None else None), "off_cov": cov,
                "recv": round(rv), "flow": flow, "flags": flags,
                "vendors": sorted(d["vendors"].values(), key=lambda x: -x["q"]),
                "n_codes": len(d["raw_codes"]),
            })
        out.sort(key=lambda x: -x["net_amt"])
        return {"ct": ct, "fr": fr, "to": to, "count": len(out), "rows": out}
    finally:
        cn.close()


def _today6():
    cn = _conn(); cu = cn.cursor()
    try:
        cu.execute("SELECT FORMAT(GETDATE(),'yyMMdd')"); return cu.fetchone()[0]
    finally:
        cn.close()


@router.get("/api/matverify/coop")
def matverify_coop(ct: str = Query("6"), ymd_from: str = Query(""), ymd_to: str = Query(""),
                   ym_from: str = Query(""), ym_to: str = Query(""), nocache: str = Query("")):
    """매입유형(ct=CUST_TYPE, 기본6=절삭협력; 'IMP'=수입)별 매입-소비 실측 수불 진단.
       기간=일자(ymd_from~ymd_to YYMMDD) 우선, 없으면 월(ym_from~ym_to). 기본=조회 당월1일~당일."""
    ct = (ct or "6").strip()
    t6 = _today6()
    fr = _digits(ymd_from, 6) or ((_digits(ym_from, 4) or t6[:4]) + "01")
    to = _digits(ymd_to, 6) or ((_digits(ym_to, 4) + "99") if _digits(ym_to, 4) else t6)
    key = (ct, fr, to); now = _time.time()
    if not str(nocache).strip():
        hit = _CACHE.get(key)
        if hit and hit[0] > now: return hit[1]
    res = _build(ct, fr, to)
    _CACHE[key] = (now + 600, res)
    return res
