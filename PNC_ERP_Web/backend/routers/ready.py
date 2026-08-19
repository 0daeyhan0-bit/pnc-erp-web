# -*- coding: utf-8 -*-
"""ready 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE)

router = APIRouter()

# ===================== 준비실적처리(키팅) (w_pr_input_250/460_new) — 준비등록/취소(nx.ready_ledger) =====================
# 근거: 준비필요=계획−준비완료. 본체키팅=자재무차감(준비마킹). 잔량=SUM 파생. write=nx 신규원장(확정).
@router.get("/api/ready/plan")
def ready_plan(from_ymd: str = Query(""), to_ymd: str = Query(""), line: str = Query(""),
               item: str = Query(""), limit: int = Query(1000)):
    """자재별 정본 자재소요(nx.plan_part_mat) + 준비완료(nx.ready_ledger SUM) + 준비필요=소요−준비.
       ★정본 파이프라인 전환: nx.plan_part(구98%) → nx.plan_part_mat(레거시 STEP5→6→7 100%검증)."""
    def d6(s):
        d = ''.join(c for c in str(s or '') if c.isdigit())
        return d[2:8] if len(d) >= 8 else d
    cn = _conn(); cur = cn.cursor(); nx = _nx(); ncur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd.strip(): w.append("pp.PLAN_YMD>=?"); p.append(d6(from_ymd))
        if to_ymd.strip(): w.append("pp.PLAN_YMD<=?"); p.append(d6(to_ymd))
        if line.strip(): w.append("pp.MAT_WORK_CENTER_CODE=?"); p.append(line.strip())
        if item.strip(): w.append("pp.MAT_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        ncur.execute(f"""SELECT TOP {max(1,min(int(limit),3000))} pp.PLAN_YMD, pp.WORK_ORDER, pp.MAT_CODE, pp.MAT_WORK_CENTER_CODE,
              SUM(CAST(pp.PART_PLAN_QTY AS float)) plan_qty,
              ISNULL((SELECT SUM(rl.MAINT_QTY) FROM nx.stock_ledger rl WHERE rl.STOCK_POINT='RDY' AND rl.ITEM_CODE=pp.MAT_CODE AND ISNULL(rl.WORK_ORDER,'')=ISNULL(pp.WORK_ORDER,'') AND ISNULL(rl.INPUT_YMD,'')=ISNULL(pp.PLAN_YMD,'')),0) ready_qty
            FROM nx.plan_part_mat pp WHERE {' AND '.join(w)}
            GROUP BY pp.PLAN_YMD, pp.WORK_ORDER, pp.MAT_CODE, pp.MAT_WORK_CENTER_CODE
            ORDER BY pp.PLAN_YMD DESC, pp.MAT_CODE""", *p)
        rows = []; parts = set()
        for r in ncur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            pq = float(r[4] or 0); rq = float(r[5] or 0)
            rows.append({"plan_ymd": g(0), "work_order": g(1), "item_code": g(2), "work_center": g(3),
                         "plan_qty": pq, "ready_qty": rq, "need_qty": round(max(pq - rq, 0), 2)})
            parts.add(g(2))
        nm = {}; pl = [x for x in parts if x]
        for i in range(0, len(pl), 900):
            ch = pl[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for a, b in cur.fetchall(): nm[str(a).strip()] = b
        for x in rows: x["nm"] = nm.get(x["item_code"], "")
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close(); nx.close()

@router.get("/api/ready/setcheck")
def ready_setcheck(item: str = Query(...), ymd: str = Query(""), qty: float = Query(0)):
    """★키팅 [확인] 팝업(레거시 w_pr_input_466) — 도번의 자도번별 사용수량·재고·세트가능수량·협력사.
       ★BOM 소스 = CS_M_ITEM_BOM(웹 정본). 레거시 화면은 PR_M_ITEM_BOM을 쓰지만 실측 결과 두 테이블이
         동일(자도번·USE_QTY·KITTING_FLAG 일치)이라, 웹 다른 화면(bom.py 등)과 기준을 통일함.
       필터(레거시 dw_pr_master_120_l02 조건 이식):
         · 유효일자: FROM_APPLY_YMD<=ymd<=TO_APPLY_YMD
         · ★KITTING_FLAG='1' 인 것만(=키팅대상). '0'은 팝업 제외(사내SUB 등).
         · ★VIR_ITEM_FLAG='1'(가상품목) 제외 — 도면에는 있으나 실제 사용 안 하는 품번.
         · USE_QTY>0 만(사용량 0은 소요 없음 → 제외)
         · ★재고 = 자재 입출고현황 화면(/api/live/matinout)과 동일 산식 = 전월말 스냅샷 + 수불누적.
           (구버전은 pu_t_mat_stock 스냅샷을 썼는데 그 값은 음수 누적이라 실제 재고와 달랐음 — 2026-08-18 교정)
         · 협력사 = work_code 있으면 pr_m_work.work_desc, 없으면 cm_m_cust.cust_desc
       세트가능수량 = FLOOR(재고 ÷ 사용수량). 화면 상단 '생산준비 세트수량'=qty(선택 셀 계획수량).
       ★조회 전용(읽기). 실제 준비등록은 /api/ready/register."""
    it = item.strip()
    d6 = ''.join(c for c in str(ymd or '') if c.isdigit())
    d6 = d6[2:8] if len(d6) >= 8 else (d6 or datetime.now().strftime('%y%m%d'))
    cn = _conn(); cur = cn.cursor()
    try:
        # 1) BOM 자도번(키팅대상)
        cur.execute("""
            SELECT a.MAT_CODE,
                   CAST(ISNULL(a.USE_QTY,0) AS float) use_qty,
                   ISNULL(CASE WHEN m.work_code>'' THEN (SELECT work_desc FROM PARTNER_ERP_TEST3.nx.pr_m_work WHERE work_code=m.work_code)
                               ELSE (SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust WHERE cust_code=m.in_cust_code) END,'') cust_desc,
                   ISNULL(m.ITEM_DESC,'') nm
              FROM PARTNER_ERP_TEST3.nx.CS_M_ITEM_BOM a WITH(NOLOCK)
              JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM m WITH(NOLOCK) ON m.ITEM_CODE=a.MAT_CODE
             WHERE a.ITEM_CODE=?
               AND a.FROM_APPLY_YMD<=? AND a.TO_APPLY_YMD>=?
               AND ISNULL(a.KITTING_FLAG,'0')='1'
               AND ISNULL(a.VIR_ITEM_FLAG,'0')<>'1'
               AND CAST(ISNULL(a.USE_QTY,0) AS float) > 0
             ORDER BY a.MAT_CODE""", it, d6, d6)
        bom = [{"mat": str(r[0] or '').strip(), "use_qty": float(r[1] or 0),
                "cust": str(r[2] or '').strip(), "nm": str(r[3] or '').strip()} for r in cur.fetchall()]
        # 2) ★재고 = nx 스냅샷(PU_T_MAT_STOCK_WH) + 웹 원장 미반영분(nx.stock_ledger)
        #    · 스냅샷: 창고=Z99990 · 파트창고=IS0001 → 자재 입출고현황 화면의 재고와 동일.
        #      ※라이브 PARTNER_ERP.dbo 쪽은 값이 오래돼(11588O-1=5,648) 화면(714)과 다름 → nx 사용.
        #    · ★웹에서 한 재고조정/입고는 nx.stock_ledger(STOCK_POINT='MAT')에만 쌓이고 스냅샷은 갱신되지 않음
        #      (예: MHH62041502 조정 +100 → 원장엔 있으나 스냅샷은 0). 그래서 스냅샷 갱신시각 이후의
        #      원장분을 더해줘야 웹에서 조정한 재고가 팝업에 즉시 반영됨. (2026-08-18 확인)
        stkmap = {}
        if bom:
            mats = [b["mat"] for b in bom]
            for i in range(0, len(mats), 900):
                ch = mats[i:i+900]; ph = ",".join("?" * len(ch))
                cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), SUM(CAST(STOCK_QTY AS float))
                                  FROM PARTNER_ERP_TEST3.nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                                 WHERE MAT_CODE IN ({ph}) AND CUST_CODE='Z99990' AND ISNULL(GAGONG_PROC_CODE,'')='IS0001'
                                 GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))""", *ch)
                for r in cur.fetchall():
                    stkmap[str(r[0] or '').strip()] = float(r[1] or 0)
            # 웹 원장 가산분: 스냅샷 최종갱신(UPDATE_DATETIME) 이후 INSERT 된 MAT 원장만 더함(이중계상 방지)
            nx2 = _nx(); ncur = nx2.cursor()
            try:
                for i in range(0, len(mats), 900):
                    ch = mats[i:i+900]; ph = ",".join("?" * len(ch))
                    ncur.execute(f"""
                        SELECT UPPER(LTRIM(RTRIM(l.MAT_CODE))), SUM(CAST(l.MAINT_QTY AS float))
                          FROM nx.stock_ledger l WITH(NOLOCK)
                          LEFT JOIN nx.PU_T_MAT_STOCK_WH s WITH(NOLOCK)
                                 ON s.MAT_CODE=l.MAT_CODE AND s.CUST_CODE='Z99990' AND ISNULL(s.GAGONG_PROC_CODE,'')='IS0001'
                         WHERE l.STOCK_POINT='MAT' AND l.MAT_CODE IN ({ph})
                           AND l.INSERT_DATETIME > ISNULL(s.UPDATE_DATETIME,'1900-01-01')
                         GROUP BY UPPER(LTRIM(RTRIM(l.MAT_CODE)))""", *ch)
                    for r in ncur.fetchall():
                        k = str(r[0] or '').strip()
                        stkmap[k] = stkmap.get(k, 0.0) + float(r[1] or 0)
            except Exception:
                pass
            finally:
                nx2.close()
        rows = []
        for b in bom:
            use = b["use_qty"]; stk = stkmap.get(b["mat"].upper(), 0.0)
            able = int(stk // use) if use > 0 else 0
            rows.append({"mat": b["mat"], "use_qty": use, "stock_qty": stk,
                         "set_able": able, "cust": b["cust"], "nm": b["nm"]})
        # 세트가능수량 = 자도번 중 최소값(하나라도 모자라면 그만큼만 가능). 자재 없으면 0.
        # ★용접봉(RAC…) 등 투입파트가 아직 공용창고로 안 바뀐 품목은 그대로 리스트에 포함되며,
        #   재고가 음수면 세트가능도 음수 → 실적이 안 잡히는 게 현 시점 정상 동작(사용자 확인 2026-08-18).
        set_able = min([x["set_able"] for x in rows]) if rows else 0
        need = float(qty or 0)
        return {"item": it, "ymd": d6, "rows": rows, "cnt": len(rows),
                "set_able": set_able, "need_qty": need,
                "ok": bool(rows) and set_able >= need and need > 0,
                "shortage": [x for x in rows if x["set_able"] < need]}
    finally:
        cn.close()

# ===================== Code128 바코드 생성(스캔 가능) =====================
# ★전표/간판 바코드는 실제 스캐너로 읽혀야 하므로 CSS 막대가 아닌 진짜 Code128 이미지로 생성.
#   외부 패키지(python-barcode) 없이 PIL만으로 인코딩 — Code128 Set B(ASCII 32~126) + 필요시 Set C 압축 없이 단순 구현.
_C128_PAT = [
    "11011001100","11001101100","11001100110","10010011000","10010001100","10001001100","10011001000","10011000100",
    "10001100100","11001001000","11001000100","11000100100","10110011100","10011011100","10011001110","10111001100",
    "10011101100","10011100110","11001110010","11001011100","11001001110","11011100100","11001110100","11101101110",
    "11101001100","11100101100","11100100110","11101100100","11100110100","11100110010","11011011000","11011000110",
    "11000110110","10100011000","10001011000","10001000110","10110001000","10001101000","10001100010","11010001000",
    "11000101000","11000100010","10110111000","10110001110","10001101110","10111011000","10111000110","10001110110",
    "11101110110","11010001110","11000101110","11011101000","11011100010","11011101110","11101011000","11101000110",
    "11100010110","11101101000","11101100010","11100011010","11101111010","11001000010","11110001010","10100110000",
    "10100001100","10010110000","10010000110","10000101100","10000100110","10110010000","10110000100","10011010000",
    "10011000010","10000110100","10000110010","11000010010","11001010000","11110111010","11000010100","10001111010",
    "10100111100","10010111100","10010011110","10111100100","10011110100","10011110010","11110100100","11110010100",
    "11110010010","11011011110","11011110110","11110110110","10101111000","10100011110","10001011110","10111101000",
    "10111100010","11110101000","11110100010","10111011110","10111101110","11101011110","11110101110","11010000100",
    "11010010000","11010011100","11000111010",
]
_C128_STOP = "1100011101011"

@router.get("/api/barcode/qr")
def barcode_qr(text: str = Query(...), scale: int = Query(4), border: int = Query(2)):
    """QR 코드 PNG — 제품스티커(라벨) 스캔용.
       QR 내용 = 도번 + 날짜코드(KPI+연월일) + 일련4  예 AJR30095101KPI68J0145
       ★qrcode 패키지 필요(requirements.txt). 미설치 시 안내문구 이미지를 대신 반환해
         서버가 죽거나 빈칸으로 인쇄되는 일이 없도록 함 — 운영 배포 시 설치 확인할 것."""
    from io import BytesIO
    s = str(text or "").strip()
    if not s:
        raise HTTPException(400, "빈 문자열")
    sc = max(1, min(int(scale or 4), 12))
    bd = max(0, min(int(border or 2), 8))
    try:
        import qrcode
    except ImportError:
        # 미설치 안내 이미지(현장에서 원인 파악 가능하도록)
        from PIL import Image, ImageDraw
        img = Image.new("1", (160, 160), 1)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 159, 159], outline=0)
        d.text((8, 60), "QR module", fill=0)
        d.text((8, 75), "not installed", fill=0)
        d.text((8, 95), "pip install", fill=0)
        d.text((8, 110), "  qrcode", fill=0)
        buf = BytesIO(); img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png",
                        headers={"Cache-Control": "no-store"})
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=sc, border=bd)
    qr.add_data(s); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("1")
    buf = BytesIO(); img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})

