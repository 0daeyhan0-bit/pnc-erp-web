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
        # ★재업로드=최신 업데이트(#9): 같은 사업부의 "그 파일에 담긴 일자(ymd)" 또는 같은 파일명 기존행 삭제 후 삽입.
        #   OSP 파일명은 다운로드마다 번호가 바뀌므로 파일명만으론 중복제거 안 됨 → biz+ymd 기준으로 같은 사업부·같은 날짜는 최신이 덮어씀.
        fn = (file.filename or "")[:200]
        ymds = sorted({x[1] for x in recs if x[1]})
        if ymds:
            inl = ",".join("'" + y + "'" for y in ymds)
            cur.execute(f"DELETE FROM nx.lg_sagub_actual WHERE ISNULL(biz,'')=? AND (ISNULL(ymd,'') IN ({inl}) OR src_file=?)", bizv, fn)
        else:
            cur.execute("DELETE FROM nx.lg_sagub_actual WHERE ISNULL(biz,'')=? AND src_file=?", bizv, fn)
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
        cur.execute("SELECT MIN(NULLIF(ymd,'')), MAX(NULLIF(ymd,'')) FROM nx.lg_sagub_actual")
        _rr = cur.fetchone(); ymd_min = _rr[0] or ""; ymd_max = _rr[1] or ""
        cur.execute("SELECT src_file, ISNULL(biz,''), MIN(ym), MAX(ym), COUNT(*), MAX(upload_dt) FROM nx.lg_sagub_actual GROUP BY src_file, ISNULL(biz,'') ORDER BY MAX(upload_dt) DESC")
        files = [{"file": r[0], "biz": r[1], "ym_from": r[2], "ym_to": r[3], "rows": r[4], "dt": str(r[5])[:19]} for r in cur.fetchall()]
        return {"by_ym": by_ym, "by_biz": by_biz, "files": files, "ymd_min": ymd_min, "ymd_max": ymd_max}
    finally:
        nx.close()


def _cls_of(name):
    """분류: 품명에 TUBE 있으면 원소재(동파이프 등), 나머지는 사급부품(사용자 규칙)."""
    return "원소재" if "TUBE" in str(name or "").upper() else "사급부품"


def _range_wh(ym, ym_from, ym_to, ymd_from, ymd_to):
    """기간 필터 조건 생성: ymd(일자 YYMMDD) 범위 우선, 없으면 ym(월). 반환 (조건리스트, 파라미터)."""
    wh = []; p = []
    if ymd_from.strip() or ymd_to.strip():
        if ymd_from.strip(): wh.append("ISNULL(s.ymd,'')>=?"); p.append(ymd_from.strip())
        if ymd_to.strip():   wh.append("ISNULL(s.ymd,'')<=?"); p.append(ymd_to.strip())
    elif ym.strip():
        wh.append("s.ym=?"); p.append(ym.strip())
    else:
        if ym_from.strip(): wh.append("s.ym>=?"); p.append(ym_from.strip())
        if ym_to.strip():   wh.append("s.ym<=?"); p.append(ym_to.strip())
    return wh, p


@router.get("/api/lgsagub/list")
def lgsagub_list(ym: str = Query(""), ym_from: str = Query(""), ym_to: str = Query(""), ymd_from: str = Query(""), ymd_to: str = Query(""),
                 biz: str = Query(""), cls: str = Query(""), q: str = Query(""), limit: int = Query(3000)):
    """LG사급 실적 품목별 요약목록(기간·사업부·분류 필터). 기간=일자범위 ymd_from~ymd_to(YYMMDD) 우선, 없으면 월(ym).
       biz=품목별 사업부(콤마구분), pmin/pmax=단가(다르면 pchg=1), ndays=일자수. cls=원소재(품명 TUBE)/사급부품."""
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur)
        wh = ["1=1"]; p = []
        rwh, rp = _range_wh(ym, ym_from, ym_to, ymd_from, ymd_to); wh += rwh; p += rp
        if biz.strip(): wh.append("ISNULL(s.biz,'')=?"); p.append(biz.strip())
        if q.strip():
            wh.append("(s.item_code LIKE ? OR s.item_name LIKE ?)"); p += [f"%{q.strip()}%", f"%{q.strip()}%"]
        whs = ' AND '.join(wh)
        # 품목별 사업부(#8): 같은 필터로 (item, biz) 집계 → item별 사업부 콤마목록
        cur.execute(f"SELECT s.item_code, ISNULL(s.biz,'') b FROM nx.lg_sagub_actual s WHERE {whs} GROUP BY s.item_code, ISNULL(s.biz,'')", *p)
        bizmap = {}
        for ic, b in cur.fetchall(): bizmap.setdefault(ic, set()).add(b or '')
        cur.execute(f"""SELECT TOP {int(limit)} s.item_code,
              MAX(ISNULL(NULLIF(s.item_name,''), ISNULL(i.item_name,''))) nm,
              SUM(ISNULL(s.qty,0)) qty, SUM(ISNULL(s.amt,0)) amt,
              MIN(NULLIF(s.price,0)) pmin, MAX(s.price) pmax, COUNT(*) cnt, COUNT(DISTINCT ISNULL(s.ymd,'')) ndays
            FROM nx.lg_sagub_actual s LEFT JOIN nx.item i ON i.item_code=s.item_code COLLATE DATABASE_DEFAULT
            WHERE {whs}
            GROUP BY s.item_code ORDER BY SUM(ISNULL(s.amt,0)) DESC, s.item_code""", *p)
        rows = []
        clsf = cls.strip()
        for r in cur.fetchall():
            pmin = float(r[4] or 0); pmax = float(r[5] or 0)
            cl = _cls_of(r[1])
            if clsf and cl != clsf:
                continue
            rows.append({"item": r[0], "name": r[1], "cls": cl,
                         "biz": ",".join(sorted(x for x in bizmap.get(r[0], set()) if x)),
                         "qty": float(r[2] or 0), "amt": float(r[3] or 0),
                         "pmin": pmin, "pmax": pmax, "cnt": r[6], "ndays": r[7],
                         "pchg": 1 if (pmin and pmax and abs(pmax - pmin) > 1e-6) else 0})
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()


