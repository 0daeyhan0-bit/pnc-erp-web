# -*- coding: utf-8 -*-
"""autoorder 도메인 라우터 — 자동발주(생산계획+주문 → MRP → 조달배분 → 업체별 PO).
소요원천은 재구현하지 않는다: 정본 자재소요(nx.plan_part_mat, 레거시 STEP5→6→7 100%검증)를
조달프로파일로 오버레이한 nx.plan_mat_source(품목별 순소요 + 공급방식·공급처·배분%적용 QTY)를 그대로 입력으로 사용.
발주대상 = 자체(내부제작) 제외 전 공급방식(매입/유상사급/외주가공/외주완성/미지정). 용접봉(RAC/sgroup910)은 STEP7에서 이미 제외.
단가 = 마스터 매입단가(PR_M_ITEM_COST COST_TAG='1' as-of, 읽기전용·불변). PO는 nx 전용(dev, 외부발송 아님).
중복방지 = 순소요(net) = 소요 − 확정된 자동발주(status='확정') 미취소분. 근거키 스코프(po_no/batch).
"""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes, _route01_ratio)

router = APIRouter()

# 발주대상 공급방식(자체 제외). 미지정은 발주업체 미확정으로 별도 표기하되 대상엔 포함.
_ORDER_GUBUN = ("매입", "유상사급", "외주가공", "외주완성", "미지정")
_AO_READY = False

def _ensure_ao_tbl(cur):
    """자동발주 PO 헤더/라인(nx 전용). po_no=근거키 스코프."""
    global _AO_READY
    if _AO_READY:
        return
    cur.execute("""IF OBJECT_ID('nx.auto_po','U') IS NULL CREATE TABLE nx.auto_po(
        po_no varchar(30) NOT NULL, gen_batch varchar(20), po_ymd varchar(6),
        vendor_code varchar(20), vendor_name nvarchar(120), supply_gubun varchar(20),
        status varchar(10) DEFAULT '확정', line_count int, total_qty decimal(18,3), total_amt decimal(18,2),
        filt_line varchar(20), filt_cr varchar(2), filt_gubun varchar(20), filt_vendor varchar(20), filt_item varchar(40),
        ins_user nvarchar(30), ins_dt datetime DEFAULT getdate(), upd_dt datetime,
        CONSTRAINT PK_nx_auto_po PRIMARY KEY(po_no))""")
    cur.execute("""IF OBJECT_ID('nx.auto_po_line','U') IS NULL CREATE TABLE nx.auto_po_line(
        po_no varchar(30) NOT NULL, seq int NOT NULL, item_code varchar(40), item_name nvarchar(200),
        supply_gubun varchar(20), req_qty decimal(18,3), already_qty decimal(18,3), order_qty decimal(18,3),
        unit_price decimal(18,4), currency varchar(6), amt decimal(18,2), source varchar(10),
        CONSTRAINT PK_nx_auto_po_line PRIMARY KEY(po_no, seq))""")
    _AO_READY = True


def _mat_requirement(cur, line, cr, vendor, item, gubun):
    """정본 조달소요(nx.plan_mat_source) 집계 = (자재×공급처×공급방식) 순소요 후보(발주대상만).
       라인/CR 필터는 제번(WORK_ORDER)→nx.plan_dtl 조인(EXISTS, 정확·additive). plan_mat_source는 제번×자재 단위."""
    w = ["s.SUPPLY_GUBUN<>N'자체'"]
    p = []
    if gubun.strip():
        w.append("s.SUPPLY_GUBUN=?"); p.append(gubun.strip())
    if vendor.strip():
        w.append("s.VENDOR_CODE=?"); p.append(vendor.strip())
    if item.strip():
        w.append("(s.MAT_CODE LIKE ? OR EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM i2 WHERE i2.ITEM_CODE COLLATE DATABASE_DEFAULT=s.MAT_CODE COLLATE DATABASE_DEFAULT AND i2.ITEM_DESC LIKE ?))")
        p += [f"%{item.strip()}%", f"%{item.strip()}%"]
    if line.strip():
        w.append("EXISTS(SELECT 1 FROM nx.plan_dtl d WHERE d.WORK_ORDER=s.WORK_ORDER AND d.LINE_NO=?)"); p.append(line.strip())
    if cr.strip() in ("C", "R"):
        w.append("EXISTS(SELECT 1 FROM nx.plan_dtl d WHERE d.WORK_ORDER=s.WORK_ORDER AND d.CR_FLAG=?)"); p.append(cr.strip())
    cur.execute(f"""SELECT s.MAT_CODE, LTRIM(RTRIM(ISNULL(s.VENDOR_CODE,''))) vc, s.SUPPLY_GUBUN,
          MAX(s.SOURCE) src, SUM(CAST(s.QTY AS float)) qty
        FROM nx.plan_mat_source s WHERE {' AND '.join(w)}
        GROUP BY s.MAT_CODE, LTRIM(RTRIM(ISNULL(s.VENDOR_CODE,''))), s.SUPPLY_GUBUN""", *p)
    return [{"item": str(r[0]).strip(), "vendor": str(r[1]).strip(), "gubun": r[2],
             "source": r[3], "req": float(r[4] or 0)} for r in cur.fetchall()]


