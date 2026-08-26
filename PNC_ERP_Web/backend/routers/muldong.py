# -*- coding: utf-8 -*-
"""LG 물동량(영업) — LG 물동계획(4주 초과 장기 수요) 엑셀 업로드+조회.
   원본 = LG_RAC_26년물동.xls / LG_SAC_26년물동.xls (시트 물동RAC/물동SAC).
   포맷: 헤더행에 '모델명' + 월컬럼 '26YYMM~'27YYMM(12개월), 데이터=모델별 월수량.
   저장 = nx.lg_muldong (정규화 long: biz×model×plan_yymm×qty + 표시속성).
   ★사업부(biz RAC/SAC)=업로드시 사용자 선택(파일 안에 컬럼 없음·파일명 fallback). 레거시 GUBUN: RAC→R·SAC→C(교차0 확정).
   자재예상매입의 '4주 초과 물동 소요' 소스. 참조패턴=lgsagub.py(사급현황 업로드)."""
import io as _io, re as _re
from fastapi import APIRouter, Query, UploadFile, File, HTTPException
from common import _nx

router = APIRouter()

_DDL = """IF OBJECT_ID('nx.lg_muldong') IS NULL
CREATE TABLE nx.lg_muldong(
  biz varchar(4), model nvarchar(60), plan_yymm varchar(4), qty float,
  tool nvarchar(40), oper_gubun nvarchar(60), cross_gubun nvarchar(40), sale_price float,
  src_file nvarchar(200), upload_dt datetime DEFAULT getdate())"""


def _biz_norm(s):
    """사업부 정규화: rac/dgz→RAC, sac/dmz→SAC. 그 외 대문자."""
    u = (str(s or "")).strip().upper()
    if u in ("RAC", "DGZ"):
        return "RAC"
    if u in ("SAC", "DMZ"):
        return "SAC"
    return u


def _biz_from_name(fn):
    """파일명에서 사업부 추론(fallback). LG_RAC_..·물동RAC→RAC."""
    u = (fn or "").upper()
    if "RAC" in u or "DGZ" in u:
        return "RAC"
    if "SAC" in u or "DMZ" in u:
        return "SAC"
    return ""


def _num(v):
    try:
        f = float(v)
        return f if f == f else 0.0  # NaN guard
    except Exception:
        return 0.0


def _parse(content, fname):
    """엑셀(.xls/.xlsx) 바이트 → (rows, months). rows=[{model,plan_yymm,qty,tool,oper_gubun,cross_gubun,sale_price}]."""
    import pandas as pd
    eng = "xlrd" if (fname or "").lower().endswith(".xls") else "openpyxl"
    try:
        df = pd.read_excel(_io.BytesIO(content), sheet_name=0, header=None, engine=eng)
    except Exception:
        # 엔진 교차 폴백
        df = pd.read_excel(_io.BytesIO(content), sheet_name=0, header=None, engine=("openpyxl" if eng == "xlrd" else "xlrd"))
    # 헤더행 = '모델명' 포함 행
    hdr = None
    for i in range(min(10, len(df))):
        if any(str(v).strip() == "모델명" for v in list(df.iloc[i])):
            hdr = i
            break
    if hdr is None:
        raise HTTPException(400, "헤더행(‘모델명’)을 찾지 못했습니다. LG 물동 엑셀이 맞는지 확인하세요.")
    head = [str(v).strip() for v in list(df.iloc[hdr])]

    def _findcol(*names):
        for j, h in enumerate(head):
            if h in names:
                return j
        return None
    mcol = _findcol("모델명")
    tcol = _findcol("TOOL", "Tool")
    ocol = _findcol("운영구분")
    ccol = _findcol("교차")
    pcol = _findcol("매출단가")
    # 월컬럼: '26YYMM/'27YYMM (선행 apostrophe 제거 후 4자리 YYMM)
    mon = {}
    for j, h in enumerate(head):
        s = h.lstrip("'").strip()
        if _re.fullmatch(r"2[0-9]\d{2}", s):
            mon[j] = s
    if mcol is None or not mon:
        raise HTTPException(400, "모델명/월컬럼을 감지하지 못했습니다.")
    rows = []
    for i in range(hdr + 1, len(df)):
        r = list(df.iloc[i])
        model = str(r[mcol]).strip()
        if not model or model.lower() == "nan":
            continue
        tool = "" if tcol is None else str(r[tcol]).strip().replace("nan", "")
        oper = "" if ocol is None else str(r[ocol]).strip().replace("nan", "")
        cross = "" if ccol is None else str(r[ccol]).strip().replace("nan", "")
        price = 0.0 if pcol is None else _num(r[pcol])
        for j, ym in mon.items():
            q = _num(r[j])
            if q:
                rows.append({"model": model, "plan_yymm": ym, "qty": q,
                             "tool": tool[:40], "oper_gubun": oper[:60], "cross_gubun": cross[:40], "sale_price": price})
    return rows, sorted(set(mon.values()))