@router.get("/api/barcode/code128")
def barcode_code128(text: str = Query(...), h: int = Query(60), scale: int = Query(2), quiet: int = Query(10)):
    """Code128-B 바코드 PNG. 전표/간판 스캔용(스캐너로 읽힘).
       text=인코딩 문자열(ASCII 32~126), h=높이px, scale=모듈폭배율, quiet=여백모듈수."""
    from io import BytesIO
    from PIL import Image
    s = "".join(ch for ch in str(text or "") if 32 <= ord(ch) <= 126)
    if not s:
        raise HTTPException(400, "빈 문자열")
    START_B = 104
    codes = [START_B] + [ord(ch) - 32 for ch in s]
    chk = codes[0]
    for i, c in enumerate(codes[1:], start=1):
        chk += c * i
    codes.append(chk % 103)
    bits = "".join(_C128_PAT[c] for c in codes) + _C128_STOP
    sc = max(1, min(int(scale or 2), 6)); hh = max(20, min(int(h or 60), 200)); q = max(0, min(int(quiet or 10), 30))
    w = (len(bits) + q * 2) * sc
    img = Image.new("1", (w, hh), 1)
    px = img.load()
    x = q * sc
    for b in bits:
        if b == "1":
            for dx in range(sc):
                for y in range(hh):
                    px[x + dx, y] = 0
        x += sc
    buf = BytesIO(); img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})

