# -*- coding: utf-8 -*-
"""coopquote 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 협력사견적: 견적(원소재비/가공비 분리) vs 현재 입고가 ============
#  모델: 원소재비 = total_weight(kg) × sagub_price(원/kg) · 가공비 고정
#        판가 = 원소재비 + 가공비 → 사급가 변경 시 원소재비만 재계산, 가공비 유지
#        현재 입고가 = PR_M_ITEM_COST.ITEM_COST (라이브, 최신 COST_APPLY_YMD)
_PREV_YMD = "251231"   # 종전입고가 기준일: 작년 12월 이하 최신 실입고
_INCOST_CACHE = {}     # code(upper) -> (cur_cost, prev_cost, cur_ymd) | None(미존재). 10분 TTL
_INCOST_TS = [0.0]
def _incost(cur, assys):
    """assy_code 리스트 → 실제 입고가(PU_T_STOCK_MAINT TAG='S' 협력사 납품 실거래).
       {assy_upper: (현재입고가=최근 MAINT_COST, 종전입고가=<=251231 최근, 최근납품일 yymmdd)}."""
    out = {}
    if not assys:
        return out
    now = time.time()
    if now - _INCOST_TS[0] > 600:       # 10분 TTL
        _INCOST_CACHE.clear(); _INCOST_TS[0] = now
    need = []
    for a in assys:
        if not a:
            continue
        k = str(a).replace("'", "").strip().upper()
        if k in _INCOST_CACHE:
            v = _INCOST_CACHE[k]
            if v is not None:
                out[k] = v
        elif k not in need:
            need.append(k)
    # ★materialize된 nx.coop_incost 조회(사전계산). 라이브 window 대신 → 첫조회도 즉시.
    #   (갱신: /api/coopquote/refresh-incost 또는 populate_incost.py)
    for i in range(0, len(need), 400):
        chunk = need[i:i + 400]
        if not chunk:
            continue
        inlist = "','".join(chunk)
        try:
            cur.execute(f"SELECT code, cur_cost, prev_cost, cur_ymd FROM nx.coop_incost "
                        f"WHERE UPPER(LTRIM(RTRIM(code))) IN ('{inlist}')")
            for r in cur.fetchall():
                k = str(r[0]).strip().upper()
                v = ((float(r[1]), (float(r[2]) if r[2] is not None else None), str(r[3] or '').strip())
                     if r[1] is not None else None)
                _INCOST_CACHE[k] = v
                if v is not None:
                    out[k] = v
        except Exception:
            pass
    for k in need:                      # 미존재 코드도 캐시(재조회 방지)
        if k not in _INCOST_CACHE:
            _INCOST_CACHE[k] = None
    return out


@router.post("/api/coopquote/refresh-incost")
def coopquote_refresh_incost():
    """nx.coop_incost 재계산(라이브 window). coop_quote/part 전 코드의 현재/종전 실입고가 갱신.
       ~17초 소요(주기/버튼). 이후 목록조회는 이 테이블을 읽어 즉시."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""IF OBJECT_ID('nx.coop_incost') IS NULL
          CREATE TABLE nx.coop_incost(code nvarchar(60) NOT NULL PRIMARY KEY, cur_cost decimal(18,4) NULL,
            prev_cost decimal(18,4) NULL, cur_ymd nvarchar(6) NULL, upd_dt datetime NOT NULL DEFAULT(getdate()))""")
        cur.execute("""SELECT DISTINCT UPPER(LTRIM(RTRIM(code))) FROM (
           SELECT assy_code code FROM nx.coop_quote
           UNION SELECT part_code FROM nx.coop_quote_part WHERE part_code IS NOT NULL) t WHERE LTRIM(RTRIM(code))<>''""")
        codes = [str(r[0]).strip() for r in cur.fetchall()]
        res = {}
        for i in range(0, len(codes), 400):
            inlist = "','".join(c.replace("'", "") for c in codes[i:i + 400])
            cur.execute(f"""WITH M AS (
               SELECT UPPER(LTRIM(RTRIM(MAT_CODE))) IC, MAINT_YMD, MAINT_COST,
                 ROW_NUMBER() OVER(PARTITION BY UPPER(LTRIM(RTRIM(MAT_CODE))) ORDER BY MAINT_YMD DESC) rc,
                 ROW_NUMBER() OVER(PARTITION BY UPPER(LTRIM(RTRIM(MAT_CODE))) ORDER BY (CASE WHEN MAINT_YMD<='{_PREV_YMD}' THEN 0 ELSE 1 END),MAINT_YMD DESC) rp
               FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT WHERE MAINT_TAG='S' AND MAINT_QTY>0 AND MAINT_COST>0
                 AND UPPER(LTRIM(RTRIM(MAT_CODE))) IN ('{inlist}'))
             SELECT IC, MAX(CASE WHEN rc=1 THEN MAINT_COST END), MAX(CASE WHEN rc=1 THEN MAINT_YMD END),
               MAX(CASE WHEN rp=1 AND MAINT_YMD<='{_PREV_YMD}' THEN MAINT_COST END) FROM M GROUP BY IC""")
            for r in cur.fetchall():
                res[str(r[0]).strip()] = (r[1], str(r[2] or '')[-6:], r[3])
        cur.execute("TRUNCATE TABLE nx.coop_incost")
        for code in codes:
            v = res.get(code)
            cur.execute("INSERT INTO nx.coop_incost(code,cur_cost,prev_cost,cur_ymd) VALUES(?,?,?,?)",
                        code, (float(v[0]) if (v and v[0] is not None) else None),
                        (float(v[2]) if (v and v[2] is not None) else None), (v[1] if v else None))
        _INCOST_CACHE.clear()
        return {"ok": True, "codes": len(codes), "with_cost": len(res)}
    finally:
        nx.close()


@router.get("/api/coopquote/vendors")
def coopquote_vendors():
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT vendor, COUNT(*) n FROM nx.coop_quote GROUP BY vendor ORDER BY vendor")
        return {"rows": [{"vendor": str(r[0]).strip(), "n": int(r[1])} for r in cur.fetchall()]}
    finally:
        nx.close()


@router.get("/api/coopquote/list")
def coopquote_list(vendor: str = Query(""), q: str = Query(""), active_only: int = Query(0),
                   ym: str = Query("", description="적용월(전체적용) YYMM|YYYYMM — 인상후 판매단가/사급가 as-of")):
    """협력사 견적 목록 — 인상전(종전) vs 인상후(적용월) 재료비·총가공비·입고가 대비.
       총가공비 = 입고가 − 재료비. 차이(신) = 인상후 총가공비 − 인상전 총가공비.
       적용월(ym)은 리스트 전체에 적용(개별 아님): 인상후 사급부품 판매단가·원소재 사급가를 그 월 기준으로.
       active_only=1 → 최근 4개월 내 실제 납품(입고) 실적 있는 품목만."""
    ym6 = "".join(ch for ch in str(ym or "") if ch.isdigit())
    ym4 = ym6[2:6] if len(ym6) == 6 else (ym6[:4] if len(ym6) >= 4 else "")   # YYMM
    asof_cur = (ym4 + "31") if ym4 else "991231"    # 인상후 판매단가 기준일(YYMMDD)
    nx = _nx(); cur = nx.cursor()
    try:
        where = ["1=1"]; args = []
        if vendor.strip():
            where.append("vendor=?"); args.append(vendor.strip())
        if q.strip():
            where.append("(assy_code LIKE ? OR item_name LIKE ?)")
            args += [f"%{q.strip()}%", f"%{q.strip()}%"]
        cur.execute(f"""SELECT quote_id,vendor,assy_code,item_name,spec,total_weight,sagub_price,
            mat_cost,proc_cost,sale_price,quote_price,final_price,lg_price,currency,status,remark,
            CONVERT(varchar(19),ISNULL(upd_dt,reg_dt),120), ISNULL(grade,N'일반CU'), mat_ratio, ISNULL(fixed_mat,0),
            ISNULL(mat_raw,0), ISNULL(mat_weld,0), ISNULL(mat_part,0)
          FROM nx.coop_quote WHERE {' AND '.join(where)}
          ORDER BY vendor, assy_code""", *args)
        rows = [dict(zip(
            ["quote_id","vendor","assy_code","item_name","spec","total_weight","sagub_price",
             "mat_cost","proc_cost","sale_price","quote_price","final_price","lg_price","currency","status","remark","upd_dt","grade","mat_ratio","fixed_mat","mat_raw","mat_weld","mat_part"],
            [r[0], str(r[1] or ""), str(r[2] or ""), str(r[3] or ""), str(r[4] or ""),
             float(r[5] or 0), float(r[6] or 0), float(r[7] or 0), float(r[8] or 0), float(r[9] or 0),
             (float(r[10]) if r[10] is not None else None), (float(r[11]) if r[11] is not None else None),
             (float(r[12]) if r[12] is not None else None), str(r[13] or "KRW"), str(r[14] or ""),
             str(r[15] or ""), r[16], str(r[17] or "일반CU"),
             (float(r[18]) if r[18] is not None else None), float(r[19] or 0),
             float(r[20] or 0), float(r[21] or 0), float(r[22] or 0)])) for r in cur.fetchall()]
        cost = _incost(cur, [r["assy_code"] for r in rows])
        for r in rows:
            c = cost.get(r["assy_code"].strip().upper())
            r["cur_incost"] = (c[0] if (c and c[0]) else None)   # 현재 실입고가(최근 실거래)
            r["prev_incost"] = c[1] if c else None               # 종전 실입고가(작년 12월 이하 최근)
            r["last_in_ymd"] = (c[2] if (c and c[2]) else None)  # 최근 납품일 yymmdd
            # 최종견적가 = 판가(sale_price = 재료비+가공비) 통합
            fin = r["sale_price"]
            r["final_quote"] = fin
            r["diff"] = (fin - r["cur_incost"]) if (r["cur_incost"] is not None) else None
        # ── ★인상전/인상후 재료비 = bom-form(BOM 소요량 정본) 배치계산 = nx.coop_matcost ──
        #   리스트=모달 자동일치. 사급=판매단가×BOM소요(종전/최신)·동관=소요중량×사급가(종전/신규)·용접봉=소요×단가.
        #   갱신: scratchpad/mat_matcost.py 또는 POST /api/coopquote/refresh-matcost
        assy_up = [r["assy_code"] for r in rows]
        matcost = {}   # assy_upper -> (mat_before, mat_after)
        for i in range(0, len(assy_up), 400):
            chunk = [str(a).replace("'", "").strip() for a in assy_up[i:i + 400] if a]
            if not chunk:
                continue
            inlist = "','".join(c.upper() for c in chunk)
            cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(assy_code))), mat_before, mat_after
                FROM nx.coop_matcost WHERE UPPER(LTRIM(RTRIM(assy_code))) IN ('{inlist}')""")
            for a, mb, ma in cur.fetchall():
                matcost[str(a).strip()] = ((float(mb) if mb is not None else None), (float(ma) if ma is not None else None))
        for r in rows:
            au = r["assy_code"].strip().upper()
            prev_in = r["prev_incost"]; cur_in = r["cur_incost"]
            mc = matcost.get(au)
            if mc and mc[1] is not None:
                mat_after = round(mc[1], 2)
                # 인상전: 종전 데이터 없으면(신규 품목) None → 인상전·손익 비교 안 함
                mat_before = round(mc[0], 2) if mc[0] is not None else None
            else:
                mat_after = round(r["mat_cost"], 2); mat_before = round(r["mat_cost"], 2)  # 미계산 폴백(견적값)
            is_new = (mat_before is None)   # 신규 품목(종전 견적 없음)
            r["is_new"] = is_new
            r["mat_before"] = mat_before; r["mat_after"] = mat_after
            r["mat_now"] = mat_after   # 모달 재료비(현재·인상후) 호환
            # 입고가 = 인상전 종전입고가 · 인상후 현재입고가 (신규는 인상전 숨김)
            r["incost_before"] = (None if is_new else prev_in); r["incost_after"] = cur_in
            # 총가공비 = 입고가 − 재료비
            r["proc_before"] = (round(prev_in - mat_before, 2) if (prev_in is not None and not is_new) else None)
            r["proc_after"] = (round(cur_in - mat_after, 2) if cur_in is not None else None)
            # 재료비율 = 재료비 / 입고가
            r["ratio_before"] = (round(mat_before / prev_in * 100, 1) if (not is_new and prev_in and prev_in > 0) else None)
            r["ratio_after"] = (round(mat_after / cur_in * 100, 1) if (cur_in and cur_in > 0) else None)
            # 가공비 차이 = 인상후 총가공비 − 인상전 총가공비 (신규는 인상전 없음 → 0)
            if is_new:
                r["diff_new"] = 0.0
            else:
                r["diff_new"] = (round(r["proc_after"] - r["proc_before"], 2)
                                 if (r["proc_after"] is not None and r["proc_before"] is not None) else None)
        if active_only:
            cutoff = (datetime.now() - timedelta(days=120)).strftime('%y%m%d')
            rows = [r for r in rows if r.get("last_in_ymd") and r["last_in_ymd"] >= cutoff]
        return {"rows": rows, "count": len(rows), "active_only": bool(active_only)}
    finally:
        nx.close()


