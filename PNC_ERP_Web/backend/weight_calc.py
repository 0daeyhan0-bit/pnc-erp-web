# -*- coding: utf-8 -*-
"""무게정산(중량조정): 원소재/용접봉 = 출고중량(tag5) − 업체가공 입고중량 = 차액, ×(시세−사급가).
   [확정규칙 — 4월 담당자마감 실측대조]
     입고수량 = ERP 확정입고(9/S/C/G/H, 마감기준 창)  ← 유일 신뢰원천
     인정부품 = CS_M_ITEM_BOM 재귀전개(_explode), SAGUB_FLAG=1(사급) 제외 leaf 단품
     중량     = 기하동중량 π(D−T)·T·L·8.94/1e6 = (D−T)·T·L·0.02809·0.001 (CU/고강도)
     용접봉   = _load_weld(레거시 정본) — 소요량식 확정 후 별도
   ※nx.coop_copper_unit(동 원단위 마스터, geom 99.9%검증) 통합은 보류:
     Assy 마스터값이 '사급 포함'+변형정규화붕괴라 현행 '사급 제외' 규칙과 충돌 → 사급규칙 확정 후 통합.
     _norm_code/_load_copper_master 헬퍼는 그때 사용(현재 미사용).
   매칭 Assy는 담당자수량과 ±5% 일치. 담당자 수기항목(전산에 없음)은 반영 안 함."""
import sys, os, threading, math, re, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'New_ERP'))  # Projects\New_ERP
import pyodbc, db_client

_lock = threading.Lock()
_MAPS = None  # (META, CH) 캐시
_CU_MASTER = None  # 동 원단위 마스터(nx.coop_copper_unit) 캐시: (부품dict, Assydict)
_SUF = re.compile(r"-\d+(-\d+)?$")

def _norm_code(c):
    """동 원단위 마스터 키 정규화(적재 시 finalize_master와 동일 규칙)."""
    c = re.sub(r"\s+", "", str(c).strip().upper())
    c = re.sub(r"[\(\+].*$", "", c)      # (링/(마·+용접링 꼬리 제거
    c = re.sub(r"번$|품\d+$", "", c)      # -2번 / 품7 제거
    return _SUF.sub("", c).strip()

def _load_copper_master():
    """검증된 동 원단위 마스터(nx.coop_copper_unit) 로드 → (부품, Assy) dict. geom99.9%·담당수불 정본."""
    global _CU_MASTER
    if _CU_MASTER is not None:
        return _CU_MASTER
    with _lock:
        if _CU_MASTER is not None:
            return _CU_MASTER
        part, assy = {}, {}
        try:
            tx = _tx(); tc = tx.cursor()
            tc.execute("SELECT norm_code, kind, copper_unit_kg FROM nx.coop_copper_unit")
            for nc, kind, kg in tc.fetchall():
                (part if str(kind).strip() == '부품' else assy).setdefault(str(nc).strip().upper(), float(kg or 0))
            tx.close()
        except Exception:
            pass
        _CU_MASTER = (part, assy)
        return _CU_MASTER

def _ro():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', readonly=True)

COPPER = {'CU', '고강도'}

