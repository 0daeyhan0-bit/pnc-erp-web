# -*- coding: utf-8 -*-
"""stock 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _mat_avail, _assert_open, _lock_msg, _closed, stock_changed)

router = APIRouter()

# ===================== 자재 재고 (nx.stock_ledger 통합원장) =====================
# 조정/입고/출고 3화면 = 동일 원장, MAINT_TAG 프리셋으로 구분. 출고는 음수저장(양수표시).
STOCK_SCREENS = {
    "adjust":  {"name": "자재개별재고조정", "tags": ["1", "2", "3", "A"], "sign": 0},   # ± 조정
    "receipt": {"name": "자재입고관리",     "tags": ["9", "S", "C", "G", "H"], "sign": 1},  # + 입고
    # ★출고 태그 = 4(생산사용/축관) + B(자재개별출고) — 레거시 w_pu_stock_150 조회조건과 동일.
    #   수동 등록(w_pu_stock_156 팝업)은 B 로 넣는다. 4 는 생산 소비에서 자동 생성.
    "issue":   {"name": "자재출고관리",     "tags": ["4", "B"], "sign": -1},            # - 출고(양수표시)
    "return":  {"name": "자재반품",         "tags": ["RT"], "sign": -1},               # - 반품(≤현재고 가드, 다음공정 이동분은 이미 재고감소=반품불가)
}

def _ym(ymd):  # MAINT_YMD(YYMMDD/YYYYMMDD) → 마감월 YYMM
    y = str(ymd or "").strip()
    return y[:4] if len(y) >= 6 else ""

@router.get("/api/stock/list")
def stock_list(screen: str = Query("adjust"), ymd_from: str = Query(...), ymd_to: str = Query(...),
               q: str = Query(""), cust: str = Query(""), cust_code: str = Query(""),
               wh: str = Query(""), tag: str = Query(""), limit: int = Query(500)):
    """q=자도번(품번) / cust=매입처(코드 또는 거래처명, LIKE) / cust_code=확정된 거래처코드(정확일치).
    2026-08-23 매입처 조건 분리. 화면에서 이름을 정확히 골랐거나 코드를 친 경우 cust_code 가 와서
    그 거래처 한 곳만 조회된다('그린산업' 입력 시 '그린산업(주)김해공장'까지 딸려오던 문제)."""
    sc = STOCK_SCREENS.get(screen)
    if not sc:
        raise HTTPException(400, "screen 오류")
    cn = _nx(); cur = cn.cursor()
    try:
        tags = "','".join(sc["tags"])
        like = f"%{q.strip()}%"
        # 매입처 = 코드확정(cust_code)이면 그 거래처만, 아니면 코드/이름 LIKE(빈값이면 조건 무시)
        ccode = cust_code.strip()
        cs = '' if ccode else cust.strip()
        clike = f"%{cs}%"
        sign = "-1" if sc["sign"] == -1 else "1"
        # ★레거시 w_pu_stock_050 정합(2026-08-28): 모도번(=ITEM_CODE)품명·입고창고·구분 필터 추가.
        #   ·모도번 품명 = ITEM_CODE 로 nx.item 재조인(자도번 품명과 별개 컬럼)
        #   ·입고창고 wh = GAGONG_PROC_CODE (레거시 「입고창고」 조건. IS0001=자재창고)
        #   ·구분 tag  = 화면 태그 중 하나만 골라보기(빈값=화면 전체 태그)
        #   ·limit     = 레거시는 전건(8,969건) 표시. 500 고정이면 대사 불가라 파라미터화.
        _lim = max(1, min(int(limit or 500), 20000))
        _wh = (wh or "").strip()
        _tg = (tag or "").strip()
        cur.execute(f"""
            SELECT TOP {_lim} l.MAINT_YMD, l.MAINT_SEQ, l.MAINT_TAG, tg.name AS tag_name,
                   l.CUST_CODE, pc.CUST_DESC AS cust_name, l.GAGONG_PROC_CODE,
                   l.MAT_CODE, i.item_name, i.item_spec, l.ITEM_CODE,
                   mi.item_name AS upper_name,
                   (l.MAINT_QTY * {sign}) AS qty, l.MAINT_COST, l.MAINT_AMT, l.REMARKS,
                   l.SHEET_NO, l.INSP_FLAG, l.WORK_CODE, l.TO_GAGONG_PROC_CODE, l.OUT_WH_GUBUN,
                   l.INSERT_USER_ID, l.INSERT_DATETIME,
                   -- ★수정/삭제 팝업(레거시 w_pu_stock_055)이 쓰는 필드
                   l.MAINT_GROUP_SEQ, l.MAINT_VAT, l.DIRECT_ITEM_FLAG, l.INSP_PROC_YMD,
                   l.ITEM_GUBUN, l.SET_MAINT_YMD, l.SET_MAINT_SEQ, l.WH_CUST_CODE,
                   l.UPDATE_USER_ID, l.UPDATE_DATETIME
            FROM nx.stock_ledger l
            LEFT JOIN nx.item i ON i.item_code = l.MAT_CODE
            LEFT JOIN nx.item mi ON mi.item_code = l.ITEM_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST pc ON pc.CUST_CODE = l.CUST_CODE
            LEFT JOIN nx.stock_tag tg ON tg.tag = l.MAINT_TAG
            WHERE l.STOCK_POINT='MAT' AND l.MAINT_YMD BETWEEN ? AND ? AND l.MAINT_TAG IN ('{tags}')
              AND (? = '%%' OR l.MAT_CODE LIKE ? OR l.CUST_CODE LIKE ?)
              AND (? = '' OR l.CUST_CODE = ?)
              AND (? = '' OR l.CUST_CODE LIKE ? OR pc.CUST_DESC LIKE ?)
              AND (? = '' OR ISNULL(l.GAGONG_PROC_CODE,'') = ?)
              AND (? = '' OR l.MAINT_TAG = ?)
            ORDER BY l.MAINT_YMD DESC, l.MAINT_SEQ DESC""",
            ymd_from.strip(), ymd_to.strip(), like, like, like, ccode, ccode, cs, clike, clike,
            _wh, _wh, _tg, _tg)
        cols = [d[0] for d in cur.description]
        rows = [{c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        return {"screen": screen, "name": sc["name"], "sign": sc["sign"], "rows": rows}
    finally:
        cn.close()


@router.get("/api/stock/warehouses")
def stock_warehouses():
    """입고창고 목록(레거시 w_pu_stock_050/057 「입고창고」 드롭다운).

    ★창고는 별도 마스터가 아니라 **가공공정 마스터(PR_M_PROC_GAGONG)의 IS* 코드**로 등록돼 있다:
        IS0001 = 자재창고 · IS0002 = 부자재창고(미키팅)
      원장 PU_T_STOCK_MAINT.GAGONG_PROC_CODE 에 이 IS 코드가 들어간다(=입고된 곳).
      TO_GAGONG_PROC_CODE 는 출발지 공정(P0001=생산 등)이고, WH_CUST_CODE(Z99990)는
      창고 '거래처'코드라 셋이 서로 다른 개념이다 — 혼동 주의(2026-08-28 사용자 지적).
    """
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT RTRIM(g.GAGONG_PROC_CODE) wh, ISNULL(g.GAGONG_PROC_DESC,'') nm,
                   ISNULL(u.c,0) c
              FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG g
              LEFT JOIN (SELECT RTRIM(ISNULL(GAGONG_PROC_CODE,'')) wh, COUNT(*) c
                           FROM nx.stock_ledger WHERE STOCK_POINT='MAT'
                          GROUP BY RTRIM(ISNULL(GAGONG_PROC_CODE,''))) u
                     ON u.wh = RTRIM(g.GAGONG_PROC_CODE)
             WHERE RTRIM(g.GAGONG_PROC_CODE) LIKE 'IS%'
             ORDER BY g.GAGONG_PROC_CODE""")
        whs = [{"wh": str(r[0]).strip(), "nm": str(r[1] or "").strip(), "cnt": int(r[2] or 0)}
               for r in cur.fetchall()]
        # ★작업처(라인/파트) 목록 — 자재출고 팝업 TO파트·TO작업처 드롭다운용.
        #   창고(IS*)를 뺀 나머지 가공공정 = 라인·파트(P1 용접, S1 02라인 …).
        #   ★정렬 = **이름 앞의 라인번호 순**(01라인·02라인·03라인…). 2026-08-28 사용자 요청.
        #     코드순(S1→S10→S2→S4)이면 라인이 뒤섞여 고르기 어렵다.
        wcs = []
        try:
            cur.execute("""SELECT RTRIM(GAGONG_PROC_CODE) code, ISNULL(GAGONG_PROC_DESC,'') nm
                  FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG
                 WHERE RTRIM(GAGONG_PROC_CODE) NOT LIKE 'IS%' AND ISNULL(GAGONG_PROC_DESC,'')<>''""")
            wcs = [{"code": str(r[0]).strip(), "nm": str(r[1] or "").strip()} for r in cur.fetchall()]
            import re as _re
            def _k(w):
                m = _re.match(r"\s*(\d+)", w["nm"])          # 「02라인」 → 2
                return (0, int(m.group(1)), w["nm"]) if m else (1, 0, w["nm"])
            wcs.sort(key=_k)                                  # 숫자 라인 먼저(오름차순), 나머지는 이름순
        except Exception:
            pass
        return {"rows": whs, "wcs": wcs}
    except Exception as e:
        return {"rows": [], "wcs": [], "_err": str(e)[:200]}
    finally:
        cn.close()