@router.get("/api/ready/sheet")
def ready_sheet(sheet_no: str = Query(...)):
    """★생산 이동 전표(용접전표) 출력 데이터 — 레거시 w_pr_input_490 인쇄양식(A4 세로) 재현용.
       [전표 레이아웃 매핑]
         자재창고        = WH_GAGONG_PROC_CODE(IS0001) 명칭
         라인(우상단)     = LINE_NO
         전표번호        = SHEET_NO 8자리 0패딩 + 동일값 바코드(Code128)
         완성품 이동창고  = STOCK_GAGONG_PROC_CODE 또는 투입파트 명칭
         상위도번/도번    = UPPER_ITEM_CODE / ITEM_CODE
         수량(대형)       = PLAN_QTY
         품명            = PR_M_ITEM.ITEM_DESC
         생산일자/투입시간 = PLAN_YMD / DS_INPUT_HM
         SEQ표(10줄고정)  = DTL: 파트(GAGONG_PROC_DESC) · 공정(S_WORK 명) · 바코드
       ★조회 전용. nx 우선, 없으면 라이브(읽기) 폴백."""
    sn = str(sheet_no or "").strip()
    if not sn:
        return {"ok": False, "detail": "전표번호 필수"}
    def _fetch(cur, sch):
        cur.execute(f"""SELECT h.SHEET_NO,h.ITEM_CODE,h.ASSY_ITEM_CODE,h.UPPER_ITEM_CODE,h.PLAN_YMD,
                          ISNULL(h.DS_INPUT_HM,'') hm, ISNULL(h.LINE_NO,'') line, h.PLAN_QTY,
                          ISNULL(h.WH_GAGONG_PROC_CODE,'') wh, ISNULL(h.STOCK_GAGONG_PROC_CODE,'') stk,
                          ISNULL(h.PRINT_USER_ID,'') usr, h.PRINT_DATETIME, ISNULL(h.PROD_FIN_FLAG,'0') fin,
                          ISNULL(i.ITEM_DESC,'') nm, ISNULL(i.ITEM_SPEC,'') spec
                        FROM {sch}.PR_T_INDI_WELD_SHEET h WITH(NOLOCK)
                        LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i WITH(NOLOCK) ON i.ITEM_CODE=h.ITEM_CODE
                       WHERE h.SHEET_NO=?""", sn)
        return cur.fetchone()
    nx = _nx(); ncur = nx.cursor()
    cn = _conn(); ccur = cn.cursor()
    try:
        row = _fetch(ncur, "nx"); src = "nx"; dcur = ncur; dsch = "nx"
        if not row:
            row = _fetch(ccur, "PARTNER_ERP.dbo"); src = "live"; dcur = ccur; dsch = "PARTNER_ERP.dbo"
        if not row:
            return {"ok": False, "detail": f"전표 {sn} 없음"}
        g = lambda i: ("" if row[i] is None else str(row[i]).strip())
        # 공정 상세(최대 10줄 표시)
        # 파트명 = PR_M_PROC_GAGONG.GAGONG_PROC_DESC (예: S10 → '10라인(자동은납)') — 캡처와 일치 확인.
        # 공정 표기 = "코드 + 설비명"(예: 'S10 자동은납'). ※PR_M_S_WORK 테이블은 DB에 없음(S_WORK_CODE는 별도코드).
        dcur.execute(f"""SELECT d.PROC_SEQ, ISNULL(d.GAGONG_PROC_CODE,'') gpc,
                            ISNULL(g1.GAGONG_PROC_DESC,'') gpcnm,
                            ISNULL(d.S_WORK_CODE,'') sw,
                            ISNULL(d.MACH_CODE,'') mach, ISNULL(d.JP_PROC_METHOD,'') meth
                          FROM {dsch}.PR_T_INDI_WELD_SHEET_DTL d WITH(NOLOCK)
                          LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG g1 WITH(NOLOCK) ON g1.GAGONG_PROC_CODE=d.GAGONG_PROC_CODE
                         WHERE d.SHEET_NO=? ORDER BY d.PROC_SEQ""", sn)
        # 실적방법: J=용접전표 / G=가간판 / L=라벨(스티커). 그 공정의 실적을 무엇으로 잡는지.
        _METH = {"J": "용접전표", "G": "가간판", "L": "라벨"}
        procs = []
        for r in dcur.fetchall():
            _m = str(r[5] or '').strip()
            procs.append({"seq": int(r[0] or 0), "gpc": str(r[1] or '').strip(),
                          "part_nm": str(r[2] or '').strip(), "s_work": str(r[3] or '').strip(),
                          "mach": str(r[4] or '').strip(), "method": _m,
                          "method_nm": _METH.get(_m, _m)})
        # 창고/파트 명칭
        def _pname(code):
            if not code: return ""
            try:
                ccur.execute("SELECT TOP 1 GAGONG_PROC_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WITH(NOLOCK) WHERE GAGONG_PROC_CODE=?", code)
                x = ccur.fetchone()
                return str(x[0]).strip() if x and x[0] else code
            except Exception:
                return code
        return {"ok": True, "src": src,
                "sheet_no": g(0), "sheet_no_fmt": g(0).zfill(8),
                "item": g(1), "assy": g(2), "upper": g(3),
                "plan_ymd": g(4), "input_hm": g(5), "line": g(6),
                "plan_qty": float(row[7] or 0),
                "wh_code": g(8), "wh_nm": _pname(g(8)) or "자재창고",
                "stock_code": g(9), "stock_nm": _pname(g(9)),
                "print_user": g(10), "print_dt": (str(row[11])[:19] if row[11] else ""),
                "fin_flag": g(12), "nm": g(13), "spec": g(14),
                "procs": procs}
    finally:
        nx.close(); cn.close()

