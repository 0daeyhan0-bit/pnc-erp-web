# -*- coding: utf-8 -*-
"""LG사급현황 — LG 사급 실적(월별 유상사급 입고) 엑셀 업로드 + 조회. 사급가 업로드와 유사 패턴.
   저장=nx.lg_sagub_actual. 실제 사급 입고(월 18~22억)를 넣어 우리 계산(예상/원가분석)과 대사용."""
import io as _io
from fastapi import APIRouter, Query, UploadFile, File, HTTPException
from common import _nx, _conn

router = APIRouter()

_DDL = """IF OBJECT_ID('nx.lg_sagub_actual') IS NULL
CREATE TABLE nx.lg_sagub_actual(
  id int IDENTITY(1,1) PRIMARY KEY, ym varchar(4), item_code varchar(50), item_name nvarchar(200),
  qty float, amt float, price float, cust_code varchar(20), remarks nvarchar(300),
  src_file nvarchar(200), upload_dt datetime DEFAULT getdate())"""

# 엑셀 헤더 → 컬럼 매핑(유연 감지). 소문자/공백제거 비교.
_ALIAS = {
    "item": ["품번", "품목", "품목코드", "자재", "자재코드", "material", "item", "itemcode", "code", "partno", "part", "품번호"],
    "name": ["품명", "품목명", "품명규격", "name", "itemname", "desc", "description", "material desc"],
    "qty": ["수량", "입고수량", "사급수량", "qty", "quantity", "inputqty", "recvqty", "입고량"],
    "amt": ["금액", "입고금액", "사급금액", "가액", "공급가액", "합계금액", "amount", "amt", "value", "총액"],
    "price": ["단가", "사급가", "사급단가", "price", "unitprice", "unit"],
    "ym": ["월", "기준월", "년월", "ym", "yearmonth"],
    "ymd": ["일자", "입고일", "입고일자", "적용일", "date", "ymd", "startdate", "start date", "transaction_ymd", "in_ymd"],
    "cust": ["거래처", "업체", "사업장", "매입처", "cust", "vendor", "site", "plant"],
}


def _norm(h):
    return "".join(str(h or "").strip().lower().split())


def _ym_of(v):
    """값에서 YYMM 추출(날짜/문자/월)."""
    if v is None or v == "":
        return ""
    if hasattr(v, "year"):
        return f"{v.year % 100:02d}{v.month:02d}"
    s = "".join(ch for ch in str(v) if ch.isdigit())
    if len(s) >= 6:      # YYYYMMDD.. or YYYYMM
        return s[2:6] if len(s) >= 8 else s[2:6]
    if len(s) == 4:      # YYMM
        return s
    if len(s) <= 2:      # 월만(1~12)
        try:
            m = int(s)
            if 1 <= m <= 12:
                return None  # 월만으론 연도 모름 → 호출측 기준연도 사용
        except Exception:
            pass
    return ""