@router.get("/api/coopquote/parts")
def coopquote_parts(assy: str = Query(...), vendor: str = Query("")):
    """Assy 하위부품 상세(3분류: 동관/사급부품/용접봉). 재료비·가공비·합계."""
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["assy_code=?"]; a = [assy.strip()]
        if vendor.strip():
            w.append("vendor=?"); a.append(vendor.strip())
        cur.execute(f"""SELECT seq,part_code,part_name,ptype,spec,mat_cost,proc_cost,part_total
            FROM nx.coop_quote_part WHERE {' AND '.join(w)} ORDER BY seq""", *a)
        rows = [dict(zip(["seq","part_code","part_name","ptype","spec","mat_cost","proc_cost","part_total"],
            [r[0], str(r[1] or ""), str(r[2] or ""), str(r[3] or ""), str(r[4] or ""),
             float(r[5] or 0), float(r[6] or 0), float(r[7] or 0)])) for r in cur.fetchall()]
        return {"rows": rows, "count": len(rows)}
    finally:
        nx.close()


@router.post("/api/coopquote/save")
def coopquote_save(payload: dict = Body(...)):
    """신규/수정 견적 저장. 원소재비=total_weight×sagub_price, 판가=원소재비+가공비."""
    qid = int(payload.get("quote_id") or 0)
    vendor = str(payload.get("vendor") or "").strip()
    assy = str(payload.get("assy_code") or "").strip()
    if not vendor or not assy:
        return {"ok": False, "error": "협력사·품번 필수"}
    def fnum(k, d=0.0):
        try: return float(payload.get(k) if payload.get(k) not in (None, "") else d)
        except: return d
    def fopt(k):
        v = payload.get(k)
        try: return float(v) if v not in (None, "") else None
        except: return None
    w = fnum("total_weight"); sg = fnum("sagub_price"); proc = fnum("proc_cost")
    mat = round(w * sg); sale = mat + round(proc)
    item_name = str(payload.get("item_name") or "")[:120]
    spec = str(payload.get("spec") or "")[:80]
    remark = str(payload.get("remark") or "")[:200]
    qp = fopt("quote_price"); fp = fopt("final_price"); lg = fopt("lg_price")
    status = "확정" if fp is not None else str(payload.get("status") or "견적")
    grade = str(payload.get("grade") or "").strip()
    if grade not in ("일반CU", "고강도CU"):
        grade = "일반CU"
    nx = _nx(); cur = nx.cursor()
    try:
        if qid:
            cur.execute("""UPDATE nx.coop_quote SET vendor=?,assy_code=?,item_name=?,spec=?,
                total_weight=?,sagub_price=?,mat_cost=?,proc_cost=?,sale_price=?,
                quote_price=?,final_price=?,lg_price=?,status=?,grade=?,remark=?,upd_user='web',upd_dt=GETDATE()
                WHERE quote_id=?""",
                vendor, assy, item_name, spec, w, sg, mat, round(proc), sale, qp, fp, lg, status, grade, remark, qid)
            return {"ok": True, "quote_id": qid, "mat_cost": mat, "sale_price": sale}
        cur.execute("""INSERT INTO nx.coop_quote(vendor,assy_code,item_name,spec,total_weight,sagub_price,
            mat_cost,proc_cost,sale_price,quote_price,final_price,lg_price,status,grade,remark,src,reg_user)
            OUTPUT INSERTED.quote_id
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'수동입력','web')""",
            vendor, assy, item_name, spec, w, sg, mat, round(proc), sale, qp, fp, lg, status, grade, remark)
        newid = cur.fetchone()[0]
        return {"ok": True, "quote_id": int(newid), "mat_cost": mat, "sale_price": sale}
    finally:
        nx.close()


