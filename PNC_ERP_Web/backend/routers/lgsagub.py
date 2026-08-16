# -*- coding: utf-8 -*-
"""LG사급현황 — LG 사급 실적(월별 유상사급 입고) 엑셀 업로드 + 조회. 사급가 업로드와 유사 패턴.
   저장=nx.lg_sagub_actual. 실제 사급 입고(월 18~22억)를 넣어 우리 계산(예상/원가분석)과 대사용."""
import io as _io
from fastapi import APIRouter, Query, UploadFile, File, HTTPException
from common import _nx, _conn

router = APIRouter()

_DDL = """IF OBJECT_ID('nx.lg_sagub_actual') IS NULL
CREATE TABLE nx.lg_sagub_actual(
  id int IDENTITY(1,1) PRIMARY KEY, ym varchar(4), ymd varchar(8), biz varchar(4), item_code varchar(50), item_name nvarchar(200),
  qty float, amt float, price float, cust_code varchar(20), remarks nvarchar(300),
  src_file nvarchar(200), upload_dt datetime DEFAULT getdate())"""
# 기존 테이블 마이그레이션: ymd(일자)·biz(사업부 RAC/SAC) 컬럼 없으면 추가
_MIGRATE = """IF COL_LENGTH('nx.lg_sagub_actual','ymd') IS NULL ALTER TABLE nx.lg_sagub_actual ADD ymd varchar(8);
IF COL_LENGTH('nx.lg_sagub_actual','biz') IS NULL ALTER TABLE nx.lg_sagub_actual ADD biz varchar(4);"""

def _prep(cur):
    cur.execute(_DDL); cur.execute(_MIGRATE)

def _biz_norm(v):
    """사업부 정규화: rac/dgz→RAC, sac/dmz→SAC. 그 외는 대문자 그대로."""
    s = str(v or "").strip().lower()
    if not s: return ""
    if "rac" in s or "dgz" in s: return "RAC"
    if "sac" in s or "dmz" in s: return "SAC"
    return str(v).strip().upper()[:4]