def _plan_head(cur, item, d6):
    """전표 헤더 보조필드(LINE_NO·ASSY·UPPER·투입시간)를 계획에서 조회.
       ★레거시 전표는 LINE_NO가 채워져 있고(1,338/1,340), 가간판이 이를 그대로 물려받아
         간판 좌상단 라인칸에 찍힌다(예 CM). 미기입 시 간판 라인칸이 빔.
       (2026-08-19: 웹 발행 전표에 LINE_NO가 없어 간판 라인이 비던 것 수정)"""
    try:
        cur.execute("""SELECT TOP 1 ISNULL(a.LINE_NO,''), ISNULL(a.ASSY_ITEM_CODE,''),
                              ISNULL(a.UPPER_ITEM_CODE,''), ISNULL(a.PART_OUTPUT_HM,'')
                         FROM nx.PR_T_PLAN_PART_COPY a WITH(NOLOCK)
                        WHERE a.ITEM_CODE=? AND a.PART_PLAN_YMD=?
                          AND a.GC_GUBUN='P' AND a.GAGONG_PROC_SEQ=1
                        ORDER BY CASE WHEN ISNULL(a.LINE_NO,'')<>'' THEN 0 ELSE 1 END""", item, d6)
        r = cur.fetchone()
        if r:
            return (str(r[0] or '').strip() or None, str(r[1] or '').strip() or None,
                    str(r[2] or '').strip() or None, str(r[3] or '').strip() or None)
    except Exception:
        pass
    return (None, None, None, None)

def _insert_sheet_dtl(cur, sheet_no, item, user):
    """전표 SEQ(공정) 상세 = 품목 공정마스터를 그대로 복사 → nx.PR_T_INDI_WELD_SHEET_DTL.
       레거시 w_pr_input_467 이 하는 동작과 동일(실측: 전표 266573 = PR_M_ITEM_PROC_GAGONG 복사).
       JP_PROC_METHOD(J=용접전표 / G=가간판)가 그 공정의 실적 잡는 방법 → A4 전표 '실적' 칸에 표시.
       (2026-08-19: 미생성 시 A4 SEQ표가 통째로 비던 것 수정)"""
    cur.execute("""SELECT PROC_SEQ, ISNULL(WORK_CODE,''), ISNULL(GAGONG_PROC_CODE,''),
                          ISNULL(S_WORK_CODE,''), ISNULL(MACH_CODE,''), ISNULL(WORK_QTY,0),
                          ISNULL(STD_SIZE,''), ISNULL(MIX_GAGONG,''), ISNULL(GAGONG_PROC_FLAG,''),
                          ISNULL(GAGONG_PROC_SEQ,0), ISNULL(READY_ST,0), ISNULL(MACH_CT,0),
                          ISNULL(INWON,0), ISNULL(HUMAN_ST,0), ISNULL(TOT_ST,0),
                          ISNULL(JP_PROC_METHOD,''), ISNULL(LT_HR,0)
                     FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)
                    WHERE ITEM_CODE=? ORDER BY PROC_SEQ""", item)
    procs = cur.fetchall()
    for p in procs:
        cur.execute("""INSERT INTO nx.PR_T_INDI_WELD_SHEET_DTL(SHEET_NO,PROC_SEQ,WORK_CODE,GAGONG_PROC_CODE,
                          S_WORK_CODE,MACH_CODE,WORK_QTY,STD_SIZE,MIX_GAGONG,GAGONG_PROC_FLAG,
                          GAGONG_PROC_SEQ,READY_ST,MACH_CT,INWON,HUMAN_ST,TOT_ST,JP_PROC_METHOD,LT_HR,
                          PROD_QTY,PROD_FIN_FLAG,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'0',?,GETDATE(),'w_pr_input_460_new')""",
                    sheet_no, p[0], (p[1] or None), p[2], (p[3] or None), (p[4] or None), p[5],
                    (p[6] or None), (p[7] or None), (p[8] or None), p[9], p[10], p[11], p[12],
                    p[13], p[14], (p[15] or None), p[16], user)
    return len(procs)