@router.post("/api/coopquote/recalc")
def coopquote_recalc(payload: dict = Body(...)):
    """사급가 변경 → 원소재비/판가 재계산(가공비 유지). 등급별 2단가 적용:
       일반CU=price_normal, 고강도CU=price_high. scope=all|vendor|ids.
       (구버전 단일 sagub_price도 허용 → 양 등급 동일 적용)"""
    def fnum(k):
        try: return float(payload.get(k))
        except (TypeError, ValueError): return None
    pn = fnum("price_normal"); ph = fnum("price_high"); single = fnum("sagub_price")
    if single is not None and pn is None and ph is None:
        pn = ph = single
    if not pn and not ph:
        return {"ok": False, "error": "사급가 필요"}
    scope = str(payload.get("scope") or "all")
    # 공통 scope where
    scope_sql = ""; scope_args = []
    if scope == "vendor" and payload.get("vendor"):
        scope_sql = " AND vendor=?"; scope_args = [str(payload["vendor"]).strip()]
    elif scope == "ids" and payload.get("ids"):
        ids = [int(x) for x in payload["ids"] if str(x).isdigit()]
        if not ids:
            return {"ok": False, "error": "대상 없음"}
        scope_sql = " AND quote_id IN (" + ",".join(str(i) for i in ids) + ")"
    nx = _nx(); cur = nx.cursor()
    try:
        total = 0; detail = {}
        for grade, price in (("일반CU", pn), ("고강도CU", ph)):
            if not price or price <= 0:
                continue
            cur.execute(f"""UPDATE nx.coop_quote
                SET sagub_price=?, mat_cost=ROUND(total_weight*?,0),
                    sale_price=ROUND(total_weight*{float(price)},0)+proc_cost,
                    upd_user='web', upd_dt=GETDATE()
                WHERE total_weight>0 AND grade=?{scope_sql}""",
                float(price), float(price), grade, *scope_args)
            detail[grade] = int(cur.rowcount); total += int(cur.rowcount)
        return {"ok": True, "count": total, "detail": detail, "price_normal": pn, "price_high": ph}
    finally:
        nx.close()


_VENDOR2CODE = {'대원산업': '2148', '미래정밀': '2096', '명진산업': '2306', '중앙정밀': '2048',
                '이젠터': '2068', '케이비': '2266', '세광산업': '2142', '썬텍코리아': '233', '썬텍': '233'}