def _load_maps():
    global _MAPS
    if _MAPS is not None:
        return _MAPS
    with _lock:
        if _MAPS is not None:
            return _MAPS
        cn = _ro(); cur = cn.cursor()
        # 단위중량 = ITEM_WEIGHT 우선(소구경 정확), 없으면(0/NULL) 기하동중량 π(D−T)·T·L·8.94/1e6
        cur.execute("""SELECT ITEM_CODE, ISNULL(ITEM_WEIGHT,0), ISNULL(ITEM_DIAM,0), ISNULL(ITEM_THICK,0),
                              ISNULL(ITEM_LENGTH,0), METAL_GUBUN, ISNULL(ITEM_DESC,'')
                       FROM PR_M_ITEM""")
        META = {}
        for ic, iw, d, t, L, mg, nm in cur.fetchall():
            cls = None; w = 0.0
            if mg in COPPER:
                cls = 'raw'
                iw = float(iw or 0)
                if iw > 0:
                    w = iw                                       # ITEM_WEIGHT 우선
                else:
                    d = float(d or 0); t = float(t or 0); L = float(L or 0)
                    if d > 0 and t > 0 and L > 0:
                        w = math.pi * (d - t) * t * L * 8.94 / 1e6   # 없으면 기하동중량
            elif '용접봉' in (nm or ''):
                cls = 'weld'
            META[str(ic).strip().upper()] = (w, cls)          # ★키 정규화(공백패딩·대소문자 통일)
        cur.execute("""SELECT ITEM_CODE, MAT_CODE, USE_QTY, ISNULL(SAGUB_FLAG,'0')
                       FROM CS_M_ITEM_BOM WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101'""")
        CH = {}
        for p, c, q, sag in cur.fetchall():
            CH.setdefault(str(p).strip().upper(), []).append((str(c).strip().upper(), float(q or 0), str(sag)))
        cn.close()
        # ★협력사 기준 단위중량 오버라이드(nx.coop_raw_spec) — 협력사 정산기준(두께 0.65·짧은 길이)은 LG(PR_M_ITEM)와 별개.
        #   coop 단품 = 협력사 정산 리프(자기 중량으로 마감). 하위 사급 BOM으로 더 전개하지 않음.
        COOP_SET = set()
        try:
            tx = _tx(); tc = tx.cursor()
            tc.execute("SELECT item_code, unit_weight FROM nx.coop_raw_spec WHERE unit_weight IS NOT NULL AND unit_weight>0")
            for ic, uw in tc.fetchall():
                k = str(ic).strip().upper()
                META[k] = (float(uw), 'raw'); COOP_SET.add(k)
            tx.close()
        except Exception:
            pass
        # 협력사 BOM(nx.coop_bom) — CS_M_ITEM_BOM 전개결손 보완(정상 전개)
        COOPB = {}
        try:
            tx = _tx(); tc = tx.cursor()
            tc.execute("SELECT parent, child, use_qty FROM nx.coop_bom")
            for p, c, u in tc.fetchall():
                COOPB.setdefault(str(p).strip().upper(), []).append((str(c).strip().upper(), float(u or 1)))
            tx.close()
        except Exception:
            pass
        _MAPS = (META, CH, COOPB, COOP_SET)
        return _MAPS

def _explode(item, META, CH, COOPB, COOP_SET, memo):
    """1개 → (raw_kg, weld_kg): 업체가공(SAGUB_FLAG!=1) 경로의 동/용접봉 중량.
       ★coop 단품(COOP_SET)은 협력사 정산 리프 = 자기 중량으로 마감(사급 하위BOM 전개 안 함).
       CS_M_ITEM_BOM 전개가 0(동/용접봉 미도달)이면 협력사BOM(nx.coop_bom)으로 정상 전개."""
    if item in memo:
        return memo[item]
    memo[item] = (0.0, 0.0)
    ch = CH.get(item)
    if ch:
        rk = wk = 0.0
        for c, q, sag in ch:
            if sag == '1':      # 사급(우리가 가공/단품 제공) 제외 — 업체가공만 인정
                continue
            cr, cw = _explode(c, META, CH, COOPB, COOP_SET, memo)
            rk += cr * q; wk += cw * q
        if rk > 0 or wk > 0:            # 정상 전개 → 그대로
            memo[item] = (rk, wk)
            return memo[item]
        # 전개가 0(자식이 전부 사급/비동) → coop 단품이면 자기중량, 아니면 협력사BOM 폴백
        if item in COOP_SET:
            r = (META[item][0], 0.0); memo[item] = r
            return r
        cb = COOPB.get(item)
        if cb:
            rk = wk = 0.0
            for c, q in cb:
                cr, cw = _explode(c, META, CH, COOPB, COOP_SET, memo)
                rk += cr * q; wk += cw * q
            memo[item] = (rk, wk)
            return memo[item]
        return memo[item]              # (0,0)
    # CS_M_ITEM_BOM 자식 없음 = 리프
    cb = COOPB.get(item)
    if cb and item not in COOP_SET:     # coop 단품은 리프(자기중량), 그 외만 협력사BOM 전개
        rk = wk = 0.0
        for c, q in cb:
            cr, cw = _explode(c, META, CH, COOPB, COOP_SET, memo)
            rk += cr * q; wk += cw * q
        memo[item] = (rk, wk)
        return memo[item]
    w, cls = META.get(item, (0.0, None))
    r = (w, 0.0) if cls == 'raw' else ((0.0, w) if cls == 'weld' else (0.0, 0.0))
    memo[item] = r
    return r