@router.post("/api/ready/commit")
def ready_commit(payload: dict = Body(...)):
    """★생산준비 실적등록(전체 프로세스) — 레거시 w_pr_input_460_new 동작 이식.

       [프로세스] (실DB 흔적으로 검증: AJR53980903 746개, 2026-08-18 15:15:00)
         ① nx.PU_T_READY_STOCK      준비재고 += 세트수량        (ITEM=도번, CUST='Z99990', PROC_GUBUN=파트)
         ② nx.PU_T_STOCK_MAINT      tag='B' qty = -(소요량×세트수량)  (자재창고 IS0001 출고)
         ③ nx.PR_T_MAT_STOCK_WH     파트재고 += 소요량×세트수량   (MAT_CODE, PART_CODE=파트)
         ④ nx.PR_T_INDI_WELD_SHEET  용접전표 발행(★항상 — 체크박스와 무관)
            · weld_print 는 A4 인쇄창을 띄울지 여부일 뿐. 체크를 해제해도 실적은 잡히고 전표코드도 등록됨.
       [취소] mode='cancel' → 위 4단계를 부호 반대로 원복.
         · 준비재고 잔량 이내에서만 허용(부족하면 거부 — 중복취소로 인한 음수 방지)
         · 전표는 SHEET_NO 1건만 삭제(payload.sheet_no 지정, 없으면 웹발행 최신 1건).
           생산실적이 잡힌 전표(PROD_FIN_FLAG='1')는 삭제 대상에서 제외.

       ★소요량 = CS_M_ITEM_BOM(KITTING_FLAG='1', VIR_ITEM_FLAG<>'1', USE_QTY>0, 유효일자) 기준.
       ★재고부족(세트가능 < 요청)이면 등록 거부 — 프론트에서도 완료버튼 비활성이지만 서버에서도 재검증.
       ★쓰기는 nx만(CLAUDE.md §1). 라이브 PARTNER_ERP 무변경.
       ★4단계는 원자적 처리(_nx_tx) — 하나라도 실패하면 전부 롤백."""
    mode = str(payload.get("mode", "register")).strip()
    item = str(payload.get("item", "") or "").strip()          # 도번
    gpc = str(payload.get("gpc", "") or "").strip()            # 파트(PROC_GUBUN / PART_CODE)
    qty = float(payload.get("qty") or 0)                        # 세트수량
    ymd = str(payload.get("ymd", "") or "").strip()
    wo = str(payload.get("wo", "") or "").strip()
    weld_print = bool(payload.get("weld_print", True))
    # ★취소 대상 전표 지정(선택). 미지정이면 그 (도번·계획일자) 중 웹발행 최신 1건만 삭제.
    req_sheet = str(payload.get("sheet_no", "") or "").strip()
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    if not item or not gpc or qty <= 0:
        return {"ok": False, "detail": "도번·파트·수량(>0) 필수"}
    d6 = ''.join(c for c in ymd if c.isdigit())
    d6 = d6[2:8] if len(d6) >= 8 else (d6 or datetime.now().strftime('%y%m%d'))
    # ★재고이동(자재창고 출고)은 "실제 발생일=오늘" 기준. 전표(PLAN_YMD)만 계획일자를 씀.
    #   (계획일자로 넣으면 과거일자에 수불이 꽂혀 일자별 재고가 어긋남 — 2026-08-18 확인)
    today6 = datetime.now().strftime('%y%m%d')
    sgn = -1 if mode == "cancel" else 1

    # 1) 소요 BOM + 재고 확인(등록시에만 부족 검증)
    chk = ready_setcheck(item=item, ymd=d6, qty=qty)
    bom = chk.get("rows") or []
    if not bom:
        return {"ok": False, "detail": "키팅 대상 자재 없음(BOM KITTING_FLAG=1 없음)"}
    if mode != "cancel" and float(chk.get("set_able") or 0) < qty:
        return {"ok": False, "detail": f"자재부족 — 세트가능 {chk.get('set_able')} < 요청 {qty:g}"}

    tx = _nx_tx(); cur = tx.cursor()
    try:
        WIN = 'w_pr_input_460_new'
        # ★취소 잔량 검증 — 준비재고보다 많이 취소하면 재고가 음수로 내려감(중복취소 방지).
        #   (2026-08-18: 기존 로직에 검증이 없어 같은 셀을 두 번 취소하면 음수 발생. 실DB에 음수 328행 존재.)
        if mode == "cancel":
            cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_READY_STOCK
                            WHERE ITEM_CODE=? AND CUST_CODE='Z99990' AND PROC_GUBUN=?""", item, gpc)
            have = float(cur.fetchone()[0] or 0)
            if have < qty:
                tx.rollback()
                return {"ok": False, "detail": f"취소불가 — 준비재고 {have:g} < 취소요청 {qty:g}"}
        # ① 준비재고 (item·Z99990·파트)
        cur.execute("""UPDATE nx.PU_T_READY_STOCK SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                          UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                        WHERE ITEM_CODE=? AND CUST_CODE='Z99990' AND PROC_GUBUN=?""",
                    sgn * qty, user, WIN, item, gpc)
        if cur.rowcount == 0:
            cur.execute("""INSERT INTO nx.PU_T_READY_STOCK(ITEM_CODE,CUST_CODE,PROC_GUBUN,STOCK_QTY,
                              UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                            VALUES(?,'Z99990',?,?,?,GETDATE(),?)""", item, gpc, sgn * qty, user, WIN)
        moved = []
        for b in bom:
            mat = b["mat"]; need = float(b["use_qty"]) * qty      # 소요량 × 세트수량
            # ② 자재창고 출고(tag='B', 음수) / 취소시 +
            #    ★MAINT_YMD = today6(실제 발생일). 계획일자(d6)가 아님 — 재고 수불은 오늘 기준.
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=?", today6)
            seq = int(cur.fetchone()[0] or 1)
            # ★TO_GAGONG_PROC_CODE(도착 파트창고) 필수 — 생산입출고현황의 '생산창고입고' 라인이
            #   tag='B' AND OUT_WH_GUBUN='1' AND TO_GAGONG_PROC_CODE>'' 조건으로 집계함(live_api._prodinout).
            #   (2026-08-18: 미기입 시 자재출고만 보이고 생산창고 입고가 통째로 누락됨 — 레거시 w_pu_stock_156은 P0001 등 기입)
            cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,MAT_CODE,
                              GAGONG_PROC_CODE,TO_GAGONG_PROC_CODE,MAINT_QTY,WORK_ORDER,OUT_WH_GUBUN,REMARKS,
                              INPUT_YMD,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                            VALUES(?,?,'B',?,'IS0001',?,?,?,'1',?,?,?,GETDATE(),?)""",
                        today6, seq, mat, gpc, -sgn * need, (wo or None),
                        ('생산준비취소' if mode == 'cancel' else '생산준비출고'),
                        d6, user, WIN)   # INPUT_YMD=계획일자(추적용), TO=파트(생산파트창고)
            # ③ 파트창고 재고 증가 / 취소시 감소
            cur.execute("""UPDATE nx.PR_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                              UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                            WHERE MAT_CODE=? AND PART_CODE=?""", sgn * need, user, 'dw_t2', mat, gpc)
            if cur.rowcount == 0:
                cur.execute("""INSERT INTO nx.PR_T_MAT_STOCK_WH(MAT_CODE,PART_CODE,STOCK_QTY,
                                  UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                VALUES(?,?,?,?,GETDATE(),?)""", mat, gpc, sgn * need, user, 'dw_t2')
            moved.append({"mat": mat, "qty": round(need, 4)})
        # ④ 용접전표
        sheet_no = None
        if mode == "cancel":
            # ★전표 삭제는 반드시 SHEET_NO 1건으로 한정.
            #   (2026-08-18: 기존은 (도번·계획일자·발행자) 조건 DELETE라 무관한 전표까지 통째 삭제.
            #    실DB에 같은 조합 전표가 2~3건씩 존재함 — 예 AJR75563402-은납 260810 3건.)
            #   요청에 sheet_no가 오면 그것을, 없으면 그 조합의 웹발행 최신 1건만 삭제.
            #   생산실적이 이미 잡힌 전표(PROD_FIN_FLAG='1')는 대상 제외.
            if req_sheet:
                cur.execute("""SELECT TOP 1 SHEET_NO FROM nx.PR_T_INDI_WELD_SHEET
                                WHERE SHEET_NO=? AND ITEM_CODE=? AND ISNULL(PROD_FIN_FLAG,'0')='0'""",
                            req_sheet, item)
            else:
                cur.execute("""SELECT TOP 1 SHEET_NO FROM nx.PR_T_INDI_WELD_SHEET
                                WHERE ITEM_CODE=? AND PLAN_YMD=? AND ISNULL(PROD_FIN_FLAG,'0')='0'
                                  AND PRINT_USER_ID=? ORDER BY PRINT_DATETIME DESC, SHEET_NO DESC""",
                            item, d6, user)
            _t = cur.fetchone()
            if _t:
                sheet_no = str(_t[0]).strip()
                cur.execute("DELETE FROM nx.PR_T_INDI_WELD_SHEET_DTL WHERE SHEET_NO=?", sheet_no)   # 공정상세 먼저
                cur.execute("DELETE FROM nx.PR_T_INDI_WELD_SHEET WHERE SHEET_NO=?", sheet_no)
        else:
            # ★전표 등록은 '용접전표 출력' 체크와 무관하게 항상 수행.
            #   체크박스는 A4 인쇄창을 띄울지 여부만 결정(프론트 판단). 실적이 잡히면 전표코드는 반드시 남아야 함
            #   (2026-08-19: 기존 elif weld_print 라 체크 해제 시 전표가 통째로 미등록되던 것 수정).
            # ★전표번호 채번 = 6자리 전역 연번(일자리셋 없음, 실측 검증: 최근 20건 모두 Δ+1).
            #   nx 기준 MAX+1. (테스트 단계라 nx가 라이브보다 뒤처질 수 있으나 컷오버 후 nx가 정본)
            cur.execute("SELECT ISNULL(MAX(CAST(SHEET_NO AS bigint)),0)+1 FROM nx.PR_T_INDI_WELD_SHEET WITH(NOLOCK) WHERE ISNUMERIC(SHEET_NO)=1")
            sheet_no = str(int(cur.fetchone()[0] or 1))
            _ln, _assy, _upr, _hm = _plan_head(cur, item, d6)   # 라인/ASSY/상위도번/투입시간
            cur.execute("""INSERT INTO nx.PR_T_INDI_WELD_SHEET(SHEET_NO,ITEM_CODE,PLAN_YMD,PLAN_QTY,
                              ORG_PLAN_QTY,WH_GAGONG_PROC_CODE,STOCK_GAGONG_PROC_CODE,
                              LINE_NO,ASSY_ITEM_CODE,UPPER_ITEM_CODE,DS_INPUT_HM,
                              PRINT_USER_ID,PRINT_DATETIME,PROD_FIN_FLAG)
                            VALUES(?,?,?,?,?,'IS0001',?,?,?,?,?,?,GETDATE(),'0')""",
                        sheet_no, item, d6, qty, qty, gpc, _ln, _assy, _upr, _hm, user)
            _insert_sheet_dtl(cur, sheet_no, item, user)
        tx.commit()
        # weld_print = A4 인쇄창을 띄울지 여부(전표 등록 자체와 무관). 프론트가 이 값으로 판단.
        return {"ok": True, "mode": mode, "item": item, "gpc": gpc, "qty": qty,
                "sheet_no": sheet_no, "weld_print": weld_print, "moved": moved}
    except Exception as e:
        try: tx.rollback()
        except Exception: pass
        return {"ok": False, "detail": str(e)[:300]}
    finally:
        tx.close()

