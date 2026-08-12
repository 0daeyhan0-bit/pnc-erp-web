# -*- coding: utf-8 -*-
"""dtrade 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 직거래 LME 월연동 판가 자동정본화 (w_tc_master_165/090 수작업 자동화) ============
# 산식: 판가(월)=base_item_cost + 동소요량×(LME월 − base_LME). 직거래LME만 재계산, 사급정체는 base 고정.
# 라이브 PR_M_ITEM_COST 읽기전용(대사). nx.dtrade_price(마스터)/dtrade_lme_index(월지수)/dtrade_price_ts(계산결과).
@router.get("/api/dtrade/lme")
def dtrade_lme():
    """월별 직거래 LME index(원/kg)."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT apply_ym, lme_index FROM nx.dtrade_lme_index ORDER BY apply_ym DESC")
        return {"rows": [{"apply_ym": r[0], "lme_index": float(r[1] or 0)} for r in cur.fetchall()]}
    finally:
        nx.close()

@router.get("/api/dtrade/summary")
def dtrade_summary():
    """linkage별 대상 건수(직거래LME/사급정체) + 동소요량 src·사급자재 분포."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT ISNULL(linkage,''), COUNT(*), SUM(CASE WHEN qty_src='LG392' THEN 1 ELSE 0 END),
              SUM(CASE WHEN qty_src='역산' THEN 1 ELSE 0 END), SUM(CAST(ISNULL(sagub_flag,0) AS int))
            FROM nx.dtrade_price GROUP BY linkage""")
        rows = [{"linkage": r[0], "cnt": r[1], "lg392": r[2], "inv": r[3], "sagub": r[4]} for r in cur.fetchall()]
        return {"rows": rows}
    finally:
        nx.close()

@router.post("/api/dtrade/recompute")
def dtrade_recompute(payload: dict = Body(...)):
    """월 판가 일괄 재계산(=w_tc_master_165 일괄등록 자동판). 직거래LME만: 판가=base+동소요량×(LME월−base_LME).
    사급정체는 base 고정(판가 그대로, ts에 그대로 기록). nx.dtrade_price_ts upsert."""
    ym = str(payload.get("ym", "")).strip()[:6]
    if len(ym) != 6: raise HTTPException(400, "ym(YYYYMM) 필요")
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT lme_index FROM nx.dtrade_lme_index WHERE apply_ym=?", ym)
        r = cur.fetchone()
        if not r: return {"ok": False, "errors": [f"{ym} LME index 없음 — LME인정가 탭에서 해당월 확보 필요"]}
        lme = float(r[0] or 0)
        cur.execute("DELETE FROM nx.dtrade_price_ts WHERE apply_ym=?", ym)
        # 직거래LME: 재계산
        cur.execute("""INSERT INTO nx.dtrade_price_ts(item_code,cust_code,cost_tag,apply_ym,lme_index,mat_cost_calc,item_cost,main_flag,remarks)
            SELECT item_code,cust_code,cost_tag,?, ?, ROUND(dong_qty*?,2),
                   ROUND(base_item_cost + dong_qty*(? - base_lme),2), main_flag, N'동가반영(직거래)'
            FROM nx.dtrade_price WHERE linkage=N'직거래LME'""", ym, lme, lme, lme)
        n_dir = cur.rowcount
        # 사급정체: base 고정
        cur.execute("""INSERT INTO nx.dtrade_price_ts(item_code,cust_code,cost_tag,apply_ym,lme_index,mat_cost_calc,item_cost,main_flag,remarks)
            SELECT item_code,cust_code,cost_tag,?, NULL, NULL, base_item_cost, main_flag, N'사급정체(고정)'
            FROM nx.dtrade_price WHERE linkage=N'사급정체'""", ym)
        n_st = cur.rowcount
        return {"ok": True, "ym": ym, "lme_index": lme, "직거래LME": n_dir, "사급정체": n_st}
    finally:
        nx.close()