_WELD = None
def _tx():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')

def _load_weld():
    """품목별 용접봉 소요량 = ★레거시 정본(w_cs_esti ×1.5룰): CS_M_ITEM_BOM.USE_QTY = Σ(관경별 CS_T_ITEM_WELD.ITEM_USE_QTY) × 1.5.
       재고소비(nx.bom)·원가(BOM)와 동일 정본으로 통일(15/15검증, AJR76562811=0.0036).
       ※nx.weld_rate/coop_rate(WELD_QTY×관경rate, 실험적)는 정본 아님 → 폐기(미사용)."""
    global _WELD
    if _WELD is not None:
        return _WELD
    with _lock:
        if _WELD is not None:
            return _WELD
        cn = _ro(); cur = cn.cursor()
        # 정본: 부모품목별 Σ ITEM_USE_QTY(관경별 소요량) × 1.5
        cur.execute("SELECT P_ITEM_CODE, ISNULL(SUM(CAST(ITEM_USE_QTY AS float)),0) FROM CS_T_ITEM_WELD GROUP BY P_ITEM_CODE")
        soyo = {str(p).strip().upper(): round(float(q or 0) * 1.5, 4) for p, q in cur.fetchall()}
        cn.close()
        _WELD = soyo
        return _WELD

_MAGAM = """WITH MAGAM(CUST_CODE,JUN_YYMM,JUN_MAGAM_DAY,MAGAM_DAY) AS (
  SELECT CUST_CODE, format(dateadd(MONTH,-1,convert(date,'{ym}'+'01',12)),'yyMM') JUN_YYMM,
    ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'{ym}'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY,
    ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='{ym}' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM CM_M_CUST A)"""
_WIN = "A.MAINT_YMD > mg.JUN_YYMM+mg.JUN_MAGAM_DAY AND A.MAINT_YMD <= '{ym}'+mg.MAGAM_DAY"