def _ymd6(v):
    """값에서 YYMMDD(6) 추출. 날짜/문자 모두. 실패시 ''."""
    if v is None or v == "": return ""
    if hasattr(v, "year"):
        return f"{v.year % 100:02d}{v.month:02d}{v.day:02d}"
    s = "".join(ch for ch in str(v) if ch.isdigit())
    if len(s) >= 8: return s[2:8]   # YYYYMMDD(+시간) → YYMMDD
    if len(s) == 6: return s        # YYMMDD
    return ""

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
async def lgsagub_upload(file: UploadFile = File(...), ym: str = Query(""), base_year: str = Query("26"), biz: str = Query("")):
    """LG 사급 실적 엑셀 업로드 → nx.lg_sagub_actual. 컬럼 유연감지(품번/수량/금액/단가/일자). 감지결과 반환.
       ★biz(사업부 RAC/SAC)=업로드 시 사용자 선택(파일명에 없어서). 일자(Transaction Date)→ymd(YYMMDD), ym=ymd 앞4."""
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
    bizv = _biz_norm(biz) or _biz_norm(file.filename)   # 사용자선택 우선, 없으면 파일명(lg_rac/lg_sac)에서 추론
    _SUMMARY = ("total", "합계", "subtotal", "소계", "grand total", "총계")
    recs = []
    for r in rows_all[best_hi + 1:]:
        if not r or not any(x not in (None, "") for x in r):
            continue
        # ★요약/Total 행 스킵(OSP 파일 끝 'Total' 행이 데이터에 섞여 이중계상 방지)
        if any(isinstance(x, str) and x.strip().lower() in _SUMMARY for x in r):
            continue
        it = str(gv(r, "item") or "").strip()
        if not it or it.lower() in ("품번", "material", "품목", "합계", "total", "소계"):
            continue
        def _f(key):
            v = gv(r, key)
            try:
                return float(str(v).replace(",", "")) if v is not None else None
            except Exception:
                return None
        q = _f("qty"); a = _f("amt"); p = _f("price")
        # 일자(Transaction Date)→ymd(YYMMDD), 월=ymd 앞4. forced_ym 있으면 우선.
        rymd = _ymd6(gv(r, "ymd"))
        rym = forced_ym or (rymd[:4] if rymd else "")
        if not rym:
            rym = _ym_of(gv(r, "ym"))
            if rym is None:  # 월만 있음
                mm = "".join(ch for ch in str(gv(r, "ym") or gv(r, "ymd") or "") if ch.isdigit())
                rym = f"{base_year}{int(mm):02d}" if mm.isdigit() and 1 <= int(mm) <= 12 else ""
        recs.append((rym or "", rymd, bizv, it, str(gv(r, "name") or "")[:200], q, a, p,
                     str(gv(r, "cust") or "")[:20], ""))
    if not recs:
        return {"ok": False, "error": "데이터 행 없음", "detected": detected, "header_row": [str(x) for x in rows_all[best_hi]]}
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur)
        # 같은 파일 재업로드 시 중복방지: src_file+biz 기존 삭제 후 삽입(같은 파일을 다른 사업부로 올릴 일 없음)
        fn = (file.filename or "")[:200]
        cur.execute("DELETE FROM nx.lg_sagub_actual WHERE src_file=? AND ISNULL(biz,'')=?", fn, bizv)
        # ★배치 다중행 INSERT — 파라미터 2100 한도: 11컬럼 × 150 = 1650 안전
        try: cur.fast_executemany = True
        except Exception: pass
        cols = "(ym,ymd,biz,item_code,item_name,qty,amt,price,cust_code,remarks,src_file)"
        n = 0; BATCH = 150
        for i in range(0, len(recs), BATCH):
            chunk = recs[i:i + BATCH]
            vals = ",".join("(?,?,?,?,?,?,?,?,?,?,?)" for _ in chunk)
            flat = []
            for ymv, ymdv, bzv, it, nmv, q, a, p, cst, rm in chunk:
                flat += [ymv, ymdv, bzv, it, nmv, q, a, p, cst, rm, fn]
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
    """업로드분 요약: 월범위·사업부별·파일목록(기간필터 기본값·필터콤보용)."""
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur)
        cur.execute("""SELECT ym, COUNT(DISTINCT item_code) items, SUM(ISNULL(qty,0)) qty, SUM(ISNULL(amt,0)) amt
            FROM nx.lg_sagub_actual GROUP BY ym ORDER BY ym""")
        by_ym = [{"ym": r[0], "items": r[1], "qty": float(r[2] or 0), "amt": float(r[3] or 0)} for r in cur.fetchall()]
        cur.execute("SELECT ISNULL(biz,'') b, COUNT(*) c, SUM(ISNULL(amt,0)) amt FROM nx.lg_sagub_actual GROUP BY ISNULL(biz,'') ORDER BY b")
        by_biz = [{"biz": r[0], "rows": r[1], "amt": float(r[2] or 0)} for r in cur.fetchall()]
        cur.execute("SELECT src_file, ISNULL(biz,''), MIN(ym), MAX(ym), COUNT(*), MAX(upload_dt) FROM nx.lg_sagub_actual GROUP BY src_file, ISNULL(biz,'') ORDER BY MAX(upload_dt) DESC")
        files = [{"file": r[0], "biz": r[1], "ym_from": r[2], "ym_to": r[3], "rows": r[4], "dt": str(r[5])[:19]} for r in cur.fetchall()]
        return {"by_ym": by_ym, "by_biz": by_biz, "files": files}
    finally:
        nx.close()


def _cls_of(name):
    """분류: 품명에 TUBE 있으면 원소재(동파이프 등), 나머지는 사급부품(사용자 규칙)."""
    return "원소재" if "TUBE" in str(name or "").upper() else "사급부품"