@router.get("/api/coopquote/bom-form")
def coopquote_bom_form(item: str = Query(..., description="품번(Assy)"), vendor: str = Query(""),
                       ym: str = Query("", description="적용월 YYMM|YYYYMM(사급가=판매단가 as-of)")):
    """견적 입력폼용: 현 BOM(CS_M_ITEM_BOM) 구성 전개 + 부품별 역할/스펙/매입가/공정 프리필.
       구성=현BOM 정본(고정). 직원은 '제작동관'의 협력사 스펙(외경/두께/길이)만 채우면 됨.
       ★재료비: 사급부품=판매단가(사급가·해당협력사·적용월기준) · 제작동관=소요중량×사급가 · 용접봉=소요×단가.
       공정=coop_part_proc(견적 유래), 가공비=Σ(임율/표준ST_공정)×횟수×소요량."""
    import math
    vendor = vendor.strip()
    item = item.strip()
    vcode = _VENDOR2CODE.get(vendor, "")
    ym6 = "".join(ch for ch in str(ym or "") if ch.isdigit())
    ym4 = ym6[2:6] if len(ym6) == 6 else (ym6[:4] if len(ym6) >= 4 else "")   # YYMM
    asof = (ym4 + "31") if ym4 else "991231"   # 적용월 이하 최신 판매단가
    cn = _conn(); cur = cn.cursor()
    try:
        # 1) BOM 재귀전개 (현행)
        cur.execute("""WITH tree AS (
            SELECT ITEM_CODE p, MAT_CODE c, CAST(USE_QTY AS decimal(18,6)) q, ISNULL(SAGUB_FLAG,'0') sag, ISNULL(BOM_SEQ,0) sq, 1 lvl
            FROM CS_M_ITEM_BOM WHERE ITEM_CODE=? AND FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101'
            UNION ALL
            SELECT b.ITEM_CODE, b.MAT_CODE, CAST(b.USE_QTY AS decimal(18,6)), ISNULL(b.SAGUB_FLAG,'0'), ISNULL(b.BOM_SEQ,0), t.lvl+1
            FROM tree t JOIN CS_M_ITEM_BOM b ON b.ITEM_CODE=t.c AND b.FROM_APPLY_YMD<='991231' AND b.TO_APPLY_YMD>='260101'
            WHERE t.lvl < 8)
            SELECT p,c,q,sag,sq,lvl FROM tree OPTION(MAXRECURSION 50)""", item)
        edges = {}
        for r in cur.fetchall():
            edges.setdefault(r[0], []).append({"child": str(r[1]).strip(), "q": float(r[2] or 0), "sag": str(r[3]), "sq": int(r[4] or 0)})
        for p in edges:
            edges[p].sort(key=lambda x: x["sq"])
        nodes = {item} | {e["child"] for lst in edges.values() for e in lst} | set(edges.keys())
        # 2) LG 마스터 정보
        info = {}
        nl = list(nodes)
        for i in range(0, len(nl), 900):
            chunk = nl[i:i+900]; ph = ",".join("?" * len(chunk))
            cur.execute(f"""SELECT ITEM_CODE, ISNULL(ITEM_DESC,''), ISNULL(ITEM_SPEC,''), ISNULL(METAL_GUBUN,''),
                  ISNULL(ITEM_DIAM,0), ISNULL(ITEM_THICK,0), ISNULL(ITEM_LENGTH,0)
                FROM PR_M_ITEM WHERE ITEM_CODE IN ({ph})""", *chunk)
            for r in cur.fetchall():
                info[str(r[0]).strip()] = {"nm": r[1], "spec": r[2], "metal": str(r[3]).strip(),
                    "diam": float(r[4] or 0), "thick": float(r[5] or 0), "length": float(r[6] or 0)}
        # 3) 매입가(PR_M_ITEM_COST 최신, 제이에스2228 제외, 매입TAG='1' 우선)
        pur = {}
        for i in range(0, len(nl), 900):
            chunk = [c.replace("'", "") for c in nl[i:i+900]]; inl = "','".join(chunk)
            cur.execute(f"""WITH C AS (
                  SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) ic, ITEM_COST, COST_APPLY_YMD,
                    ROW_NUMBER() OVER (PARTITION BY UPPER(LTRIM(RTRIM(ITEM_CODE)))
                      ORDER BY (CASE WHEN COST_TAG='1' THEN 0 ELSE 1 END), COST_APPLY_YMD DESC) rn
                  FROM PR_M_ITEM_COST
                  WHERE UPPER(LTRIM(RTRIM(ITEM_CODE))) IN ('{inl}')
                    AND LTRIM(RTRIM(CUST_CODE))<>'2228' AND ITEM_COST>0)
                SELECT ic, ITEM_COST FROM C WHERE rn=1""")
            for r in cur.fetchall():
                pur[str(r[0]).strip().upper()] = float(r[1] or 0)
        # 3b) 판매단가(COST_TAG='S' 내수 · 해당 협력사 · 대표우선·날짜최신).
        #     sale_asof=최신(인상후, 적용월 이하) · sale_prev=종전(인상전, 작년12월 이전=<=251130)
        sale_asof = {}; sale_prev = {}
        if vcode:
            for tgt, cut in ((sale_asof, asof), (sale_prev, "251130")):
                for i in range(0, len(nl), 900):
                    chunk = [c.replace("'", "") for c in nl[i:i+900]]; inl = "','".join(chunk)
                    cur.execute(f"""WITH S AS (
                          SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) ic, ITEM_COST,
                            ROW_NUMBER() OVER (PARTITION BY UPPER(LTRIM(RTRIM(ITEM_CODE)))
                              ORDER BY ISNULL(MAIN_FLAG,'0') DESC, COST_APPLY_YMD DESC) rn
                          FROM PR_M_ITEM_COST
                          WHERE UPPER(LTRIM(RTRIM(ITEM_CODE))) IN ('{inl}')
                            AND COST_TAG='S' AND LTRIM(RTRIM(ISNULL(CUST_CODE,'')))=?
                            AND COST_APPLY_YMD<=? AND ITEM_COST>0)
                        SELECT ic, ITEM_COST FROM S WHERE rn=1""", vcode, cut)
                    for r in cur.fetchall():
                        tgt[str(r[0]).strip().upper()] = float(r[1] or 0)
    finally:
        cn.close()
    # 4) 협력사 스펙 프리필(coop_raw_spec) + 기존 견적여부
    nx = _nx(); ncur = nx.cursor()
    coop = {}; quoted = False
    try:
        for i in range(0, len(nl), 900):
            chunk = [c.replace("'", "") for c in nl[i:i+900]]; inl = "','".join(chunk)
            ncur.execute(f"""SELECT UPPER(LTRIM(RTRIM(item_code))), diam, thick, length_mm, unit_weight, sagub_price
                FROM nx.coop_raw_spec WHERE UPPER(LTRIM(RTRIM(item_code))) IN ('{inl}')""")
            for r in ncur.fetchall():
                coop[str(r[0]).strip().upper()] = {"diam": float(r[1] or 0), "thick": float(r[2] or 0),
                    "length": float(r[3] or 0), "uw": float(r[4] or 0), "sagub": float(r[5] or 0)}
        ncur.execute("SELECT COUNT(*) FROM nx.coop_quote WHERE assy_code=?", item)
        quoted = ncur.fetchone()[0] > 0
        # 저장 부품 합계(엑셀 AQ) — bottom-up 합산 표시용
        partmap = {}; part_sum = 0.0; sale_stored = 0.0; mat_stored = 0.0; grade_q = "일반CU"; sagub_q = 0.0; cur_incost = None; prev_incost = None
        quote_rows = []   # 원본 행(중복 포함) — 다회사용 부품 정확 합산용(sum-all)
        weld_quote = {}   # 견적 용접봉 재료비 {code: mat}. 현 BOM(우리기준) 무시, 견적기준 사용
        try:
            ncur.execute("SELECT UPPER(LTRIM(RTRIM(part_code))), part_total, mat_cost, proc_cost, ISNULL(ptype,'') FROM nx.coop_quote_part WHERE assy_code=? ORDER BY seq", item)
            for r in ncur.fetchall():
                pt = float(r[1] or 0); part_sum += pt
                code_u = str(r[0]).strip().upper()
                ptype_q = str(r[4] or "").strip()
                partmap[code_u] = {"total": pt, "mat": float(r[2] or 0), "proc": float(r[3] or 0), "ptype": ptype_q}
                quote_rows.append((code_u, ptype_q, float(r[2] or 0)))
                if "용접" in ptype_q:
                    weld_quote[code_u] = float(r[2] or 0)
            ncur.execute("SELECT ISNULL(sale_price,0), ISNULL(mat_cost,0), ISNULL(grade,N'일반CU'), ISNULL(sagub_price,0) FROM nx.coop_quote WHERE assy_code=?", item)
            rr = ncur.fetchone()
            if rr:
                sale_stored = float(rr[0] or 0); mat_stored = float(rr[1] or 0); grade_q = str(rr[2] or "일반CU").strip(); sagub_q = float(rr[3] or 0)
            ncur.execute("SELECT cur_cost, prev_cost FROM nx.coop_incost WHERE UPPER(LTRIM(RTRIM(code)))=?", item.upper())
            _ic = ncur.fetchone()
            if _ic:
                if _ic[0] is not None:
                    cur_incost = float(_ic[0])
                if _ic[1] is not None:
                    prev_incost = float(_ic[1])
        except Exception:
            partmap = {}
        # ★인상후(최신) 원소재 사급가(등급별·적용월 기준): 종전 견적사급가(예 7575) 대신 현재 사급가(20000/22000) 표시·계산
        cur_sagub_val = 22000.0 if grade_q == "고강도CU" else 20000.0
        try:
            if ym4:
                ym6f = ("20" + ym4) if len(ym4) == 4 else ym4
                ncur.execute("SELECT TOP 1 sagub_price FROM nx.mat_price_month WHERE category=N'원소재' AND sagub_price>0 AND apply_ym<=? ORDER BY apply_ym DESC", ym6f)
            else:
                ncur.execute("SELECT TOP 1 sagub_price FROM nx.mat_price_month WHERE category=N'원소재' AND sagub_price>0 ORDER BY apply_ym DESC")
            mpr = ncur.fetchone()
            if mpr and mpr[0]:
                base = float(mpr[0]); cur_sagub_val = round(base * 1.1, 0) if grade_q == "고강도CU" else base
        except Exception:
            pass
        # 서브 조립 공정비 = 판가 − Σ하위부품합계 (견적서엔 용접봉줄에 넣었던 실제 조립작업 공정)
        assembly_proc = round(sale_stored - part_sum) if (sale_stored and part_sum) else 0
        # 서브조립 상세(공정ST·가공비·관리/운반/이윤) from coop_assembly
        assembly = None
        try:
            import json as _json
            ncur.execute("SELECT procs, gagong, mgmt, transport, profit, total FROM nx.coop_assembly WHERE assy_code=?", item)
            ar = ncur.fetchone()
            if ar:
                assembly = {"procs": _json.loads(ar[0] or '{}'), "gagong": int(ar[1] or 0), "mgmt": int(ar[2] or 0),
                            "transport": int(ar[3] or 0), "profit": int(ar[4] or 0), "total": int(ar[5] or 0)}
        except Exception:
            assembly = None
        # 공정(부품별 op:cnt) from coop_part_proc — (Assy,부품)별 정확값
        procmap = {}
        try:
            ncur.execute("SELECT UPPER(LTRIM(RTRIM(part_code))), op, cnt FROM nx.coop_part_proc WHERE assy_code=?", item)
            for r in ncur.fetchall():
                procmap.setdefault(str(r[0]).strip().upper(), {})[str(r[1]).strip()] = int(r[2] or 0)
        except Exception:
            procmap = {}
        # 표준ST(공정 divisor): 해당 벤더 우선, 없으면 전체 평균
        rate = {}
        try:
            if vendor:
                ncur.execute("SELECT op, divisor FROM nx.coop_gagong_rate WHERE vendor=?", vendor)
                for r in ncur.fetchall(): rate[str(r[0]).strip()] = float(r[1] or 0)
            ncur.execute("SELECT op, AVG(divisor) FROM nx.coop_gagong_rate GROUP BY op")
            for r in ncur.fetchall(): rate.setdefault(str(r[0]).strip(), float(r[1] or 0))
        except Exception:
            rate = {}
        # 임율
        labor = 6300.0
        try:
            ncur.execute("SELECT TOP 1 CAST(val AS float) FROM nx.coop_config WHERE k IN ('임율','labor_rate','rate')")
            rr = ncur.fetchone()
            if rr and rr[0]: labor = float(rr[0])
        except Exception:
            pass
    finally:
        nx.close()

    def gagong_piece(code):
        """부품 1개당 가공비 = Σ(임율/표준ST_공정)×횟수. 세척 등 제수없는 공정 제외."""
        ops = procmap.get(code.upper()) or {}
        tot = 0.0
        for op, cnt in ops.items():
            div = rate.get(op, 0)
            if div and div > 0: tot += (labor / div) * cnt
        return tot

    def role_of(code, sag, metal, haskids):
        u = code.upper()
        if haskids: return "반제품"
        if u.startswith("RAC") or u.startswith("BCUP"): return "용접봉"
        if sag == "1": return "사급"
        if metal in ("CU", "고강도"): return "제작동관"
        return "매입부품"

    rows = []; need = 0
    seen = set()
    def geom(d, t, L): return round(math.pi*(d-t)*t*L*8.94/1e6, 5) if (d and t and L) else 0.0
    def walk(code, lvl, cumq):
        if code in seen: return
        seen.add(code)
        for e in edges.get(code, []):
            ch = e["child"]; ci = info.get(ch, {}); haskids = ch in edges
            role = role_of(ch, e["sag"], ci.get("metal", ""), haskids)
            cq = cumq * e["q"]
            cs = coop.get(ch.upper()); uw = 0.0; src = ""
            if cs and (cs["uw"] > 0 or (cs["diam"] and cs["thick"] and cs["length"])):
                uw = cs["uw"] if cs["uw"] > 0 else geom(cs["diam"], cs["thick"], cs["length"]); src = "협력사"
            elif role == "제작동관" and ci.get("diam") and ci.get("thick") and ci.get("length"):
                uw = geom(ci["diam"], ci["thick"], ci["length"]); src = "LG참고"
            need_input = (role == "제작동관" and not (cs and (cs["uw"] > 0 or (cs["diam"] and cs["thick"]))))
            pp = pur.get(ch.upper(), None)
            # 용접봉 재료비 = ★견적 기준(현 BOM 소요×단가 무시=우리기준). 코드매치분만; 미매치는 walk후 견적잔여 배분
            weld_cost = round(weld_quote[ch.upper()]) if (role == "용접봉" and ch.upper() in weld_quote) else 0
            procs = procmap.get(ch.upper()) if role == "제작동관" else None
            gp_piece = gagong_piece(ch) if role == "제작동관" else 0
            proc_cost = round(gp_piece * cq) if role == "제작동관" else 0
            pt = partmap.get(ch.upper())   # 저장 합계(엑셀 AQ)
            # ★재료비(현재/적용월): 사급=판매단가(사급가)×소요 · 매입부품=매입가×소요 · 제작동관=소요중량×사급가 · 용접봉=소요×단가
            sp_sale = sale_asof.get(ch.upper())
            eff_sagub = (cs.get("sagub", 0) if cs else 0)   # 표시용 사급가(제작동관은 현재 사급가로 대체)
            if role == "용접봉":
                mat_now = weld_cost
            elif role == "사급":
                mat_now = round(sp_sale * cq) if sp_sale else (round(pt["mat"]) if pt else (round(pp * cq) if pp else 0))
            elif role == "매입부품":
                mat_now = round(pp * cq) if pp else (round(pt["mat"]) if pt else 0)
            elif role == "제작동관":
                # ★인상후: 종전 견적사급가 대신 현재 원소재 사급가(20000/22000). 협력사 스펙에 사급가 있으면 그걸 우선
                sgr = (cs.get("sagub", 0) if cs else 0) or cur_sagub_val
                eff_sagub = sgr
                mat_now = round(uw * cq * sgr) if uw else (round(pt["mat"]) if pt else 0)
            else:
                mat_now = (round(pt["mat"]) if pt else 0)
            # ★인상전(종전·BOM소요 정본): 사급=종전판매단가×소요 · 동관=소요중량×종전사급가(견적) · 용접봉/매입=인상후와 동일
            sp_prev = sale_prev.get(ch.upper())
            if role == "용접봉":
                mat_before = weld_cost
            elif role == "사급":
                mat_before = round(sp_prev * cq) if sp_prev else (round(pt["mat"]) if pt else (round(pp * cq) if pp else 0))
            elif role == "매입부품":
                mat_before = round(pp * cq) if pp else (round(pt["mat"]) if pt else 0)
            elif role == "제작동관":
                # 종전 동관재료 = 견적값(소요중량×종전동사급가). coop_quote.sagub_price는 일부 오염(621 등)이라 안씀.
                mat_before = round(pt["mat"]) if (pt and pt.get("mat")) else (round(uw * cq * sagub_q) if (uw and sagub_q > 0) else 0)
            else:
                mat_before = (round(pt["mat"]) if pt else 0)
            rows.append({
                "mat_now": mat_now, "mat_before": mat_before, "sale_price": (round(sp_sale) if sp_sale else None),
                "part_total": (round(pt["total"]) if pt else None),
                "part_mat": (round(pt["mat"]) if pt else None),
                "level": lvl, "code": ch, "name": ci.get("nm", ""), "role": role,
                "use_qty": e["q"], "cum_qty": round(cq, 5), "sagub": e["sag"] == "1",
                "lg_diam": ci.get("diam", 0), "lg_thick": ci.get("thick", 0), "lg_length": ci.get("length", 0),
                "coop_diam": (cs["diam"] if cs else 0), "coop_thick": (cs["thick"] if cs else 0),
                "coop_length": (cs["length"] if cs else 0), "coop_sagub": eff_sagub,
                "unit_weight": uw, "weight_src": src, "soyo_weight": round(uw*cq, 5),
                "pur_price": pp, "weld_cost": weld_cost, "is_proc": role == "용접봉",
                "procs": procs, "proc_cost": proc_cost,
                "need_input": need_input, "haskids": haskids})
            walk(ch, lvl+1, cq)
        seen.discard(code)
    walk(item, 1, 1.0)
    # 용접봉 견적기준: BOM 용접봉코드가 견적과 달라 미매치인 행에 견적 용접봉 잔여액 균등배분(현BOM 소요 무시)
    wr = [r for r in rows if r["role"] == "용접봉"]
    if wr and weld_quote:
        matched = {c for c in weld_quote if any(r["code"].upper() == c for r in wr)}
        leftover = sum(m for c, m in weld_quote.items() if c not in matched)
        un = [r for r in wr if r["code"].upper() not in weld_quote]
        if un and leftover:
            share = round(leftover / len(un))
            for r in un:
                r["weld_cost"] = share; r["mat_now"] = share; r["mat_before"] = share   # 용접봉 인상전=인상후(단가 동일)
    need = sum(1 for r in rows if r["need_input"])
    total_soyo = round(sum(r["soyo_weight"] for r in rows if r["role"] == "제작동관"), 4)
    total_weld = round(sum(r["weld_cost"] for r in rows if r["role"] == "용접봉"))
    total_proc = round(sum(r["proc_cost"] for r in rows if r["role"] == "제작동관"))
    # ★★ v3 재료비/분류 오버라이드 (coop_quote_part = 리스트·손익엔진과 동일). 있으면 우선.
    #   프론트가 role별로 재료비를 재계산하므로 role도 v3로 교체(동관 오분류 → 사급부품 등).
    _v3 = {}
    try:
        _nxc = _nx(); _nc = _nxc.cursor()
        _nc.execute("SELECT UPPER(LTRIM(RTRIM(part_code))), mat_before, mat_after, ptype_v2 FROM nx.coop_quote_part WHERE assy_code=?", item)
        _v3 = {str(x[0]).strip(): ((float(x[1]) if x[1] is not None else None), (float(x[2]) if x[2] is not None else None), str(x[3] or '')) for x in _nc.fetchall()}
        _nxc.close()
    except Exception:
        _v3 = {}
    _ROLE = {'사급부품': '사급', '자작': '사급', '무상': '사급', '기존가': '사급', '매입부품': '매입부품',
             '동관': '제작동관', '동관고강도': '제작동관', '용접봉': '용접봉'}
    for r in rows:
        _k = str(r["code"]).strip().upper()
        if _k in _v3:
            _mb, _ma, _pt = _v3[_k]
            if _ma is not None:
                r["mat_now"] = round(_ma)
            if _mb is not None:
                r["mat_before"] = round(_mb)
            r["role_v3"] = _pt
            _nr = _ROLE.get(_pt)
            if _nr and _nr != r["role"]:
                r["role"] = _nr   # v3 재분류 반영 → 프론트가 사급 경로로 mat_now 직접 사용
    # ★재료비 = Σ in_quote 행. v3 있으면 v3 부품집합 기준.
    _pmset = set(partmap.keys())
    for r in rows:
        if _v3:
            r["in_quote"] = (str(r["code"]).strip().upper() in _v3)
        else:
            r["in_quote"] = (str(r["code"]).strip().upper() in _pmset) or (r["role"] == "용접봉" and (r.get("weld_cost") or 0) > 0)
    if _v3:
        total_mat = round(sum(ma for (mb, ma, pt) in _v3.values() if ma is not None))
        total_mat_before = round(sum(mb for (mb, ma, pt) in _v3.values() if mb is not None))
    elif partmap:
        total_mat = round(sum((r["mat_now"] or 0) for r in rows if r["in_quote"]))
        total_mat_before = round(sum((r["mat_before"] or 0) for r in rows if r["in_quote"]))
    elif mat_stored > 0:
        # 견적 헤더는 있으나 per-part 분해 없음 → 견적 재료비(헤더)
        total_mat = round(mat_stored); total_mat_before = round(mat_stored)
        for r in rows:
            r["in_quote"] = False
    else:
        # 신규견적(견적 없음) → BOM 리프행 합(반제품 제외, 이중계상 방지)
        total_mat = round(sum((r["mat_now"] or 0) for r in rows if not r["haskids"]))
        total_mat_before = round(sum((r["mat_before"] or 0) for r in rows if not r["haskids"]))
        for r in rows:
            r["in_quote"] = (not r["haskids"])
    # 공정 컬럼 고정(엑셀 전체 공정 순서) — 품번마다 변동하지 않음
    proc_ops = ['컷팅','면취','벤딩','CNC','딤플','벌징','원교정','피어싱','압착','T뽑기','후레아','축확관','실링','망삽입','막음','코킹','세척','용접','부삽입','교/체','수몰검사','포장']
    root = info.get(item, {})
    return {"item": item, "name": root.get("nm", ""), "already_quoted": quoted, "labor_rate": labor,
            "rows": rows, "count": len(rows), "need_input": need, "proc_ops": proc_ops, "rate": rate,
            "total_soyo_weight": total_soyo, "total_weld_cost": total_weld, "total_proc_cost": total_proc,
            "total_mat": total_mat, "total_mat_before": total_mat_before, "ym": ym4, "asof": asof, "vendor_code": vcode,
            "cur_sagub": cur_sagub_val, "grade": grade_q, "cur_incost": cur_incost, "prev_incost": prev_incost,
            "part_sum": round(part_sum), "assembly_proc": assembly_proc, "sale_stored": round(sale_stored),
            "assembly": assembly}