@router.get("/api/stock/assybom")
def stock_assybom(assy: str = Query(...), setqty: float = Query(1)):
    """ASSY도번 → 하위자재 BOM 전개 (소요량 × 세트수량).

    ⚠자재출고관리(w_pu_stock_156)에서는 **쓰지 않는다** — 그 화면은 단품을 다른 창고로
      내보내는 것이라 BOM 전개가 필요 없다(2026-08-28 사용자 확정).
      세트 단위 출고가 필요한 다른 화면을 위해 남겨둔다.
    ★웹 정본만 읽는다: nx.v_pr_bom · nx.item · nx.mat_stock_daily(현재고).
      except_flag='1' 제외(편성과 동일 규칙). 같은 자재 여러 행이면 소요량 합산.
    """
    assy = str(assy or "").strip().upper()
    try:
        sq = float(setqty or 1)
    except (TypeError, ValueError):
        sq = 1.0
    if not assy:
        return {"rows": [], "assy": ""}
    cn = _nx(); cur = cn.cursor()
    try:
        # ★같은 자재가 BOM 에 여러 행이면 소요량을 합산한다(레거시도 자재 1행으로 출고).
        cur.execute("""SELECT TOP 500
                 RTRIM(b.MAT_CODE) mat, MAX(ISNULL(i.item_name,'')) nm, MAX(ISNULL(i.item_spec,'')) spec,
                 MAX(ISNULL(i.UNIT,'EA')) unit, SUM(CONVERT(float,ISNULL(b.USE_QTY_PR,1))) use_qty,
                 MAX(ISNULL(i.in_cust,'')) cust, MAX(ISNULL(i.work_code,'')) wc
              FROM nx.v_pr_bom b
              LEFT JOIN nx.item i ON RTRIM(i.item_code)=RTRIM(b.MAT_CODE)
             WHERE RTRIM(b.ITEM_CODE)=? AND ISNULL(b.EXCEPT_FLAG,'0')<>'1'
             GROUP BY RTRIM(b.MAT_CODE)
             ORDER BY RTRIM(b.MAT_CODE)""", assy)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        # 현재고 배치조회(정본 nx.mat_stock_daily 최신일)
        mats = [r["mat"] for r in rows if r["mat"]]
        stk = {}
        for i in range(0, len(mats), 900):
            ch = mats[i:i+900]; ph = ",".join("?" * len(ch))
            try:
                cur.execute(f"""SELECT UPPER(d.mat_code), d.stock_qty FROM (
                        SELECT mat_code, stock_qty,
                               ROW_NUMBER() OVER(PARTITION BY UPPER(mat_code) ORDER BY ymd DESC) rn
                          FROM nx.mat_stock_daily WHERE UPPER(mat_code) IN ({ph})) d
                     WHERE d.rn=1""", *ch)
                for r in cur.fetchall():
                    stk[str(r[0]).strip().upper()] = float(r[1] or 0)
            except Exception:
                pass
        # 도번(상위) 이름
        cur.execute("SELECT TOP 1 ISNULL(item_name,'') FROM nx.item WHERE RTRIM(item_code)=?", assy)
        _a = cur.fetchone()
        for r in rows:
            r["stock"] = stk.get((r["mat"] or "").upper(), 0)
            r["qty"] = round(float(r["use_qty"] or 1) * sq, 4)     # 소요량 × 세트수량
            r["assy"] = assy
            r["level"] = 1
        return {"rows": rows, "assy": assy, "assynm": (_a[0] if _a else ""), "setqty": sq}
    finally:
        cn.close()


@router.get("/api/stock/mastercost")
def stock_mastercost(mat: str = Query(...), cust: str = Query(""), ymd: str = Query("")):
    """★MASTER단가 — 레거시 w_pu_stock_055 「MASTER단가」 버튼.
       정본 = nx.price_item(CLAUDE.md §1-9 클린본). price_type='매입' 중
       적용일(apply_ymd) 이 기준일 이하인 최신 1건. 거래처를 주면 그 거래처 단가 우선."""
    mat = str(mat or "").strip().upper()
    if not mat:
        return {"cost": None}
    base = (str(ymd or "").strip() or datetime.now().strftime("%y%m%d"))
    cn = _nx(); cur = cn.cursor()
    try:
        cc = str(cust or "").strip()
        cur.execute("""SELECT TOP 1 price, vendor_code, apply_ymd, currency
              FROM nx.price_item
             WHERE UPPER(item_code)=? AND price_type=N'매입' AND apply_ymd<=?
             ORDER BY CASE WHEN ?<>'' AND RTRIM(ISNULL(vendor_code,''))=? THEN 0 ELSE 1 END,
                      apply_ymd DESC""", mat, base, cc, cc)
        r = cur.fetchone()
        if not r:
            return {"cost": None, "mat": mat}
        return {"cost": float(r[0] or 0), "vendor": str(r[1] or "").strip(),
                "apply_ymd": str(r[2] or "").strip(), "currency": str(r[3] or "KRW").strip(),
                "mat": mat}
    except Exception as e:
        return {"cost": None, "_err": str(e)[:200]}
    finally:
        cn.close()


@router.post("/api/stock/matinfo")
def stock_matinfo(payload: dict = Body(...)):
    """★자재개별일괄입고 팝업(레거시 w_pu_stock_057) — 자도번 입력 시 따라올 정보 배치조회.
       codes[] 를 받아 품명·규격·단위·현재고를 한 번에 돌려준다.
       ·엑셀 붙여넣기(수십~수백행)를 행마다 조회하면 느려서 배치 API 로 만든다.
       ·★발주(PU_T_PURCHASE_DTL) 미조회 — 개별자재 발주기능이 없다(2026-08-28 사용자 확정).
         레거시 057 은 발주잔량 컬럼을 갖지만 우리는 쓰지 않으므로 빼서 쿼리도 가볍게 한다."""
    codes = [str(x).strip().upper() for x in (payload.get("codes") or []) if str(x).strip()]
    if not codes:
        return {"rows": []}
    codes = codes[:2000]
    cn = _nx(); cur = cn.cursor()
    out = {}
    try:
        for i in range(0, len(codes), 900):
            ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"""SELECT item_code, ISNULL(item_name,''), ISNULL(item_spec,''), ISNULL(UNIT,'EA')
                              FROM nx.item WHERE item_code IN ({ph})""", *ch)
            for r in cur.fetchall():
                out[str(r[0]).strip().upper()] = {"mat": str(r[0]).strip(), "nm": r[1], "spec": r[2],
                                                  "unit": r[3], "stock": 0}
        # 현재고(참고표시) — 정본 nx.mat_stock_daily 최신일(common._mat_avail 과 동일 기준).
        #   행마다 _mat_avail 을 부르면 수백행에서 느려서 배치 1회로 뽑는다.
        try:
            for i in range(0, len(codes), 900):
                ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
                cur.execute(f"""SELECT UPPER(d.mat_code), d.stock_qty
                      FROM (SELECT mat_code, stock_qty,
                                   ROW_NUMBER() OVER(PARTITION BY UPPER(mat_code) ORDER BY ymd DESC) rn
                              FROM nx.mat_stock_daily WHERE UPPER(mat_code) IN ({ph})) d
                     WHERE d.rn=1""", *ch)
                for r in cur.fetchall():
                    k = str(r[0]).strip().upper()
                    if k in out:
                        out[k]["stock"] = float(r[1] or 0)
        except Exception:
            pass
        # ★MASTER 단가(2026-08-31 요청) — 입고단가 칸의 기본값. 사용자가 고칠 수 있다.
        #   정본 = nx.price_item(§1-9 클린본) price_type='매입', 적용일<=기준일 최신 1건.
        #   거래처(cust)를 주면 그 거래처 단가를 우선(같은 자재라도 업체별 단가가 다르다).
        #   /api/stock/mastercost 와 같은 규칙이되, 행마다 부르면 느려 배치 1회로 뽑는다.
        try:
            base = (str(payload.get("ymd") or "").strip()
                    or datetime.now().strftime("%y%m%d"))
            cc = str(payload.get("cust") or "").strip()
            for i in range(0, len(codes), 900):
                ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
                cur.execute(f"""SELECT UPPER(p.item_code), p.price, ISNULL(p.vendor_code,''),
                                       ISNULL(p.apply_ymd,''), ISNULL(p.currency,'KRW')
                      FROM (SELECT item_code, price, vendor_code, apply_ymd, currency,
                                   ROW_NUMBER() OVER(PARTITION BY UPPER(item_code)
                                     ORDER BY CASE WHEN ?<>'' AND RTRIM(ISNULL(vendor_code,''))=?
                                                   THEN 0 ELSE 1 END, apply_ymd DESC) rn
                              FROM nx.price_item
                             WHERE UPPER(item_code) IN ({ph}) AND price_type=N'매입'
                               AND apply_ymd<=?) p
                     WHERE p.rn=1""", cc, cc, *ch, base)
                for r in cur.fetchall():
                    k = str(r[0]).strip().upper()
                    if k in out:
                        _v = str(r[2]).strip()
                        out[k]["cost"] = float(r[1] or 0)
                        out[k]["cost_vendor"] = _v
                        out[k]["cost_ymd"] = str(r[3]).strip()
                        out[k]["currency"] = str(r[4]).strip() or 'KRW'
                        # ★단가 출처 표시(2026-08-31 요청) — 그 거래처 단가가 없어
                        #   다른 업체(또는 공통) 단가를 가져온 경우를 화면이 구분해 보여준다.
                        #   'own'  = 조회 거래처의 단가
                        #   'other'= 다른 업체 단가로 대체(★표시 대상)
                        #   'any'  = 거래처 미지정 상태에서 가져온 최신 단가
                        out[k]["cost_src"] = ('own' if (cc and _v == cc)
                                              else ('other' if cc else 'any'))
        except Exception:
            pass   # 단가 조회 실패로 입고 자체를 막지 않는다(화면에서 직접 입력 가능)
        # 요청 순서 유지 + 미등록 코드도 돌려줌(화면에서 빨갛게 경고)
        return {"rows": [out.get(cd, {"mat": cd, "nm": "", "spec": "", "unit": "",
                                      "stock": 0, "unknown": 1})
                         for cd in codes]}
    finally:
        cn.close()