@router.post("/api/lgsagub/upload")
async def lgsagub_upload(file: UploadFile = File(...), ym: str = Query(""), base_year: str = Query("26")):
    """LG 사급 실적 엑셀 업로드 → nx.lg_sagub_actual. 컬럼 유연감지(품번/수량/금액/단가/월). 감지결과 반환.
       ym(YYMM) 주면 전 행 그 월로. 없으면 각 행 일자/월 컬럼에서 추출(월만 있으면 base_year 사용)."""
    try:
        import openpyxl
    except Exception:
        raise HTTPException(500, "openpyxl 미설치(서버)")
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(_io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(400, f"엑셀 열기 실패: {str(e)[:120]}")
    ws = wb.active
    rows_all = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows_all:
        raise HTTPException(400, "빈 파일")
    # 헤더행 자동탐지: 앞 10행 중 alias 매칭 최다 행
    best_hi, best_map, best_score = 0, {}, -1
    for hi in range(min(10, len(rows_all))):
        hdr = rows_all[hi]
        nm = {i: _norm(h) for i, h in enumerate(hdr)}
        mp = {}
        for key, al in _ALIAS.items():
            als = ["".join(a.split()) for a in al]
            for i, h in nm.items():
                if h and (h in als or any(h == a or a in h for a in als)):
                    mp.setdefault(key, i)
        score = len(mp) + (2 if "item" in mp else 0) + (1 if ("qty" in mp or "amt" in mp) else 0)
        if score > best_score:
            best_hi, best_map, best_score = hi, mp, score
    ixmap = best_map
    detected = {k: str(rows_all[best_hi][i]) for k, i in ixmap.items()}
    if "item" not in ixmap:
        return {"ok": False, "error": "품번 컬럼 감지 실패", "header_row": [str(x) for x in rows_all[best_hi]], "detected": detected}

    def gv(r, key):
        i = ixmap.get(key)
        if i is None or i >= len(r):
            return None
        v = r[i]
        return None if v in (None, "") else v

    forced_ym = ym.strip()
    recs = []
    for r in rows_all[best_hi + 1:]:
        if not r or not any(x not in (None, "") for x in r):
            continue
        it = str(gv(r, "item") or "").strip()
        if not it or it.lower() in ("품번", "합계", "total", "소계"):
            continue
        def _f(key):
            v = gv(r, key)
            try:
                return float(str(v).replace(",", "")) if v is not None else None
            except Exception:
                return None
        q = _f("qty"); a = _f("amt"); p = _f("price")
        # 월 결정
        rym = forced_ym
        if not rym:
            rym = _ym_of(gv(r, "ymd")) or _ym_of(gv(r, "ym"))
            if rym is None:  # 월만 있음
                mm = "".join(ch for ch in str(gv(r, "ym") or gv(r, "ymd") or "") if ch.isdigit())
                rym = f"{base_year}{int(mm):02d}" if mm.isdigit() and 1 <= int(mm) <= 12 else ""
        recs.append((rym or "", it, str(gv(r, "name") or "")[:200], q, a, p,
                     str(gv(r, "cust") or "")[:20], ""))
    if not recs:
        return {"ok": False, "error": "데이터 행 없음", "detected": detected, "header_row": [str(x) for x in rows_all[best_hi]]}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(_DDL)
        # 같은 파일 재업로드 시 중복방지: src_file+ym 기존 삭제 후 삽입
        fn = (file.filename or "")[:200]
        yms = sorted(set(x[0] for x in recs if x[0]))
        if yms:
            inl = ",".join("'" + y.replace("'", "") + "'" for y in yms)
            cur.execute(f"DELETE FROM nx.lg_sagub_actual WHERE src_file=? AND ym IN ({inl})", fn)
        else:
            cur.execute("DELETE FROM nx.lg_sagub_actual WHERE src_file=?", fn)
        # ★배치 다중행 INSERT(200행/쿼리) — 행별 왕복 제거로 대용량 고속. (SQL Server 파라미터 2100 한도: 200×9=1800 안전)
        try: cur.fast_executemany = True
        except Exception: pass
        cols = "(ym,item_code,item_name,qty,amt,price,cust_code,remarks,src_file)"
        n = 0; BATCH = 200
        for i in range(0, len(recs), BATCH):
            chunk = recs[i:i + BATCH]
            vals = ",".join("(?,?,?,?,?,?,?,?,?)" for _ in chunk)
            flat = []
            for ymv, it, nmv, q, a, p, cst, rm in chunk:
                flat += [ymv, it, nmv, q, a, p, cst, rm, fn]
            cur.execute(f"INSERT INTO nx.lg_sagub_actual{cols} VALUES {vals}", *flat)
            n += len(chunk)
        nx.commit()
        # 업로드 요약
        cur.execute("SELECT ym, COUNT(*), SUM(ISNULL(qty,0)), SUM(ISNULL(amt,0)) FROM nx.lg_sagub_actual WHERE src_file=? GROUP BY ym ORDER BY ym", fn)
        by_ym = [{"ym": r[0], "rows": r[1], "qty": float(r[2] or 0), "amt": float(r[3] or 0)} for r in cur.fetchall()]
        return {"ok": True, "file": fn, "rows": n, "detected": detected, "by_ym": by_ym}
    finally:
        nx.close()


@router.get("/api/lgsagub/summary")
def lgsagub_summary():
    """월별 LG사급 실적 집계(업로드분) + 전체 파일 목록."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(_DDL)
        cur.execute("""SELECT ym, COUNT(DISTINCT item_code) items, SUM(ISNULL(qty,0)) qty, SUM(ISNULL(amt,0)) amt
            FROM nx.lg_sagub_actual GROUP BY ym ORDER BY ym""")
        by_ym = [{"ym": r[0], "items": r[1], "qty": float(r[2] or 0), "amt": float(r[3] or 0)} for r in cur.fetchall()]
        cur.execute("SELECT src_file, MIN(ym), MAX(ym), COUNT(*), MAX(upload_dt) FROM nx.lg_sagub_actual GROUP BY src_file ORDER BY MAX(upload_dt) DESC")
        files = [{"file": r[0], "ym_from": r[1], "ym_to": r[2], "rows": r[3], "dt": str(r[4])[:19]} for r in cur.fetchall()]
        return {"by_ym": by_ym, "files": files}
    finally:
        nx.close()


@router.get("/api/lgsagub/list")
def lgsagub_list(ym: str = Query(""), q: str = Query(""), limit: int = Query(3000)):
    """LG사급 실적 품목별 목록(월 필터). item_name 없으면 마스터 보강."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(_DDL)
        wh = ["1=1"]; p = []
        if ym.strip():
            wh.append("s.ym=?"); p.append(ym.strip())
        if q.strip():
            wh.append("(s.item_code LIKE ? OR s.item_name LIKE ?)"); p += [f"%{q.strip()}%", f"%{q.strip()}%"]
        cur.execute(f"""SELECT TOP {int(limit)} s.ym, s.item_code,
              MAX(ISNULL(NULLIF(s.item_name,''), ISNULL(i.item_name,''))) nm,
              SUM(ISNULL(s.qty,0)) qty, SUM(ISNULL(s.amt,0)) amt, MAX(s.price) price
            FROM nx.lg_sagub_actual s LEFT JOIN nx.item i ON i.item_code=s.item_code COLLATE DATABASE_DEFAULT
            WHERE {' AND '.join(wh)}
            GROUP BY s.ym, s.item_code ORDER BY SUM(ISNULL(s.amt,0)) DESC, s.item_code""", *p)
        rows = [{"ym": r[0], "item": r[1], "name": r[2], "qty": float(r[3] or 0), "amt": float(r[4] or 0),
                 "price": float(r[5] or 0)} for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()
