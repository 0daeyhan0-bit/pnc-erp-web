# -*- coding: utf-8 -*-
"""영업계획현황(w_pr_plan_050) — SA_T_PLAN_DTL 기반 일별 크로스탭. 레거시 dw_pr_plan_050_t1 SQL 그대로 실행.
   구분: 1=상세(원행) · 2=집계(연속 line·output_hm·work_order 병합+일별 overwrite+도번 concat) · 3=도번집계.
   ★집계 알고리즘은 레거시 srw 379~412 PowerScript 후처리 충실이식(검증: 2607/260814 7일 = 2,028행·일별합계 완전일치).
   조회 우선(라이브 PARTNER_ERP RO). 필터 오토컴플리트는 프론트."""
import os, datetime, time
from fastapi import APIRouter, Query, HTTPException
from common import _conn

router = APIRouter()
with open(os.path.join(os.path.dirname(__file__), 'sql_plan050.txt'), encoding='utf-8') as _f:
    _BASE_SQL = _f.read()

# ★raw SQL 결과 캐시(동일 기준일·일수·필터 30초 재사용) — 레거시 SQL이 무거워(상관서브쿼리) 반복조회 가속. 합계 불변.
_CACHE = {}
_TTL = 120.0   # 계획은 자주 바뀌지 않는다(일 단위 업로드) — 재조회·구분전환을 가볍게
def _cache_get(k):
    v = _CACHE.get(k)
    if v and (time.time() - v[0]) < _TTL: return v[1]
    return None
def _cache_put(k, raw):
    _CACHE[k] = (time.time(), raw)
    if len(_CACHE) > 40:   # 상한(메모리)
        for old in sorted(_CACHE, key=lambda x: _CACHE[x][0])[:20]: _CACHE.pop(old, None)

def _d6(s): return ''.join(ch for ch in str(s or '') if ch.isdigit())[:6]
def _like(s):
    s = str(s or '').strip()
    if not s or s in ('%', '전체', 'XX 전체'): return '%'
    return s.replace("'", "''").replace(";", "")   # 인젝션 방지(내부 RO지만 방어)
def _rel(ymd, n):
    d = datetime.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6])) + datetime.timedelta(days=n)
    return d.strftime('%y%m%d')
def _label(ymd):
    d = datetime.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    return ymd[4:6] + '월화수목금토일'[d.weekday()]

@router.get("/api/salesplan")
def salesplan(from_ymd: str = Query(...), days: int = Query(7), gubun: str = Query("2"),
              cust: str = Query(""), line: str = Query(""), model: str = Query(""),
              wo: str = Query(""), item: str = Query("")):
    fr = _d6(from_ymd)
    if len(fr) != 6: raise HTTPException(400, "기준일자(YYMMDD) 필요")
    days = max(1, min(int(days or 7), 31))
    to = _rel(fr, days - 1)
    sub = {':as_from_ymd': "'%s'" % fr, ':as_to_ymd': "'%s'" % to,
           ':as_cust_code': "'%s'" % _like(cust), ':as_line_no': "'%s'" % _like(line),
           ':as_model_no': "'%s'" % _like(model), ':as_work_order': "'%s'" % _like(wo),
           ':as_item_code': "'%s'" % _like(item)}
    # ★조회부(raw+line_nm) 캐시 — gubun은 캐시키 제외(같은 필터서 구분전환 즉시). 캐시 히트시 복사본으로 gubun 처리(원본보존).
    ckey = (fr, days, _like(cust), _like(line), _like(model), _like(wo), _like(item))
    cached = _cache_get(ckey)
    if cached is not None:
        rows = [dict(x, d=x["d"][:]) for x in cached]   # 깊은복사(gubun 변형 방지)
    else:
        sql = _BASE_SQL
        for k, v in sub.items(): sql = sql.replace(k, v)
        # ★성능(2026-08-21 실측): 바깥에서 컬럼을 명시하고 ISNULL 로 감싸면 SQL Server 가
        #   실행계획을 다시 짜면서 3.4초가 걸린다. SELECT * 로 그대로 받으면 0.6초.
        #   (같은 결과, 5배 차이) → NULL 처리·정렬은 파이썬에서 한다.
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("SELECT * FROM (" + sql + ") q")
            cols = [d[0].lower() for d in cur.description]
            raw = cur.fetchall()
        finally:
            cn.close()
        ix = {c: i for i, c in enumerate(cols)}
        def g(r, name, dflt=''):
            i = ix.get(name)
            return dflt if i is None or r[i] is None else r[i]
        dpos = [ix.get("plan_qty_%02d" % i) for i in range(1, days + 1)]
        def mk(r):
            return {"line": str(g(r, "line_no")).strip(), "ymd": str(g(r, "plan_ymd")).strip(),
                    "ohm": str(g(r, "output_hm")).strip(), "wo": str(g(r, "work_order")).strip(),
                    "model": str(g(r, "model_no")).strip(), "tool": str(g(r, "tools_desc")).strip(),
                    "item": str(g(r, "c_item_code")).strip(), "wc": str(g(r, "work_center")).strip(),
                    "lot": float(g(r, "lot_qty", 0) or 0), "rate": float(g(r, "prod_rate", 0) or 0),
                    "remarks": str(g(r, "remarks2")).strip(),
                    "d": [float(r[p] or 0) if p is not None else 0.0 for p in dpos]}
        rows = [mk(r) for r in raw]
        # 정렬도 파이썬에서(SQL ORDER BY 를 붙이면 위 실행계획 문제가 재현될 수 있다)
        rows.sort(key=lambda x: (x["line"], x["ymd"], x["ohm"], x["wo"], x["item"]))
        lnm = {}
        try:
            cn2 = _conn(); c2 = cn2.cursor()
            try:
                c2.execute("SELECT DETAIL_CODE, ISNULL(DETAIL_DESC,'') FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WHERE KIND_CODE='PR003'")   # 분리: 레거시dbo→nx미러(데이터동일 검증)
                for a, b in c2.fetchall(): lnm[str(a).strip()] = str(b).strip()
            finally: cn2.close()
        except Exception: pass
        for x in rows: x["line_nm"] = lnm.get(x["line"], "")
        _cache_put(ckey, [dict(x, d=x["d"][:]) for x in rows])   # 원본 복사본 저장

    if gubun == "2":       # 집계 (레거시 379~412)
        out = []
        for x in rows:
            p = out[-1] if out else None
            if p and p["line"] == x["line"] and p["ohm"] == x["ohm"] and p["wo"] == x["wo"]:
                for i in range(days):
                    if x["d"][i] > 0: p["d"][i] = x["d"][i]     # overwrite(비-0)
                if x["item"] and x["item"] not in p["item"]:
                    p["item"] = (p["item"] + " " + x["item"]).strip(); p["wc"] = ""; p["rate"] = 0
            else:
                out.append(x)
        rows = out
    elif gubun == "3":     # 도번집계 (도번별 합산)
        agg = {}
        for x in rows:
            k = x["item"]
            a = agg.get(k)
            if not a:
                a = agg[k] = {"line": x["line"], "ohm": "", "wo": "", "model": "", "tool": "",
                              "item": k, "wc": x["wc"], "lot": 0.0, "rate": 0.0, "remarks": "", "d": [0.0] * days}
            for i in range(days): a["d"][i] += x["d"][i]
            a["lot"] += x["lot"]
        rows = list(agg.values())

    for x in rows: x["total"] = sum(x["d"])
    tot = {"cnt": len(rows), "lot": sum(x["lot"] for x in rows), "total": sum(x["total"] for x in rows),
           "d": [sum(x["d"][i] for x in rows) for i in range(days)]}
    labels = [_label(_rel(fr, i)) for i in range(days)]
    return {"from": fr, "to": to, "days": days, "labels": labels, "gubun": gubun, "rows": rows, "tot": tot}