@router.post("/api/stock/save")
def stock_save(payload: dict = Body(...)):
    """재고원장 저장(신규행 insert). 가드: 마감월 잠금·FK·출고 재고부족(음수방지)."""
    screen = str(payload.get("screen", "")).strip()
    rows = payload.get("rows", []) or []
    sc = STOCK_SCREENS.get(screen)
    if not sc:
        raise HTTPException(400, "screen 오류")
    # ★등록자 = 로그인 사용자 이름(2026-08-28). 종전엔 'web' 고정이라 누가 넣었는지 몰랐다.
    #   레거시는 실명(진선미·윤경빈…)이 남는다. 미전달 시에만 'web' 폴백.
    _usr = (str(payload.get("user") or "").strip() or "web")[:20]
    cn = _nx(); cur = cn.cursor()
    try:
        # 마감월 집합
        cur.execute("SELECT ym FROM nx.stock_close WHERE close_flag=1")
        closed = {str(r[0]).strip() for r in cur.fetchall()}   # ym=char(6) 패딩 제거(_ym은 4자 → 집합비교 일치)
        errs = []
        for idx, r in enumerate(rows, 1):
            ymd = str(r.get("MAINT_YMD", "")).strip()
            mat = str(r.get("MAT_CODE", "")).strip()
            qty = float(r.get("qty") or 0)
            if not ymd or len(ymd) < 6:
                errs.append(f"{idx}행: 일자 필요"); continue
            # ★마감잠금 = 공용 게이트(nx.period_close: 일마감+월마감+도메인). 구 nx.stock_close 는 폴백으로 유지.
            _lm = _lock_msg(cur, ymd, "MAT")
            if _lm:
                errs.append(f"{idx}행: {_lm}")
            elif _ym(ymd) in closed:
                errs.append(f"{idx}행: 마감월({_ym(ymd)}) 편집 불가")
            if not mat:
                errs.append(f"{idx}행: 자도번 필요"); continue
            cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", mat)
            if not cur.fetchone():
                errs.append(f"{idx}행: 미등록 품목({mat})")
            # 조정=부호입력 허용(불량·개발불출 −, 장부수정 ±), 그 외=양수만
            if screen == "adjust":
                if qty == 0:
                    errs.append(f"{idx}행: 조정수량은 0일 수 없습니다(증가 +, 감소 −)")
            elif qty <= 0:
                errs.append(f"{idx}행: 수량은 0보다 커야 함")
            # ★입고 신규등록은 개별입고(9)만(2026-08-28 사용자 확정).
            #   C(가공입고)=가공이동전표 바코드 · S(세트입고)=세트납품 으로만 생성돼야 하고
            #   여기서 수기로 만들면 근거 없는 입고가 된다. 수정/삭제는 전 구분 허용.
            if screen == "receipt":
                _tg = str(r.get("MAINT_TAG") or "").strip()
                if _tg and _tg != "9":
                    errs.append(f"{idx}행: 수동 등록은 개별입고(9)만 가능합니다"
                                f" — {_tg}는 해당 업무화면에서 생성하세요")
                # ★거래처 필수(2026-08-28) — 매입처 없는 입고는 매입마감·수불에서 누락된다.
                if not str(r.get("CUST_CODE") or "").strip():
                    errs.append(f"{idx}행: 거래처(매입처)가 필요합니다")
            # 재고 음수방지: 출고·반품(가용 이내) / 조정 감소(결과재고 ≥ 0). 현재고=원장 SUM.
            if mat and screen in ("issue", "return"):
                avail = _mat_avail(cur, mat)   # ★정본=실시간(확정스냅샷+이후전표, 마감·수불장과 같은 엔진). G-1 승격 2026-08-28
                if qty > avail:
                    lbl = "반품" if screen == "return" else "출고"
                    errs.append(f"{idx}행: 재고부족 ({mat} 가용 {avail:g} < {lbl} {qty:g}) — 다음공정 이동분은 반품 불가")
            elif mat and screen == "adjust" and qty < 0:
                avail = _mat_avail(cur, mat)   # ★정본=실시간(확정스냅샷+이후전표, 마감·수불장과 같은 엔진). G-1 승격 2026-08-28
                if avail + qty < 0:
                    errs.append(f"{idx}행: 음수재고 유발 ({mat} 결과재고 {avail+qty:g} < 0)")
        if errs:
            return {"ok": False, "errors": errs}
        # insert (일자별 SEQ 채번, 출고 음수 저장)
        # ★★채번 경쟁 방지(2026-08-31). PK=(MAINT_YMD,MAINT_SEQ) 인데 채번이 MAX+1 이라
        #   두 사람이 동시에 저장하면 같은 seq 를 받아 PK 중복 → 500(HTML) 이 나고
        #   프론트는 그걸 JSON 으로 파싱하다 "Unexpected token 'I'" 로 표시했다.
        #   (실측: 21:06:16~18 에 8건이 몰려 들어옴 — 먼저 커밋한 쪽만 성공)
        #   → UPDLOCK/HOLDLOCK 으로 그 일자 키를 트랜잭션 끝까지 잠가 직렬화한다.
        saved = 0
        for r in rows:
            ymd = str(r.get("MAINT_YMD", "")).strip()
            cur.execute("""SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WITH(UPDLOCK, HOLDLOCK)
                            WHERE MAINT_YMD=?""", ymd)
            seq = cur.fetchone()[0]
            tag = str(r.get("MAINT_TAG") or sc["tags"][0]).strip()
            qty = float(r.get("qty") or 0)
            store_qty = -abs(qty) if sc["sign"] == -1 else qty
            # ★입고금액·부가세(2026-08-31 레거시 w_pu_stock_057 정합).
            #   종전엔 MAINT_AMT 를 클라이언트가 안 보내 **0으로 저장**되고 MAINT_VAT 는
            #   컬럼에서 아예 빠져 있었다(같은 파일 L602 개별입고 경로는 이미 채우고 있었음).
            #   금액 = |수량| x 단가(반올림) · 부가세 = 금액의 10%. 클라이언트가 보내면 그 값 우선.
            _cost = float(r.get("MAINT_COST") or 0)
            _amt = r.get("MAINT_AMT")
            _amt = float(_amt) if _amt not in (None, "") else round(abs(qty) * _cost)
            _vat = r.get("MAINT_VAT")
            _vat = float(_vat) if _vat not in (None, "") else round(_amt * 0.1)
            cur.execute("""INSERT INTO nx.stock_ledger
                (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,GAGONG_PROC_CODE,TO_GAGONG_PROC_CODE,OUT_WH_GUBUN,
                 MAT_CODE,ITEM_CODE,WORK_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,MAINT_VAT,REMARKS,SHEET_NO,INSERT_USER_ID,INSERT_DATETIME)
                VALUES('MAT',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,GETDATE())""",
                ymd, seq, tag, (r.get("CUST_CODE") or None), (r.get("GAGONG_PROC_CODE") or None),
                (r.get("TO_GAGONG_PROC_CODE") or None), (r.get("OUT_WH_GUBUN") or None),
                str(r.get("MAT_CODE", "")).strip(), (r.get("ITEM_CODE") or None), (r.get("WORK_CODE") or None),
                store_qty, _cost, _amt, _vat,
                (r.get("REMARKS") or None), (r.get("SHEET_NO") or None), _usr)
            # ★자재창고 재고에도 반영(2026-08-20) — 레거시와 같은 구조.
            #   기존엔 nx.stock_ledger 에만 쌓여서 화면마다 반영이 갈렸음:
            #     준비등록 팝업 = 스냅샷 + stock_ledger 합산 → 조정분 보임
            #     자재입출고현황 = pu_t_stock_maint 만 조회   → 조정분 안 보임
            #   → 조정/입고/출고 시 nx.PU_T_MAT_STOCK_WH 잔액도 함께 증감시켜
            #     모든 화면이 같은 값을 보게 한다. (원장은 이력용으로 그대로 유지)
            #   ※버킷 키 = (MAT_CODE, CUST_CODE, GAGONG_PROC_CODE).
            #     자재창고 기본 버킷은 CUST_CODE='Z99990' · GAGONG_PROC_CODE='IS0001'
            #     (준비등록 setcheck 가 읽는 버킷과 동일해야 값이 맞음 — ready.py line 101)
            _mc = str(r.get("MAT_CODE", "")).strip()
            _cc = (str(r.get("CUST_CODE") or "").strip() or "Z99990")
            _gp = (str(r.get("GAGONG_PROC_CODE") or "").strip() or "IS0001")
            # ★출고(개별일괄출고)의 CUST_CODE 는 **원장 기록용 거래처**(영업창고로 보낼 상대처)이지
            #   재고 버킷 키가 아니다. 레거시 w_pu_stock_156 도 재고처리엔 'Z99990' 고정을 쓴다:
            #     f_pu_set_mat_stock_wh(..., ls_mat_code, 'Z99990', ls_gagong_proc_code, ld_qty,'')
            #   그대로 버킷키에 쓰면 자재창고 재고가 안 줄고 거래처 버킷만 음수가 된다.
            if screen == "issue":
                _cc = "Z99990"
            try:
                cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                                  UPDATE_USER_ID='web', UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW='stockadjust'
                                WHERE MAT_CODE=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                            store_qty, _mc, _cc, _gp)
                if cur.rowcount == 0:
                    cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK_WH(MAT_CODE,CUST_CODE,GAGONG_PROC_CODE,STOCK_QTY,
                                      UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                    VALUES(?,?,?,?,'web',GETDATE(),'stockadjust')""",
                                _mc, _cc, _gp, store_qty)
            except Exception: pass   # 재고 반영 실패해도 원장 기록은 유지(이력 우선)
            # ★★생산창고 출고(구분1) = 받는 파트에 **입고**를 잡아야 한다(2026-08-28).
            #   레거시 w_pu_stock_156 ue_save_after 원문:
            #       else                                             /* out_wh_gubun='1' */
            #          f_pr_set_mat_stock   (..., ls_work_code,           ls_mat_code, -ld_qty,'')
            #          f_pr_set_mat_stock_wh(..., ls_to_gagong_proc_code, ls_mat_code, -ld_qty,'')
            #   ld_qty 는 음수(출고)라 -ld_qty = 양수 → TO파트 재고 증가.
            #   ※f_pr_set_mat_stock(PR_T_MAT_STOCK) 은 현재 의미 없는 값이라 구현하지 않는다
            #     (사용자 확정 2026-08-28. 실측: WORK_CODE=''=69,204/P1=0 으로 화면 어디서도 안 읽음).
            #     파트재고 nx.PR_T_MAT_STOCK_WH 만이 정본 — 준비실적(ready.py:504)·생산실적
            #     (prodsheet.py:787)·가공바코드(procbc.py:162) 가 모두 여기에 쓰고 키팅·410 이 읽는다.
            #   이게 빠져서 "04라인 출고했는데 생산창고에 재고가 없다"가 났다.
            if screen == "issue" and str(r.get("OUT_WH_GUBUN") or "").strip() == "1":
                _tp = str(r.get("TO_GAGONG_PROC_CODE") or "").strip()
                if _tp:
                    _in = -store_qty          # store_qty 는 음수(출고) → 받는 파트는 양수
                    try:
                        cur.execute("""UPDATE nx.PR_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                                          UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                                        WHERE MAT_CODE=? AND PART_CODE=?""", _in, _usr, screen, _mc, _tp)
                        if cur.rowcount == 0:
                            cur.execute("""INSERT INTO nx.PR_T_MAT_STOCK_WH(MAT_CODE,PART_CODE,STOCK_QTY,
                                              UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                            VALUES(?,?,?,?,GETDATE(),?)""", _mc, _tp, _in, _usr, screen)
                    except Exception: pass
            # ★영업창고 출고(구분2) = 영업창고 재고 증가.
            #   레거시 원문: f_sa_set_item_stock(is_window_name, ls_maint_ymd, ls_mat_code, -ld_qty,'')
            #   ★잔액(nx.SA_T_ITEM_STOCK)만 갱신한다 — 레거시와 동일.
            #     실측: 라이브 SA_T_STOCK_MAINT 에 w_pu_stock_156 등록분 0건.
            #   ※이력을 SA_T_STOCK_MAINT 에 **넣으면 안 된다(이중계상)**.
            #     제품입출고현황(live_api._prodinvout L1 3번째 UNION, line 973)이
            #       SELECT mat_code, maint_qty*-1, '자재창고에서입고'
            #         FROM nx.pu_t_stock_maint WHERE ISNULL(out_wh_gubun,'1')='2'
            #     로 **자재출고 미러행을 직접** 집계하기 때문. 위쪽 PU_T_STOCK_MAINT
            #     INSERT 가 이미 그 원천이다.
            #   ※화면에 안 뜨던 이유는 이력이 아니라 잔액이었다 — _prodinvout line 1000 이
            #     SA_T_ITEM_STOCK 잔액 0 인 품목을 목록에서 제외(continue)한다.
            #   ※세트재고(PU_T_SET_OUTPUT_DTL)는 레거시에서도 **주석 처리**돼 있어 건드리지 않는다:
            #     "직납품은 출하처리 될때 세트출고실적을 추가하기 때문에 자재창고에서 영업창고로
            #      이동할때는 세트재고를 변경하지 않는다."
            elif screen == "issue" and str(r.get("OUT_WH_GUBUN") or "").strip() == "2":
                _inq = -store_qty                 # store_qty 음수(출고) → 영업창고는 양수 입고
                try:      # 잔액 = 레거시 f_sa_set_item_stock 과 동일
                    cur.execute("""UPDATE nx.SA_T_ITEM_STOCK SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                                    WHERE ITEM_CODE=?""", _inq, _usr, screen, _mc)
                    if cur.rowcount == 0:
                        cur.execute("""INSERT INTO nx.SA_T_ITEM_STOCK(ITEM_CODE,STOCK_QTY,
                                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                        VALUES(?,?,?,GETDATE(),?)""", _mc, _inq, _usr, screen)
                except Exception: pass
            # ★자재 입출고이력에도 기록(2026-08-20) — 레거시 w_pu_stock_016 과 동일 형태.
            #   자재입출고현황·자재수불장 등은 nx.PU_T_STOCK_MAINT 를 읽으므로 여기 없으면
            #   잔액은 맞는데 "입출고 내역"에는 안 잡힌다.
            #   ★WH_CUST_CODE·GAGONG_PROC_CODE 필수 — 공백이면 창고 필터에서 빠져 조회 누락됨.
            try:
                cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
                _sq = int(cur.fetchone()[0] or 1)
                # ★출고 전용 필드도 함께 넣는다(2026-08-28) — 자재출고관리(w_pu_stock_150) 조회가
                #   out_wh_gubun(1생산/2영업)·to_gagong_proc_code·item_code(ASSY도번) 를 보여주므로
                #   빠지면 저장은 됐는데 화면 컬럼이 비는 현상이 생긴다.
                cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
                        (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
                         WH_CUST_CODE,GAGONG_PROC_CODE,TO_GAGONG_PROC_CODE,OUT_WH_GUBUN,ITEM_CODE,
                         INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                         UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,GETDATE(),?,?,GETDATE(),?)""",
                    # ★CUST_CODE=업무상 거래처(원문 그대로) / WH_CUST_CODE=창고코드(Z99990).
                    #   출고에서 _cc 를 버킷키용으로 Z99990 으로 덮으므로 여기선 원문을 다시 쓴다.
                    ymd, _sq, ("T" if tag == "RT" else tag),
                    (str(r.get("CUST_CODE") or "").strip() or None), _mc, store_qty, (r.get("REMARKS") or None),
                    _cc, _gp,
                    (r.get("TO_GAGONG_PROC_CODE") or None), (r.get("OUT_WH_GUBUN") or None),
                    (r.get("ITEM_CODE") or None),
                    _usr, screen, _usr, screen)
                    # ★F2: MAINT_TAG=CHAR(1) → 반품 'RT'(2글자) 잘림오류로 수불장 누락됐음 → 'T'(자재창고반품) 매핑
            except Exception: pass
            saved += 1
        stock_changed("stock_save")           # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "count": saved}
    finally:
        cn.close()

@router.get("/api/stock/kanban")
def stock_kanban(q: str = Query("")):
    """자재입고진행현황(읽기전용 집계): 품목별 현재고=원장 SUM. 계획대비는 추후 확장."""
    cn = _nx(); cur = cn.cursor()
    try:
        like = f"%{q.strip()}%"
        cur.execute("""
            SELECT TOP 300 l.MAT_CODE, i.item_name, i.item_spec, MAX(l.GAGONG_PROC_CODE) AS part,
                   SUM(l.MAINT_QTY) AS stock_qty,
                   SUM(CASE WHEN l.MAINT_QTY>0 THEN l.MAINT_QTY ELSE 0 END) AS in_qty,
                   SUM(CASE WHEN l.MAINT_QTY<0 THEN -l.MAINT_QTY ELSE 0 END) AS out_qty
            FROM nx.stock_ledger l LEFT JOIN nx.item i ON i.item_code=l.MAT_CODE
            WHERE l.STOCK_POINT='MAT' AND (? = '%%' OR l.MAT_CODE LIKE ?)
            GROUP BY l.MAT_CODE, i.item_name, i.item_spec
            HAVING SUM(l.MAINT_QTY) <> 0
            ORDER BY SUM(l.MAINT_QTY) DESC""", like, like)
        cols = [d[0] for d in cur.description]
        rows = [{c: v for c, v in zip(cols, r)} for r in cur.fetchall()]
        return {"rows": rows}
    finally:
        cn.close()

# ============ 자재입고: 발주분 입고(057 개별일괄 / 057_1 PO바코드) — 발주잔량 차감·nx.stock_ledger 기록 ============
# 발주잔량 = 발주(PU_T_PURCHASE_DTL.PUR_QTY) − 레거시기입고(IN_QTY) − 취소(CANCEL_QTY) − nx웹입고(발주링크 SUM). [[nextgen-erp-ledger-consistency]] 원장파생.
@router.get("/api/matrecv/po_pending")
def matrecv_po_pending(cust: str = Query(""), item: str = Query(""), sheet: str = Query(""),
                       from_ymd: str = Query(""), to_ymd: str = Query("")):
    """발주분 입고대기(발주잔량>0). 개별일괄/PO바코드 공용. sheet=발주번호(PUR_SEQ, 바코드 PO뒤 숫자)."""
    C = " COLLATE DATABASE_DEFAULT"
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["(p.PUR_QTY - ISNULL(p.IN_QTY,0) - ISNULL(p.CANCEL_QTY,0)) > 0"]; pr = []
        if cust.strip(): w.append("p.CUST_CODE LIKE ?"); pr.append(f"%{cust.strip()}%")
        if item.strip(): w.append("p.ITEM_CODE LIKE ?"); pr.append(f"%{item.strip()}%")
        if sheet.strip(): w.append("p.PUR_SEQ=?"); pr.append(sheet.strip())
        if from_ymd.strip(): w.append("p.PUR_YMD>=?"); pr.append(_d6(from_ymd))
        if to_ymd.strip(): w.append("p.PUR_YMD<=?"); pr.append(_d6(to_ymd))
        cur.execute(f"""SELECT TOP 800 p.PUR_YMD, p.PUR_SEQ, p.PUR_SEQ_ROW, p.CUST_CODE, ISNULL(cu.CUST_DESC,'') cust_nm,
              p.ITEM_CODE, ISNULL(it.item_name,'') nm, ISNULL(it.item_spec,'') spec, ISNULL(it.unit,'') unit, p.DLVY_YMD,
              p.PUR_QTY, ISNULL(p.IN_QTY,0) in_qty, ISNULL(p.CANCEL_QTY,0) cancel_qty, ISNULL(nx.q,0) nx_in,
              ISNULL(p.PUR_COST,0) pur_cost, ISNULL(p.MAT_INSPECTION,'') insp,
              (p.PUR_QTY - ISNULL(p.IN_QTY,0) - ISNULL(p.CANCEL_QTY,0) - ISNULL(nx.q,0)) remain
            FROM PARTNER_ERP_TEST3.nx.PU_T_PURCHASE_DTL p
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON cu.CUST_CODE=p.CUST_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.item it ON it.item_code=p.ITEM_CODE
            LEFT JOIN (SELECT PUR_YMD,PUR_SEQ,PUR_SEQ_ROW,SUM(MAINT_QTY) q FROM nx.stock_ledger
                       WHERE MAINT_TAG='9' AND ISNULL(PUR_YMD,'')<>'' GROUP BY PUR_YMD,PUR_SEQ,PUR_SEQ_ROW) nx
              ON nx.PUR_YMD{C}=p.PUR_YMD{C} AND nx.PUR_SEQ{C}=p.PUR_SEQ{C} AND nx.PUR_SEQ_ROW=p.PUR_SEQ_ROW
            WHERE {' AND '.join(w)}
            ORDER BY p.PUR_YMD DESC, p.PUR_SEQ, p.PUR_SEQ_ROW""", *pr)
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["remain"] = float(d["remain"] or 0)
            if d["remain"] <= 0:  # nx입고로 이미 충족분 제외
                continue
            for k in ("PUR_QTY", "in_qty", "cancel_qty", "nx_in", "pur_cost"):
                d[k] = float(d[k] or 0)
            d["DLVY_YMD"] = str(d["DLVY_YMD"] or "")
            rows.append(d)
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.post("/api/matrecv/receive")
def matrecv_receive(payload: dict = Body(...)):
    """발주분 입고 확정 → nx.stock_ledger(MAINT_TAG='9', 발주링크). 마감월/미등록품목/발주잔량초과 가드.
    입고수량이 발주잔량 초과시 차단. 삭제는 /api/stock/delete(원장행 제거=역진행)."""
    ymd = str(payload.get("ymd") or "").strip()      # 입고일자 YYMMDD
    wh = str(payload.get("wh") or "IS0001").strip()   # 입고창고(gagong_proc_code)
    rows = payload.get("rows", []) or []
    if not ymd or len(ymd) < 6:
        raise HTTPException(400, "입고일자 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        if _closed(cur, ymd, "MAT"):
            return {"ok": False, "errors": [f"마감월({_ym(ymd)}) 입고 불가"]}
        errs = []
        # 검증: 품목등록·발주잔량 초과
        for idx, r in enumerate(rows, 1):
            item = str(r.get("item", "")).strip(); qty = float(r.get("qty") or 0)
            py = str(r.get("pur_ymd", "")).strip(); ps = str(r.get("pur_seq", "")).strip(); prw = r.get("pur_seq_row")
            if qty <= 0: errs.append(f"{idx}행: 입고수량>0 필요"); continue
            cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", item)
            if not cur.fetchone(): errs.append(f"{idx}행: 미등록품목({item})")
            if py and ps and prw is not None:  # 발주잔량 초과 가드
                cur.execute("""SELECT (p.PUR_QTY-ISNULL(p.IN_QTY,0)-ISNULL(p.CANCEL_QTY,0)
                    -ISNULL((SELECT SUM(MAINT_QTY) FROM nx.stock_ledger WHERE MAINT_TAG='9' AND PUR_YMD=? AND PUR_SEQ=? AND PUR_SEQ_ROW=?),0))
                    FROM PARTNER_ERP_TEST3.nx.PU_T_PURCHASE_DTL p WHERE p.PUR_YMD=? AND p.PUR_SEQ=? AND p.PUR_SEQ_ROW=?""",
                    py, ps, int(prw), py, ps, int(prw))
                rem = cur.fetchone()
                remain = float(rem[0]) if rem and rem[0] is not None else None
                if remain is not None and qty > remain + 0.001:
                    errs.append(f"{idx}행: 발주잔량 초과({item} 잔량 {remain:g} < 입고 {qty:g})")
        if errs:
            return {"ok": False, "errors": errs}
        saved = 0
        for r in rows:
            item = str(r.get("item", "")).strip(); qty = float(r.get("qty") or 0)
            if qty <= 0: continue
            cost = float(r.get("cost") or 0); vat = float(r.get("vat") or round(qty * cost * 0.1))
            py = (str(r.get("pur_ymd", "")).strip() or None); ps = (str(r.get("pur_seq", "")).strip() or None)
            prw = r.get("pur_seq_row")
            # ★채번 경쟁 방지 — 위 stock_save 와 같은 이유(PK 중복 → 500).
            cur.execute("""SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WITH(UPDLOCK, HOLDLOCK)
                            WHERE MAINT_YMD=?""", ymd)
            seq = cur.fetchone()[0]
            cur.execute("""INSERT INTO nx.stock_ledger
                (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,GAGONG_PROC_CODE,MAT_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,MAINT_VAT,
                 PUR_YMD,PUR_SEQ,PUR_SEQ_ROW,INSP_FLAG,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                VALUES('MAT',?,?, '9',?,?,?,?,?,?,?, ?,?,?,?,?, ?, GETDATE())""",
                ymd, seq, (r.get("cust") or None), wh, item, qty, cost, round(qty * cost), vat,
                py, ps, (int(prw) if prw is not None else None), (r.get("insp") or None),
                (r.get("remarks") or "발주입고"), "web")
            saved += 1
        stock_changed("stock_save")           # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "count": saved}
    finally:
        cn.close()

# ============ 자재입고: 가공이동전표 입고(057_2 바코드) — PU_T_STOCK_MAINT_GAGONG_MOVE → nx.stock_ledger(tag C) ============
@router.get("/api/matrecv/gagong_pending")
def matrecv_gagong_pending(sheet: str = Query(""), item: str = Query("")):
    """가공이동전표 미입고분. sheet=바코드(MV+MAINT_GROUP_SEQ). 미입고=IN_CONFIRM_FLAG≠1 & nx웹입고 미충족.

    ★원천 = **nx 단독**(2026-08-28 사용자 확정 "여기도 nx로 다 만들어줘").
      라이브 전표 34,927행을 nx 로 전량 복사해 nx 를 정본으로 만들었다(그 시점 미복사 44행 = 오늘
      레거시 발행분만 남아 있었다 — nx 는 원래 이 테이블의 미러라 34,883행이 이미 동일했다).
      → 이후 조회·입고확인·완료표시(IN_CONFIRM_FLAG)가 전부 nx 한 곳에서 끝난다.
        (라이브는 읽기전용이라 UNION 으로 읽으면 완료표시를 못 써서 상태가 갈렸다)"""
    C = " COLLATE DATABASE_DEFAULT"
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["ISNULL(g.IN_CONFIRM_FLAG,'0')<>'1'"]; pr = []
        if sheet.strip():
            gs = "".join(ch for ch in sheet.strip() if ch.isdigit())
            w.append("g.MAINT_GROUP_SEQ=?"); pr.append(int(gs) if gs else -1)
        if item.strip(): w.append("g.MAT_CODE LIKE ?"); pr.append(f"%{item.strip()}%")
        cur.execute(f"""SELECT TOP 500 g.MAINT_GROUP_SEQ, g.MAT_CODE, ISNULL(it.item_name,'') nm, ISNULL(it.item_spec,'') spec,
              ISNULL(it.unit,'') unit, g.ITEM_CODE upper_code, g.MAINT_QTY, g.GAGONG_PROC_CODE, g.TO_GAGONG_PROC_CODE,
              g.MAINT_YMD, ISNULL(nx.q,0) nx_in
            FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_GAGONG_MOVE g
            LEFT JOIN PARTNER_ERP_TEST3.nx.item it ON it.item_code{C}=g.MAT_CODE{C}
            LEFT JOIN (SELECT MAINT_GROUP_SEQ, SUM(MAINT_QTY) q FROM nx.stock_ledger WHERE MAINT_TAG='C' AND MAINT_GROUP_SEQ IS NOT NULL GROUP BY MAINT_GROUP_SEQ) nx
              ON nx.MAINT_GROUP_SEQ=g.MAINT_GROUP_SEQ
            WHERE {' AND '.join(w)}
            ORDER BY g.MAINT_YMD DESC, g.MAINT_GROUP_SEQ DESC""", *pr)
        cols = [d[0] for d in cur.description]; rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["MAINT_QTY"] = float(d["MAINT_QTY"] or 0); d["nx_in"] = float(d["nx_in"] or 0)
            d["remain"] = d["MAINT_QTY"] - d["nx_in"]
            d["MAINT_YMD"] = str(d["MAINT_YMD"] or "")
            if d["remain"] <= 0: continue
            rows.append(d)
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.post("/api/matrecv/gagong_receive")
def matrecv_gagong_receive(payload: dict = Body(...)):
    """가공이동전표 입고 확정 (레거시 w_pu_stock_057_2 ue_save_after 이식).

    웹이 하는 일 (종전엔 ①만 있어 재고가 안 늘었다 — 2026-08-28 보완):
      ① nx.stock_ledger  MAINT_TAG='C' · MAINT_GROUP_SEQ 링크(이력)
      ② 창고별 자재재고 **증가** — f_pu_set_mat_stock_wh → nx.PU_T_MAT_STOCK_WH
         (취소 ue_cancel 이 같은 함수에 음수를 주므로, 입고는 양수가 맞다)
      ③ 전표에 완료표시 — IN_CONFIRM_FLAG='1' + IN_MAINT_YMD/SEQ/QTY
    ※버킷 = (MAT_CODE, CUST_CODE=파트창고코드, GAGONG_PROC_CODE=입고창고).
      레거시 ls_in_cust_code = f_get_part_info(파트,'in_cust_code'), 없으면 'Z99990'.

      ④ 가공창고 재고 **차감**(f_pr_set_mat_stock_wh) + 생산자재수불 이력
         — 가공창고→자재창고 '이동'이므로 출발지가 줄어야 한다. 안 빼면 이중계상.

    ★레거시 원문에 있으나 **웹은 하지 않는 것**(2026-08-28 사용자 확정) — 임의로 넣지 말 것:
      · f_pu_set_mat_stock (총재고 PU_T_MAT_STOCK) = 옛날 잔재, 현재 미사용
      · PU_T_SET_GAGONG_STOCK 세트재고 차감 = 웹은 **생산실적 등록 시점**에 처리
        (세트재고와 가공이동재고(세트)는 서로 다른 개념 — 실적 테스트로 확인 예정)
    마감 가드 유지."""
    ymd = str(payload.get("ymd") or "").strip()
    rows = payload.get("rows", []) or []
    in_wh = str(payload.get("in_wh") or "IS0001").strip() or "IS0001"
    _usr = (str(payload.get("user") or "").strip() or "web")[:30]
    if not ymd or len(ymd) < 6:
        raise HTTPException(400, "입고일자 필요")

    def _g(r, *keys):
        """프론트/구버전 키 호환 — MAT_CODE|item, qty, MAINT_GROUP_SEQ|group_seq …"""
        for k in keys:
            v = r.get(k)
            if v not in (None, ""):
                return v
        return None

    cn = _nx(); cur = cn.cursor()
    try:
        if _closed(cur, ymd, "MAT"):
            return {"ok": False, "errors": [f"마감월({_ym(ymd)}) 입고 불가"]}
        errs = []; saved = 0
        for idx, r in enumerate(rows, 1):
            item = str(_g(r, "MAT_CODE", "item") or "").strip()
            qty = float(_g(r, "qty", "MAINT_QTY") or 0)
            if not item: errs.append(f"{idx}행: 자도번 없음"); continue
            if qty <= 0: errs.append(f"{idx}행: 입고수량>0 필요"); continue
            cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", item)
            if not cur.fetchone(): errs.append(f"{idx}행: 미등록품목({item})")
        if errs:
            return {"ok": False, "errors": errs}

        gseqs = set()
        for r in rows:
            item = str(_g(r, "MAT_CODE", "item") or "").strip()
            qty = float(_g(r, "qty", "MAINT_QTY") or 0)
            if not item or qty <= 0: continue
            gseq = _g(r, "MAINT_GROUP_SEQ", "group_seq")
            wh = str(_g(r, "TO_GAGONG_PROC_CODE", "to_gagong", "wh") or in_wh).strip()
            frm = _g(r, "GAGONG_PROC_CODE", "gagong")
            upper = _g(r, "ITEM_CODE", "upper")
            # ① 원장  ★채번 경쟁 방지 — 위 stock_save 와 같은 이유(PK 중복 → 500).
            cur.execute("""SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WITH(UPDLOCK, HOLDLOCK)
                            WHERE MAINT_YMD=?""", ymd)
            seq = int(cur.fetchone()[0] or 1)
            cur.execute("""INSERT INTO nx.stock_ledger
                (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_GROUP_SEQ,MAINT_TAG,GAGONG_PROC_CODE,TO_GAGONG_PROC_CODE,MAT_CODE,ITEM_CODE,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                VALUES('MAT',?,?,?, 'C', ?,?,?,?,?, ?, ?, GETDATE())""",
                ymd, seq, (int(gseq) if gseq is not None else None), (frm or None), wh,
                item, (upper or None), qty, (r.get("remarks") or "가공이동입고"), _usr)
            # ② 자재재고 증가(버킷 = 자재 · 파트창고코드 · 입고창고)
            cur.execute("""SELECT TOP 1 ISNULL(NULLIF(RTRIM(in_cust_code),''),'Z99990')
                             FROM nx.PR_M_PROC_GAGONG WHERE RTRIM(GAGONG_PROC_CODE)=?""", wh)
            _row = cur.fetchone()
            _cc = (str(_row[0]).strip() if _row else "Z99990") or "Z99990"
            try:
                cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                                  UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW='gagongmove'
                                WHERE MAT_CODE=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                            qty, _usr, item, _cc, wh)
                if cur.rowcount == 0:
                    cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK_WH(MAT_CODE,CUST_CODE,GAGONG_PROC_CODE,STOCK_QTY,
                                      UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                    VALUES(?,?,?,?,?,GETDATE(),'gagongmove')""", item, _cc, wh, qty, _usr)
            except Exception: pass
            # ②-b ★자재 입출고이력(nx.PU_T_STOCK_MAINT)에도 기록 — 2026-08-28 추가.
            #   「자재 입출고현황」·자재수불장이 **이 미러 테이블**을 읽는다. 여기 없으면
            #   재고는 늘었는데 화면 이력에 안 나온다(실측: MJU00813901 입고 40 반영됐으나
            #   현황 화면 0건). 레거시도 같은 곳에 INSERT_WINDOW='w_pu_stock_057_2' 로 남긴다.
            #   ★WH_CUST_CODE·GAGONG_PROC_CODE 필수 — 공백이면 창고필터에서 빠져 조회 누락.
            try:
                cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
                _msq = int(cur.fetchone()[0] or 20000)
                # ★컬럼 규칙 = 레거시 w_pu_stock_057_2 실측(2026-08-28):
                #     GAGONG_PROC_CODE   = 입고창고(IS0001)
                #     TO_GAGONG_PROC_CODE= 출발 가공파트(P0001)  ← 「생산입출고현황」이 이걸 파트로 집계
                #     CUST_CODE·WH_CUST_CODE = **빈값**(넣으면 화면 거래처칸에 '피앤씨창고'가 뜬다)
                cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
                        (MAINT_YMD,MAINT_SEQ,MAINT_GROUP_SEQ,MAINT_TAG,MAT_CODE,ITEM_CODE,MAINT_QTY,REMARKS,
                         GAGONG_PROC_CODE,TO_GAGONG_PROC_CODE,
                         INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                         UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?, 'C', ?,?,?,?, ?,?, ?,GETDATE(),'gagongmove', ?,GETDATE(),'gagongmove')""",
                    ymd, _msq, (int(gseq) if gseq is not None else None),
                    item, (upper or None), qty, (r.get("remarks") or "가공이동입고"),
                    wh, (frm or None), _usr, _usr)
            except Exception: pass
            # ③ ★가공창고 재고 **차감** — 레거시 원문 그대로(2026-08-28 실측으로 확정).
            #     f_pr_set_mat_stock_wh(win, ymd, ls_to_gagong_proc_code, mat, -ld_maint_qty)
            #   가공창고(P0001)에서 자재창고(IS0001)로 **옮기는** 것이므로 출발지는 줄어야 한다.
            #   ※한 번 뺐다가 되살림 — 「생산입출고현황」에서 MJU00813901 가공창고 재고가
            #     40 그대로 남아 있었다(자재창고는 +40 됐는데 출발지가 안 줄어 이중계상).
            #     정상 패턴은 그 화면 8/11·8/21 처럼 「가공부품이동」으로 출고가 찍히는 것.
            #   ※출발 파트 = 전표의 GAGONG_PROC_CODE(frm). 없으면 건너뛴다.
            _from_wh = str(frm or "").strip()
            if _from_wh:
                try:
                    cur.execute("""UPDATE nx.PR_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)-?,
                                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW='gagongmove'
                                    WHERE MAT_CODE=? AND RTRIM(PART_CODE)=?""", qty, _usr, item, _from_wh)
                    if cur.rowcount == 0:
                        cur.execute("""INSERT INTO nx.PR_T_MAT_STOCK_WH(MAT_CODE,PART_CODE,STOCK_QTY,
                                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                        VALUES(?,?,?,?,GETDATE(),'gagongmove')""", item, _from_wh, -qty, _usr)
                except Exception: pass
                # ⛔PR_T_STOCK_MAINT_MAT 에는 넣지 않는다(2026-08-28 실측 확정).
                #   「생산입출고현황」의 '가공부품이동' 출고는 **PU_T_STOCK_MAINT tag='C' 한 행**에서
                #   나온다(live_api._prodinout line 866: TO_GAGONG_PROC_CODE 를 파트로 집계).
                #   레거시 w_pu_stock_057_2 도 PU_T_STOCK_MAINT 에만 쓰고 여기엔 안 쓴다(실측).
                #   여기 또 넣으면 '생산사용'이 하나 더 생겨 **이중 출고**가 된다
                #   (실증: MJU00813901 가공창고 40 → 가공부품이동 40 + 생산사용 40 = −40).
            # ④-1 전표행에 입고결과 기록
            if gseq is not None:
                gseqs.add(int(gseq))
                try:
                    cur.execute("""UPDATE nx.PU_T_STOCK_MAINT_GAGONG_MOVE
                                      SET IN_MAINT_YMD=?, IN_MAINT_SEQ=?, IN_MAINT_QTY=ISNULL(IN_MAINT_QTY,0)+?
                                    WHERE MAINT_GROUP_SEQ=? AND MAT_CODE=?""", ymd, seq, qty, int(gseq), item)
                except Exception: pass
            saved += 1

        # ④-2 전표 완료표시 (전표 단위 1회)
        # ※가공세트재고(PU_T_SET_GAGONG_STOCK) 차감은 **여기서 하지 않는다**(2026-08-28 사용자 확정).
        #   레거시 057_2 에는 MERGE 로 차감이 있으나, 웹은 **생산실적 등록 시점**에 차감한다.
        #   여기서 또 빼면 이중차감이 된다.
        for gs in gseqs:
            try:
                cur.execute("""UPDATE nx.PU_T_STOCK_MAINT_GAGONG_MOVE
                                  SET IN_CONFIRM_FLAG='1', IN_CONFIRM_DATETIME=GETDATE(), IN_CONFIRM_USER_ID=?
                                WHERE MAINT_GROUP_SEQ=?""", _usr, gs)
            except Exception: pass
        stock_changed("stock_save")           # ★재고 변경 → 수불장 캐시 버림 (main #97)
        return {"ok": True, "count": saved, "sheets": sorted(gseqs)}
    finally:
        cn.close()

# ★로컬 _closed 제거(2026-08-28) — 구 stock_close 만 보던 사본이 common 의 공용 게이트를 가렸다.
#   이제 common._closed(=_lock_msg 위임)를 그대로 쓴다.

# ===================== ★Phase5: nx 재고 월마감 스냅샷 (STOCK_POINT별 기초→기말=기초+ΣMAINT) =====================
# 기말 스냅샷=다음달 기초 연속성·마감후 파생 고정. 잠금=기존 nx.stock_close(ym) 플래그 재사용(옵션).
# ★사고 재발방지: stock_ledger 무삭제. 재계산은 자기생성 근거키(ym+point)의 stock_close_snap만 갱신.
@router.post("/api/stockclose/run")
def stockclose_run(payload: dict = Body(...)):
    """월마감 실행: (ym, point) 기말 스냅샷 산출·저장(set-based, 고속). 기초=단일원장 누적(<ym01, =직전월기말 동치). 기말=기초+입−출.
    lock=true면 nx.stock_close(ym) 잠금 플래그 set(기존 가드 발동=이전 원장 쓰기잠금). 멱등(같은 ym+point 재실행=재계산).
    ★사고 재발방지: stock_ledger 무삭제. 정리는 자기생성 근거키(ym+point)의 stock_close_snap만."""
    ym = str(payload.get("ym", "")).strip()
    point = str(payload.get("point", "")).strip().upper()
    lock = bool(payload.get("lock", False))
    user = (str(payload.get("user", "")).strip() or "web")[:30]
    if len(ym) != 4 or point not in ("MAT", "PRD", "ASY", "RDY", "SAG"):
        raise HTTPException(400, "ym=YYMM(4자)·point=MAT/PRD/ASY/RDY/SAG 필수")
    # ★C4(2026-08-27) 사용중단 — 마감관리(/api/close/*)로 일원화.
    #   MAT/PRD/ASY 는 새 마감이 정본이며, 이 API 는 (a)MAT 을 stock_ledger 로 계산해 45.88% 부정확
    #   (b)nx.stock_close 를 세워 새 잠금(nx.period_close)과 이중 잠금원이 된다 → 차단.
    #   RDY/SAG 는 아직 대체 스냅샷이 없어 스냅샷 산출만 남겨두되 잠금(lock)은 금지한다.
    if point in ("MAT", "PRD", "ASY"):
        raise HTTPException(410, f"사용중단된 API 입니다({point}) — 마감관리 /api/close/run 을 사용하세요"
                                 f" (domain MAT=자재 · PRD=생산 · SAL=영업).")
    if lock:
        raise HTTPException(400, "잠금(lock)은 마감관리 /api/close/run 으로 일원화되었습니다"
                                 " — 여기서는 스냅샷 산출만 가능합니다.")
    y01, y99 = ym + "01", ym + "99"
    cn = _nx(); cur = cn.cursor()
    try:
        # 자기생성 근거키(ym+point) 재계산분만 제거(멱등 — 이 마감의 스냅샷만)
        cur.execute("DELETE FROM nx.stock_close_snap WHERE ym=? AND stock_point=?", ym, point)
        # set-based: RTRIM 정규화 GROUP BY(후행공백 PK중복 방지), 기초=Σ(<y01)·입출=당월. 기말=기초+입−출.
        cur.execute("""INSERT INTO nx.stock_close_snap(ym,stock_point,item_key,gpc,cust,base_qty,in_qty,out_qty,end_qty,close_user,close_dt)
            SELECT ?, ?, LEFT(t.k,40), LEFT(t.g,20), LEFT(t.c,10), t.base, t.inq, t.outq, t.base+t.inq-t.outq, ?, GETDATE()
            FROM (
              SELECT COALESCE(NULLIF(RTRIM(L.MAT_CODE),''),RTRIM(L.ITEM_CODE)) k,
                     RTRIM(ISNULL(L.GAGONG_PROC_CODE,'')) g, RTRIM(ISNULL(L.CUST_CODE,'')) c,
                     SUM(CASE WHEN L.MAINT_YMD<? THEN L.MAINT_QTY ELSE 0 END) base,
                     SUM(CASE WHEN L.MAINT_YMD BETWEEN ? AND ? AND L.MAINT_QTY>0 THEN L.MAINT_QTY ELSE 0 END) inq,
                     SUM(CASE WHEN L.MAINT_YMD BETWEEN ? AND ? AND L.MAINT_QTY<0 THEN -L.MAINT_QTY ELSE 0 END) outq
              FROM nx.stock_ledger L WHERE L.STOCK_POINT=?
              GROUP BY COALESCE(NULLIF(RTRIM(L.MAT_CODE),''),RTRIM(L.ITEM_CODE)), RTRIM(ISNULL(L.GAGONG_PROC_CODE,'')), RTRIM(ISNULL(L.CUST_CODE,''))
            ) t
            WHERE (t.base<>0 OR t.inq<>0 OR t.outq<>0) AND t.k IS NOT NULL AND t.k<>''""",
            ym, point, user, y01, y01, y99, y01, y99, point)
        n = cur.rowcount
        if lock:  # 기존 nx.stock_close(ym) 플래그 재사용(신설 아님) — 이전 원장 쓰기잠금 발동
            cur.execute("IF EXISTS(SELECT 1 FROM nx.stock_close WHERE ym=?) UPDATE nx.stock_close SET close_flag=1,close_user=?,close_dt=GETDATE() WHERE ym=? ELSE INSERT INTO nx.stock_close(ym,close_flag,close_user,close_dt) VALUES(?,1,?,GETDATE())", ym, user, ym, ym, user)
        cur.execute("SELECT ISNULL(SUM(end_qty),0) FROM nx.stock_close_snap WHERE ym=? AND stock_point=?", ym, point)
        endsum = float(cur.fetchone()[0] or 0)
        stock_changed("stockclose")           # ★스냅샷 확정 → 수불장 캐시 버림
        return {"ok": True, "ym": ym, "point": point, "rows": n, "end_total": round(endsum, 3),
                "base_from": "단일원장 누적(<ym01 = 직전월기말 동치)", "locked": lock}
    finally:
        cn.close()

@router.get("/api/stockclose/status")
def stockclose_status(ym: str = Query(""), point: str = Query("")):
    """마감 현황: 스냅샷 요약(ym·point별 행수·기말합) + 잠금 플래그."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = []; p = []
        if ym.strip(): w.append("ym=?"); p.append(ym.strip())
        if point.strip(): w.append("stock_point=?"); p.append(point.strip().upper())
        wh = ("WHERE " + " AND ".join(w)) if w else ""
        cur.execute(f"""SELECT ym, stock_point, COUNT(*) rows, ISNULL(SUM(end_qty),0) end_total, MAX(close_dt) close_dt
            FROM nx.stock_close_snap {wh} GROUP BY ym, stock_point ORDER BY ym DESC, stock_point""", *p)
        snaps = [{"ym": r[0], "point": r[1], "rows": int(r[2]), "end_total": round(float(r[3] or 0), 3),
                  "close_dt": str(r[4] or "")[:19]} for r in cur.fetchall()]
        cur.execute("SELECT ym, close_flag, close_user, close_dt FROM nx.stock_close ORDER BY ym DESC")
        locks = [{"ym": str(r[0]).strip(), "locked": bool(r[1]), "user": r[2], "dt": str(r[3] or "")[:19]} for r in cur.fetchall()]
        return {"snapshots": snaps, "locks": locks}
    finally:
        cn.close()

def _mat_mirror_edit(cur, ymd, mat, cc, gp, tag, old_q, new_q, window):
    """★F1: 자재 원장(stock_ledger MAT) 수정/삭제 시 조회정본(자재재고 PU_T_MAT_STOCK_WH·자재수불장 PU_T_STOCK_MAINT)도 동반 반영.
       save는 3곳 반영하나 update/delete는 원장만 고쳐 수불장·재고가 stale(F1)였음. old_q→new_q(삭제=new_q=0).
       ★F2: PU_T_STOCK_MAINT.MAINT_TAG=CHAR(1) → 반품 'RT'(2글자)는 'T'(자재창고반품)로 매핑(truncation 방지)."""
    mat = str(mat or "").strip()
    if not mat: return
    # ★★자재재고 버킷의 CUST_CODE 는 **창고 소유주**('Z99990' 고정)이지 원장의 거래처(매입처)가 아니다.
    #   실측(2026-09-01): 라이브 PU_T_MAT_STOCK_WH 7,762행이 **전부** Z99990 단일값이다.
    #   종전엔 원장 CUST_CODE 를 그대로 버킷키로 썼다 → UPDATE 가 기존 행(Z99990)을 못 찾아
    #   rowcount=0 → **매입처 코드로 새 행을 INSERT** → 같은 (자재,창고)에 2행이 생겼다.
    #     AJR77144307-STS : [Z99990·IS0001 = 92] + [2005·IS0001 = **-4**]  ← 음수 유령행
    #   재고조회는 창고 합을 보므로 값이 조용히 틀어지고, 음수차단 규칙도 이 행은 못 막는다.
    #   save 경로는 이미 같은 이유로 issue 에서 Z99990 을 고정하고 있었다(line 415) —
    #   update/delete 에만 그 처리가 빠져 있었다. 버킷키는 여기서 일원화한다.
    _led_cc = (str(cc or "").strip() or "Z99990")   # 수불장 전표에 남길 거래처(원장 값 유지)
    cc = "Z99990"                                    # 재고 버킷키 = 창고 소유주 고정
    gp = (str(gp or "").strip() or "IS0001")
    mtag = "T" if str(tag).strip() == "RT" else (str(tag or "").strip()[:1] or "2")
    dq = new_q - old_q
    # 1) 자재재고 잔액(버킷=MAT_CODE·CUST_CODE·GAGONG_PROC_CODE) 델타 반영
    try:
        cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
              UPDATE_USER_ID='web',UPDATE_DATETIME=GETDATE(),UPDATE_WINDOW=?
              WHERE MAT_CODE=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""", dq, window, mat, cc, gp)
        if cur.rowcount == 0 and abs(dq) > 1e-9:
            cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK_WH(MAT_CODE,CUST_CODE,GAGONG_PROC_CODE,STOCK_QTY,
                  UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW) VALUES(?,?,?,?,'web',GETDATE(),?)""", mat, cc, gp, dq, window)
    except Exception: pass
    # 2) 자재수불장: save가 남긴 web행(INSERT_WINDOW='stockadjust') 찾으면 in-place 수정/삭제, 못찾으면 보정행 insert
    try:
        cur.execute("""SELECT TOP 1 MAINT_YMD,MAINT_SEQ FROM nx.PU_T_STOCK_MAINT
              WHERE MAINT_YMD=? AND MAT_CODE=? AND ABS(MAINT_QTY-?)<0.0001 AND MAINT_TAG=?
                AND ISNULL(WH_CUST_CODE,'')=? AND ISNULL(GAGONG_PROC_CODE,'')=? AND INSERT_WINDOW='stockadjust'
              ORDER BY MAINT_SEQ DESC""", ymd, mat, old_q, mtag, _led_cc, gp)
        hit = cur.fetchone()
        if hit and abs(new_q) < 1e-9:            # 삭제 → 그 web행 삭제(내역서 사라짐)
            cur.execute("DELETE FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ=?", hit[0], hit[1])
        elif hit:                                 # 수정 → 그 web행 수량 갱신
            cur.execute("""UPDATE nx.PU_T_STOCK_MAINT SET MAINT_QTY=?,UPDATE_USER_ID='web',UPDATE_DATETIME=GETDATE(),UPDATE_WINDOW=?
                  WHERE MAINT_YMD=? AND MAINT_SEQ=?""", new_q, window, hit[0], hit[1])
        elif abs(dq) > 1e-9:                       # 원본 못찾음 → 보정(델타)행 기록(잔액·수불합 정합 유지)
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
            nsq = int(cur.fetchone()[0] or 1)
            cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
                  WH_CUST_CODE,GAGONG_PROC_CODE,INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                  VALUES(?,?,?,?,?,?,?,?,?,'web',GETDATE(),?,'web',GETDATE(),?)""",
                ymd, nsq, mtag, _led_cc, mat, dq, "원장수정보정", _led_cc, gp, window, window)
    except Exception: pass