@router.get("/api/lgsagub/detail")
def lgsagub_detail(item: str = Query(""), ym_from: str = Query(""), ym_to: str = Query(""),
                   ymd_from: str = Query(""), ymd_to: str = Query(""), biz: str = Query(""), limit: int = Query(3000)):
    """품번별 개별 사급 기록(일자·사업부·단가별). 가격 변동일자 확인용. 같은 일자·사업부·단가는 합산."""
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur)
        if not item.strip():
            return {"rows": [], "cnt": 0}
        wh = ["s.item_code=?"]; p = [item.strip()]
        rwh, rp = _range_wh("", "", "", ymd_from, ymd_to); wh += rwh; p += rp
        if not (ymd_from.strip() or ymd_to.strip()):
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


# ============================================================================
#  LG 정산 원단위(동정산) — 리시빙 비교용. Assy별 동부자재 소요(사급/직거래 구분).
#  ★중량 = (외경−T)·T·길이·π·8.94/1e6 × 수량  → 수량이 이미 반영됨(합산만, ×수량 금지).
#  ★사급=LG유상사급 인정동 / 직거래=우리 직매입(미인정, 설치동류).
# ============================================================================
_SETTLE_DDL = """IF OBJECT_ID('nx.lg_settle_unit') IS NULL
CREATE TABLE nx.lg_settle_unit(
  id int IDENTITY(1,1) PRIMARY KEY, ym varchar(4), coop nvarchar(60),
  assy_pn varchar(50), assy_desc nvarchar(200), sub_pn varchar(50), sub_desc nvarchar(200),
  qty float, gubun1 nvarchar(10), gubun2 nvarchar(30),
  od float, thk float, leng float, weight float, mat_cost float,
  eff_ym varchar(4), src_file nvarchar(200), upload_dt datetime DEFAULT getdate())"""
# eff_ym = Update 일정(품목 추가/변경 시점, YYMM). 유효일자 필터(리시빙월 ≤ eff_ym 제외)용.
_SETTLE_MIGRATE = "IF COL_LENGTH('nx.lg_settle_unit','eff_ym') IS NULL ALTER TABLE nx.lg_settle_unit ADD eff_ym varchar(4);"

def _settle_prep(cur):
    cur.execute(_SETTLE_DDL); cur.execute(_SETTLE_MIGRATE)


def _upd_ym(v):
    """Update 일정 문자열 → YYMM(효력월). '19.05월'→'1905', '16.9월->17.6월'→'1706'(최신),
       '17.11월(황동물 추가)'→'1711'. 빈값/'수정'→'' (기초행=항상 유효). 여러 날짜면 마지막 채택."""
    import re
    s = str(v or "")
    ms = re.findall(r"(\d{1,2})[.\-/](\d{1,2})", s)
    if not ms:
        return ""
    y, m = ms[-1]                      # 마지막 날짜(→ 이동 후 최신)
    y = int(y); m = int(m)
    if y >= 100: y = y % 100
    return f"{y:02d}{m:02d}"


def _pick_sheet(wb):
    """원단위 파일에서 피앤씨 탭 선택(이름에 '피앤씨' 포함, 공백무시). 없으면 첫 시트."""
    for sn in wb.sheetnames:
        if "피앤씨" in sn.replace(" ", ""):
            return wb[sn]
    return wb[wb.sheetnames[0]]