# ===================== 드롭다운 목록 (라인 / 작업처) =====================
# 레거시 w_pr_plan_050 상단 콤보 재현.
#   라인   = 계획에 실제 쓰인 LINE_NO(코드만, 예 C1/CA/CC…) + 마스터 PR003(코드+이름, 예 AA 설치)
#            → 스크린샷 순서와 동일(사용코드 먼저, 이어서 마스터코드)
#   작업처 = 계획 품목의 work_center(사내공정명 또는 사급거래처명) 실측 목록
_OPT_CACHE = {"t": 0.0, "v": None}

@router.get("/api/salesplan/opts")
def salesplan_opts():
    """상단 필터 드롭다운 목록. 5분 캐시."""
    now = time.time()
    if _OPT_CACHE["v"] is not None and (now - _OPT_CACHE["t"]) < 300:
        return _OPT_CACHE["v"]
    lines = []
    cn = _conn(); cur = cn.cursor()
    try:
        # ① 계획에 실제 쓰인 라인코드(최근 3개월)
        cur.execute("""SELECT DISTINCT LINE_NO FROM PARTNER_ERP.dbo.SA_T_PLAN_DTL WITH(NOLOCK)
                        WHERE ISNULL(LINE_NO,'')<>''
                          AND PLAN_YMD >= CONVERT(varchar(6),DATEADD(month,-3,getdate()),12)
                        ORDER BY LINE_NO""")
        used = [str(r[0]).strip() for r in cur.fetchall() if r[0]]
        seen = set(used)
        lines = [{"code": u, "nm": ""} for u in used]
        # ② 마스터 PR003(코드+이름) — 위에 없는 것만 이어붙임
        cur.execute("""SELECT DETAIL_CODE, ISNULL(DETAIL_DESC,'')
                         FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL
                        WHERE KIND_CODE='PR003' ORDER BY DETAIL_CODE""")
        for a, b in cur.fetchall():
            code = str(a).strip()
            if code and code not in seen:
                seen.add(code)
                lines.append({"code": code, "nm": str(b).strip()})
        # ※작업처는 드롭다운을 만들지 않는다 — work_center_code 체계가 정리돼 있지 않아
        #   (사내공정코드와 사급거래처코드가 섞임) 목록이 무의미하다. 화면에서 검색(부분일치)으로 처리.
    except Exception as e:
        return {"lines": lines, "err": str(e)[:200]}
    finally:
        cn.close()
    v = {"lines": lines}
    _OPT_CACHE["t"] = now; _OPT_CACHE["v"] = v
    return v