@router.post("/api/stock/update")
def stock_update(payload: dict = Body(...)):
    """기존 원장행 수정(값 필드만). 키(MAINT_YMD,MAINT_SEQ)·자도번 불변, 저장부호 보존.
    가드: 대상존재·마감월 잠금·수량>0·음수재고 유발 차단."""
    screen = str(payload.get("screen", "")).strip()
    sc = STOCK_SCREENS.get(screen)
    if not sc:
        raise HTTPException(400, "screen 오류")
    ymd = str(payload.get("MAINT_YMD", "")).strip()
    try:
        seq = int(payload.get("MAINT_SEQ"))
    except (TypeError, ValueError):
        raise HTTPException(400, "MAINT_SEQ 오류")
    qty = float(payload.get("qty") or 0)
    _usr = (str(payload.get("user") or "").strip() or "web")[:20]   # ★갱신자 실명(2026-08-28)
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT MAT_CODE, MAINT_QTY, ISNULL(CUST_CODE,''), ISNULL(GAGONG_PROC_CODE,''), ISNULL(MAINT_TAG,'') FROM nx.stock_ledger WHERE MAINT_YMD=? AND MAINT_SEQ=?", ymd, seq)
        row = cur.fetchone()
        if not row:
            return {"ok": False, "errors": [f"대상 없음 ({ymd}/{seq})"]}
        mat = str(row[0] or "").strip()
        old_stored = float(row[1] or 0)
        old_cc = str(row[2] or "").strip(); old_gp = str(row[3] or "").strip(); old_tag = str(row[4] or "").strip()
        errs = []
        if _closed(cur, ymd, "MAT"):
            errs.append(f"마감월({_ym(ymd)}) 편집 불가")
        if screen == "adjust":
            # 조정=부호 그대로(불량·개발불출 −, 장부수정 ±). 음수재고는 아래 new_sum 검증에서 차단.
            if qty == 0:
                errs.append("조정수량은 0일 수 없습니다(증가 +, 감소 −)")
            new_stored = qty
        else:
            if qty <= 0:
                errs.append("수량은 0보다 커야 함")
            # 저장부호 보존(기존 음수→음수, 0이면 화면부호)
            neg = old_stored < 0 or (old_stored == 0 and sc["sign"] == -1)
            new_stored = -abs(qty) if neg else abs(qty)
        # 음수재고 유발 차단(악화 시에만)
        cur.execute("SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE MAT_CODE=?", mat)
        cur_sum = float(cur.fetchone()[0] or 0)
        new_sum = cur_sum - old_stored + new_stored
        if new_sum < 0 and new_sum < cur_sum:
            errs.append(f"음수재고 유발 ({mat} 결과재고 {new_sum:g} < 0)")
        if errs:
            return {"ok": False, "errors": errs}
        # ★단가 수정(2026-08-28 사용자 요청) — 별도 권한으로 게이트할 예정이나 현재는 개방.
        #   CLAUDE.md §1-2 는 "단가는 마감 때만 수정"이지만 레거시 w_pu_stock_055 는
        #   입고 단가를 직접 고칠 수 있어(MASTER단가 버튼 옆 입력칸) 같은 조작감을 맞춘다.
        #   cost 가 payload 에 없으면 기존값 유지(다른 화면·경로가 단가를 덮지 않게).
        #   금액·부가세는 수량×단가로 재계산(레거시 동일).
        _has_cost = ("MAINT_COST" in payload) and (payload.get("MAINT_COST") is not None)
        if _has_cost:
            try:
                _cost = float(payload.get("MAINT_COST") or 0)
            except (TypeError, ValueError):
                _cost = 0.0
            if _cost < 0:
                return {"ok": False, "errors": ["단가는 0 이상이어야 합니다"]}
            _amt = abs(new_stored) * _cost
            cur.execute("""UPDATE nx.stock_ledger
                SET MAINT_QTY=?, MAINT_TAG=?, CUST_CODE=?, GAGONG_PROC_CODE=?, REMARKS=?,
                    MAINT_COST=?, MAINT_AMT=?, MAINT_VAT=?,
                    UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE()
                WHERE MAINT_YMD=? AND MAINT_SEQ=?""",
                new_stored, (str(payload.get("MAINT_TAG") or sc["tags"][0]).strip()),
                (str(payload.get("CUST_CODE") or "").strip() or None),
                (str(payload.get("GAGONG_PROC_CODE") or "").strip() or None),
                (str(payload.get("REMARKS") or "").strip() or None),
                _cost, _amt, round(_amt * 0.1),
                _usr, ymd, seq)
        else:
            cur.execute("""UPDATE nx.stock_ledger
                SET MAINT_QTY=?, MAINT_TAG=?, CUST_CODE=?, GAGONG_PROC_CODE=?, REMARKS=?,
                    UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE()
                WHERE MAINT_YMD=? AND MAINT_SEQ=?""",
                new_stored, (str(payload.get("MAINT_TAG") or sc["tags"][0]).strip()),
                (str(payload.get("CUST_CODE") or "").strip() or None),
                (str(payload.get("GAGONG_PROC_CODE") or "").strip() or None),
                (str(payload.get("REMARKS") or "").strip() or None),
                _usr, ymd, seq)
        # ★F1: 원장만 고치면 자재수불장·자재재고(조회정본) stale → 미러 동반 반영
        _mat_mirror_edit(cur, ymd, mat, old_cc, old_gp, old_tag, old_stored, new_stored, "stockupdate")
        stock_changed("stock_update")         # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "stored_qty": new_stored, "stock": new_sum}
    finally:
        cn.close()