def compute(ym, real_raw=25000.0, sagub_raw=20000.0, real_weld=None, sagub_weld=None):
    """업체별 원소재/용접봉 출고·입고·차액·정산금액. ym=YYMM."""
    META, CH, COOPB, COOP_SET = _load_maps()
    WELD = _load_weld()
    memo = {}
    cn = _ro(); cur = cn.cursor()
    mg = _MAGAM.format(ym=ym); win = _WIN.format(ym=ym)
    # 원소재 출고: tag5 원소재(E/G 210 KG)
    cur.execute(f"""{mg}
      SELECT A.CUST_CODE, SUM(-A.MAINT_QTY)
      FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG='5' AND {win} AND M.ITEM_SGROUP='210' AND M.UNIT='KG' AND M.ITEM_LGROUP IN ('E','G')
      GROUP BY A.CUST_CODE""")
    out = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    # 용접봉 출고(사급): tag5 용접봉(RAC*/Solder) by vendor
    cur.execute(f"""{mg}
      SELECT A.CUST_CODE, SUM(-A.MAINT_QTY)
      FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG='5' AND {win} AND (A.MAT_CODE LIKE 'RAC%' OR M.ITEM_DESC LIKE '%용접봉%' OR M.ITEM_DESC LIKE '%Solder%')
      GROUP BY A.CUST_CODE""")
    wout = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    # 입고중량: 확정입고(9/S/C/G/H) × 업체가공 동/용접봉 중량
    cur.execute(f"""{mg}
      SELECT A.CUST_CODE, A.MAT_CODE, SUM(A.MAINT_QTY)
      FROM PU_T_STOCK_MAINT A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG IN ('9','S','C','G','H') AND {win}
      GROUP BY A.CUST_CODE, A.MAT_CODE HAVING SUM(A.MAINT_QTY)>0""")
    inr = {}; inw = {}
    for cc, mat, q in cur.fetchall():
        mk = str(mat).strip().upper()   # ★키 정규화(META/CH/COOPB/WELD 조회 일치)
        rk, _wk = _explode(mk, META, CH, COOPB, COOP_SET, memo)
        qf = float(q or 0)
        if rk: inr[cc] = inr.get(cc, 0.0) + rk * qf
        ws = WELD.get(mk, 0.0)          # 용접봉 소요 = 부품별(포인트×coop_rate) × 입고qty
        if ws: inw[cc] = inw.get(cc, 0.0) + ws * qf
    cn.close()
    res = {}
    for cc in set(out) | set(inr) | set(inw) | set(wout):
        ro_ = out.get(cc, 0.0); ri = inr.get(cc, 0.0)
        wo = wout.get(cc, 0.0); wi = inw.get(cc, 0.0)
        rdiff = ro_ - ri
        ramt = round(rdiff * (real_raw - sagub_raw))
        wdiff = wo - wi                                  # 용접봉 차액 = 출고 − 소요
        wamt = round(wdiff * (real_weld - sagub_weld)) if (real_weld is not None) else 0  # 용접봉 시세 입력 후
        res[cc] = {
            "raw_out": round(ro_, 1), "raw_in": round(ri, 1), "raw_diff": round(rdiff, 1), "raw_amt": ramt,
            "weld_out": round(wo, 3), "weld_in": round(wi, 3), "weld_diff": round(wdiff, 3), "weld_amt": wamt,
        }
    return res

# ================= ★견적기준 무게정산(신규, compute()와 완전 독립) =================
# 거래처코드(CUST) → coop_quote vendor명 (절삭 8개 협력사). 견적 소요는 이 업체만 적용.
_COOP_CUST_VENDOR = {
    '2142': '세광산업', '233': '썬텍코리아주식회사', '2148': '대원산업', '2096': '미래정밀',
    '2306': '명진산업', '2068': '이젠터', '2266': '케이비', '2048': '중앙정밀',
    '2250': '수테크',   # 어큐뮬레이터 제작(신규 9번째). 견적=수불장 치수 geom. 출고=일신실업(ERP tag5 없음).
}
_QUOTE_SOYO = None
_QUOTE_TS = [0.0]
def _load_quote_soyo():
    """견적서(nx.coop_quote_part_v2) 소요 맵: (vendor, assy_upper) → (동소요중량, 용접봉소요).
       동=ptype_v2='수불'(제작동관) Σsoyo_weight(kg) · 용접봉=ptype_v2='용접봉' Σsoyo. 10분 TTL."""
    global _QUOTE_SOYO
    now = time.time()
    if _QUOTE_SOYO is not None and (now - _QUOTE_TS[0] < 600):
        return _QUOTE_SOYO
    qraw = {}; qweld = {}
    tx = _tx(); tc = tx.cursor()
    tc.execute("""SELECT vendor, UPPER(LTRIM(RTRIM(assy_code))), ISNULL(ptype_v2,''),
        ISNULL(soyo_weight,0), ISNULL(soyo,0)
        FROM nx.coop_quote_part_v2 WHERE ISNULL(is_active,1)=1 AND ISNULL(settle_exclude,0)=0""")
    for v, assy, pt, sw, so in tc.fetchall():
        v = str(v).strip()
        if pt == '수불':
            qraw[(v, assy)] = qraw.get((v, assy), 0.0) + float(sw or 0)
        elif pt == '용접봉':
            qweld[(v, assy)] = qweld.get((v, assy), 0.0) + float(so or 0)
    tx.close()
    _QUOTE_SOYO = (qraw, qweld); _QUOTE_TS[0] = now
    return _QUOTE_SOYO