@router.get("/api/dtrade/list")
def dtrade_list(ym: str = Query(""), linkage: str = Query(""), q: str = Query(""), limit: int = Query(300)):
    """대상 목록 + (ym 지정시)계산 판가. linkage/품번 필터."""
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if linkage.strip(): w.append("d.linkage=?"); p.append(linkage.strip())
        if q.strip(): w.append("(d.item_code LIKE ? OR d.item_desc LIKE ?)"); p += [f"%{q.strip()}%"] * 2
        cur.execute(f"""SELECT TOP {int(limit)} d.item_code,d.cust_code,d.cost_tag,d.linkage,d.dong_qty,d.qty_src,
              d.base_ym,d.base_item_cost,d.base_lme,d.main_flag,ISNULL(d.item_desc,''),d.last_ymd,d.sagub_flag,
              t.item_cost, t.mat_cost_calc, lg.price, lg.created_ymd
            FROM nx.dtrade_price d LEFT JOIN nx.dtrade_price_ts t ON t.item_code=d.item_code AND t.cust_code=d.cust_code
              AND t.cost_tag=d.cost_tag AND t.apply_ym=?
            LEFT JOIN (SELECT item_code, price, created_ymd,
                 ROW_NUMBER() OVER(PARTITION BY item_code ORDER BY created_ymd DESC) rn FROM nx.dtrade_lg_price) lg
              ON lg.item_code=d.item_code AND lg.rn=1
            WHERE {' AND '.join(w)} ORDER BY d.linkage, d.item_code""", ym.strip(), *p)
        cols = ["item_code", "cust_code", "cost_tag", "linkage", "dong_qty", "qty_src", "base_ym",
                "base_item_cost", "base_lme", "main_flag", "item_desc", "last_ymd", "sagub_flag", "calc_item_cost", "calc_mat",
                "lg_price", "lg_ymd"]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            for k in ("dong_qty", "base_item_cost", "base_lme", "calc_item_cost", "calc_mat", "lg_price"):
                r[k] = float(r[k]) if r[k] is not None else None
            r["lg_diff"] = (round(r["calc_item_cost"] - r["lg_price"], 1)
                            if (r["calc_item_cost"] is not None and r["lg_price"] is not None) else None)
        cur.execute("SELECT COUNT(*) FROM nx.dtrade_price d WHERE " + ' AND '.join(w), *p)
        return {"rows": rows, "cnt": cur.fetchone()[0], "ym": ym}
    finally:
        nx.close()