@router.post("/api/stock/delete")
def stock_delete(payload: dict = Body(...)):
    """기존 원장행 삭제. 가드: 대상존재·마감월 잠금·삭제 시 음수재고 유발 차단(입고행 삭제로 재고<0 방지)."""
    ymd = str(payload.get("MAINT_YMD", "")).strip()
    try:
        seq = int(payload.get("MAINT_SEQ"))
    except (TypeError, ValueError):
        raise HTTPException(400, "MAINT_SEQ 오류")
    cn = _nx_tx(); cur = cn.cursor()   # ★원자화(2026-08-31 데이터손실 사고 후속): 원장삭제+미러잔액 되돌림을 원자로.
    try:                                #   autocommit이면 미러 되돌림 중간실패 시 원장만 삭제·커밋돼 재고 영구 어긋남.
        cur.execute("SELECT MAT_CODE, MAINT_QTY, ISNULL(CUST_CODE,''), ISNULL(GAGONG_PROC_CODE,''), ISNULL(MAINT_TAG,'') FROM nx.stock_ledger WHERE MAINT_YMD=? AND MAINT_SEQ=?", ymd, seq)
        row = cur.fetchone()
        if not row:
            return {"ok": False, "errors": [f"대상 없음 ({ymd}/{seq})"]}
        mat = str(row[0] or "").strip()
        old_stored = float(row[1] or 0)
        old_cc = str(row[2] or "").strip(); old_gp = str(row[3] or "").strip(); old_tag = str(row[4] or "").strip()
        errs = []
        if _closed(cur, ymd, "MAT"):
            errs.append(f"마감월({_ym(ymd)}) 삭제 불가")
        cur.execute("SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE MAT_CODE=?", mat)
        cur_sum = float(cur.fetchone()[0] or 0)
        new_sum = cur_sum - old_stored
        if new_sum < 0 and new_sum < cur_sum:
            errs.append(f"음수재고 유발 ({mat} 삭제 후 재고 {new_sum:g} < 0)")
        if errs:
            return {"ok": False, "errors": errs}
        cur.execute("DELETE FROM nx.stock_ledger WHERE MAINT_YMD=? AND MAINT_SEQ=?", ymd, seq)
        n = cur.rowcount
        # ★F1: 삭제도 자재수불장·자재재고(조회정본) 동반 반영(save가 남긴 web행 삭제 + 잔액 되돌림)
        _mat_mirror_edit(cur, ymd, mat, old_cc, old_gp, old_tag, old_stored, 0.0, "stockdelete")
        cn.commit()
        stock_changed("stock_delete")         # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "deleted": n}
    except Exception:
        cn.rollback(); raise   # ★원장삭제+미러 중 하나라도 실패 = 전체 롤백
    finally:
        cn.close()