@router.post("/api/ready/force-sheet")
def ready_force_sheet(payload: dict = Body(...)):
    """★생산이동전표 강제발행 (레거시 460_new '생산이동표 강제발행' 버튼).

       용도: 준비실적(자재 재고이동)을 거치지 않고 **전표 데이터만** 등록해서
             생산실적을 잡을 수 있게 하는 우회 경로.
             (자재가 이미 현장에 있거나 재고가 안 맞아 준비등록이 막힐 때 사용)

       [하는 일]  nx.PR_T_INDI_WELD_SHEET 에 전표 INSERT (SHEET_NO = nx MAX+1)
       [안 하는 일] 준비재고 증가 X · 자재창고 출고 X · 파트창고 입고 X · BOM 소요 검증 X
                    → /api/ready/commit 과 달리 재고는 일절 건드리지 않음.

       payload: rows[{item,gpc,ymd,qty}] 다건. user.
       ※쓰기는 nx만. 라이브 PARTNER_ERP 무변경."""
    rows = payload.get("rows") or []
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    if not rows:
        return {"ok": False, "detail": "발행할 행이 없습니다."}
    tx = _nx_tx(); cur = tx.cursor()
    try:
        cur.execute("SELECT ISNULL(MAX(CAST(SHEET_NO AS bigint)),0) FROM nx.PR_T_INDI_WELD_SHEET WITH(NOLOCK) WHERE ISNUMERIC(SHEET_NO)=1")
        nxt = int(cur.fetchone()[0] or 0)
        issued = []; skipped = []
        for r in rows:
            item = str(r.get("item", "") or "").strip()
            gpc = str(r.get("gpc", "") or "").strip()
            qty = float(r.get("qty") or 0)
            ymd = str(r.get("ymd", "") or "").strip()
            d6 = ''.join(c for c in ymd if c.isdigit())
            d6 = d6[2:8] if len(d6) >= 8 else (d6 or datetime.now().strftime('%y%m%d'))
            if not item or qty <= 0:
                skipped.append({"item": item, "why": "도번/수량 오류"}); continue
            nxt += 1
            sheet_no = str(nxt)
            _ln, _assy, _upr, _hm = _plan_head(cur, item, d6)   # 라인/ASSY/상위도번/투입시간
            cur.execute("""INSERT INTO nx.PR_T_INDI_WELD_SHEET(SHEET_NO,ITEM_CODE,PLAN_YMD,PLAN_QTY,
                              ORG_PLAN_QTY,WH_GAGONG_PROC_CODE,STOCK_GAGONG_PROC_CODE,
                              LINE_NO,ASSY_ITEM_CODE,UPPER_ITEM_CODE,DS_INPUT_HM,
                              PRINT_USER_ID,PRINT_DATETIME,PROD_FIN_FLAG)
                            VALUES(?,?,?,?,?,'IS0001',?,?,?,?,?,?,GETDATE(),'0')""",
                        sheet_no, item, d6, qty, qty, gpc, _ln, _assy, _upr, _hm, user)
            _insert_sheet_dtl(cur, sheet_no, item, user)   # SEQ 공정상세도 함께(A4 전표용)
            issued.append({"sheet_no": sheet_no, "item": item, "gpc": gpc, "ymd": d6, "qty": qty})
        tx.commit()
        return {"ok": True, "issued": issued, "cnt": len(issued), "skipped": skipped}
    except Exception as e:
        try: tx.rollback()
        except Exception: pass
        return {"ok": False, "detail": str(e)[:300]}
    finally:
        tx.close()