@router.post("/api/lgsagub/settle_upload")
async def settle_upload(file: UploadFile = File(...), ym: str = Query(""), sheet: str = Query("")):
    """LG 동정산 원단위 엑셀 업로드 → nx.lg_settle_unit. 피앤씨 탭의 (Assy×하위동부자재) 소요.
       컬럼: Assy P/N·Desc·협력사·P/N(하위1)·Desc·수량·구분1·구분2·외경·T·길이·중량(+소재비).
       ★중량은 수량 반영값이라 그대로 저장. ym=기준월(미지정시 파일에서 추론 안됨→필수 권장)."""
    try:
        import openpyxl
    except Exception:
        raise HTTPException(500, "openpyxl 미설치(서버)")
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(_io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(400, f"엑셀 열기 실패: {str(e)[:120]}")
    ws = wb[sheet] if (sheet and sheet in wb.sheetnames) else _pick_sheet(wb)
    rows_all = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows_all:
        raise HTTPException(400, "빈 시트")

    def nrm(v):
        return "".join(str(v or "").strip().lower().split()).replace("\n", "")

    # 헤더행 탐지: 'assyp/n' 포함 행
    hi = -1
    for i in range(min(8, len(rows_all))):
        joined = [nrm(x) for x in rows_all[i]]
        if any("assyp/n" == c or "assyp/n" in c for c in joined):
            hi = i; break
    if hi < 0:
        raise HTTPException(400, "헤더행(Assy P/N) 감지 실패")
    hdr = [nrm(x) for x in rows_all[hi]]

    def find(*keys, after=None):
        start = (after + 1) if after is not None else 0
        for j in range(start, len(hdr)):
            if hdr[j] in keys:
                return j
        return None
    ci_assy = find("assyp/n")
    ci_assydesc = ci_assy + 1 if ci_assy is not None else None  # Assy 바로 뒤 Desc
    ci_coop = find("협력사")
    ci_sub = find("p/n(하위1)", "p/n하위1", "p/n(하위)", after=ci_coop)
    if ci_sub is None:
        ci_sub = find("p/n(하위1)", "p/n하위1")
    ci_subdesc = ci_sub + 1 if ci_sub is not None else None
    ci_qty = find("수량")
    ci_g1 = find("구분1")
    ci_g2 = find("구분2")
    ci_od = find("외경")
    ci_thk = find("t", "두께")
    ci_len = find("길이")
    ci_wt = find("중량")
    ci_mc = find("소재비변경후", "소재비")
    ci_upd = find("update일정", "update", "업데이트일정")
    if ci_assy is None or ci_g1 is None or ci_wt is None:
        return {"ok": False, "error": "필수컬럼(Assy P/N·구분1·중량) 감지 실패",
                "header": [str(x) for x in rows_all[hi]]}

    def gv(r, i):
        return r[i] if (i is not None and i < len(r)) else None
    def _f(r, i):
        v = gv(r, i)
        try:
            return float(str(v).replace(",", "")) if v not in (None, "") else 0.0
        except Exception:
            return 0.0

    recs = []
    for r in rows_all[hi + 1:]:
        assy = str(gv(r, ci_assy) or "").strip()
        if not assy or nrm(assy) in ("assyp/n", "합계", "total"):
            continue
        g1 = str(gv(r, ci_g1) or "").strip()
        if not g1:
            continue
        recs.append((ym.strip(), str(gv(r, ci_coop) or "")[:60], assy[:50],
                     str(gv(r, ci_assydesc) or "")[:200], str(gv(r, ci_sub) or "")[:50],
                     str(gv(r, ci_subdesc) or "")[:200], _f(r, ci_qty), g1[:10],
                     str(gv(r, ci_g2) or "")[:30], _f(r, ci_od), _f(r, ci_thk),
                     _f(r, ci_len), _f(r, ci_wt), _f(r, ci_mc), _upd_ym(gv(r, ci_upd))))
    if not recs:
        return {"ok": False, "error": "데이터 행 없음", "header": [str(x) for x in rows_all[hi]]}

    nx = _nx(); cur = nx.cursor()
    try:
        _settle_prep(cur)
        fn = (file.filename or "")[:200]
        # 재업로드=덮어쓰기: 같은 ym(+협력사)의 기존행 삭제. ym 없으면 파일명 기준.
        if ym.strip():
            coops = sorted({x[1] for x in recs if x[1]})
            cur.execute("DELETE FROM nx.lg_settle_unit WHERE ISNULL(ym,'')=?", ym.strip())
        else:
            cur.execute("DELETE FROM nx.lg_settle_unit WHERE src_file=?", fn)
        try: cur.fast_executemany = True
        except Exception: pass
        cols = "(ym,coop,assy_pn,assy_desc,sub_pn,sub_desc,qty,gubun1,gubun2,od,thk,leng,weight,mat_cost,eff_ym,src_file)"
        n = 0; BATCH = 120
        for i in range(0, len(recs), BATCH):
            chunk = recs[i:i + BATCH]
            vals = ",".join("(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)" for _ in chunk)
            flat = []
            for t in chunk:
                flat += list(t) + [fn]
            cur.execute(f"INSERT INTO nx.lg_settle_unit{cols} VALUES {vals}", *flat)
            n += len(chunk)
        nx.commit()
        cur.execute("""SELECT gubun1, COUNT(*), SUM(ISNULL(weight,0)) FROM nx.lg_settle_unit
                       WHERE src_file=? GROUP BY gubun1""", fn)
        by_g = [{"gubun1": r[0], "rows": r[1], "weight": float(r[2] or 0)} for r in cur.fetchall()]
        return {"ok": True, "file": fn, "sheet": ws.title, "ym": ym.strip(), "rows": n, "by_gubun1": by_g}
    finally:
        nx.close()


@router.get("/api/lgsagub/settle_summary")
def settle_summary():
    """업로드된 원단위 요약(기준월·협력사·구분1별)."""
    nx = _nx(); cur = nx.cursor()
    try:
        _settle_prep(cur)
        cur.execute("""SELECT ym, COUNT(DISTINCT assy_pn) assys, COUNT(*) rows,
              SUM(CASE WHEN gubun1=N'사급' THEN weight ELSE 0 END) sg_wt,
              SUM(CASE WHEN gubun1=N'직거래' THEN weight ELSE 0 END) jk_wt, MAX(upload_dt) dt
            FROM nx.lg_settle_unit GROUP BY ym ORDER BY ym""")
        by_ym = [{"ym": r[0], "assys": r[1], "rows": r[2], "sagub_wt": float(r[3] or 0),
                  "jikgae_wt": float(r[4] or 0), "dt": str(r[5])[:19]} for r in cur.fetchall()]
        return {"by_ym": by_ym}
    finally:
        nx.close()


@router.get("/api/lgsagub/recvcompare")
def recvcompare(ym: str = Query(""), ymd_from: str = Query(""), ymd_to: str = Query(""), settle_ym: str = Query(""), limit: int = Query(2000)):
    """리시빙 비교(원소재 동): 기간 LG리시빙 × 원단위(settle_ym) → OUT 동(사급/직거래) vs IN OSP.
       ★OUT = Σ 리시빙수량 × Σ(원단위 중량 by 구분1)  [중량=수량반영값이라 그대로 합산].
       사급=인정동(IN OSP원소재와 대사), 직거래=미인정. 기간(ymd_from~ymd_to) 우선, 없으면 월(ym)."""
    f = lambda v: float(v or 0)
    nx = _nx(); cur = nx.cursor()
    try:
        _settle_prep(cur)
        sy = settle_ym.strip()
        if not sy:
            cur.execute("SELECT MAX(ym) FROM nx.lg_settle_unit")
            r0 = cur.fetchone(); sy = (r0[0] if r0 else "") or ""
        rwh, rp, yms = _recv_where(ym, ymd_from, ymd_to)
        # 유효일자 컷오프 = 리시빙 최종월. 그 시점에 아직 추가 안 된 품목(eff_ym > M)은 소요 제외.
        eff_cut = (max(yms) if yms else (ym.strip() or sy))
        # 원단위 Assy별 사급/직거래 중량(1제품당) + 사급 소재비(원, 등급별 mat_cost 단가 반영)
        # 금액 = Σ(컴포넌트 중량 × 컴포넌트 단가). mat_cost=등급/코드별 동관 단가(원/kg): 일반18,458·고강도19,216 등.
        # ★eff_ym 필터: 빈값(기초행)·eff_ym ≤ 리시빙월만 = 그 시점 유효 스펙(누적 마스터 point-in-time).
        cur.execute("""SELECT UPPER(LTRIM(RTRIM(assy_pn))) a, gubun1, SUM(ISNULL(weight,0)) w,
                         SUM(ISNULL(weight,0)*ISNULL(mat_cost,0)) c
                       FROM nx.lg_settle_unit
                       WHERE ym=? AND (eff_ym IS NULL OR eff_ym='' OR eff_ym<=?)
                       GROUP BY UPPER(LTRIM(RTRIM(assy_pn))), gubun1""", sy, eff_cut)
        u_sg = {}; u_jk = {}; u_sg_c = {}
        for a, g1, w, c in cur.fetchall():
            g1 = (g1 or "").strip()
            if g1 == "사급": u_sg[a] = f(w); u_sg_c[a] = f(c)
            elif g1 == "직거래": u_jk[a] = f(w)
        cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it,
              SUM(CASE WHEN GUBUN='C' THEN CONVERT(float,ISNULL(RECV_QTY,0)) ELSE 0 END) qc,
              SUM(CASE WHEN GUBUN='R' THEN CONVERT(float,ISNULL(RECV_QTY,0)) ELSE 0 END) qr,
              SUM(CASE WHEN GUBUN='C' THEN ISNULL(RECV_AMT,0) ELSE 0 END) ac
            FROM nx.SA_T_LG_RECEIVING_DTL WHERE {rwh} GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))""", *rp)
        recv = [(r[0], f(r[1]), f(r[2]), f(r[3])) for r in cur.fetchall()]
        # 품명 매핑
        nm = {}
        cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), MAX(item_name) FROM nx.item GROUP BY UPPER(LTRIM(RTRIM(item_code)))")
        for a, b in cur.fetchall():
            nm[a] = b
        out = {"sg_c": 0.0, "sg_r": 0.0, "jk_c": 0.0, "jk_r": 0.0, "sga_c": 0.0, "sga_r": 0.0}
        items = []; matched_qc = 0.0; total_qc = 0.0; unmatched = 0
        for it, qc, qr, ac in recv:
            total_qc += qc
            sg = u_sg.get(it); jk = u_jk.get(it)
            has = (sg is not None) or (jk is not None)
            sg = sg or 0.0; jk = jk or 0.0
            sgc = u_sg_c.get(it, 0.0)          # 개당 사급 소재비(원, 등급별 단가 반영)
            if has:
                matched_qc += qc
            else:
                unmatched += 1
            out["sg_c"] += qc * sg; out["sg_r"] += qr * sg
            out["sga_c"] += qc * sgc; out["sga_r"] += qr * sgc
            out["jk_c"] += qc * jk; out["jk_r"] += qr * jk
            items.append({"item": it, "name": nm.get(it, ""), "recv_c": qc, "recv_r": qr,
                          "recv_amt": ac, "matched": 1 if has else 0,
                          "out_sagub": qc * sg, "out_jikgae": qc * jk,
                          "per_sagub": sg, "per_jikgae": jk, "per_sagub_amt": sgc})
        # IN OSP(사급입고) — 원소재/사급부품
        inl = ",".join("'" + y + "'" for y in yms) if yms else "''"
        cur.execute(f"""SELECT CASE WHEN UPPER(item_name) LIKE '%TUBE%' THEN N'원소재' ELSE N'사급부품' END cl,
              SUM(ISNULL(qty,0)) q, SUM(ISNULL(amt,0)) a FROM nx.lg_sagub_actual WHERE ym IN ({inl}) GROUP BY
              CASE WHEN UPPER(item_name) LIKE '%TUBE%' THEN N'원소재' ELSE N'사급부품' END""")
        osp = {r[0]: {"qty": f(r[1]), "amt": f(r[2])} for r in cur.fetchall()}
        in_raw = osp.get("원소재", {"qty": 0, "amt": 0})
        # OSP 원소재 평균단가(참고). 실제 OUT 금액은 원단위 등급별 단가(mat_cost)로 계산.
        price = (in_raw["amt"] / in_raw["qty"]) if in_raw["qty"] else 0.0
        out_sagub_net = out["sg_c"] - out["sg_r"]
        out_sagub_net_amt = out["sga_c"] - out["sga_r"]      # 등급별 단가 반영(정확)
        eff_price = (out_sagub_net_amt / out_sagub_net) if out_sagub_net else 0.0
        items.sort(key=lambda x: -(x["out_sagub"] + x["out_jikgae"]))
        return {
            "ym": ym.strip(), "settle_ym": sy,
            "copper": {
                "out_sagub_c": out["sg_c"], "out_sagub_r": out["sg_r"], "out_sagub_net": out_sagub_net,
                "out_jikgae_c": out["jk_c"], "out_jikgae_r": out["jk_r"], "out_jikgae_net": out["jk_c"] - out["jk_r"],
                "in_osp_kg": in_raw["qty"], "in_osp_amt": in_raw["amt"], "osp_price": price,
                "out_sagub_net_amt": out_sagub_net_amt, "eff_price": eff_price,
            },
            "parts_in": osp.get("사급부품", {"qty": 0, "amt": 0}),
            "coverage": {"matched_qty": matched_qc, "total_qty": total_qc, "unmatched_items": unmatched,
                         "rate": (matched_qc / total_qc * 100) if total_qc else 0},
            "items": items[:int(limit)],
        }
    finally:
        nx.close()


@router.get("/api/lgsagub/recvcompare_ledger")
def recvcompare_ledger(from_ym: str = Query(""), to_ym: str = Query(""), settle_ym: str = Query("")):
    """동 원소재 수불(월별 누적): 기초 + 입고(OSP TUBE) − 소요(리시빙×원단위 eff≤월) = 기말.
       from_ym(기초0 시작월, 미지정=OSP 첫 입고월)~to_ym(미지정=OSP 최신월). eff_ym로 각 월 point-in-time 원단위.
       ★기초=0 가정: 시작월 이전 동재고 없음. OSP 데이터 없는 달로 시작하면 입고0→마이너스 되므로 첫 OSP월 권장."""
    f = lambda v: float(v or 0)
    nx = _nx(); cur = nx.cursor()
    try:
        _settle_prep(cur)
        sy = settle_ym.strip()
        if not sy:
            cur.execute("SELECT MAX(ym) FROM nx.lg_settle_unit")
            r0 = cur.fetchone(); sy = (r0[0] if r0 else "") or ""
        # ★수불 개시월 = 2603(2026.03) 사용자 확정. 그 이전 OSP 데이터 없어 기초0 시작. to_ym 기본 = OSP 최신월.
        cur.execute("SELECT MIN(ym), MAX(ym) FROM nx.lg_sagub_actual WHERE UPPER(item_name) LIKE '%TUBE%'")
        r0 = cur.fetchone(); osp_min = (r0[0] if r0 and r0[0] else "") or ""; osp_max = (r0[1] if r0 and r0[1] else "") or ""
        LEDGER_START = "2602"
        frm = from_ym.strip() or LEDGER_START
        if osp_min and frm < osp_min:    # OSP 데이터 없는 이전달로 시작하면 입고0→마이너스 → 첫 OSP월로 클램프
            frm = osp_min
        to = to_ym.strip() or osp_max or frm

        def ym_next(y):
            yy = int(y[:2]); mm = int(y[2:]) + 1
            if mm > 12: mm = 1; yy += 1
            return f"{yy:02d}{mm:02d}"
        months = []; m = frm; guard = 0
        while m <= to and guard < 120:
            months.append(m); m = ym_next(m); guard += 1

        rows = []; bal_kg = 0.0; bal_amt = 0.0
        for M in months:
            cur.execute("""SELECT UPPER(LTRIM(RTRIM(assy_pn))) a, SUM(ISNULL(weight,0)) w,
                             SUM(ISNULL(weight,0)*ISNULL(mat_cost,0)) c
                           FROM nx.lg_settle_unit
                           WHERE ym=? AND gubun1=N'사급' AND (eff_ym IS NULL OR eff_ym='' OR eff_ym<=?)
                           GROUP BY UPPER(LTRIM(RTRIM(assy_pn)))""", sy, M)
            usg = {}; usc = {}
            for a, w, c in cur.fetchall():
                usg[a] = f(w); usc[a] = f(c)
            cur.execute("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it,
                  SUM(CASE WHEN GUBUN='C' THEN CONVERT(float,ISNULL(RECV_QTY,0)) ELSE 0 END)
                 -SUM(CASE WHEN GUBUN='R' THEN CONVERT(float,ISNULL(RECV_QTY,0)) ELSE 0 END) net
                FROM nx.SA_T_LG_RECEIVING_DTL WHERE LEFT(RECEIVING_YMD,4)=?
                GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))""", M)
            soyo_kg = 0.0; soyo_amt = 0.0
            for it, net in cur.fetchall():
                net = f(net)
                soyo_kg += usg.get(it, 0.0) * net
                soyo_amt += usc.get(it, 0.0) * net
            cur.execute("""SELECT SUM(ISNULL(qty,0)), SUM(ISNULL(amt,0)) FROM nx.lg_sagub_actual
                           WHERE ym=? AND UPPER(item_name) LIKE '%TUBE%'""", M)
            r = cur.fetchone(); in_kg = f(r[0]); in_amt = f(r[1])
            open_kg = bal_kg; open_amt = bal_amt
            bal_kg = open_kg + in_kg - soyo_kg
            bal_amt = open_amt + in_amt - soyo_amt
            rows.append({"ym": M, "open_kg": open_kg, "open_amt": open_amt,
                         "in_kg": in_kg, "in_amt": in_amt, "soyo_kg": soyo_kg, "soyo_amt": soyo_amt,
                         "close_kg": bal_kg, "close_amt": bal_amt})
        return {"settle_ym": sy, "from_ym": frm, "to_ym": to, "osp_min": osp_min, "rows": rows}
    finally:
        nx.close()