@router.get("/api/dtrade/compare")
def dtrade_compare(ym: str = Query(...), batch_ymd: str = Query(...), tol: float = Query(5.0)):
    """★라이브 대사: 우리 계산판가(ym) vs 라이브 PR_M_ITEM_COST 실판가(batch_ymd 배치) diff·일치율(±tol원).
    직거래LME 대상만. 산식 재현 검증."""
    ym = ym.strip()[:6]; batch = batch_ymd.strip()
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT t.item_code,t.cust_code,t.cost_tag,t.item_cost
            FROM nx.dtrade_price_ts t JOIN nx.dtrade_price d ON d.item_code=t.item_code AND d.cust_code=t.cust_code AND d.cost_tag=t.cost_tag
            WHERE t.apply_ym=? AND d.linkage=N'직거래LME'""", ym)
        calc = {(r[0], str(r[1]).strip(), r[2]): float(r[3] or 0) for r in cur.fetchall()}
    finally:
        nx.close()
    if not calc:
        return {"ym": ym, "batch_ymd": batch, "cnt": 0, "msg": "재계산 결과 없음 — 먼저 recompute 실행"}
    cn = _conn(); cur = cn.cursor()
    try:
        items = list({k[0] for k in calc})
        live = {}
        for i in range(0, len(items), 900):
            ch = items[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"""SELECT ITEM_CODE,ISNULL(CUST_CODE,''),COST_TAG,ITEM_COST FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_COST
                WHERE COST_APPLY_YMD=? AND COST_TAG IN('E','S') AND ITEM_CODE IN ({ph})""", batch, *ch)
            for r in cur.fetchall():
                live[(r[0].strip(), str(r[1]).strip(), r[2])] = float(r[3] or 0)
    finally:
        cn.close()
    matched = both = 0; diffs = []; samples = []
    for k, cv in calc.items():
        lv = live.get(k)
        if lv is None: continue
        both += 1; d = cv - lv; diffs.append(abs(d))
        if abs(d) <= tol: matched += 1
        elif len(samples) < 15: samples.append({"item": k[0], "cust": k[1], "tag": k[2], "calc": round(cv, 1), "live": round(lv, 1), "diff": round(d, 1)})
    import statistics as _st
    return {"ym": ym, "batch_ymd": batch, "tol": tol, "calc_cnt": len(calc), "live_matched_keys": both,
            "within_tol": matched, "match_rate": round(matched / both * 100, 1) if both else 0,
            "mean_abs_diff": round(_st.mean(diffs), 1) if diffs else 0,
            "median_abs_diff": round(_st.median(diffs), 1) if diffs else 0, "mismatch_samples": samples}


# ============ LG PO Price(판가 정본) 업로드 — 옵션A: LG 파일값=정본, LME계산=검증용 ============
@router.post("/api/dtrade/po_upload")
async def dtrade_po_upload(file: UploadFile = File(...)):
    """LG PO Price 엑셀 업로드 → nx.dtrade_lg_price(정본) upsert.
       품번=Material, 판가=Unit Price, 갱신회차=Created Date(YYMMDD), Start/End Date, MKT, 품명=Material Desc.
       (품번,MKT,Created)별 dedup(Line 1·2 동일가). 최신 Created가 정본."""
    import io as _io
    try:
        import openpyxl
    except Exception:
        raise HTTPException(500, "openpyxl 미설치(서버)")
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(_io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(400, f"엑셀 열기 실패: {str(e)[:120]}")
    ws = wb.active; itr = ws.iter_rows(values_only=True)
    try:
        hdr = next(itr)
    except StopIteration:
        raise HTTPException(400, "빈 파일")
    ix = {str(h or '').strip().lower(): i for i, h in enumerate(hdr)}
    if not all(k in ix for k in ('material', 'unit price', 'created date')):
        raise HTTPException(400, "PO Price 형식 아님 — 헤더에 Material·Unit Price·Created Date 필요")
    def gv(r, n):
        i = ix.get(n); v = r[i] if (i is not None and i < len(r)) else None
        return None if v in (None, '') else v
    def _ymd6(dt):
        if hasattr(dt, 'year'): return f"{dt.year % 100:02d}{dt.month:02d}{dt.day:02d}"
        s = ''.join(ch for ch in str(dt) if ch.isdigit())
        return s[2:8] if len(s) >= 8 else (s[-6:] if len(s) >= 6 else '')
    def _ymd8(dt):
        if hasattr(dt, 'year'): return f"{dt.year:04d}{dt.month:02d}{dt.day:02d}"
        s = ''.join(ch for ch in str(dt) if ch.isdigit())
        return s[:8] if len(s) >= 8 else ''
    seen = {}
    for r in itr:
        if not r or not any(x not in (None, '') for x in r): continue
        mat = str(gv(r, 'material') or '').strip()
        if not mat: continue
        try: price = float(gv(r, 'unit price') or 0)
        except Exception: continue
        cy = _ymd6(gv(r, 'created date'))
        if not cy or price <= 0: continue
        mkt = str(gv(r, 'mkt') or '').strip()[:4]
        sy = _ymd6(gv(r, 'start date')); ey = _ymd8(gv(r, 'end date'))
        desc = str(gv(r, 'material desc') or '')[:200]
        seen[(mat, mkt, cy)] = (price, sy, ey, desc)     # Line 1·2 동일 dedup
    wb.close()
    if not seen:
        raise HTTPException(400, "데이터 행 없음")
    fn = (file.filename or '')[:200]
    data = [(mat, mkt, cy, price, (sy or None), (ey or None), desc, fn)
            for (mat, mkt, cy), (price, sy, ey, desc) in seen.items()]
    nx = _nx_tx(); cur = nx.cursor()          # 트랜잭션 1회 커밋(멱등, 배치)
    try:
        cur.execute("""CREATE TABLE #stg(item_code varchar(30), mkt varchar(4), created_ymd char(6),
            price decimal(18,4), start_ymd char(6), end_ymd char(8), item_desc nvarchar(200), src_file nvarchar(200))""")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #stg VALUES(?,?,?,?,?,?,?,?)", data)
        cur.execute("""MERGE nx.dtrade_lg_price AS t USING #stg AS s
              ON t.item_code=s.item_code AND t.mkt=s.mkt AND t.created_ymd=s.created_ymd
              WHEN MATCHED THEN UPDATE SET price=s.price, start_ymd=s.start_ymd, end_ymd=s.end_ymd,
                   item_desc=s.item_desc, src_file=s.src_file, upload_dt=GETDATE()
              WHEN NOT MATCHED THEN INSERT(item_code,mkt,created_ymd,price,start_ymd,end_ymd,item_desc,src_file)
                VALUES(s.item_code,s.mkt,s.created_ymd,s.price,s.start_ymd,s.end_ymd,s.item_desc,s.src_file);""")
        cur.execute("SELECT COUNT(DISTINCT item_code), MAX(created_ymd) FROM nx.dtrade_lg_price")
        tot, maxc = cur.fetchone()
        nx.commit()
        return {"ok": True, "rows": len(data), "items": len({d[0] for d in data}), "file": fn,
                "total_items": tot, "latest_created": maxc}
    except Exception as e:
        try: nx.rollback()
        except Exception: pass
        raise HTTPException(500, f"업로드 저장 실패: {str(e)[:160]}")
    finally:
        nx.close()


@router.get("/api/dtrade/lg_compare")
def dtrade_lg_compare(ym: str = Query(""), tol: float = Query(5.0)):
    """계산판가(ym) vs LG확정판가(최신 회차) 일치율 — 옵션A 검증 요약."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT t.item_cost, lg.price
            FROM nx.dtrade_price_ts t
            JOIN nx.dtrade_price d ON d.item_code=t.item_code AND d.cust_code=t.cust_code AND d.cost_tag=t.cost_tag
            JOIN (SELECT item_code, price, ROW_NUMBER() OVER(PARTITION BY item_code ORDER BY created_ymd DESC) rn
                  FROM nx.dtrade_lg_price) lg ON lg.item_code=t.item_code AND lg.rn=1
            WHERE t.apply_ym=? AND d.linkage=N'직거래LME'""", ym.strip()[:6])
        both = matched = 0; diffs = []
        for calc, lg in cur.fetchall():
            if calc is None or lg is None: continue
            both += 1; dd = abs(float(calc) - float(lg)); diffs.append(dd)
            if dd <= tol: matched += 1
        import statistics as _st
        return {"ym": ym, "compared": both, "within_tol": matched,
                "match_rate": round(matched / both * 100, 1) if both else 0,
                "mean_abs_diff": round(_st.mean(diffs), 1) if diffs else 0,
                "over1pct": sum(1 for d in diffs if d > 0)}
    finally:
        nx.close()