@router.post("/api/ready/register")
def ready_register(payload: dict = Body(...)):
    """준비등록(+)/취소(−) 다건. ★Phase1: 단일원장 nx.stock_ledger(STOCK_POINT='RDY', K1/K2). 셀키=item·wo·gpc(파트)·plan_ymd(INPUT_YMD).
       취소는 준비잔량 이내. flag-only(자재무차감). 쓰기 nx만.
       ※재고이동까지 하는 전체 프로세스는 /api/ready/commit 사용."""
    mode = str(payload.get("mode", "register")).strip()
    rows = payload.get("rows", []) or []
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    tag = "K2" if mode == "cancel" else "K1"; remk = "키팅취소" if mode == "cancel" else "키팅확인"
    nx = _nx(); cur = nx.cursor()
    try:
        n = 0; skipped = 0
        for r in rows:
            ic = str(r.get("item_code", "") or "").strip()
            qty = float(r.get("qty") or 0)
            if not ic or qty <= 0:
                skipped += 1; continue
            wo = str(r.get("work_order", "") or "").strip(); py = str(r.get("plan_ymd", "") or "").strip()
            gpc = (str(r.get("gpc") or r.get("work_center") or "").strip() or None)   # 파트(gpc) 우선, 없으면 작업처
            if mode == "cancel":
                cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='RDY'
                      AND ITEM_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=? AND ISNULL(WORK_ORDER,'')=? AND ISNULL(INPUT_YMD,'')=?""",
                      ic, (gpc or ''), wo, py)
                if qty > float(cur.fetchone()[0] or 0):
                    skipped += 1; continue
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
            seq = int(cur.fetchone()[0] or 1)
            cur.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,GAGONG_PROC_CODE,
                  WORK_ORDER,INPUT_YMD,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                VALUES('RDY',RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,?,'Z99990',?,?,?,?,?,?,?,GETDATE())""",
                seq, tag, ic, gpc, (wo or None), (py or None), (-qty if mode == "cancel" else qty), remk, user)
            n += 1
        return {"ok": True, "count": n, "skipped": skipped, "mode": mode}
    finally:
        nx.close()

# ===================== Spec Sheet(BOM) 출력 — 준비실적처리(키팅) [BOM출력] 버튼 =====================
# 레거시 w_pr_input_460 [BOM출력] → Print미리보기 "Spec Sheet(BOM)" A4 가로.
#   헤더 : 공정구분(용접) · 파트명(04라인) · 도번 · 품명 · 시발예정(빈칸) · 지그보관구역
#   본문 : 레벨 | 품목코드 | 소분류 | 차수 | 대표매입처 | 재고취처 | 재고 | 소요량 | 품명 | 규격 | 지름 | 두께 | 길이
#          + 자재사양/제조사양/품질사양(빈칸 — 수기기입란)
#   푸터 : 마지막 페이지에 [n 건] · 소요량합계 + 서명표(준비수량/자재팀/제조팀/품질팀 초물/품질팀 OQC/내사경 검사)
# 데이터 소스(실측 확정 2026-08-19):
#   소분류   = PR_M_ITEM.ITEM_SGROUP (코드 → 명칭 매핑 _SGRP)
#   대표매입처 = PR_M_ITEM.IN_CUST_CODE → CM_M_CUST.CUST_DESC
#   재고취처 = PR_M_ITEM_SUB.RACK_NO            (예 A-02-03)
#   재고     = PU_T_MAT_STOCK_WH 합계 (자재창고재고)
#   치수     = PR_M_ITEM.ITEM_DIAM / ITEM_THICK / ITEM_LENGTH
# ※키팅대상 회색음영은 제외(사용자 지시).
_SGRP = {"110": "원자재", "120": "SUB-ASSY", "130": "가공품", "210": "소재컷팅",
         "220": "소재컷팅", "230": "부자재", "310": "LG사급", "910": "전자재",
         "991": "부자재", "992": "부자재", "993": "수불예외"}