def _build_preview(line, cr, vendor, item, gubun, asof):
    """미리보기/확정 공용 산출. 반환: (pos[업체별], summary). 순소요=소요−확정발주(status='확정')."""
    nx = _nx(); ncur = nx.cursor()
    try:
        _ensure_ao_tbl(ncur)
        base = _mat_requirement(ncur, line, cr, vendor, item, gubun)
        # 발주업체 배분(nx.order_vendor) — R01(현행) 근거 재사용. ★다중업체+alloc_ratio(합100%) → 비율분할.
        cur_items = sorted({b["item"] for b in base})
        alloc = {}   # item -> [(vendor, ratio|None)]
        try:
            ncur.execute("IF OBJECT_ID('nx.order_vendor','U') IS NULL SELECT 1 WHERE 1=0")
            has_ratio = (ncur.execute("SELECT COL_LENGTH('nx.order_vendor','alloc_ratio')").fetchone()[0] is not None)
            for i in range(0, len(cur_items), 900):
                ch = cur_items[i:i+900]; ph = ",".join("?" * len(ch))
                col = "alloc_ratio" if has_ratio else "NULL"
                ncur.execute(f"SELECT LTRIM(RTRIM(item_code)), ISNULL(vendor_code,''), {col} FROM nx.order_vendor WHERE item_code IN ({ph})", *ch)
                for r in ncur.fetchall():
                    v = str(r[1] or "").strip()
                    if v:
                        alloc.setdefault(str(r[0]).strip(), []).append((v, (float(r[2]) if r[2] is not None else None)))
        except Exception:
            pass
        route01 = _route01_ratio(ncur, cur_items)   # ★실발주비율 = route01%(현행 경로) × 업체비율. 현재 R01=100.
        # 이미 발주된 순소요 차감분: 확정 PO 라인 (item, vendor)별 order_qty 합
        already = {}
        ncur.execute("""SELECT l.item_code, h.vendor_code, SUM(CAST(l.order_qty AS float))
            FROM nx.auto_po_line l JOIN nx.auto_po h ON h.po_no=l.po_no
            WHERE h.status='확정' GROUP BY l.item_code, h.vendor_code""")
        for it, vc, q in ncur.fetchall():
            already[(str(it).strip(), str(vc or "").strip())] = float(q or 0)
    finally:
        nx.close()
    # 유효벤더 확정 후 (item,vendor) 병합 — ★override 배분(다중업체+alloc_ratio)이면 소요를 비율분할
    merged = {}
    for b in base:
        # ★'경로대안'(R02+) 행은 compose_mat에서 이미 경로율×경로업체 배정됨 → order_vendor 재분할 제외(이중배분 방지, 규칙 §8·§9).
        lst = alloc.get(b["item"]) if b.get("source") != "경로대안" else None
        if lst:
            rated = [(v, r) for (v, r) in lst if r is not None]
            if len(rated) == len(lst) and rated:                          # 전원 배분%: 합100 정규화 분할
                tot = sum(r for _, r in rated) or 1.0
                splits = [(v, b["req"] * (r / tot)) for (v, r) in rated]
            else:                                                          # 비율 미입력(단일 등) → 균등분할
                n = len(lst); splits = [(v, b["req"] / n) for (v, _) in lst]
            overridden = True
        else:
            splits = [(b["vendor"], b["req"])]
            overridden = False
        rf = route01.get(b["item"], 100.0) / 100.0   # ★route01 경로 계수(현재 100=무영향)
        for (eff, qty) in splits:
            k = (b["item"], eff)
            g = merged.get(k)
            if not g:
                g = {"item": b["item"], "vendor": eff, "gubun": b["gubun"], "source": b["source"], "req": 0.0,
                     "overridden": overridden}
                merged[k] = g
            g["req"] += qty * rf
            if b["gubun"] == "매입":   # 공급방식: 매입 우선 표기(혼재 시)
                g["gubun"] = "매입"
    lines = list(merged.values())
    # 단가(마스터 매입단가 as-of, 읽기전용) + 자재명 + 업체명 (라이브 PARTNER_ERP 조회만)
    codes = sorted({l["item"] for l in lines})
    vcodes = sorted({l["vendor"] for l in lines if l["vendor"]})
    price = {}; nm = {}; vmap = {}
    cn = _conn(); cur = cn.cursor()
    try:
        for i in range(0, len(codes), 900):
            ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT LTRIM(RTRIM(ITEM_CODE)), ISNULL(ITEM_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for r in cur.fetchall():
                nm[str(r[0]).strip()] = r[1]
        for i in range(0, len(codes), 900):
            ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"""SELECT ITEM_CODE, ITEM_COST, curr FROM (
                SELECT LTRIM(RTRIM(ITEM_CODE)) ITEM_CODE, ITEM_COST, ISNULL(CURRENCY,'') curr,
                  ROW_NUMBER() OVER(PARTITION BY LTRIM(RTRIM(ITEM_CODE)) ORDER BY ISNULL(MAIN_FLAG,'') DESC, COST_APPLY_YMD DESC) rn
                FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_COST WHERE COST_TAG='1' AND COST_APPLY_YMD<=? AND LTRIM(RTRIM(ITEM_CODE)) IN ({ph})) z WHERE rn=1""", asof, *ch)
            for r in cur.fetchall():
                price[str(r[0]).strip()] = {"cost": (float(r[1]) if r[1] is not None else None), "curr": r[2]}
        vmap = _custnm_map(cur, vcodes)
    finally:
        cn.close()
    # 라인 완성 + 순소요 차감
    povend = {}
    for l in lines:
        it = l["item"]; vc = l["vendor"]
        alr = already.get((it, vc), 0.0)
        net = round(l["req"] - alr, 3)
        if net <= 0:
            continue
        pp = price.get(it, {})
        unit = pp.get("cost")
        amt = round(net * unit, 2) if unit is not None else 0.0
        row = {"item_code": it, "item_name": nm.get(it, ""), "supply_gubun": l["gubun"], "source": l["source"],
               "vendor_code": vc, "vendor_name": (vmap.get(vc, vc) if vc else ""),
               "req_qty": round(l["req"], 3), "already_qty": round(alr, 3), "order_qty": net,
               "unit_price": unit, "currency": pp.get("curr", ""), "amt": amt,
               "overridden": l["overridden"], "no_vendor": (not vc), "no_price": (unit is None)}
        povend.setdefault(vc, []).append(row)
    pos = []
    for vc in sorted(povend, key=lambda v: -sum(r["amt"] for r in povend[v])):
        rows = sorted(povend[vc], key=lambda r: -r["amt"])
        pos.append({"vendor_code": vc, "vendor_name": (vmap.get(vc, vc) if vc else "(발주업체 미지정)"),
                    "no_vendor": (not vc), "line_count": len(rows),
                    "total_qty": round(sum(r["order_qty"] for r in rows), 3),
                    "total_amt": round(sum(r["amt"] for r in rows), 2), "lines": rows})
    summary = {"vendor_count": len([p for p in pos if not p["no_vendor"]]),
               "novendor_lines": sum(p["line_count"] for p in pos if p["no_vendor"]),
               "line_count": sum(p["line_count"] for p in pos),
               "total_qty": round(sum(p["total_qty"] for p in pos), 3),
               "total_amt": round(sum(p["total_amt"] for p in pos), 2)}
    return pos, summary


