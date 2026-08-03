# -*- coding: utf-8 -*-
"""lglme 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ LG전자 LME인정가 (Cost Table 직거래) — 재료비=f(LME,환율)·가공비=국가믹스 · nx.lg_lme_* ============
def _ensure_lglme_tbl(cur):
    cur.execute("""IF OBJECT_ID('nx.lg_lme_header','U') IS NULL CREATE TABLE nx.lg_lme_header(
        apply_ym CHAR(6) PRIMARY KEY, cu_lme FLOAT, brass_lme FLOAT, cable_lme FLOAT,
        fx_now FLOAT, fx_prev FLOAT, premium FLOAT DEFAULT 152, surcharge FLOAT DEFAULT 1.05,
        upd_user NVARCHAR(30), upd_dt datetime DEFAULT getdate())""")
    cur.execute("""IF OBJECT_ID('nx.lg_lme_gagong','U') IS NULL CREATE TABLE nx.lg_lme_gagong(
        apply_ym CHAR(6), gubun NVARCHAR(20), diam FLOAT, thick FLOAT,
        vn_gagong FLOAT, vn_prem FLOAT, vn_mul FLOAT, vn_naeryuk FLOAT,
        cn_gagong FLOAT, cn_prem FLOAT, cn_mul FLOAT, cn_naeryuk FLOAT,
        duty_vn FLOAT DEFAULT 0, duty_cn FLOAT DEFAULT 0.016, mix_cn FLOAT DEFAULT 0.3, mix_vn FLOAT DEFAULT 0.7,
        CONSTRAINT PK_lglme_gagong PRIMARY KEY(apply_ym,gubun,diam,thick))""")
    cur.execute("""IF OBJECT_ID('nx.lg_lme_costtable','U') IS NULL CREATE TABLE nx.lg_lme_costtable(
        id INT IDENTITY(1,1) PRIMARY KEY, apply_ym CHAR(6), gubun NVARCHAR(20), diam FLOAT, thick FLOAT,
        p_no NVARCHAR(30), jaeryo FLOAT, gagong FLOAT, wonjae FLOAT, seq INT)""")

def _lglme_metal_lme(gubun, h):
    """구분→재질 LME: 황동/Cable 키워드면 해당, 그외 Cu(선물). h=header dict."""
    g = str(gubun or "")
    if "황동" in g: return float(h.get("brass_lme") or 0)
    if "Cable" in g or "케이블" in g: return float(h.get("cable_lme") or 0)
    return float(h.get("cu_lme") or 0)

def _lglme_jaeryo(gubun, h):
    """재료비(원/kg): 직관&P/C=(LME+premium)×surcharge×fx/1000, 그외=LME×fx/1000."""
    lme = _lglme_metal_lme(gubun, h); fx = float(h.get("fx_now") or 0)
    g = str(gubun or "")
    if "직관" in g or "P/C" in g:
        return round((lme + float(h.get("premium") or 0)) * float(h.get("surcharge") or 1.0) * fx / 1000, 2)
    return round(lme * fx / 1000, 2)

def _lglme_gagong_won(gr, lme, fx):
    """가공비(원) = (중국Price×mix_cn + 베트남Price×mix_vn)×fx/1000. 국가Price=가공비+프리미엄+물류+관세+내륙(USD)."""
    vn = (gr["vn_gagong"] + gr["vn_prem"] + gr["vn_mul"]
          + (lme + gr["vn_gagong"] + gr["vn_mul"]) * gr["duty_vn"] + gr["vn_naeryuk"])
    cn = (gr["cn_gagong"] + gr["cn_prem"] + gr["cn_mul"]
          + (lme + gr["cn_gagong"] + gr["cn_mul"]) * gr["duty_cn"] + gr["cn_naeryuk"])
    return round((cn * gr["mix_cn"] + vn * gr["mix_vn"]) * fx / 1000, 2)

@router.get("/api/lglme/months")
def lglme_months():
    """LME인정가 적용월 목록(최신순) + 편집가능(header 존재) 여부."""
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_lglme_tbl(cur)
        cur.execute("""SELECT c.apply_ym, COUNT(*) nrow, MAX(CASE WHEN h.apply_ym IS NULL THEN 0 ELSE 1 END) editable
            FROM nx.lg_lme_costtable c LEFT JOIN nx.lg_lme_header h ON h.apply_ym=c.apply_ym
            GROUP BY c.apply_ym ORDER BY c.apply_ym DESC""")
        return {"rows": [{"apply_ym": r[0], "n_row": int(r[1]), "editable": bool(r[2])} for r in cur.fetchall()]}
    finally:
        nx.close()

@router.get("/api/lglme/table")
def lglme_table(ym: str = Query(...)):
    """월별 Cost Table: header(입력값) + costtable 행(구분·외경·두께·P/No·재료비·가공비·원재료가). header 없으면 과거값 읽기전용."""
    ym = ym.strip()[:6]
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_lglme_tbl(cur)
        cur.execute("""SELECT apply_ym,cu_lme,brass_lme,cable_lme,fx_now,fx_prev,premium,surcharge FROM nx.lg_lme_header WHERE apply_ym=?""", ym)
        h = cur.fetchone()
        header = None
        if h:
            header = {"apply_ym": h[0], "cu_lme": h[1], "brass_lme": h[2], "cable_lme": h[3],
                      "fx_now": h[4], "fx_prev": h[5], "premium": h[6], "surcharge": h[7]}
        cur.execute("""SELECT id,gubun,diam,thick,ISNULL(p_no,''),jaeryo,gagong,wonjae,seq
            FROM nx.lg_lme_costtable WHERE apply_ym=? ORDER BY seq,id""", ym)
        rows = [{"id": r[0], "gubun": r[1], "diam": r[2], "thick": r[3], "p_no": r[4],
                 "jaeryo": r[5], "gagong": r[6], "wonjae": r[7], "seq": r[8]} for r in cur.fetchall()]
        return {"ym": ym, "header": header, "editable": bool(header), "rows": rows}
    finally:
        nx.close()

@router.get("/api/lglme/gagong")
def lglme_gagong(ym: str = Query(...)):
    """월별 국가믹스 원천(spec별 베트남·중국 가공비/프리미엄/물류/내륙 + 관세율·믹스)."""
    ym = ym.strip()[:6]
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_lglme_tbl(cur)
        cur.execute("""SELECT gubun,diam,thick,vn_gagong,vn_prem,vn_mul,vn_naeryuk,cn_gagong,cn_prem,cn_mul,cn_naeryuk,
            duty_vn,duty_cn,mix_cn,mix_vn FROM nx.lg_lme_gagong WHERE apply_ym=? ORDER BY gubun,diam,thick""", ym)
        cols = ["gubun", "diam", "thick", "vn_gagong", "vn_prem", "vn_mul", "vn_naeryuk",
                "cn_gagong", "cn_prem", "cn_mul", "cn_naeryuk", "duty_vn", "duty_cn", "mix_cn", "mix_vn"]
        return {"ym": ym, "rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
    finally:
        nx.close()

@router.post("/api/lglme/header/save")
def lglme_header_save(payload: dict = Body(...)):
    """헤더(재질 LME·환율·premium·할증) upsert. 필수=apply_ym·cu_lme·fx_now."""
    p = payload; ym = str(p.get("apply_ym", "")).strip()[:6]
    if len(ym) != 6: raise HTTPException(400, "apply_ym(YYYYMM) 필요")
    def f(k, d=0.0):
        try: return float(p.get(k))
        except Exception: return d
    if f("cu_lme") <= 0: return {"ok": False, "errors": ["Cu 적용 LME는 필수(>0)"]}
    if f("fx_now") <= 0: return {"ok": False, "errors": ["적용환율은 필수(>0)"]}
    usr = (str(p.get("user", "")).strip() or "web")[:30]
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_lglme_tbl(cur)
        cur.execute("""MERGE nx.lg_lme_header AS t USING (SELECT ? apply_ym) s ON t.apply_ym=s.apply_ym
            WHEN MATCHED THEN UPDATE SET cu_lme=?,brass_lme=?,cable_lme=?,fx_now=?,fx_prev=?,premium=?,surcharge=?,upd_user=?,upd_dt=getdate()
            WHEN NOT MATCHED THEN INSERT(apply_ym,cu_lme,brass_lme,cable_lme,fx_now,fx_prev,premium,surcharge,upd_user)
              VALUES(?,?,?,?,?,?,?,?,?);""",
            ym, f("cu_lme"), (f("brass_lme") or f("cu_lme")), (f("cable_lme") or f("cu_lme")), f("fx_now"), f("fx_prev"),
            (f("premium") or 152.0), (f("surcharge") or 1.05), usr,
            ym, f("cu_lme"), (f("brass_lme") or f("cu_lme")), (f("cable_lme") or f("cu_lme")), f("fx_now"), f("fx_prev"),
            (f("premium") or 152.0), (f("surcharge") or 1.05), usr)
        return {"ok": True, "apply_ym": ym}
    finally:
        nx.close()

@router.post("/api/lglme/gagong/save")
def lglme_gagong_save(payload: dict = Body(...)):
    """국가믹스 원천 1행 upsert(spec별). 필수=apply_ym·gubun·diam·thick."""
    p = payload; ym = str(p.get("apply_ym", "")).strip()[:6]
    gub = str(p.get("gubun", "")).strip()[:20]
    try: diam = float(p.get("diam")); thick = float(p.get("thick"))
    except Exception: raise HTTPException(400, "diam·thick 필요")
    if len(ym) != 6 or not gub: raise HTTPException(400, "apply_ym·gubun 필요")
    def f(k, d=0.0):
        try: return float(p.get(k))
        except Exception: return d
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_lglme_tbl(cur)
        cur.execute("""MERGE nx.lg_lme_gagong AS t USING (SELECT ? a,? g,? d,? th) s
            ON t.apply_ym=s.a AND t.gubun=s.g AND t.diam=s.d AND t.thick=s.th
            WHEN MATCHED THEN UPDATE SET vn_gagong=?,vn_prem=?,vn_mul=?,vn_naeryuk=?,cn_gagong=?,cn_prem=?,cn_mul=?,cn_naeryuk=?,duty_vn=?,duty_cn=?,mix_cn=?,mix_vn=?
            WHEN NOT MATCHED THEN INSERT(apply_ym,gubun,diam,thick,vn_gagong,vn_prem,vn_mul,vn_naeryuk,cn_gagong,cn_prem,cn_mul,cn_naeryuk,duty_vn,duty_cn,mix_cn,mix_vn)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);""",
            ym, gub, diam, thick,
            f("vn_gagong"), f("vn_prem"), f("vn_mul"), f("vn_naeryuk"), f("cn_gagong"), f("cn_prem"), f("cn_mul"), f("cn_naeryuk"), f("duty_vn"), f("duty_cn", 0.016), f("mix_cn", 0.3), f("mix_vn", 0.7),
            ym, gub, diam, thick,
            f("vn_gagong"), f("vn_prem"), f("vn_mul"), f("vn_naeryuk"), f("cn_gagong"), f("cn_prem"), f("cn_mul"), f("cn_naeryuk"), f("duty_vn"), f("duty_cn", 0.016), f("mix_cn", 0.3), f("mix_vn", 0.7))
        return {"ok": True}
    finally:
        nx.close()

@router.post("/api/lglme/recompute")
def lglme_recompute(payload: dict = Body(...)):
    """월 Cost Table 재계산: 재료비(구분별 산식)+가공비(국가믹스, spec매칭)+원재료가(합) → costtable upsert. header 필수."""
    ym = str(payload.get("ym", "")).strip()[:6]
    if len(ym) != 6: raise HTTPException(400, "ym 필요")
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_lglme_tbl(cur)
        cur.execute("SELECT cu_lme,brass_lme,cable_lme,fx_now,fx_prev,premium,surcharge FROM nx.lg_lme_header WHERE apply_ym=?", ym)
        h = cur.fetchone()
        if not h: return {"ok": False, "errors": ["헤더(LME/환율)가 없습니다 — 먼저 저장하세요"]}
        H = {"cu_lme": h[0], "brass_lme": h[1], "cable_lme": h[2], "fx_now": h[3], "fx_prev": h[4], "premium": h[5], "surcharge": h[6]}
        cur.execute("""SELECT gubun,diam,thick,vn_gagong,vn_prem,vn_mul,vn_naeryuk,cn_gagong,cn_prem,cn_mul,cn_naeryuk,duty_vn,duty_cn,mix_cn,mix_vn
            FROM nx.lg_lme_gagong WHERE apply_ym=?""", ym)
        gk = ["vn_gagong", "vn_prem", "vn_mul", "vn_naeryuk", "cn_gagong", "cn_prem", "cn_mul", "cn_naeryuk", "duty_vn", "duty_cn", "mix_cn", "mix_vn"]
        gmap = {}
        for r in cur.fetchall():
            gmap[(str(r[0]).strip(), float(r[1]), float(r[2]))] = {k: float(r[3 + i] or 0) for i, k in enumerate(gk)}
        cur.execute("SELECT id,gubun,diam,thick,jaeryo,gagong FROM nx.lg_lme_costtable WHERE apply_ym=?", ym)
        recs = cur.fetchall(); n = 0
        for cid, gub, diam, thick, ojae, ogag in recs:
            jae = _lglme_jaeryo(gub, H)
            gr = gmap.get((str(gub).strip(), float(diam or 0), float(thick or 0)))
            lme = _lglme_metal_lme(gub, H)
            gag = _lglme_gagong_won(gr, lme, float(H["fx_now"] or 0)) if gr else float(ogag or 0)
            cur.execute("UPDATE nx.lg_lme_costtable SET jaeryo=?,gagong=?,wonjae=? WHERE id=?", jae, gag, round(jae + gag, 2), cid)
            n += 1
        return {"ok": True, "updated": n}
    finally:
        nx.close()

@router.post("/api/lglme/copy")
def lglme_copy(payload: dict = Body(...)):
    """전월(from_ym) → 신규월(to_ym) 복사: header+gagong+costtable 복제(to_ym 기존 근거범위 제거 후). 이후 LME/환율/국가단가 갱신·재계산."""
    fr = str(payload.get("from_ym", "")).strip()[:6]; to = str(payload.get("to_ym", "")).strip()[:6]
    usr = (str(payload.get("user", "")).strip() or "web")[:30]
    if len(fr) != 6 or len(to) != 6: raise HTTPException(400, "from_ym·to_ym(YYYYMM) 필요")
    if fr == to: raise HTTPException(400, "원본월과 신규월이 같습니다")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_lglme_tbl(cur)
        cur.execute("SELECT 1 FROM nx.lg_lme_costtable WHERE apply_ym=?", to)
        if cur.fetchone(): raise HTTPException(409, f"{to} 는 이미 존재합니다(중복 생성 방지)")
        cur.execute("""INSERT INTO nx.lg_lme_header(apply_ym,cu_lme,brass_lme,cable_lme,fx_now,fx_prev,premium,surcharge,upd_user)
            SELECT ?,cu_lme,brass_lme,cable_lme,fx_now,fx_prev,premium,surcharge,? FROM nx.lg_lme_header WHERE apply_ym=?""", to, usr, fr)
        cur.execute("""INSERT INTO nx.lg_lme_gagong(apply_ym,gubun,diam,thick,vn_gagong,vn_prem,vn_mul,vn_naeryuk,cn_gagong,cn_prem,cn_mul,cn_naeryuk,duty_vn,duty_cn,mix_cn,mix_vn)
            SELECT ?,gubun,diam,thick,vn_gagong,vn_prem,vn_mul,vn_naeryuk,cn_gagong,cn_prem,cn_mul,cn_naeryuk,duty_vn,duty_cn,mix_cn,mix_vn FROM nx.lg_lme_gagong WHERE apply_ym=?""", to, fr)
        cur.execute("""INSERT INTO nx.lg_lme_costtable(apply_ym,gubun,diam,thick,p_no,jaeryo,gagong,wonjae,seq)
            SELECT ?,gubun,diam,thick,p_no,jaeryo,gagong,wonjae,seq FROM nx.lg_lme_costtable WHERE apply_ym=?""", to, fr)
        cur.execute("SELECT COUNT(*) FROM nx.lg_lme_costtable WHERE apply_ym=?", to)
        n = cur.fetchone()[0]
        nx.commit()
        return {"ok": True, "to_ym": to, "rows": n}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()