_CS_KIDS = {}   # code -> [자식코드] (CS_M_ITEM_BOM, except제외). BOM 구조는 정적 → 영구캐시
def _cs_kids(bcur, code):
    if code not in _CS_KIDS:
        bcur.execute("SELECT UPPER(LTRIM(RTRIM(MAT_CODE))) FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM "
                     "WHERE UPPER(LTRIM(RTRIM(ITEM_CODE)))=? AND ISNULL(CS_CALC_EXCEPT_FLAG,'')<>'1'", code)
        _CS_KIDS[code] = [str(r[0]).strip() for r in bcur.fetchall()]
    return _CS_KIDS[code]
def _expand_dong(bcur, vendor, code, qraw, seen):
    """완제품 견적 동 소요중량 = 자기 직접 동(qraw) + 조립SUB자식들의 동 재귀합.
       ★레거시 bom()이 CG2 SUB를 매입leaf로 막아 안의 동을 놓치던 것 보정 — 조립품(자체BOM 보유)이면 전개."""
    if code in seen:
        return 0.0
    seen = seen | {code}
    tot = qraw.get((vendor, code), 0.0)
    for ch in _cs_kids(bcur, code):
        if _cs_kids(bcur, ch):   # 자식BOM 보유 = 조립SUB → 전개(그 안의 동 포함)
            tot += _expand_dong(bcur, vendor, ch, qraw, seen)
    return tot

def compute_quote(ym, real_raw=25000.0, sagub_raw=20000.0, real_weld=None, sagub_weld=None, expand_sub=True):
    """★견적기준 무게정산: 출고(tag5) − 견적서 소요(coop_quote_part_v2) = 차액.
       원소재 소요 = Σ(완제품 입고수량 × 견적 동소요중량) · 용접봉 소요 = Σ(입고수량 × 견적 용접봉소요).
       견적 없는 완제품 = 소요 0(compute()의 ITEM_WEIGHT master 폴백 안 함). 절삭 8개 협력사만.
       compute()와 독립 — 기존 마스터기준 무게정산에 영향 없음."""
    qraw, qweld = _load_quote_soyo()
    cn = _ro(); cur = cn.cursor()
    mg = _MAGAM.format(ym=ym); win = _WIN.format(ym=ym)
    # 원소재 출고: tag5 원소재(E/G 210 KG) — compute()와 동일
    cur.execute(f"""{mg}
      SELECT A.CUST_CODE, SUM(-A.MAINT_QTY)
      FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG='5' AND {win} AND M.ITEM_SGROUP='210' AND M.UNIT='KG' AND M.ITEM_LGROUP IN ('E','G')
      GROUP BY A.CUST_CODE""")
    out = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    # 용접봉 출고(사급): tag5 용접봉 — compute()와 동일
    cur.execute(f"""{mg}
      SELECT A.CUST_CODE, SUM(-A.MAINT_QTY)
      FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG='5' AND {win} AND (A.MAT_CODE LIKE 'RAC%' OR M.ITEM_DESC LIKE '%용접봉%' OR M.ITEM_DESC LIKE '%Solder%')
      GROUP BY A.CUST_CODE""")
    wout = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    # 입고(완제품) × 견적 소요 = 소요중량
    cur.execute(f"""{mg}
      SELECT A.CUST_CODE, UPPER(LTRIM(RTRIM(A.MAT_CODE))), SUM(A.MAINT_QTY)
      FROM PU_T_STOCK_MAINT A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG IN ('9','S','C','G','H') AND {win}
      GROUP BY A.CUST_CODE, UPPER(LTRIM(RTRIM(A.MAT_CODE))) HAVING SUM(A.MAINT_QTY)>0""")
    inr = {}; inw = {}; noq = {}
    ingo = cur.fetchall()
    bcur = cn.cursor()   # CG2 SUB 전개용(BOM 조회) — 별도 커서
    for cc, mat, q in ingo:
        vendor = _COOP_CUST_VENDOR.get(str(cc).strip())
        if not vendor:
            continue
        qf = float(q or 0)
        # ★원소재 동 = CG2 SUB 전개 포함(expand_sub=True) / 미전개 시 직접 견적만
        rk = _expand_dong(bcur, vendor, mat, qraw, set()) if expand_sub else qraw.get((vendor, mat), 0.0)
        ws = qweld.get((vendor, mat))
        if rk and rk > 0:
            inr[cc] = inr.get(cc, 0.0) + rk * qf
        if ws is not None:
            inw[cc] = inw.get(cc, 0.0) + ws * qf
        if (not rk or rk <= 0) and ws is None:
            noq[cc] = noq.get(cc, 0) + 1        # 견적없는 완제품(정보용)
    cn.close()
    res = {}
    for cc in set(out) | set(inr) | set(inw) | set(wout):
        ro_ = out.get(cc, 0.0); ri = inr.get(cc, 0.0)
        wo = wout.get(cc, 0.0); wi = inw.get(cc, 0.0)
        rdiff = ro_ - ri
        ramt = round(rdiff * (real_raw - sagub_raw))
        wdiff = wo - wi
        wamt = round(wdiff * (real_weld - sagub_weld)) if (real_weld is not None) else 0
        res[cc] = {
            "raw_out": round(ro_, 1), "raw_in": round(ri, 1), "raw_diff": round(rdiff, 1), "raw_amt": ramt,
            "weld_out": round(wo, 3), "weld_in": round(wi, 3), "weld_diff": round(wdiff, 3), "weld_amt": wamt,
            "no_quote_items": noq.get(cc, 0),
        }
    return res