@router.get("/api/autoorder/preview")
def autoorder_preview(line: str = Query(""), cr: str = Query(""), vendor: str = Query(""),
                      item: str = Query(""), gubun: str = Query(""), ymd: str = Query("")):
    """자동발주 미리보기 = 정본 자재소요(nx.plan_mat_source)→업체별 PO 후보(순소요·단가·금액). 확정 안 함(읽기)."""
    asof = _d6(ymd) if ymd.strip() else datetime.now().strftime("%y%m%d")
    pos, summary = _build_preview(line, cr, vendor, item, gubun, asof)
    return {"ok": True, "asof": asof, "pos": pos, "summary": summary,
            "note": "정본 자재소요(nx.plan_part_mat STEP5→6→7 100%검증)+조달프로파일 오버레이(nx.plan_mat_source) → 순소요=소요−확정발주. 단가=마스터 매입단가 as-of(읽기전용). 자체(내부제작)·용접봉 제외."}


@router.post("/api/autoorder/confirm")
def autoorder_confirm(payload: dict = Body(...)):
    """확정 = 미리보기를 서버측 재산출(클라이언트 수량 불신) 후 nx.auto_po(업체별 헤더)+nx.auto_po_line 생성.
       vendors=[코드] 지정 시 그 업체만 확정. 미지정 업체(공란)는 확정 제외(발주업체 지정 필요)."""
    line = str(payload.get("line", "")).strip(); cr = str(payload.get("cr", "")).strip()
    vendor = str(payload.get("vendor", "")).strip(); item = str(payload.get("item", "")).strip()
    gubun = str(payload.get("gubun", "")).strip()
    ymd = str(payload.get("ymd", "")).strip()
    only = set(str(v).strip() for v in (payload.get("vendors") or []) if str(v).strip())
    user = (str(payload.get("user", "")).strip() or "웹사용자")[:30]
    asof = _d6(ymd) if ymd else datetime.now().strftime("%y%m%d")
    pos, summary = _build_preview(line, cr, vendor, item, gubun, asof)
    # 발주업체 확정 대상: 미지정(공란) 제외. only 지정 시 교집합.
    targets = [p for p in pos if not p["no_vendor"] and (not only or p["vendor_code"] in only)]
    if not targets:
        return {"ok": False, "error": "확정 대상 없음(발주업체 미지정 제외 또는 필터 결과 없음). 미리보기를 확인하세요.",
                "skipped_novendor": summary["novendor_lines"]}
    batch = "AO" + datetime.now().strftime("%y%m%d%H%M%S")
    po_ymd = datetime.now().strftime("%y%m%d")
    made = []
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_ao_tbl(cur)
        for vi, p in enumerate(targets, 1):
            po_no = f"{batch}-{vi:03d}"
            cur.execute("""INSERT INTO nx.auto_po(po_no,gen_batch,po_ymd,vendor_code,vendor_name,supply_gubun,status,
                line_count,total_qty,total_amt,filt_line,filt_cr,filt_gubun,filt_vendor,filt_item,ins_user,ins_dt)
                VALUES(?,?,?,?,?,?, '확정', ?,?,?,?,?,?,?,?,?, getdate())""",
                po_no, batch, po_ymd, p["vendor_code"], p["vendor_name"][:120],
                (p["lines"][0]["supply_gubun"] if p["lines"] else ""), p["line_count"], p["total_qty"], p["total_amt"],
                line[:20], cr[:2], gubun[:20], vendor[:20], item[:40], user)
            lrows = [(po_no, si, r["item_code"], (r["item_name"] or "")[:200], r["supply_gubun"],
                      r["req_qty"], r["already_qty"], r["order_qty"],
                      r["unit_price"], (r["currency"] or "")[:6], r["amt"], (r["source"] or "")[:10])
                     for si, r in enumerate(p["lines"], 1)]
            cur.fast_executemany = True
            cur.executemany("""INSERT INTO nx.auto_po_line(po_no,seq,item_code,item_name,supply_gubun,
                req_qty,already_qty,order_qty,unit_price,currency,amt,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", lrows)
            made.append({"po_no": po_no, "vendor_code": p["vendor_code"], "vendor_name": p["vendor_name"],
                         "line_count": p["line_count"], "total_qty": p["total_qty"], "total_amt": p["total_amt"]})
        nx.commit()
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()
    return {"ok": True, "batch": batch, "po_count": len(made), "pos": made,
            "line_count": sum(m["line_count"] for m in made),
            "total_amt": round(sum(m["total_amt"] for m in made), 2),
            "skipped_novendor": summary["novendor_lines"]}


@router.get("/api/autoorder/list")
def autoorder_list(batch: str = Query(""), vendor: str = Query(""), status: str = Query(""),
                   po_no: str = Query("")):
    """확정된 자동발주 조회(헤더 또는 명세). po_no 지정 시 그 PO 라인 명세, 아니면 헤더 목록."""
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_ao_tbl(cur)
        if po_no.strip():
            cur.execute("""SELECT po_no, seq, item_code, item_name, supply_gubun, req_qty, already_qty, order_qty,
                  unit_price, currency, amt, source FROM nx.auto_po_line WHERE po_no=? ORDER BY seq""", po_no.strip())
            cols = [d[0] for d in cur.description]
            lines = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                for k in ("req_qty", "already_qty", "order_qty", "unit_price", "amt"):
                    d[k] = float(d[k]) if d[k] is not None else None
                lines.append(d)
            return {"ok": True, "po_no": po_no.strip(), "lines": lines}
        w = ["1=1"]; p = []
        if batch.strip(): w.append("gen_batch=?"); p.append(batch.strip())
        if vendor.strip(): w.append("vendor_code=?"); p.append(vendor.strip())
        if status.strip(): w.append("status=?"); p.append(status.strip())
        cur.execute(f"""SELECT po_no, gen_batch, po_ymd, vendor_code, vendor_name, supply_gubun, status,
              line_count, total_qty, total_amt, ins_user, CONVERT(varchar(19),ins_dt,120) ins_dt
            FROM nx.auto_po WHERE {' AND '.join(w)} ORDER BY po_no DESC""", *p)
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            for k in ("total_qty", "total_amt"):
                d[k] = float(d[k]) if d[k] is not None else None
            rows.append(d)
        return {"ok": True, "rows": rows, "count": len(rows),
                "total_amt": round(sum((r["total_amt"] or 0) for r in rows if r["status"] == '확정'), 2)}
    finally:
        nx.close()


@router.post("/api/autoorder/cancel")
def autoorder_cancel(payload: dict = Body(...)):
    """자동발주 취소(status='취소', 근거키=po_no 스코프). 취소분은 순소요 차감에서 제외 → 재발주 가능.
       hard=1 이면 스코프 하드삭제(po_no/batch 한정 — 태그 대량삭제 아님). 테스트 정리용."""
    po_no = str(payload.get("po_no", "")).strip()
    batch = str(payload.get("batch", "")).strip()
    hard = bool(payload.get("hard"))
    if not po_no and not batch:
        raise HTTPException(400, "po_no 또는 batch 필요(근거키 스코프)")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_ao_tbl(cur)
        scope = ("po_no=?", po_no) if po_no else ("gen_batch=?", batch)
        if hard:
            cur.execute(f"DELETE FROM nx.auto_po_line WHERE po_no IN (SELECT po_no FROM nx.auto_po WHERE {scope[0]})", scope[1])
            nline = cur.rowcount
            cur.execute(f"DELETE FROM nx.auto_po WHERE {scope[0]}", scope[1])
            nhead = cur.rowcount
            nx.commit()
            return {"ok": True, "mode": "hard_delete", "po_deleted": nhead, "line_deleted": nline, "scope": scope[1]}
        cur.execute(f"UPDATE nx.auto_po SET status='취소', upd_dt=getdate() WHERE {scope[0]}", scope[1])
        n = cur.rowcount
        nx.commit()
        return {"ok": True, "mode": "cancel", "po_cancelled": n, "scope": scope[1]}
    except HTTPException:
        nx.rollback(); raise
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()
