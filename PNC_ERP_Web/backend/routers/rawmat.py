# -*- coding: utf-8 -*-
"""rawmat 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 원소재 마스터 + 5가격 통합 뷰 (nx.raw_material ↔ price_metal/price_item/lg_lme_costtable) ============
_MATCODE = {"구리": "CU", "고강도관": "고강도", "알루미늄": "AL", "STS": "STS"}
# LG LME 인정가 = lg_lme_costtable 재료비(재질 대표구분). CU←L/W·고강도←고강도관. (구 price_lme_lg 빈테이블 통합제거)
_LG_GUBUN = {"CU": "L/W", "고강도": "고강도관"}
@router.get("/api/rawmat/list")
def rawmat_list(q: str = Query(""), material: str = Query("")):
    """원소재 마스터(외경×두께×재질×조질) + 5가격: 시세·파트너(사급)·매입·매출·LG인증. 규격/재질/품번 조인."""
    nx = _nx(); cur = nx.cursor()
    try:
        # 원소재 마스터
        w = ["1=1"]; p = []
        if material.strip(): w.append("material=?"); p.append(material.strip())
        if q.strip(): w.append("(CAST(outer_diam AS varchar)+'x'+CAST(thickness AS varchar) LIKE ? OR part_no LIKE ? OR src_codes LIKE ?)"); p += [f"%{q.strip()}%"] * 3
        cur.execute(f"""SELECT raw_id, material, outer_diam, thickness, temper, part_no, unit, std_length,
              y2026_kg, src_codes, vendors FROM nx.raw_material WHERE {' AND '.join(w)}
              ORDER BY material, outer_diam, thickness""", *p)
        rms = cur.fetchall()
        # price_metal 규격별 최신 시세/파트너
        cur.execute("""SELECT metal_gubun, diam, thick, std_price, partner_price FROM nx.price_metal pm
              WHERE apply_ym = (SELECT MAX(apply_ym) FROM nx.price_metal x WHERE x.metal_gubun=pm.metal_gubun AND x.diam=pm.diam AND x.thick=pm.thick)""")
        pmet = {}
        for r in cur.fetchall():
            pmet[(str(r[0]).strip(), float(r[1]) if r[1] is not None else None, float(r[2]) if r[2] is not None else None)] = (r[3], r[4])
        # LG 인증가 = lg_lme_costtable 재료비(최신월, 재질 대표구분 L/W·고강도관) — 단일정본, 매월 자동반영
        cur.execute("""SELECT gubun, MAX(jaeryo) FROM nx.lg_lme_costtable
              WHERE apply_ym=(SELECT MAX(apply_ym) FROM nx.lg_lme_costtable) AND gubun IN ('L/W','고강도관') GROUP BY gubun""")
        _g2m = {"L/W": "CU", "고강도관": "고강도"}
        plme = {_g2m[str(r[0]).strip()]: r[1] for r in cur.fetchall() if str(r[0]).strip() in _g2m}
        # 품번별 최신 매입/사급/매출 (price_item)
        cur.execute("""SELECT item_code, price_type, price FROM nx.price_item pi
              WHERE apply_ymd=(SELECT MAX(apply_ymd) FROM nx.price_item x WHERE x.item_code=pi.item_code AND x.price_type=pi.price_type)""")
        pit = {}
        for r in cur.fetchall():
            pit.setdefault(str(r[0]).strip(), {})[str(r[1]).strip()] = r[2]
        rows = []
        for r in rms:
            mat = str(r[1] or "").strip(); od = float(r[2]) if r[2] is not None else None; th = float(r[3]) if r[3] is not None else None
            sise, partner = pmet.get((_MATCODE.get(mat, mat), od, th), (None, None))
            # 매입/사급/매출 = 원천품번들 중 대표(최대) 값
            codes = [c.strip() for c in str(r[9] or "").split(",") if c.strip()]
            buy = sale = sagub = None
            for c in codes:
                d = pit.get(c, {})
                for k, dst in (("매입", "buy"), ("TAGS", "sagub"), ("TAGE", "sale")):
                    v = d.get(k)
                    if v and float(v) > 0:
                        if dst == "buy": buy = max(buy or 0, float(v))
                        elif dst == "sagub": sagub = max(sagub or 0, float(v))
                        else: sale = max(sale or 0, float(v))
            rows.append({
                "raw_id": r[0], "material": mat, "outer_diam": od, "thickness": th,
                "temper": r[4] or "", "part_no": r[5] or "", "unit": r[6] or "KG", "std_length": r[7],
                "y2026_kg": float(r[8]) if r[8] is not None else 0, "codes_cnt": len(codes), "vendors": r[10] or "",
                "price_sise": float(sise) if sise is not None else None,     # 직거래 시세
                "price_partner": float(partner) if partner is not None else None,  # 파트너(사급)가
                "price_buy": buy, "price_sale": sale, "price_sagub_item": sagub,
                "price_lg_recog": float(plme[_MATCODE.get(mat, mat)]) if _MATCODE.get(mat, mat) in plme else None})
        return {"rows": rows, "cnt": len(rows),
                "materials": [{"code": m, "nm": m} for m in ["구리", "고강도관", "알루미늄", "STS"]]}
    finally:
        nx.close()


@router.get("/api/rawmat/prices")
def rawmat_prices(raw_id: int = Query(...)):
    """선택 원소재의 월별 단가 시계열: LG인증가(lg_lme_costtable 재료비)·LG사급가(rawmat_lg_sagub, 입력값 미입력=0)·현물가/협력사사급가(price_metal). 최신월 상단."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT material, outer_diam, thickness, temper, part_no FROM nx.raw_material WHERE raw_id=?", raw_id)
        r = cur.fetchone()
        if not r:
            return {"raw_id": raw_id, "material": "", "spec": "", "rows": []}
        mat = str(r[0] or "").strip(); od = r[1]; th = r[2]
        mg = _MATCODE.get(mat, mat)
        series = {}
        cur.execute("SELECT apply_ym, std_price, partner_price FROM nx.price_metal WHERE metal_gubun=? AND diam=? AND thick=?", mg, od, th)
        for ym, sp, pp in cur.fetchall():
            d = series.setdefault(str(ym).strip(), {})
            d["sise"] = float(sp) if sp is not None else None
            d["partner"] = float(pp) if pp is not None else None
        _lgg = _LG_GUBUN.get(mg)
        if _lgg:
            cur.execute("SELECT apply_ym, MAX(jaeryo) FROM nx.lg_lme_costtable WHERE gubun=? GROUP BY apply_ym", _lgg)
            for ym, v in cur.fetchall():
                series.setdefault(str(ym).strip(), {})["lg_recog"] = float(v) if v is not None else None
        cur.execute("SELECT apply_ym, price FROM nx.rawmat_lg_sagub WHERE raw_id=?", raw_id)
        for ym, v in cur.fetchall():
            series.setdefault(str(ym).strip(), {})["lg_sagub"] = float(v) if v is not None else 0
        rows = []
        for ym in sorted(series.keys(), reverse=True):
            d = series[ym]
            rows.append({"ym": ym, "lg_recog": d.get("lg_recog"), "lg_sagub": d.get("lg_sagub", 0),
                         "sise": d.get("sise"), "partner": d.get("partner")})
        spec = f"⌀{od}×{th}" + (f" {r[3]}" if r[3] else "")
        return {"raw_id": raw_id, "material": mat, "spec": spec, "part_no": r[4] or "", "rows": rows}
    finally:
        nx.close()