# ================= ★규격별 LME 정산금액 (담당 MASTER 모델: 규격별 재고 × (현물가−사급가)) =================
def _load_price_metal(ym):
    """price_metal(apply_ym=20+ym) → (PRICE[(재질,외경)]=(현물,사급), PM[(재질,외경,두께)], canon외경리스트)."""
    apply = ('20' + ym) if len(str(ym)) == 4 else str(ym)
    tx = _tx(); tc = tx.cursor()
    tc.execute("SELECT metal_gubun,CAST(diam AS float),CAST(thick AS float),CAST(std_price AS float),CAST(partner_price AS float) "
               "FROM nx.price_metal WHERE apply_ym=?", apply)
    PRICE = {}; PM = []; canon = set()
    for g, od, th, std, pp in tc.fetchall():
        od = round(float(od), 2); canon.add(od)
        PRICE.setdefault((g, od), (float(std or 0), float(pp or 0)))
        PM.append((g, od, float(th or 0)))
    tx.close()
    return PRICE, PM, sorted(canon)

def _snap_od(od, canon):
    if od is None or not canon:
        return od
    b = min(canon, key=lambda x: abs(x - od))
    return b if abs(b - od) <= 0.35 else round(od, 2)

def _classify_mat(od, th, PM, canon):
    """(외경,두께)→재질: price_metal에서 같은 외경의 최근접 두께 재질. 동점(고강도·CU 등거리)이면 일반(CU) 우선.
       ★얇은 일반관(Φ5×0.41 등)이 고강도로 오분류되는 것 방지 — 실제 스펙표 최근접 매칭."""
    so = _snap_od(od, canon); th = th if th else 0.7
    rows = [r for r in PM if abs(r[1] - so) <= 0.35]
    if not rows and PM:
        nd = min(PM, key=lambda r: abs(r[1] - so))[1]
        rows = [r for r in PM if r[1] == nd]
    if not rows:
        return 'CU'
    ds = sorted((abs(tt - th), g) for g, dd, tt in rows)
    mind = ds[0][0]
    gs = {g for d, g in ds if abs(d - mind) <= 1e-9}
    return 'CU' if ('CU' in gs and len(gs) > 1) else ds[0][1]