# ── 사급부품(소분류310) BOM 전개 캐시 ──
_PARTS_MAPS = None
def _parts_maps(cur):
    """CS_M_ITEM_BOM 부모→자식 맵 + 사급부품(SGROUP 310) 집합. 모듈캐시(1회 로드).
       ★CS_CALC_EXCEPT_FLAG<>'1' 필터 유지: 이 플래그는 변형SUB 이중계상 방지용.
         예) AJR30077403은 MJX65072203을 (a)직접행(except='1') + (b)-F&T 변형서브 안 = 2경로로 가짐.
         except 필터가 (a)를 걸러 1회만 계상. 제거하면 2배 이중계상됨(실측 확인)."""
    global _PARTS_MAPS
    if _PARTS_MAPS is not None:
        return _PARTS_MAPS
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(MAT_CODE))), ISNULL(USE_QTY,0)
                   FROM nx.CS_M_ITEM_BOM WHERE ISNULL(CS_CALC_EXCEPT_FLAG,'0')<>'1'""")
    ch = {}
    for p, c2, q in cur.fetchall():
        ch.setdefault(p, []).append((c2, float(q or 0)))
    cur.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) FROM nx.item WHERE LTRIM(RTRIM(sgroup))='310'")
    sg310 = set(r[0] for r in cur.fetchall())
    _PARTS_MAPS = (ch, sg310)
    return _PARTS_MAPS

def _explode_parts(item, ch, sg310, memo):
    """1개 완제품 → {사급부품(310): 소요개수}. 310 도달시 계상 후 정지(LG가 완성제공)."""
    if item in memo:
        return memo[item]
    memo[item] = {}
    acc = {}
    for c2, q in ch.get(item, []):
        if q <= 0:
            continue
        if c2 in sg310:
            acc[c2] = acc.get(c2, 0.0) + q
        else:
            for k, v in _explode_parts(c2, ch, sg310, memo).items():
                acc[k] = acc.get(k, 0.0) + v * q
    memo[item] = acc
    return acc


@router.get("/api/lgsagub/settle_list")
def settle_list(ym: str = Query(""), q: str = Query(""), gubun1: str = Query(""), limit: int = Query(20000)):
    """원단위 관리 목록: 적용월(ym)의 (Assy×하위동부자재) 행 조회 + 월목록(드롭다운용)."""
    f = lambda v: float(v or 0)
    nx = _nx(); cur = nx.cursor()
    try:
        _settle_prep(cur)
        cur.execute("SELECT ym, COUNT(*) FROM nx.lg_settle_unit GROUP BY ym ORDER BY ym DESC")
        yms = [{"ym": r[0], "rows": r[1]} for r in cur.fetchall()]
        if not ym.strip() and yms:
            ym = yms[0]["ym"]
        wh = ["ym=?"]; p = [ym.strip()]
        if gubun1.strip():
            wh.append("gubun1=?"); p.append(gubun1.strip())
        if q.strip():
            wh.append("(assy_pn LIKE ? OR sub_pn LIKE ? OR assy_desc LIKE ? OR sub_desc LIKE ?)")
            p += [f"%{q.strip()}%"] * 4
        cur.execute(f"""SELECT TOP {int(limit)} assy_pn, assy_desc, coop, sub_pn, sub_desc, qty,
              gubun1, gubun2, od, thk, leng, weight
            FROM nx.lg_settle_unit WHERE {' AND '.join(wh)}
            ORDER BY assy_pn, sub_pn""", *p)
        rows = [{"assy_pn": r[0], "assy_desc": r[1], "coop": r[2], "sub_pn": r[3], "sub_desc": r[4],
                 "qty": f(r[5]), "gubun1": r[6], "gubun2": r[7], "od": f(r[8]), "thk": f(r[9]),
                 "leng": f(r[10]), "weight": f(r[11])} for r in cur.fetchall()]
        return {"ym": ym.strip(), "yms": yms, "rows": rows, "cnt": len(rows)}
    finally:
        nx.close()


@router.post("/api/lgsagub/settle_copy")
def settle_copy(from_ym: str = Query(...), to_ym: str = Query(...)):
    """전월 복사로 신규월: from_ym 원단위를 to_ym로 복제(기존 to_ym 삭제 후). 상대적 불변이라 복사후 부분수정용."""
    nx = _nx(); cur = nx.cursor()
    try:
        _settle_prep(cur)
        cur.execute("DELETE FROM nx.lg_settle_unit WHERE ym=?", to_ym.strip())
        cur.execute("""INSERT INTO nx.lg_settle_unit
              (ym,coop,assy_pn,assy_desc,sub_pn,sub_desc,qty,gubun1,gubun2,od,thk,leng,weight,mat_cost,src_file)
            SELECT ?, coop,assy_pn,assy_desc,sub_pn,sub_desc,qty,gubun1,gubun2,od,thk,leng,weight,mat_cost,
              N'copy<'+ym+N'>' FROM nx.lg_settle_unit WHERE ym=?""", to_ym.strip(), from_ym.strip())
        n = cur.rowcount
        nx.commit()
        return {"ok": True, "from_ym": from_ym.strip(), "to_ym": to_ym.strip(), "rows": n}
    finally:
        nx.close()


def _ym_list(a, b):
    """YYMMDD 범위 → 걸치는 YYMM 리스트. 둘 다 없으면 []."""
    if not a and not b:
        return []
    a = a or b; b = b or a
    try:
        ya, ma = int(a[:2]), int(a[2:4]); yb, mb = int(b[:2]), int(b[2:4])
    except Exception:
        return []
    out = []; y, m = ya, ma
    while (y, m) <= (yb, mb) and len(out) < 60:
        out.append(f"{y:02d}{m:02d}")
        m += 1
        if m > 12: m = 1; y += 1
    return out

def _recv_where(ym, ymd_from, ymd_to):
    """리시빙 필터: 기간(ymd_from~ymd_to YYMMDD) 우선, 없으면 월(ym=YYMM=LEFT4). (where, params, yms)."""
    if ymd_from.strip() or ymd_to.strip():
        return ("RECEIVING_YMD>=? AND RECEIVING_YMD<=?",
                [ymd_from.strip() or "000000", ymd_to.strip() or "999999"],
                _ym_list(ymd_from.strip(), ymd_to.strip()))
    return ("LEFT(RECEIVING_YMD,4)=?", [ym.strip()], [ym.strip()] if ym.strip() else [])


@router.get("/api/lgsagub/recvcompare_parts")
def recvcompare_parts(ym: str = Query(""), ymd_from: str = Query(""), ymd_to: str = Query(""), limit: int = Query(3000)):
    """리시빙 비교(부품): 기간 리시빙 × BOM 사급부품(310) 소요개수 = OUT vs OSP 사급부품입고 IN.
       ★부품=개수 단위. 소비=C(정상)만(R은 반품 아님→차감안함). BOM=CS_M_ITEM_BOM 전체(원가제외필터 미적용).
       기간(ymd_from~ymd_to) 우선, 없으면 월(ym)."""
    f = lambda v: float(v or 0)
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur)
        ch, sg310 = _parts_maps(cur)
        rwh, rp, yms = _recv_where(ym, ymd_from, ymd_to)
        # ② IN OSP 사급부품 (lg_sagub, 품명 TUBE 아님) — 기간내 월합. ★이 OSP 목록 자체가 '사급부품 정의' = 전개 정지점.
        inl = ",".join("'" + y + "'" for y in yms) if yms else "''"
        cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(item_code))) it, MAX(item_name) nm,
              SUM(ISNULL(qty,0)) q, SUM(ISNULL(amt,0)) a,
              SUM(ISNULL(amt,0))/NULLIF(SUM(ISNULL(qty,0)),0) p
            FROM nx.lg_sagub_actual WHERE ym IN ({inl}) AND UPPER(item_name) NOT LIKE '%TUBE%'
            GROUP BY UPPER(LTRIM(RTRIM(item_code)))""")
        in_map = {r[0]: {"nm": r[1], "q": f(r[2]), "a": f(r[3]), "p": f(r[4])} for r in cur.fetchall()}
        # ★전개 정지=OSP 목록(SGROUP=310 아님). 310으로만 멈추면 MAZ30083301(sg230, 구매단가)처럼
        #   310 아닌 사급부품을 통째로 놓침. OSP에 있는 부품이면 어디서든 정지·계상.
        osp_set = set(in_map)
        # ③ 리시빙 → 사급부품 소요개수 (C+R 전부. R은 반품 아니라 정상 리시빙 다른 구분)
        cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it,
              SUM(CASE WHEN GUBUN='C' THEN CONVERT(float,ISNULL(RECV_QTY,0)) ELSE 0 END) qc,
              SUM(CASE WHEN GUBUN='R' THEN CONVERT(float,ISNULL(RECV_QTY,0)) ELSE 0 END) qr
            FROM nx.SA_T_LG_RECEIVING_DTL WHERE {rwh} GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))""", *rp)
        recv = [(r[0], f(r[1]), f(r[2])) for r in cur.fetchall()]
        memo = {}
        out_c = {}; out_r = {}   # 사급부품별 OUT 소요개수
        for it, qc, qr in recv:
            pmap = _explode_parts(it, ch, osp_set, memo)   # ★정지=OSP
            for part, per in pmap.items():
                out_c[part] = out_c.get(part, 0.0) + qc * per
                out_r[part] = out_r.get(part, 0.0) + qr * per
        # ★① 우리 ERP 확정입고(입고기준): 확정입고집계표와 동일 원천 = PU_T_STOCK_MAINT(9/S/C/G/H 검사통과)+_C(수입 DIVISION=P). MAT_CODE별 기간합.
        #   ★2026-08-21 수정: 라이브 dbo 직독. 웹 자재입고관리(stock.py)가 nx.PU_T_STOCK_MAINT(미러 테이블)에 직접 등록 →
        #   레거시 미러분과 이중계상(EBD64385805 300→600). 라이브 원본이 확정입고 정본이므로 nx 대신 라이브 읽음.
        erp_map = {}
        if yms:
            cn2 = _conn(); cur2 = cn2.cursor()
            try:
                cur2.execute(f"""SELECT UPPER(LTRIM(RTRIM(mat))) it, SUM(qty) q FROM (
                      SELECT MAT_CODE mat, CONVERT(float,ISNULL(MAINT_QTY,0)) qty FROM dbo.PU_T_STOCK_MAINT
                        WHERE LEFT(MAINT_YMD,4) IN ({inl}) AND MAINT_TAG IN ('9','S','C','G','H')
                          AND ((ISNULL(INSP_FLAG,'N') IN ('','N')) OR (ISNULL(INSP_FLAG,'N') IN ('S','F') AND INSP_PROC_YMD >= ''))
                      UNION ALL
                      SELECT MAT_CODE, CONVERT(float,ISNULL(MAINT_QTY,0)) FROM dbo.PU_T_STOCK_MAINT_C
                        WHERE LEFT(MAINT_YMD,4) IN ({inl}) AND DIVISION='P'
                    ) t GROUP BY UPPER(LTRIM(RTRIM(mat)))""")
                for r in cur2.fetchall():
                    erp_map[r[0]] = f(r[1])
            finally:
                cn2.close()
        # ★OSP에 나오는 부품(=LG 사급 목록)만 대상. 품명은 OSP(in_map)에 이미 있음(nx.item 전체조회 제거=속도).
        parts = set(in_map)
        items = []
        tot_out = tot_in_q = tot_in_a = tot_erp = 0.0
        for p in parts:
            # ★소비 = C+R 전부. GUBUN='R'은 반품이 아니라 정상 리시빙의 다른 구분(R전용 제품 다수)이라
            #   C만 세면 그 제품들의 부품이 통째로 0이 됨(EAP65270720 등). C+R로 ③/②=0.72→0.97 검증.
            oc = out_c.get(p, 0.0) + out_r.get(p, 0.0)
            ind = in_map.get(p, {})
            iq = ind.get("q", 0.0); ia = ind.get("a", 0.0); price = ind.get("p", 0.0)
            ei = erp_map.get(p, 0.0)   # ① 우리 ERP 확정입고
            tot_out += oc; tot_in_q += iq; tot_in_a += ia; tot_erp += ei
            # ★3-way: ①우리ERP입고(erp_in) vs ②LG OSP(in_qty) vs ③LG리시빙소비(out_net=C+R).
            #   ①≈② 정상(둘 다 공급)·③≈② 정상(넓은 기간)·diff_erp=②−①(기록불일치)·diff=②−③(선입고).
            items.append({"item": p, "name": ind.get("nm") or "",
                          "erp_in": ei, "out_net": oc,
                          "in_qty": iq, "in_amt": ia, "price": price,
                          "diff": iq - oc, "diff_erp": iq - ei})
        items.sort(key=lambda x: -(x["in_qty"] + x["erp_in"] + abs(x["out_net"])))
        return {
            "ym": ym.strip(),
            "summary": {"erp_in": tot_erp, "out_net": tot_out,
                        "in_qty": tot_in_q, "in_amt": tot_in_a, "parts": len(parts)},
            "items": items[:int(limit)],
        }
    finally:
        nx.close()
