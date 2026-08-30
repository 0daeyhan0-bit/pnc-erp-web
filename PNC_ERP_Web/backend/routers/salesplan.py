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
              wo: str = Query(""), item: str = Query(""), src: str = Query("nx")):
    # ★src: nx(기본)=웹 DB / live=레거시 라이브(대조용)
    _live = str(src or "").strip().lower() == "live"
    fr = _d6(from_ymd)
    if len(fr) != 6: raise HTTPException(400, "기준일자(YYMMDD) 필요")
    days = max(1, min(int(days or 7), 31))
    to = _rel(fr, days - 1)
    sub = {':as_from_ymd': "'%s'" % fr, ':as_to_ymd': "'%s'" % to,
           ':as_cust_code': "'%s'" % _like(cust), ':as_line_no': "'%s'" % _like(line),
           ':as_model_no': "'%s'" % _like(model), ':as_work_order': "'%s'" % _like(wo),
           ':as_item_code': "'%s'" % _like(item)}
    # ★조회부(raw+line_nm) 캐시 — gubun은 캐시키 제외(같은 필터서 구분전환 즉시). 캐시 히트시 복사본으로 gubun 처리(원본보존).
    ckey = (fr, days, _like(cust), _like(line), _like(model), _like(wo), _like(item), _live)
    cached = _cache_get(ckey)
    if cached is not None:
        rows = [dict(x, d=x["d"][:]) for x in cached]   # 깊은복사(gubun 변형 방지)
    else:
        sql = _BASE_SQL
        for k, v in sub.items(): sql = sql.replace(k, v)
        # ★원천 전환(2026-08-28): 기본 = **웹(nx)**. 레거시 대조용으로 src=live 를 남긴다.
        #   sql_plan050.txt 는 스키마 없이 테이블명만 써서 접속 DB 를 그대로 따른다.
        #   → nx 모드에서는 각 테이블 앞에 PARTNER_ERP_TEST3.nx. 를 붙인다.
        #   ※nx.PR_V_MODEL_BOM 은 라이브 뷰가 WITH ENCRYPTION 이라 복제 불가 →
        #     같은 컬럼셋으로 nx 에 새로 만들었다(PR_M_MODEL_BOM 기반, 62,897행 일치).
        if not _live:
            import re as _re
            for _t in ("sa_t_plan_dtl", "sa_t_plan_item_dtl", "pr_t_plan_input",
                       "pr_v_model_bom", "pr_m_item", "pr_m_work", "cm_m_cust",
                       "PR_M_ITEM_PROC_GAGONG", "PR_M_PROC_GAGONG"):
                sql = _re.sub(r"(?i)(?<![\w\.\[])" + _t + r"(?![\w\]])",
                              "PARTNER_ERP_TEST3.nx." + _t, sql)
        # ★성능(2026-08-21 실측): 바깥에서 컬럼을 명시하고 ISNULL 로 감싸면 SQL Server 가
        #   실행계획을 다시 짜면서 3.4초가 걸린다. SELECT * 로 그대로 받으면 0.6초.
        #   (같은 결과, 5배 차이) → NULL 처리·정렬은 파이썬에서 한다.
        # ★긴 기간(15일↑)은 바깥 GROUP BY 가 급격히 느려진다(실측 31일 = 13.4초).
        #   내부 UNION 원행만 받아 파이썬에서 집계하면 2.2초. 짧은 기간은 SQL 집계가 더 빠르므로
        #   기간에 따라 갈라 쓴다(결과는 전수대조로 동일 확인 — 10,791그룹·합계 일치).
        heavy = days >= 15
        if heavy:
            _i = sql.rfind("group by"); _in = sql[:_i]; _j = _in.find("from (")
            q = "SELECT * FROM (" + _in[_j + 6:_in.rfind(") t")] + ") x"
        else:
            q = "SELECT * FROM (" + sql + ") q"
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute(q)
            cols = [d[0].lower() for d in cur.description]
            raw = cur.fetchall()
        finally:
            cn.close()
        ix = {c: i for i, c in enumerate(cols)}
        def g(r, name, dflt=''):
            i = ix.get(name)
            return dflt if i is None or r[i] is None else r[i]

        if heavy:
            # 레거시 바깥 GROUP BY 재현:
            #   키   = work_order, line_no, output_hm, c_item_code+sina_flag
            #   집계 = min(plan_ymd) / max(그 외 표시항목) / sum(plan_qty)
            #   일자 = plan_ymd 로 버킷팅(레거시의 CASE 31개와 동치)
            dpos_ymd = {_rel(fr, i): i for i in range(days)}
            acc = {}
            for r in raw:
                item = (str(g(r, "c_item_code")) + str(g(r, "sina_flag"))).strip()
                k = (str(g(r, "work_order")).strip(), str(g(r, "line_no")).strip(),
                     str(g(r, "output_hm")).strip(), item)
                o = acc.get(k)
                if not o:
                    o = acc[k] = {"line": k[1], "ymd": None, "ohm": k[2], "wo": k[0],
                                  "model": "", "tool": "", "item": item, "wc": "",
                                  "lot": 0.0, "rate": 0.0, "remarks": "", "d": [0.0] * days}
                y = str(g(r, "plan_ymd")).strip()
                if o["ymd"] is None or y < o["ymd"]: o["ymd"] = y
                qv = float(g(r, "plan_qty", 0) or 0)
                p = dpos_ymd.get(y)
                if p is not None: o["d"][p] += qv
                o["lot"] = max(o["lot"], float(g(r, "lot_qty", 0) or 0))
                o["rate"] = max(o["rate"], float(g(r, "prod_rate", 0) or 0))
                for fld, col in (("model", "model_no"), ("tool", "tools_desc"),
                                 ("wc", "work_center"), ("remarks", "remarks2")):
                    v = str(g(r, col)).strip()
                    if v > o[fld]: o[fld] = v          # max() 재현
            rows = list(acc.values())
            for x in rows:
                if x["ymd"] is None: x["ymd"] = ""
        else:
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
    elif gubun == "3":     # 도번집계 — 레거시 dw_pr_plan_050_t3 규칙
        # ★t1/t2 와 다른 점(2026-08-21 실측 대조):
        #   ① t3 는 c_item_code 에 use_qty 접미 '(n)' 을 붙이지 않는다
        #      → t1 의 'AJR30071101(2)' 는 t3 에선 'AJR30071101' 로 합쳐진다
        #   ② t3 는 join pr_m_item m on t.c_item_code=m.item_code
        #      → 품목마스터에 없는 도번(빈값·'(모델BOM확인)' 표기 등)은 제외된다
        #   ③ lot_qty 는 max (t1 의 합산이 아님)
        #   ④ 표시는 'c_item_code + sina_flag'(예 'AJJ30041801(신규)')지만
        #      pr_m_item 조인은 순수 c_item_code 로 한다. '(신규)' 같은 sina_flag 를
        #      접미로 오인해 떼면 안 되고, 마스터 조회시엔 반대로 떼야 한다.
        import re as _re
        _SFX = _re.compile(r"\(\d+\)$")            # use_qty 접미 '(2)' — t3 는 붙이지 않음
        #   ⑤ 레거시 t3 는 join 을 'c_item_code + (t2가 덧붙인 문자열)' 그대로 수행한다.
        #      → '(모델BOM확인)' 이 붙은 도번은 마스터와 매칭되지 않아 제외된다(레거시 실동작).
        #        반면 sina_flag '(신규)' 는 join 뒤에 표시용으로 붙으므로 떼고 조인해야 한다.
        _SINA = _re.compile(r"\((?!\d+\)$)(?!모델BOM확인\)$)[^()]*\)$")
        base = {}
        for x in rows:
            disp = _SFX.sub("", x["item"] or "").strip()   # ① use_qty 접미만 제거
            if not disp:
                continue
            code = _SINA.sub("", disp).strip()             # 마스터 조인용 순수 도번
            a = base.get(disp)
            if not a:
                a = base[disp] = {"line": x["line"], "ohm": "", "wo": "", "model": "", "tool": "",
                                  "item": disp, "_code": code, "wc": x["wc"], "lot": 0.0,
                                  "rate": 0.0, "remarks": "", "d": [0.0] * days}
            for i in range(days): a["d"][i] += x["d"][i]
            a["lot"] = max(a["lot"], x["lot"])             # ③ max
            if not a["wc"] and x["wc"]: a["wc"] = x["wc"]
        # ② 품목마스터에 있는 도번만 남긴다(조인은 순수 코드로)
        codes = sorted({v["_code"] for v in base.values() if v["_code"]})
        alive = set()
        if codes:
            cn3 = _conn(); c3 = cn3.cursor()
            try:
                for i in range(0, len(codes), 900):
                    ck = codes[i:i + 900]
                    ph = ",".join("?" * len(ck))
                    c3.execute("SELECT ITEM_CODE FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE IN (%s)" % ph, *ck)
                    for r in c3.fetchall(): alive.add(str(r[0]).strip())
            except Exception:
                alive = set(codes)     # 조회 실패시 필터하지 않음(데이터 누락 방지)
            finally:
                cn3.close()
        rows = [v for v in base.values() if v["_code"] in alive]
        for v in rows: v.pop("_code", None)
        rows.sort(key=lambda x: x["item"])

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
    lines = []; wcs = []
    cn = _conn(); cur = cn.cursor()
    try:
        # ① 계획에 실제 쓰인 라인코드(최근 3개월)
        cur.execute("""SELECT DISTINCT LINE_NO FROM PARTNER_ERP_TEST3.nx.SA_T_PLAN_DTL WITH(NOLOCK)
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
        # ※작업처 드롭다운은 **조회결과에서 프론트가 수집**한다(2026-08-28).
        #   SA_T_PLAN_DTL 에는 작업처 컬럼이 없고(WORK_ORDER/SPLIT_WORK_ORDER 뿐),
        #   화면의 work_center 는 SP 가 조인해 만든 값이라 마스터로는 목록을 못 만든다.
        #   → screens.sales.js 가 st.rows 의 wc 를 모아 드롭다운을 채운다.
    except Exception as e:
        return {"lines": lines, "wcs": wcs, "err": str(e)[:200]}
    finally:
        cn.close()
    v = {"lines": lines, "wcs": wcs}
    _OPT_CACHE["t"] = now; _OPT_CACHE["v"] = v
    return v