def _price_lookup(mg, od, PRICE):
    key = (mg, round(od, 2))
    if key in PRICE:
        return PRICE[key]
    cand = [(abs(o - od), v) for (g, o), v in PRICE.items() if g == mg]
    return min(cand)[1] if cand else (None, None)

def _parse_raw_od(desc):
    """원소재 DESC('Tube,Raw (9.52*0.7)'/'7*0.55 고강도관')에서 외경·두께·고강도여부."""
    g = '고강도' if (desc and '고강' in str(desc)) else None
    od = th = None
    if desc:
        m = re.search(r'(\d+\.?\d*)\s*[\*xX×]\s*(\d+\.?\d*)', str(desc))
        if m:
            od = float(m.group(1)); th = float(m.group(2))
    return g, od, th

def _load_quote_spec():
    """(vendor, assy_upper) → [(외경,두께,soyo_weight)] 수불 부품(스펙 파싱)."""
    tx = _tx(); tc = tx.cursor()
    tc.execute("SELECT vendor, UPPER(LTRIM(RTRIM(assy_code))), spec, ISNULL(soyo_weight,0) "
               "FROM nx.coop_quote_part_v2 WHERE ISNULL(is_active,1)=1 AND ISNULL(settle_exclude,0)=0 AND ptype_v2=N'수불'")
    d = {}
    for v, a, spec, sw in tc.fetchall():
        od = th = None
        if spec and 'x' in str(spec).lower():
            try:
                p = str(spec).lower().split('x'); od = float(p[0]); th = float(p[1])
            except Exception:
                pass
        d.setdefault((str(v).strip(), a), []).append((od, th, float(sw or 0)))
    tx.close()
    return d

def _expand_spec(bcur, vendor, code, qspec, seen, acc, eqb):
    """완제품 소요 동을 규격별로: 자기 수불부품 + 조립SUB(자체BOM) 재귀."""
    if code in seen:
        return
    seen = seen | {code}
    for od, th, sw in qspec.get((vendor, code), []):
        if sw > 0 and od:
            acc.append((od, th, sw * eqb))
    for ch in _cs_kids(bcur, code):
        if _cs_kids(bcur, ch):
            _expand_spec(bcur, vendor, ch, qspec, seen, acc, eqb)