@router.post("/api/rawmat/lg_sagub/save")
def rawmat_lg_sagub_save(payload: dict = Body(...)):
    """원소재별 월별 LG사급가 저장(upsert). rows=[{ym,price}]. 미입력월은 0."""
    raw_id = int(payload.get("raw_id") or 0)
    rows = payload.get("rows", []) or []
    if not raw_id:
        return {"ok": False, "error": "raw_id 필요"}
    nx = _nx(); cur = nx.cursor()
    try:
        n = 0
        for r in rows:
            ym = "".join(ch for ch in str(r.get("ym", "")) if ch.isdigit())[:6]
            if len(ym) != 6:
                continue
            price = float(r.get("price") or 0)
            cur.execute("""MERGE nx.rawmat_lg_sagub AS t USING (SELECT ? raw_id, ? apply_ym) s
                ON t.raw_id=s.raw_id AND t.apply_ym=s.apply_ym
                WHEN MATCHED THEN UPDATE SET price=?, upd_user='web', upd_dt=GETDATE()
                WHEN NOT MATCHED THEN INSERT(raw_id,apply_ym,price,upd_user,upd_dt) VALUES(?,?,?,'web',GETDATE());""",
                raw_id, ym, price, raw_id, ym, price)
            n += 1
        return {"ok": True, "count": n}
    finally:
        nx.close()