def _coop_soyo(item):
    """현 BOM 재귀전개 × coop_raw_spec(협력사 개당중량) → 제작동관 소요중량 합.
       returns (total_soyo_weight, leaf_rows[{code,cum_qty,unit_weight,role}])."""
    import math
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""WITH tree AS (
            SELECT ITEM_CODE p, MAT_CODE c, CAST(USE_QTY AS decimal(18,6)) q, ISNULL(SAGUB_FLAG,'0') sag, 1 lvl
            FROM CS_M_ITEM_BOM WHERE ITEM_CODE=? AND FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101'
            UNION ALL
            SELECT b.ITEM_CODE, b.MAT_CODE, CAST(b.USE_QTY AS decimal(18,6)), ISNULL(b.SAGUB_FLAG,'0'), t.lvl+1
            FROM tree t JOIN CS_M_ITEM_BOM b ON b.ITEM_CODE=t.c AND b.FROM_APPLY_YMD<='991231' AND b.TO_APPLY_YMD>='260101'
            WHERE t.lvl<8)
            SELECT p,c,q,sag FROM tree OPTION(MAXRECURSION 50)""", item)
        edges = {}
        for r in cur.fetchall():
            edges.setdefault(str(r[0]).strip(), []).append((str(r[1]).strip(), float(r[2] or 0), str(r[3])))
        nodes = {item} | {c for lst in edges.values() for (c, q, s) in lst}
        metal = {}
        nl = list(nodes)
        for i in range(0, len(nl), 900):
            ch = nl[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(METAL_GUBUN,'') FROM PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for r in cur.fetchall(): metal[str(r[0]).strip()] = str(r[1]).strip()
    finally:
        cn.close()
    nx = _nx(); ncur = nx.cursor(); coop = {}
    try:
        for i in range(0, len(nl), 900):
            ch = [c.replace("'", "") for c in nl[i:i+900]]; inl = "','".join(ch)
            ncur.execute(f"""SELECT UPPER(LTRIM(RTRIM(item_code))), diam, thick, length_mm, unit_weight, sagub_price
                FROM nx.coop_raw_spec WHERE UPPER(LTRIM(RTRIM(item_code))) IN ('{inl}')""")
            for r in ncur.fetchall():
                coop[str(r[0]).strip().upper()] = (float(r[1] or 0), float(r[2] or 0), float(r[3] or 0), float(r[4] or 0), float(r[5] or 0))
    finally:
        nx.close()
    def geom(d, t, L): return round(math.pi*(d-t)*t*L*8.94/1e6, 5) if (d and t and L) else 0.0
    leaves = []; seen = set()
    def walk(code, cq):
        if code in seen: return
        seen.add(code)
        for (ch, q, sag) in edges.get(code, []):
            haskids = ch in edges
            role = ("반제품" if haskids else ("용접봉" if ch.upper().startswith("RAC") or ch.upper().startswith("BCUP")
                    else ("사급" if sag == "1" else ("제작동관" if metal.get(ch, "") in ("CU", "고강도") else "매입부품"))))
            cc = cq * q
            if role == "제작동관":
                cs = coop.get(ch.upper()); uw = 0.0; psag = 0.0
                if cs: uw = cs[3] if cs[3] > 0 else geom(cs[0], cs[1], cs[2]); psag = cs[4] if len(cs) > 4 else 0.0
                leaves.append({"code": ch, "cum_qty": round(cc, 5), "unit_weight": uw, "role": role, "sagub": psag})
            walk(ch, cc)
        seen.discard(code)
    walk(item, 1.0)
    total = round(sum(l["unit_weight"] * l["cum_qty"] for l in leaves), 5)
    return total, leaves


@router.post("/api/coopquote/bom-save")
def coopquote_bom_save(payload: dict = Body(...)):
    """견적 입력폼 저장: 제작동관 협력사스펙 upsert(coop_raw_spec) → 소요중량 재계산 → 견적 생성/수정.
       payload: item, vendor, grade, sagub_price, proc_cost, specs:[{code,diam,thick,length}]."""
    import math
    item = str(payload.get("item") or "").strip()
    vendor = str(payload.get("vendor") or "").strip()
    if not item or not vendor:
        return {"ok": False, "error": "품번·협력사 필수"}
    grade = str(payload.get("grade") or "일반CU").strip()
    if grade not in ("일반CU", "고강도CU"): grade = "일반CU"
    def fnum(v, d=0.0):
        try: return float(v) if v not in (None, "") else d
        except: return d
    sagub = fnum(payload.get("sagub_price"))
    proc = round(fnum(payload.get("proc_cost")))
    base_mat = round(fnum(payload.get("base_mat")))   # 부속품+용접봉(held) 재료비
    specs = payload.get("specs") or []
    nx = _nx(); cur = nx.cursor()
    try:
        # 1) 협력사 스펙 upsert
        upd = 0
        for s in specs:
            code = str(s.get("code") or "").strip()
            d = fnum(s.get("diam")); t = fnum(s.get("thick")); L = fnum(s.get("length"))
            psag = fnum(s.get("sagub"))            # ★관경별 사급가(부품별). 미입력 시 헤더 기본 사급가 사용
            if psag <= 0: psag = sagub
            if not code or not (d and t and L):
                continue
            uw = round(math.pi*(d-t)*t*L*8.94/1e6, 5)
            cur.execute("SELECT 1 FROM nx.coop_raw_spec WHERE UPPER(LTRIM(RTRIM(item_code)))=?", code.upper())
            if cur.fetchone():
                cur.execute("""UPDATE nx.coop_raw_spec SET diam=?,thick=?,length_mm=?,unit_weight=?,sagub_price=?
                    WHERE UPPER(LTRIM(RTRIM(item_code)))=?""", d, t, L, uw, psag, code.upper())
            else:
                cur.execute("""INSERT INTO nx.coop_raw_spec(item_code,vendor,diam,thick,length_mm,unit_weight,sagub_price)
                    VALUES(?,?,?,?,?,?,?)""", code, vendor, d, t, L, uw, psag)
            upd += 1
        # 1b) 공정 ST upsert (제작동관, assy+part별) — 직원 편집 반영
        for pr in (payload.get("procs") or []):
            pc = str(pr.get("code") or "").strip()
            if not pc: continue
            cur.execute("DELETE FROM nx.coop_part_proc WHERE assy_code=? AND part_code=?", item, pc)
            for op, cnt in (pr.get("ops") or {}).items():
                try: c = int(cnt)
                except: c = 0
                if c > 0:
                    cur.execute("INSERT INTO nx.coop_part_proc(assy_code,part_code,op,cnt) VALUES(?,?,?,?)", item[:60], pc[:60], str(op)[:20], c)
        # 1c) 서브조립 공정/관리/운반/이윤 upsert
        asm = payload.get("assembly")
        if asm is not None:
            import json as _json
            aprocs = _json.dumps(asm.get("procs") or {}, ensure_ascii=False)
            gg = round(fnum(asm.get("gagong"))); mg = round(fnum(asm.get("mgmt"))); tr = round(fnum(asm.get("transport"))); pf = round(fnum(asm.get("profit")))
            atot = gg + mg + tr + pf
            cur.execute("SELECT 1 FROM nx.coop_assembly WHERE assy_code=?", item)
            if cur.fetchone():
                cur.execute("UPDATE nx.coop_assembly SET procs=?,gagong=?,mgmt=?,transport=?,profit=?,total=? WHERE assy_code=?", aprocs, gg, mg, tr, pf, atot, item)
            else:
                cur.execute("INSERT INTO nx.coop_assembly(assy_code,procs,gagong,mgmt,transport,profit,total) VALUES(?,?,?,?,?,?,?)", item[:60], aprocs, gg, mg, tr, pf, atot)
        nx.commit()
    finally:
        nx.close()
    # 2) 소요중량 재계산 (upsert 반영 후). 재료비=원소재비+부속품/용접봉(held), 판가=재료비+가공비
    #    ★원소재비 = Σ(리프 소요중량 × 해당 관경 사급가) — 관경별 사급가 반영(미저장 리프는 헤더 sagub)
    total_soyo, leaves = _coop_soyo(item)
    mat_raw = round(sum(l["unit_weight"] * l["cum_qty"] * ((l.get("sagub") or 0) or sagub) for l in leaves))
    mat = mat_raw + base_mat
    sale = mat + proc
    # 3) 견적 upsert
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT quote_id FROM nx.coop_quote WHERE assy_code=? AND vendor=?", item, vendor)
        row = cur.fetchone()
        nm = str(payload.get("item_name") or "")[:120]; spec = str(payload.get("spec") or "")[:80]
        if row:
            cur.execute("""UPDATE nx.coop_quote SET item_name=?,spec=?,total_weight=?,sagub_price=?,mat_cost=?,
                proc_cost=?,sale_price=?,mat_raw=?,grade=?,src='폼입력',upd_user='web',upd_dt=GETDATE()
                WHERE quote_id=?""", nm, spec, total_soyo, sagub, mat, proc, sale, mat_raw, grade, row[0])
            qid = row[0]
        else:
            cur.execute("""INSERT INTO nx.coop_quote(vendor,assy_code,item_name,spec,total_weight,sagub_price,
                mat_cost,proc_cost,sale_price,mat_raw,status,grade,src,reg_user)
                OUTPUT INSERTED.quote_id VALUES(?,?,?,?,?,?,?,?,?,?,'견적',?,'폼입력','web')""",
                vendor, item, nm, spec, total_soyo, sagub, mat, proc, sale, mat_raw, grade)
            qid = cur.fetchone()[0]
        # 작업목록 완료 처리(직원 입력 검증 후 resolved)
        try:
            cur.execute("UPDATE nx.coop_worklist SET resolved=1 WHERE assy_code=?", item)
        except Exception:
            pass
        nx.commit()
        return {"ok": True, "quote_id": int(qid), "spec_updated": upd,
                "total_soyo_weight": total_soyo, "mat_cost": mat, "sale_price": sale}
    finally:
        nx.close()


@router.get("/api/coopquote/worklist")
def coopquote_worklist(wtype: str = Query("")):
    """직원 입력 작업목록: ①데이터문제(견적재료비 불일치) ②신규(견적없는 입고품). resolved=0만, 입고수량 우선."""
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["resolved=0"]; a = []
        if wtype.strip():
            w.append("wtype=?"); a.append(wtype.strip())
        cur.execute(f"""SELECT assy_code,vendor,wtype,reason,in_qty,db_mat,xl_mat
            FROM nx.coop_worklist WHERE {' AND '.join(w)} ORDER BY in_qty DESC, assy_code""", *a)
        rows = [dict(zip(["assy_code","vendor","wtype","reason","in_qty","db_mat","xl_mat"],
            [str(r[0]).strip(), str(r[1] or ""), str(r[2] or ""), str(r[3] or ""), int(r[4] or 0), int(r[5] or 0), str(r[6] or "")])) for r in cur.fetchall()]
        cur.execute("SELECT wtype, COUNT(*) FROM nx.coop_worklist WHERE resolved=0 GROUP BY wtype")
        by = {str(r[0]): int(r[1]) for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM nx.coop_worklist WHERE resolved=1")
        done = int(cur.fetchone()[0])
        return {"rows": rows, "count": len(rows), "by_type": by, "resolved": done}
    finally:
        nx.close()