@router.get("/api/ready/bomsheet")
def ready_bomsheet(item: str = Query(...), gpc: str = Query("")):
    """Spec Sheet(BOM) 데이터 — 선택 도번의 BOM 다단 전개(레벨 포함).
       ★전개 규칙(2026-08-19 실측): 하위 BOM 이 있으면 무조건 한 단계 더 내려간다.
         (VIR_ITEM_FLAG 는 이 데이터에서 전부 '0' 이라 판별에 못 씀 —
          SUB-ASSY 도 vir=0 인데 하위 7건을 갖고 있어 전개 대상. 실측 36건 = 레거시 화면과 동일)
         부모 자신도 한 줄로 출력하고(레벨 n), 그 아래에 자식들(레벨 n+1)이 이어짐.
       except_flag='1' 제외. 정렬 = BOM_SEQ 계층 경로순(레거시 화면 순서)."""
    it = str(item or "").strip()
    if not it:
        raise HTTPException(400, "도번(item)이 필요합니다.")
    nx = _nx(); cur = nx.cursor()
    cn = _conn(); c2 = cn.cursor()
    try:
        # 헤더 — 도번 품명 / 지그보관구역 / 파트명
        cur.execute("""SELECT ISNULL(ITEM_DESC,''), ISNULL(JIG_KEEP_AREA,'')
                         FROM nx.PR_M_ITEM WITH(NOLOCK) WHERE ITEM_CODE=?""", it)
        h = cur.fetchone()
        nm  = str(h[0]).strip() if h else ""
        jig = str(h[1]).strip() if h else ""
        part_nm = ""; proc_nm = ""
        g = str(gpc or "").strip()
        if g:
            cur.execute("""SELECT TOP 1 ISNULL(GAGONG_PROC_DESC,''), ISNULL(PART_GROUP_CODE,'')
                             FROM nx.PR_M_PROC_GAGONG WITH(NOLOCK) WHERE GAGONG_PROC_CODE=?""", g)
            r = cur.fetchone()
            if r:
                part_nm = str(r[0]).strip()
                proc_nm = "용접"          # 레거시 헤더 좌상단 고정표기(용접 파트)
        # BOM 다단 전개 — 레벨 유지, 가상품목만 재귀
        cur.execute("""
            WITH CTE (lvl, seq, path, mat_code, use_qty) AS (
                SELECT 1, b.BOM_SEQ,
                       CAST(RIGHT('0000'+CAST(b.BOM_SEQ AS varchar(4)),4) AS varchar(400)),
                       b.MAT_CODE, CAST(ISNULL(b.USE_QTY,0) AS float)
                  FROM nx.PR_M_ITEM_BOM b WITH(NOLOCK)
                 WHERE b.ITEM_CODE=? AND ISNULL(b.EXCEPT_FLAG,'0')<>'1'
                UNION ALL
                SELECT c.lvl+1, b.BOM_SEQ,
                       CAST(c.path+'.'+RIGHT('0000'+CAST(b.BOM_SEQ AS varchar(4)),4) AS varchar(400)),
                       b.MAT_CODE, CAST(ISNULL(b.USE_QTY,0) AS float)
                  FROM CTE c
                  JOIN nx.PR_M_ITEM_BOM b WITH(NOLOCK) ON b.ITEM_CODE=c.mat_code
                 WHERE ISNULL(b.EXCEPT_FLAG,'0')<>'1'
                   AND c.lvl < 10                    -- 순환 BOM 방어(실측 최대 3레벨)
            )
            SELECT c.lvl, c.mat_code, c.use_qty,
                   ISNULL(m.ITEM_DESC,''), ISNULL(m.ITEM_SPEC,''), ISNULL(m.ITEM_SGROUP,''),
                   ISNULL(m.IN_CUST_CODE,''), ISNULL(m.ITEM_DIAM,0), ISNULL(m.ITEM_THICK,0),
                   ISNULL(m.ITEM_LENGTH,0), ISNULL(s.RACK_NO,''), ISNULL(k.stk,0)
              FROM CTE c
              LEFT JOIN nx.PR_M_ITEM m     WITH(NOLOCK) ON m.ITEM_CODE=c.mat_code
              LEFT JOIN nx.PR_M_ITEM_SUB s WITH(NOLOCK) ON s.ITEM_CODE=c.mat_code
              LEFT JOIN (SELECT MAT_CODE, SUM(STOCK_QTY) stk
                           FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK) GROUP BY MAT_CODE) k
                     ON k.MAT_CODE=c.mat_code
             ORDER BY c.path
             OPTION(MAXRECURSION 0)""", it)
        raw = cur.fetchall()
        custs = {str(r[6]).strip() for r in raw if str(r[6] or "").strip()}
        cnm = {}
        cl = [x for x in custs if x]
        for i in range(0, len(cl), 900):
            ch = cl[i:i+900]; ph = ",".join("?" * len(ch))
            c2.execute(f"SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE IN ({ph})", *ch)
            for a, b in c2.fetchall(): cnm[str(a).strip()] = b
        f = lambda v: float(v or 0)
        rows = []
        for r in raw:
            sg = str(r[5] or "").strip()
            rows.append({"lvl": int(r[0] or 1), "mat": str(r[1] or "").strip(),
                         "use_qty": f(r[2]), "nm": str(r[3] or "").strip(),
                         "spec": str(r[4] or "").strip(),
                         "sgrp": _SGRP.get(sg, sg), "cust": cnm.get(str(r[6] or "").strip(), ""),
                         "diam": f(r[7]), "thick": f(r[8]), "length": f(r[9]),
                         "rack": str(r[10] or "").strip(), "stock": f(r[11])})
        return {"item": it, "nm": nm, "jig": jig, "part_nm": part_nm, "proc_nm": proc_nm,
                "rows": rows, "cnt": len(rows),
                "sum_qty": round(sum(x["use_qty"] for x in rows), 4)}
    finally:
        nx.close(); cn.close()