@router.get("/api/lgsagub/list")
def lgsagub_list(ym: str = Query(""), ym_from: str = Query(""), ym_to: str = Query(""), biz: str = Query(""), cls: str = Query(""), q: str = Query(""), limit: int = Query(3000)):
    """LG사급 실적 품목별 요약목록(기간·사업부·분류 필터). 기간=ym_from~ym_to(YYMM), ym=단월 우선.
       pmin/pmax=단가 최소/최대(다르면 가격변동 有→pchg=1), ndays=일자수. cls=원소재(품명 TUBE)/사급부품. item_name 없으면 마스터 보강."""
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur)
        wh = ["1=1"]; p = []
        if ym.strip():
            wh.append("s.ym=?"); p.append(ym.strip())
        else:
            if ym_from.strip(): wh.append("s.ym>=?"); p.append(ym_from.strip())
            if ym_to.strip():   wh.append("s.ym<=?"); p.append(ym_to.strip())
        if biz.strip(): wh.append("ISNULL(s.biz,'')=?"); p.append(biz.strip())
        if q.strip():
            wh.append("(s.item_code LIKE ? OR s.item_name LIKE ?)"); p += [f"%{q.strip()}%", f"%{q.strip()}%"]
        cur.execute(f"""SELECT TOP {int(limit)} s.item_code,
              MAX(ISNULL(NULLIF(s.item_name,''), ISNULL(i.item_name,''))) nm,
              SUM(ISNULL(s.qty,0)) qty, SUM(ISNULL(s.amt,0)) amt,
              MIN(NULLIF(s.price,0)) pmin, MAX(s.price) pmax, COUNT(*) cnt, COUNT(DISTINCT ISNULL(s.ymd,'')) ndays
            FROM nx.lg_sagub_actual s LEFT JOIN nx.item i ON i.item_code=s.item_code COLLATE DATABASE_DEFAULT
            WHERE {' AND '.join(wh)}
            GROUP BY s.item_code ORDER BY SUM(ISNULL(s.amt,0)) DESC, s.item_code""", *p)
        rows = []
        clsf = cls.strip()
        for r in cur.fetchall():
            pmin = float(r[4] or 0); pmax = float(r[5] or 0)
            cl = _cls_of(r[1])
            if clsf and cl != clsf:
                continue
            rows.append({"item": r[0], "name": r[1], "cls": cl, "qty": float(r[2] or 0), "amt": float(r[3] or 0),
                         "pmin": pmin, "pmax": pmax, "cnt": r[6], "ndays": r[7],
                         "pchg": 1 if (pmin and pmax and abs(pmax - pmin) > 1e-6) else 0})
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()


@router.get("/api/lgsagub/detail")
def lgsagub_detail(item: str = Query(""), ym_from: str = Query(""), ym_to: str = Query(""), biz: str = Query(""), limit: int = Query(3000)):
    """품번별 개별 사급 기록(일자·사업부·단가별). 가격 변동일자 확인용. 같은 일자·사업부·단가는 합산."""
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur)
        if not item.strip():
            return {"rows": [], "cnt": 0}
        wh = ["s.item_code=?"]; p = [item.strip()]
        if ym_from.strip(): wh.append("s.ym>=?"); p.append(ym_from.strip())
        if ym_to.strip():   wh.append("s.ym<=?"); p.append(ym_to.strip())
        if biz.strip():     wh.append("ISNULL(s.biz,'')=?"); p.append(biz.strip())
        cur.execute(f"""SELECT TOP {int(limit)} ISNULL(s.ymd,'') ymd, ISNULL(s.biz,'') biz, s.price,
              SUM(ISNULL(s.qty,0)) qty, SUM(ISNULL(s.amt,0)) amt, COUNT(*) cnt
            FROM nx.lg_sagub_actual s
            WHERE {' AND '.join(wh)}
            GROUP BY ISNULL(s.ymd,''), ISNULL(s.biz,''), s.price
            ORDER BY ISNULL(s.ymd,''), ISNULL(s.biz,''), s.price""", *p)
        rows = [{"ymd": r[0], "biz": r[1], "price": float(r[2] or 0), "qty": float(r[3] or 0),
                 "amt": float(r[4] or 0), "cnt": r[5]} for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()