def compute_quote_lme(ym, weld_spot=62700.0, weld_sagub=21100.0):
    """★규격별 LME 정산금액(동) + 용접봉 정산. 담당 MASTER 모델: 재고(출고−소요) × (현물가−사급가).
       동=규격(재질·외경)별 price_metal. 용접봉=1% 단일단가(현물 62700/사급 21100). compute_quote와 독립.
       반환 {CUST_CODE: {raw_out,raw_in,raw_diff,settle_amt,unmapped_out,soyo_only,specs,
                         weld_out,weld_in,weld_diff,weld_amt}}."""
    PRICE, PM, canon = _load_price_metal(ym)
    qspec = _load_quote_spec()
    _qraw, qweld = _load_quote_soyo()   # 용접봉 소요맵 (vendor, assy)→soyo
    cn = _ro(); cur = cn.cursor(); bcur = cn.cursor()
    mg = _MAGAM.format(ym=ym); win = _WIN.format(ym=ym)
    buck = {}   # cc -> {(재질,외경): [출고,소요]}
    unmap = {}  # cc -> 미매핑 출고
    wout = {}; win_ = {}   # 용접봉 출고/소요
    # 출고: tag5 원소재(210·KG·E/G), 외경은 DESC
    cur.execute(f"""{mg}
      SELECT A.CUST_CODE, SUM(-A.MAINT_QTY), MAX(M.ITEM_DESC)
      FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG='5' AND {win} AND M.ITEM_SGROUP='210' AND M.UNIT='KG' AND M.ITEM_LGROUP IN ('E','G')
      GROUP BY A.CUST_CODE, A.MAT_CODE""")
    for cc, q, desc in cur.fetchall():
        if cc not in _COOP_CUST_VENDOR:
            continue
        q = float(q or 0); gk, od, th = _parse_raw_od(desc)
        if not od:
            unmap[cc] = unmap.get(cc, 0.0) + q; continue
        g = gk or _classify_mat(od, th, PM, canon)
        buck.setdefault(cc, {}).setdefault((g, _snap_od(od, canon)), [0.0, 0.0])[0] += q
    # 용접봉 출고(tag5): RAC% / 용접봉 / Solder
    cur.execute(f"""{mg}
      SELECT A.CUST_CODE, SUM(-A.MAINT_QTY)
      FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG='5' AND {win} AND (A.MAT_CODE LIKE 'RAC%' OR M.ITEM_DESC LIKE '%용접봉%' OR M.ITEM_DESC LIKE '%Solder%')
      GROUP BY A.CUST_CODE""")
    for cc, q in cur.fetchall():
        if cc in _COOP_CUST_VENDOR:
            wout[cc] = wout.get(cc, 0.0) + float(q or 0)
    # 소요: 완제품 입고(9/S/C/G/H) × 견적 규격별 동, CG2 전개
    cur.execute(f"""{mg}
      SELECT A.CUST_CODE, UPPER(LTRIM(RTRIM(A.MAT_CODE))), SUM(A.MAINT_QTY)
      FROM PU_T_STOCK_MAINT A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG IN ('9','S','C','G','H') AND {win}
      GROUP BY A.CUST_CODE, UPPER(LTRIM(RTRIM(A.MAT_CODE))) HAVING SUM(A.MAINT_QTY)>0""")
    ingo = cur.fetchall()
    for cc, mat, q in ingo:
        vendor = _COOP_CUST_VENDOR.get(str(cc).strip())
        if not vendor:
            continue
        acc = []; _expand_spec(bcur, vendor, mat, qspec, set(), acc, float(q or 0))
        for od, th, w in acc:
            g = _classify_mat(od, th, PM, canon)
            buck.setdefault(cc, {}).setdefault((g, _snap_od(od, canon)), [0.0, 0.0])[1] += w
        wq = qweld.get((vendor, mat))
        if wq:
            win_[cc] = win_.get(cc, 0.0) + wq * float(q or 0)
    cn.close()
    res = {}
    for cc in set(buck) | set(wout) | set(win_):
        sp = buck.get(cc, {})
        tout = tin = tamt = 0.0; specs = []
        for (g, od), (o, i) in sorted(sp.items()):
            std, pp = _price_lookup(g, od, PRICE)
            diff = (std - pp) if (std is not None and pp is not None) else 0.0
            stock = o - i; amt = stock * diff
            tout += o; tin += i; tamt += amt
            specs.append({"mat": g, "od": od, "out": round(o, 1), "in": round(i, 1),
                          "diff": round(stock, 1), "spot": (round(std) if std else None),
                          "sagub": (round(pp) if pp else None), "amt": round(amt)})
        # 출고 원장(tag5)이 없는 업체(예: 수테크=일신실업 직접공급) → 소요만 표기, 재고·정산은 비움(오해 방지)
        soyo_only = (tout <= 0.01)
        wo = wout.get(cc, 0.0); wi = win_.get(cc, 0.0); wdiff = wo - wi
        wamt = round(wdiff * (weld_spot - weld_sagub))
        res[cc] = {"raw_out": (None if soyo_only else round(tout, 1)), "raw_in": round(tin, 1),
                   "raw_diff": (None if soyo_only else round(tout - tin, 1)),
                   "settle_amt": (None if soyo_only else round(tamt)),
                   "unmapped_out": round(unmap.get(cc, 0.0), 1), "soyo_only": soyo_only,
                   "specs": sorted(specs, key=lambda x: -abs(x["amt"])),
                   "weld_out": (None if soyo_only else round(wo, 1)), "weld_in": round(wi, 3),
                   "weld_diff": (None if soyo_only else round(wdiff, 3)),
                   "weld_amt": (None if soyo_only else wamt)}
    return res