@router.post("/api/muldong/upload")
async def muldong_upload(file: UploadFile = File(...), biz: str = Query("")):
    """LG 물동 엑셀 업로드 → nx.lg_muldong. biz(RAC/SAC) 필수(미지정 시 파일명 추론).
       재업로드 = 같은 biz 기존행 전체 교체(물동은 전체 스냅샷)."""
    fn = file.filename or ""
    bizv = _biz_norm(biz) or _biz_from_name(fn)
    if bizv not in ("RAC", "SAC"):
        raise HTTPException(400, "사업부(RAC/SAC)를 선택하세요.")
    content = await file.read()
    rows, months = _parse(content, fn)
    if not rows:
        return {"ok": True, "biz": bizv, "rows": 0, "models": 0, "months": months, "file": fn, "note": "추출행 0(수량 전부 0?)"}
    cn = _nx(); cur = cn.cursor()
    try:
        for stmt in _DDL.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        # 재업로드: 같은 사업부 전체 교체(물동=전량 스냅샷)
        cur.execute("DELETE FROM nx.lg_muldong WHERE ISNULL(biz,'')=?", bizv)
        cols = "biz,model,plan_yymm,qty,tool,oper_gubun,cross_gubun,sale_price,src_file"
        ph = "?,?,?,?,?,?,?,?,?"
        buf = [[bizv, r["model"], r["plan_yymm"], r["qty"], r["tool"], r["oper_gubun"], r["cross_gubun"], r["sale_price"], fn] for r in rows]
        try:
            cur.fast_executemany = True
        except Exception:
            pass
        BATCH = 200  # 9파라미터×200=1800 < 2100
        n = 0
        for i in range(0, len(buf), BATCH):
            cur.executemany(f"INSERT INTO nx.lg_muldong({cols}) VALUES({ph})", buf[i:i + BATCH])
            n += len(buf[i:i + BATCH])
        cn.commit()
        return {"ok": True, "biz": bizv, "rows": n, "models": len(set(r["model"] for r in rows)),
                "months": months, "file": fn}
    except Exception as e:
        try: cn.rollback()
        except Exception: pass
        return {"ok": False, "error": str(e)[:200]}
    finally:
        cn.close()


@router.get("/api/muldong/summary")
def muldong_summary():
    """보유 물동 현황: 사업부별 모델수·월범위·파일·최근업로드."""
    cn = _nx(); cur = cn.cursor()
    try:
        for stmt in _DDL.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        cn.commit()
        cur.execute("""SELECT biz, COUNT(DISTINCT model) models, MIN(plan_yymm) ym0, MAX(plan_yymm) ym1,
                       MAX(src_file) src, CONVERT(varchar,MAX(upload_dt),120) upd, SUM(qty) tq
                       FROM nx.lg_muldong GROUP BY biz ORDER BY biz""")
        rows = [{"biz": r[0], "models": r[1], "ym0": r[2], "ym1": r[3], "src": r[4], "upd": r[5], "qty": float(r[6] or 0)}
                for r in cur.fetchall()]
        return {"rows": rows}
    finally:
        cn.close()


@router.get("/api/muldong/list")
def muldong_list(biz: str = Query(""), ym_from: str = Query(""), ym_to: str = Query(""), q: str = Query("")):
    """물동 조회 — 모델×월 피벗(long 반환, 프론트가 피벗). biz·월범위·모델/툴 검색."""
    cn = _nx(); cur = cn.cursor()
    try:
        for stmt in _DDL.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        cn.commit()
        w = ["1=1"]; p = []
        b = _biz_norm(biz)
        if b in ("RAC", "SAC"):
            w.append("biz=?"); p.append(b)
        if ym_from:
            w.append("plan_yymm>=?"); p.append(ym_from[-4:])
        if ym_to:
            w.append("plan_yymm<=?"); p.append(ym_to[-4:])
        if q:
            w.append("(model LIKE ? OR tool LIKE ?)"); p += ["%" + q + "%", "%" + q + "%"]
        cur.execute(f"""SELECT biz, model, plan_yymm, qty, tool, oper_gubun, cross_gubun, sale_price
                        FROM nx.lg_muldong WHERE {' AND '.join(w)} ORDER BY biz, model, plan_yymm""", *p)
        rows = [{"biz": r[0], "model": r[1], "ym": r[2], "qty": float(r[3] or 0), "tool": r[4],
                 "oper": r[5], "cross": r[6], "price": float(r[7] or 0)} for r in cur.fetchall()]
        months = sorted(set(r["ym"] for r in rows))
        return {"rows": rows, "months": months, "count": len(rows)}
    finally:
        cn.close()
