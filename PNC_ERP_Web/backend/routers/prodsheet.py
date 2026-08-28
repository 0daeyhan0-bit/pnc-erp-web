# -*- coding: utf-8 -*-
"""prodsheet 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _prod_stock_map)

from routers.backflush import _backflush_core, _final_proc_code, _is_inner_prod
router = APIRouter()

# ===================== 생산전표출력관리 (w_pr_input_490) — 전표 기준 마스터-디테일 =====================
# ★2026-08-19 전면 재구성: 레거시 w_pr_input_490 구조로 맞춤(스크린샷 대조).
#   [이전] 계획(PR_T_PLAN_PART_COPY) 기준 목록 — 계획일자로 조회
#   [현재] 발행된 전표(PR_T_INDI_WELD_SHEET) 기준 목록 — ★출력기간(PRINT_DATETIME)으로 조회
#   [사유] 이 화면의 목적은 "발행된 전표를 골라 가간판/라벨을 추가 발행"하는 것.
#          계획 기준이면 발행 안 된 것까지 섞여 전표 단위 작업이 안 됨.
#
#   레거시 레이아웃:
#     조회조건 : 출력기간 · 파트 · 도번 · 전표번호 · 간판번호 · 라벨번호 · 생산완료(전체/미완료/완료)
#     좌측     : 전표목록(전표번호·투입파트·계획일자·계획수량·도번·전표완료여부)
#     우상단   : 공정상세(PR_T_INDI_WELD_SHEET_DTL) — 파트명·공정명·SEQ·전표처리방법(J전표/G가간판)·
#                작업완료여부·작업수량·생산실적수량·시작/종료시각·파트코드·공정코드·설비코드
#     우하단좌 : 간판목록(PR_T_INDI_SHEET2) — 재발행·간판번호·도번·계획수량·최초출력수량·분할·실적처리자
#     우하단우 : 라벨목록(PR_T_PRINT_STICKER) — 재발행·출력일자·라벨시작번호·도번·출력수량·출력담당자
_METH_NM = {"J": "전표", "G": "가간판", "L": "라벨"}

@router.get("/api/prodsheet/list")
def prodsheet_list(from_ymd: str = Query(""), to_ymd: str = Query(""), part: str = Query(""),
                   item: str = Query(""), sheet_no: str = Query(""), box_no: str = Query(""),
                   label_no: str = Query(""), fin: str = Query("N"), limit: int = Query(1000)):
    """전표 목록(좌측). ★출력기간=PRINT_DATETIME 기준. fin: N=미완료(기본)/Y=완료/''=전체."""
    def d8(s):   # YYYY-MM-DD / YYMMDD → YYYYMMDD (PRINT_DATETIME 비교용)
        d = ''.join(c for c in str(s or '') if c.isdigit())
        if len(d) >= 8: return d[:8]
        if len(d) == 6: return "20" + d
        return ""
    nx = _nx(); ncur = nx.cursor()
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        f8, t8 = d8(from_ymd), d8(to_ymd)
        if f8: w.append("CONVERT(varchar(8),h.PRINT_DATETIME,112)>=?"); p.append(f8)
        if t8: w.append("CONVERT(varchar(8),h.PRINT_DATETIME,112)<=?"); p.append(t8)
        # 파트 필터도 표시와 같은 기준(DTL 첫 공정, 없으면 헤더)으로 — 안 그러면
        # 화면엔 08라인인데 06라인으로 조회해야 나오는 어긋남이 생긴다.
        if part.strip():
            w.append("""ISNULL((SELECT TOP 1 d2.GAGONG_PROC_CODE
                                  FROM nx.PR_T_INDI_WELD_SHEET_DTL d2 WITH(NOLOCK)
                                 WHERE d2.SHEET_NO=h.SHEET_NO
                                   AND ISNULL(d2.GAGONG_PROC_CODE,'')<>''
                                   AND ISNULL(d2.GAGONG_PROC_CODE,'') NOT LIKE 'P00%'
                                 ORDER BY d2.PROC_SEQ), ISNULL(h.STOCK_GAGONG_PROC_CODE,''))=?""")
            p.append(part.strip())
        if item.strip():     w.append("h.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if sheet_no.strip(): w.append("CAST(h.SHEET_NO AS varchar(20)) LIKE ?"); p.append(f"%{sheet_no.strip()}%")
        # 생산완료 필터 = PROD_FIN_FLAG
        _f = (fin or "").strip().upper()
        if _f == "N": w.append("ISNULL(h.PROD_FIN_FLAG,'0')<>'1'")
        elif _f == "Y": w.append("ISNULL(h.PROD_FIN_FLAG,'0')='1'")
        # 간판번호/라벨번호로 역검색 → 해당 전표만
        if box_no.strip():
            w.append("EXISTS(SELECT 1 FROM nx.PR_T_INDI_SHEET2 b WITH(NOLOCK) WHERE b.SHEET_NO=h.SHEET_NO AND CAST(b.BOX_NO AS varchar(20)) LIKE ?)")
            p.append(f"%{box_no.strip()}%")
        if label_no.strip():
            w.append("EXISTS(SELECT 1 FROM nx.PR_T_PRINT_STICKER s WITH(NOLOCK) WHERE s.SHEET_NO=h.SHEET_NO AND CAST(s.PRINT_SEQ AS varchar(20)) LIKE ?)")
            p.append(f"%{label_no.strip()}%")
        # ★투입파트 = 전표 DTL 의 실제 공정(첫 공정). 헤더 STOCK_GAGONG_PROC_CODE 는
        #   상위 P/No 기준값이라 -SUB·은납 등 하위품목이 전부 상위라인(예: RAC=06라인)으로
        #   잘못 보였다. 실측(8/24~28 전표 649건): 헤더=DTL 12건뿐, 다름 412 · 헤더만 225.
        #   DTL 은 발행방법(JP_PROC_METHOD J=전표/G=가간판) 무관하게 공정이 들어있으므로
        #   method 로 거르지 않고 PROC_SEQ 최소 행을 쓴다. 가공파트(P00xx)는 별도 화면 소관이라 제외.
        #   DTL 이 아예 없는 전표만 헤더값으로 폴백.  2026-08-28
        ncur.execute(f"""SELECT TOP {max(1,min(int(limit),3000))}
              h.SHEET_NO, ISNULL(h.UPPER_ITEM_CODE,''),
              ISNULL((SELECT TOP 1 d.GAGONG_PROC_CODE
                        FROM nx.PR_T_INDI_WELD_SHEET_DTL d WITH(NOLOCK)
                       WHERE d.SHEET_NO=h.SHEET_NO
                         AND ISNULL(d.GAGONG_PROC_CODE,'')<>''
                         AND ISNULL(d.GAGONG_PROC_CODE,'') NOT LIKE 'P00%'
                       ORDER BY d.PROC_SEQ), ISNULL(h.STOCK_GAGONG_PROC_CODE,'')),
              h.PLAN_YMD, h.PLAN_QTY, h.ITEM_CODE, ISNULL(h.PROD_FIN_FLAG,'0'),
              ISNULL(h.LINE_NO,''), ISNULL(h.DS_INPUT_HM,''), ISNULL(h.PRINT_USER_ID,''), h.PRINT_DATETIME,
              (SELECT COUNT(*) FROM nx.PR_T_INDI_SHEET2 b WITH(NOLOCK)
                WHERE b.SHEET_NO=h.SHEET_NO AND ISNULL(b.DELETE_FLAG,'0')<>'1'),
              (SELECT COUNT(*) FROM nx.PR_T_PRINT_STICKER s WITH(NOLOCK) WHERE s.SHEET_NO=h.SHEET_NO)
            FROM nx.PR_T_INDI_WELD_SHEET h WITH(NOLOCK)
           WHERE {' AND '.join(w)}
           ORDER BY h.SHEET_NO""", *p)
        rows = []; items = set(); gpcs = set()
        for r in ncur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            ic = g(5)
            rows.append({"sheet_no": g(0), "upper": g(1), "gpc": g(2), "plan_ymd": g(3),
                         "plan_qty": float(r[4] or 0), "item_code": ic, "fin_flag": g(6),
                         "line": g(7), "input_hm": g(8), "print_user": g(9),
                         "print_dt": (str(r[10])[:19] if r[10] else ""),
                         "gcnt": int(r[11] or 0), "lcnt": int(r[12] or 0)})
            items.add(ic); gpcs.add(g(2))
        # 품명 · 파트명 디코드
        nm = {}; il = [x for x in items if x]
        for i in range(0, len(il), 900):
            ch = il[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(item_name,'') FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE IN ({ph})", *ch)
            for a, b in cur.fetchall(): nm[str(a).strip()] = b
        pn = {}; gl = [x for x in gpcs if x]
        if gl:
            ph = ",".join("?" * len(gl))
            cur.execute(f"SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE IN ({ph})", *gl)
            for a, b in cur.fetchall(): pn[str(a).strip()] = b
        for x in rows:
            x["nm"] = nm.get(x["item_code"], "")
            x["gpc_nm"] = pn.get(x["gpc"], x["gpc"])
            x["fin_nm"] = "완료" if x["fin_flag"] == "1" else ""
        return {"rows": rows, "cnt": len(rows),
                "sum_qty": round(sum(x["plan_qty"] for x in rows), 2)}
    finally:
        nx.close(); cn.close()

@router.get("/api/prodsheet/detail")
def prodsheet_detail(sheet_no: str = Query(...)):
    """선택 전표의 디테일 3종 — 공정상세(우상단) · 간판(우하단좌) · 라벨(우하단우)."""
    sn = str(sheet_no or "").strip()
    if not sn:
        return {"ok": False, "detail": "전표번호 필수"}
    nx = _nx(); cur = nx.cursor()
    try:
        # ① 공정상세 — 레거시 우상단 그리드
        cur.execute("""SELECT d.PROC_SEQ, ISNULL(g.GAGONG_PROC_DESC,'') partnm, ISNULL(d.GAGONG_PROC_CODE,''),
                          ISNULL(d.JP_PROC_METHOD,''), ISNULL(d.PROD_FIN_FLAG,'0'),
                          ISNULL(d.WORK_QTY,0), ISNULL(d.PROD_QTY,0),
                          d.STA_DATETIME, d.FIN_DATETIME, ISNULL(d.MACH_CODE,''), ISNULL(d.S_WORK_CODE,''),
                          ISNULL(d.WORK_CODE,''), ISNULL(d.TOT_ST,0)
                        FROM nx.PR_T_INDI_WELD_SHEET_DTL d WITH(NOLOCK)
                        LEFT JOIN nx.PR_M_PROC_GAGONG g WITH(NOLOCK) ON g.GAGONG_PROC_CODE=d.GAGONG_PROC_CODE
                       WHERE d.SHEET_NO=? ORDER BY d.PROC_SEQ""", sn)
        procs = []
        for r in cur.fetchall():
            m = str(r[3] or '').strip()
            procs.append({"seq": int(r[0] or 0), "part_nm": str(r[1] or '').strip(),
                          "gpc": str(r[2] or '').strip(), "method": m,
                          "method_nm": (m + ":" + _METH_NM[m]) if m in _METH_NM else m,
                          "fin_flag": str(r[4] or '0').strip(),
                          "work_qty": float(r[5] or 0), "prod_qty": float(r[6] or 0),
                          "sta_dt": (str(r[7])[:19] if r[7] else ""),
                          "fin_dt": (str(r[8])[:19] if r[8] else ""),
                          "mach": str(r[9] or '').strip(), "s_work": str(r[10] or '').strip(),
                          "work_code": str(r[11] or '').strip(), "tot_st": float(r[12] or 0)})
        # ② 간판 — 레거시 우하단 그리드 전 컬럼:
        #    재발행·간판번호·도번·계획수량·최초출력수량·분할·실적처리자·생산처리일시
        #    ·Line No·전표번호·삭제여부·분할전간판번호(PARENT_BOX_NO)
        #    ★삭제분도 포함(삭제여부 컬럼으로 구분) — 레거시가 이력으로 함께 보여줌
        cur.execute("""SELECT BOX_NO, ITEM_CODE, PLAN_QTY, ORG_PLAN_QTY, ISNULL(PROD_FLAG,''),
                          ISNULL(PROD_USER_ID,''), PROD_DATETIME, ISNULL(PARENT_BOX_NO,0),
                          ISNULL(LINE_NO,''), PLAN_YMD, ISNULL(PRINT_USER_ID,''), PRINT_DATETIME,
                          ISNULL(DELETE_FLAG,'0')
                        FROM nx.PR_T_INDI_SHEET2 WITH(NOLOCK)
                       WHERE SHEET_NO=? ORDER BY BOX_NO""", sn)
        kanbans = []
        for r in cur.fetchall():
            kanbans.append({"box_no": int(r[0] or 0), "item_code": str(r[1] or '').strip(),
                            "plan_qty": float(r[2] or 0), "org_qty": float(r[3] or 0),
                            "prod_flag": str(r[4] or '').strip(), "prod_user": str(r[5] or '').strip(),
                            "prod_dt": (str(r[6])[:19] if r[6] else ""),
                            "parent": int(r[7] or 0), "line": str(r[8] or '').strip(),
                            "plan_ymd": str(r[9] or '').strip(),
                            "print_user": str(r[10] or '').strip(),
                            "print_dt": (str(r[11])[:19] if r[11] else ""),
                            "sheet_no": sn,
                            "del_flag": str(r[12] or '0').strip()})
        # ③ 라벨 — 레거시 우하단 그리드 전 컬럼:
        #    재발행·출력일자·라벨시작번호(PRINT_SEQ)·도번·출력수량·출력담당자·라벨출력일시
        #    ·전표번호·작업처코드(WORK_CODE)·작업자코드(WORKER_CODE)·시작번호(START_NO)
        #    ·QR Barcode From/To
        #    ※QR 포맷(실측): 도번 + 'KPI' + 연1 + 월1 + 일1 + 일련4  예 AJR74423601KPI6720001
        cur.execute("""SELECT PRINT_SEQ, PRINT_YMD, ITEM_CODE, PRINT_QTY, ISNULL(START_NO,0),
                          ISNULL(QR_BARCODE_FROM,''), ISNULL(QR_BARCODE_TO,''),
                          ISNULL(PRINT_USER_ID,''), PRINT_DATETIME,
                          ISNULL(WORK_CODE,''), ISNULL(WORKER_CODE,''), ISNULL(PROD_TAG,'')
                        FROM nx.PR_T_PRINT_STICKER WITH(NOLOCK)
                       WHERE SHEET_NO=? ORDER BY PRINT_SEQ""", sn)
        labels = []
        for r in cur.fetchall():
            labels.append({"print_seq": int(r[0] or 0), "print_ymd": str(r[1] or '').strip(),
                           "item_code": str(r[2] or '').strip(), "qty": float(r[3] or 0),
                           "start_no": int(r[4] or 0),
                           "qr_from": str(r[5] or '').strip(), "qr_to": str(r[6] or '').strip(),
                           "print_user": str(r[7] or '').strip(),
                           "print_dt": (str(r[8])[:19] if r[8] else ""),
                           "work_code": str(r[9] or '').strip(),
                           "worker_code": str(r[10] or '').strip(),
                           "prod_tag": str(r[11] or '').strip(),
                           "sheet_no": sn})
        return {"ok": True, "sheet_no": sn, "procs": procs, "kanbans": kanbans, "labels": labels}
    finally:
        nx.close()

@router.get("/api/prodsheet/parts")
def prodsheet_parts():
    """파트 드롭다운(투입파트) — 전표에 실제 쓰인 공정만.
       ★목록/필터와 같은 기준(DTL 첫 공정, 없으면 헤더). 2026-08-28"""
    nx = _nx(); cur = nx.cursor()
    cn = _conn(); c2 = cn.cursor()
    try:
        cur.execute("""SELECT DISTINCT c FROM (
                         SELECT ISNULL((SELECT TOP 1 d.GAGONG_PROC_CODE
                                          FROM nx.PR_T_INDI_WELD_SHEET_DTL d WITH(NOLOCK)
                                         WHERE d.SHEET_NO=h.SHEET_NO
                                           AND ISNULL(d.GAGONG_PROC_CODE,'')<>''
                                           AND ISNULL(d.GAGONG_PROC_CODE,'') NOT LIKE 'P00%'
                                         ORDER BY d.PROC_SEQ),
                                       ISNULL(h.STOCK_GAGONG_PROC_CODE,'')) c
                           FROM nx.PR_T_INDI_WELD_SHEET h WITH(NOLOCK)) X
                        WHERE ISNULL(c,'')<>''""")
        codes = [str(r[0]).strip() for r in cur.fetchall() if r[0]]
        nm = {}
        if codes:
            ph = ",".join("?" * len(codes))
            c2.execute(f"SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE IN ({ph})", *codes)
            for a, b in c2.fetchall(): nm[str(a).strip()] = b
        rows = sorted(({"code": c, "nm": nm.get(c, c)} for c in codes), key=lambda x: x["nm"])
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close(); cn.close()

@router.get("/api/prodsheet/packinfo")
def prodsheet_packinfo(item: str = Query(...)):
    """포장정보(가간판/스티커 팝업 기본값) = nx.PR_M_ITEM_SUB (레거시 dw_pr_master_080).
       PACK_KIND=포장BOX · PACK_QTY=표준포장수 · PROD_WORKER=생산자(용접사) · INSP_WORKER=검사자."""
    ic = str(item or "").strip()
    if not ic:
        return {"ok": False, "detail": "품번 필수"}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT ISNULL(s.PACK_KIND,''), ISNULL(s.PACK_QTY,0), ISNULL(s.CUST_PACK_QTY,0),
                          ISNULL(s.PROD_WORKER,''), ISNULL(s.INSP_WORKER,''), ISNULL(s.STICKER_COLOR,''),
                          ISNULL(i.item_name,''), ISNULL(i.item_spec,'')
                        FROM nx.item i WITH(NOLOCK)
                        LEFT JOIN nx.PR_M_ITEM_SUB s WITH(NOLOCK) ON s.ITEM_CODE=i.ITEM_CODE
                       WHERE i.ITEM_CODE=?""", ic)
        r = cur.fetchone()
        if not r:
            return {"ok": False, "detail": f"품목 {ic} 없음"}
        return {"ok": True, "item": ic,
                "pack_kind": str(r[0] or '').strip(), "pack_qty": int(r[1] or 0),
                "cust_pack_qty": int(r[2] or 0),
                "prod_worker": str(r[3] or '').strip(), "insp_worker": str(r[4] or '').strip(),
                "sticker_color": str(r[5] or '').strip(),
                "nm": str(r[6] or '').strip(), "spec": str(r[7] or '').strip()}
    finally:
        nx.close()

def _split_qty(total: float, pack: int):
    """포장수량 단위로 분할 → [pack, pack, …, 잔여]. pack<=0 이거나 total<=pack 이면 1장.
       레거시 예: 계획 200 · 포장 30 → [30]*6 + [20] (7장)."""
    t = float(total or 0)
    p = int(pack or 0)
    if t <= 0: return []
    if p <= 0 or t <= p: return [t]
    out = []
    left = t
    while left > p:
        out.append(float(p)); left -= p
    if left > 0: out.append(round(left, 4))
    return out

@router.get("/api/prodsheet/kanban-preview")
def prodsheet_kanban_preview(sheet_no: str = Query(...), pack_qty: int = Query(0)):
    """가간판 발행 팝업 미리보기 — 포장수량 입력 시 분할 결과·기본값 반환.
       기본 포장정보 = nx.PR_M_ITEM_SUB(PACK_KIND/PACK_QTY/PROD_WORKER/INSP_WORKER).
       ★대상공정 = 그 전표 DTL 중 JP_PROC_METHOD='G' 이고 가공파트(P00xx) 아닌 공정.
         (가공파트 P0002 등은 별도 화면 소관 — 이 화면에서 실적 안 잡음)"""
    sn = str(sheet_no or "").strip()
    if not sn:
        return {"ok": False, "detail": "전표번호 필수"}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT h.ITEM_CODE, h.PLAN_YMD, h.PLAN_QTY, ISNULL(h.LINE_NO,''),
                          ISNULL(h.STOCK_GAGONG_PROC_CODE,''), ISNULL(i.item_name,''),
                          ISNULL(s.PACK_KIND,''), ISNULL(s.PACK_QTY,0),
                          ISNULL(s.PROD_WORKER,''), ISNULL(s.INSP_WORKER,''),
                          ISNULL(h.PROD_FIN_FLAG,'0')
                        FROM nx.PR_T_INDI_WELD_SHEET h WITH(NOLOCK)
                        LEFT JOIN nx.item i WITH(NOLOCK) ON i.ITEM_CODE=h.ITEM_CODE
                        LEFT JOIN nx.PR_M_ITEM_SUB s WITH(NOLOCK) ON s.ITEM_CODE=h.ITEM_CODE
                       WHERE h.SHEET_NO=?""", sn)
        r = cur.fetchone()
        if not r:
            return {"ok": False, "detail": f"전표 {sn} 없음"}
        item = str(r[0] or '').strip(); plan_qty = float(r[2] or 0)
        # 대상공정(G) — 가공파트 제외
        cur.execute("""SELECT d.PROC_SEQ, d.GAGONG_PROC_CODE, ISNULL(g.GAGONG_PROC_DESC,'')
                         FROM nx.PR_T_INDI_WELD_SHEET_DTL d WITH(NOLOCK)
                         LEFT JOIN nx.PR_M_PROC_GAGONG g WITH(NOLOCK) ON g.GAGONG_PROC_CODE=d.GAGONG_PROC_CODE
                        WHERE d.SHEET_NO=? AND ISNULL(d.JP_PROC_METHOD,'')='G'
                          AND ISNULL(d.GAGONG_PROC_CODE,'') NOT LIKE 'P00%'
                        ORDER BY d.PROC_SEQ""", sn)
        gp = [{"seq": int(x[0] or 0), "gpc": str(x[1] or '').strip(), "nm": str(x[2] or '').strip()}
              for x in cur.fetchall()]
        # 이미 발행된 간판 수량 → 잔여만 발행
        cur.execute("""SELECT ISNULL(SUM(PLAN_QTY),0), COUNT(*) FROM nx.PR_T_INDI_SHEET2 WITH(NOLOCK)
                        WHERE SHEET_NO=? AND ISNULL(DELETE_FLAG,'0')<>'1'""", sn)
        x = cur.fetchone()
        issued_qty = float(x[0] or 0); issued_cnt = int(x[1] or 0)
        pack = int(pack_qty) if int(pack_qty or 0) > 0 else int(r[7] or 0)
        remain = round(plan_qty - issued_qty, 4)
        parts = _split_qty(remain, pack)
        warn = ""
        if not gp:
            warn = "이 전표에 가간판(G) 공정이 없습니다 — 실적이 잡히지 않을 수 있습니다."
        elif len(gp) > 1:
            warn = f"가간판 공정이 {len(gp)}개입니다({', '.join(p['gpc'] for p in gp)}) — 어느 공정용인지 확인하세요."
        if remain <= 0:
            warn = (warn + " / " if warn else "") + f"발행 잔여 0 (계획 {plan_qty:g} · 기발행 {issued_qty:g})"
        return {"ok": True, "sheet_no": sn, "item": item, "nm": str(r[5] or '').strip(),
                "plan_ymd": str(r[1] or '').strip(), "plan_qty": plan_qty, "line": str(r[3] or '').strip(),
                "gpc": str(r[4] or '').strip(),
                "pack_kind": str(r[6] or '').strip(), "pack_qty": pack,
                "prod_worker": str(r[8] or '').strip(), "insp_worker": str(r[9] or '').strip(),
                "fin_flag": str(r[10] or '0').strip(),
                "issued_qty": issued_qty, "issued_cnt": issued_cnt, "remain": remain,
                "parts": parts, "cnt": len(parts), "procs": gp, "warn": warn}
    finally:
        nx.close()

@router.post("/api/prodsheet/kanban-issue")
def prodsheet_kanban_issue(payload: dict = Body(...)):
    """가간판 발행 → nx.PR_T_INDI_SHEET2. BOX_NO = 전역 MAX+1(실측: 현재 2,633,699대).
       레거시 인쇄 시 저장되는 동작과 동일. 재고/실적 무변동(전표 데이터만).
       payload: sheet_no · pack_qty · qtys[](선택, 없으면 pack_qty로 자동분할) · user"""
    sn = str(payload.get("sheet_no", "") or "").strip()
    pack = int(payload.get("pack_qty") or 0)
    qtys = payload.get("qtys") or []
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    if not sn:
        return {"ok": False, "detail": "전표번호 필수"}
    tx = _nx_tx(); cur = tx.cursor()
    try:
        cur.execute("""SELECT ITEM_CODE, PLAN_YMD, PLAN_QTY, ISNULL(LINE_NO,'')
                         FROM nx.PR_T_INDI_WELD_SHEET WHERE SHEET_NO=?""", sn)
        h = cur.fetchone()
        if not h:
            tx.rollback(); return {"ok": False, "detail": f"전표 {sn} 없음"}
        item = str(h[0] or '').strip(); ymd = str(h[1] or '').strip()
        plan_qty = float(h[2] or 0); line = str(h[3] or '').strip()
        cur.execute("""SELECT ISNULL(SUM(PLAN_QTY),0) FROM nx.PR_T_INDI_SHEET2
                        WHERE SHEET_NO=? AND ISNULL(DELETE_FLAG,'0')<>'1'""", sn)
        issued = float(cur.fetchone()[0] or 0)
        remain = round(plan_qty - issued, 4)
        lst = [float(q) for q in qtys if float(q or 0) > 0] if qtys else _split_qty(remain, pack)
        if not lst:
            tx.rollback(); return {"ok": False, "detail": f"발행할 수량이 없습니다(계획 {plan_qty:g} · 기발행 {issued:g})"}
        tot = round(sum(lst), 4)
        if tot > remain + 0.0001:
            tx.rollback(); return {"ok": False, "detail": f"발행수량 {tot:g} > 잔여 {remain:g}"}
        cur.execute("SELECT ISNULL(MAX(BOX_NO),0) FROM nx.PR_T_INDI_SHEET2")
        box = int(cur.fetchone()[0] or 0)
        issued_rows = []
        for q in lst:
            box += 1
            cur.execute("""INSERT INTO nx.PR_T_INDI_SHEET2(BOX_NO,ITEM_CODE,PLAN_YMD,LINE_NO,PLAN_QTY,
                              ORG_PLAN_QTY,PRINT_USER_ID,PRINT_DATETIME,SHEET_NO,DELETE_FLAG,PARENT_BOX_NO)
                            VALUES(?,?,?,?,?,?,?,GETDATE(),?,'0',0)""",
                        box, item, ymd, (line or None), q, q, user, sn)
            issued_rows.append({"box_no": box, "qty": q})
        tx.commit()
        return {"ok": True, "sheet_no": sn, "item": item, "cnt": len(issued_rows),
                "total": tot, "issued": issued_rows}
    except Exception as e:
        try: tx.rollback()
        except Exception: pass
        return {"ok": False, "detail": str(e)[:300]}
    finally:
        tx.close()

@router.post("/api/prodsheet/kanban-split")
def prodsheet_kanban_split(payload: dict = Body(...)):
    """★간판 분할 (레거시 w_pr_input_495).
       용도: 대차/박스에 나눠 담기 위해 기존 간판 1장을 여러 장으로 쪼갬.

       [동작] (실측 역산: 원본 1,205건 전부 DELETE_FLAG='1')
         ① 원본 간판 DELETE_FLAG='1' (삭제 표시 — 행은 남겨 이력 추적)
         ② 분할수량만큼 새 BOX_NO 채번 + PARENT_BOX_NO=원본 으로 INSERT
         ③ 분할본 합계 = 원본 수량 (초과/미달 거부)
       [제약] 이미 실적이 잡힌 간판(PROD_FLAG='1')은 분할 불가 — 바코드 실적 연결이 끊김.
       ※재고/실적 무변동. 쓰기는 nx만."""
    box = ''.join(c for c in str(payload.get("box_no", "") or "") if c.isdigit())
    qtys = payload.get("qtys") or []
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    if not box:
        return {"ok": False, "detail": "간판번호 필수"}
    lst = [float(q) for q in qtys if float(q or 0) > 0]
    if len(lst) < 2:
        return {"ok": False, "detail": "분할수량을 2개 이상 입력하세요."}
    tx = _nx_tx(); cur = tx.cursor()
    try:
        cur.execute("""SELECT BOX_NO, ITEM_CODE, PLAN_YMD, ISNULL(LINE_NO,''), PLAN_QTY,
                          SHEET_NO, ISNULL(PROD_FLAG,''), ISNULL(DELETE_FLAG,'0'), ISNULL(PARENT_BOX_NO,0)
                        FROM nx.PR_T_INDI_SHEET2 WHERE BOX_NO=?""", int(box))
        r = cur.fetchone()
        if not r:
            tx.rollback(); return {"ok": False, "detail": f"간판 {box} 없음"}
        if str(r[7] or '0').strip() == '1':
            tx.rollback(); return {"ok": False, "detail": f"간판 {box} 은(는) 이미 삭제/분할된 간판입니다."}
        if str(r[6] or '').strip() == '1':
            tx.rollback(); return {"ok": False, "detail": f"간판 {box} 은(는) 이미 실적이 잡혀 분할할 수 없습니다."}
        item = str(r[1] or '').strip(); ymd = str(r[2] or '').strip()
        line = str(r[3] or '').strip(); org = float(r[4] or 0); sn = str(r[5] or '').strip()
        tot = round(sum(lst), 4)
        if abs(tot - org) > 0.0001:
            tx.rollback()
            return {"ok": False, "detail": f"분할수량 합계 {tot:g} ≠ 원본수량 {org:g} (같아야 합니다)"}
        # ① 원본 삭제표시
        cur.execute("""UPDATE nx.PR_T_INDI_SHEET2 SET DELETE_FLAG='1' WHERE BOX_NO=?""", int(box))
        # ② 분할본 생성
        cur.execute("SELECT ISNULL(MAX(BOX_NO),0) FROM nx.PR_T_INDI_SHEET2")
        nb = int(cur.fetchone()[0] or 0)
        made = []
        for q in lst:
            nb += 1
            cur.execute("""INSERT INTO nx.PR_T_INDI_SHEET2(BOX_NO,ITEM_CODE,PLAN_YMD,LINE_NO,PLAN_QTY,
                              ORG_PLAN_QTY,PRINT_USER_ID,PRINT_DATETIME,SHEET_NO,DELETE_FLAG,PARENT_BOX_NO)
                            VALUES(?,?,?,?,?,?,?,GETDATE(),?,'0',?)""",
                        nb, item, ymd, (line or None), q, q, user, sn, int(box))
            made.append({"box_no": nb, "qty": q})
        tx.commit()
        return {"ok": True, "parent": int(box), "sheet_no": sn, "item": item,
                "cnt": len(made), "total": tot, "issued": made}
    except Exception as e:
        try: tx.rollback()
        except Exception: pass
        return {"ok": False, "detail": str(e)[:300]}
    finally:
        tx.close()

@router.get("/api/prodsheet/kanban-print")
def prodsheet_kanban_print(box_no: str = Query(...)):
    """가간판 1장 인쇄 데이터(A4 1/3 양식).
       레이아웃(실측 대조): 라인 · 도번 · 간판순번 · 박스종류/표준포장수 · 바코드(GP+BOX_NO 8자리)
                          · 생산날짜 · 품명 · 공정순서(파트명) · 용접자/검사자 · 출력일시/발행자 · 용접전표번호"""
    bn = ''.join(c for c in str(box_no or '') if c.isdigit())
    if not bn:
        return {"ok": False, "detail": "간판번호 필수"}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT b.BOX_NO, b.ITEM_CODE, b.PLAN_YMD, ISNULL(b.LINE_NO,''), b.PLAN_QTY,
                          b.ORG_PLAN_QTY, b.SHEET_NO, ISNULL(b.PRINT_USER_ID,''), b.PRINT_DATETIME,
                          ISNULL(i.item_name,''), ISNULL(s.PACK_KIND,''), ISNULL(s.PACK_QTY,0),
                          ISNULL(s.PROD_WORKER,''), ISNULL(s.INSP_WORKER,'')
                        FROM nx.PR_T_INDI_SHEET2 b WITH(NOLOCK)
                        LEFT JOIN nx.item i WITH(NOLOCK) ON i.ITEM_CODE=b.ITEM_CODE
                        LEFT JOIN nx.PR_M_ITEM_SUB s WITH(NOLOCK) ON s.ITEM_CODE=b.ITEM_CODE
                       WHERE b.BOX_NO=?""", int(bn))
        r = cur.fetchone()
        if not r:
            return {"ok": False, "detail": f"간판 {bn} 없음"}
        sn = str(r[6] or '').strip()
        # 간판 순번(그 전표 내 몇 번째) · 전체 매수
        cur.execute("""SELECT COUNT(*) FROM nx.PR_T_INDI_SHEET2 WITH(NOLOCK)
                        WHERE SHEET_NO=? AND ISNULL(DELETE_FLAG,'0')<>'1' AND BOX_NO<=?""", sn, int(bn))
        seq = int(cur.fetchone()[0] or 1)
        cur.execute("""SELECT COUNT(*) FROM nx.PR_T_INDI_SHEET2 WITH(NOLOCK)
                        WHERE SHEET_NO=? AND ISNULL(DELETE_FLAG,'0')<>'1'""", sn)
        tot = int(cur.fetchone()[0] or 1)
        # ★공정순서 = 그 전표의 전 공정을 PROC_SEQ 순으로 이어붙임.
        #   레거시 실측: "01라인(용접)-01라인(조립)"  (G공정 하나만이 아니라 전체)
        #   (2026-08-19: 기존엔 G공정 1건만 표시해 다공정 품목에서 앞공정이 누락됐음)
        cur.execute("""SELECT ISNULL(g.GAGONG_PROC_DESC, d.GAGONG_PROC_CODE)
                         FROM nx.PR_T_INDI_WELD_SHEET_DTL d WITH(NOLOCK)
                         LEFT JOIN nx.PR_M_PROC_GAGONG g WITH(NOLOCK) ON g.GAGONG_PROC_CODE=d.GAGONG_PROC_CODE
                        WHERE d.SHEET_NO=? ORDER BY d.PROC_SEQ""", sn)
        _seq = [str(x[0]).strip() for x in cur.fetchall() if x and x[0] and str(x[0]).strip()]
        proc_nm = "-".join(_seq)
        return {"ok": True, "box_no": int(r[0] or 0), "barcode": "GP" + str(int(r[0] or 0)).zfill(8),
                "item": str(r[1] or '').strip(), "plan_ymd": str(r[2] or '').strip(),
                "line": str(r[3] or '').strip(), "qty": float(r[4] or 0), "org_qty": float(r[5] or 0),
                "sheet_no": sn, "sheet_no_fmt": sn.zfill(8),
                "print_user": str(r[7] or '').strip(),
                "print_dt": (str(r[8])[:19] if r[8] else ""),
                "nm": str(r[9] or '').strip(), "pack_kind": str(r[10] or '').strip(),
                "pack_qty": int(r[11] or 0), "prod_worker": str(r[12] or '').strip(),
                "insp_worker": str(r[13] or '').strip(),
                "seq": seq, "tot": tot, "proc_nm": proc_nm}
    finally:
        nx.close()

_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def _qr_datecode(ymd6: str) -> str:
    """QR 날짜코드 = 'KPI' + 연1 + 월1 + 일1 (0-9 다음 A-Z; 10=A … 31=V).
       ★실측 검증: 2026-01~08 총 168개 일자 전부 일치(불일치 0).
         예 260819 → KPI68J  (6=2026 / 8=8월 / J=19일)
       ※연도자리는 2026년 데이터만 있어 '연 끝자리' 가정. 10~12월(A/B/C)도 미검증
         — 2026-10월 데이터가 쌓이면 KPI6A 인지 재확인할 것."""
    d = ''.join(c for c in str(ymd6 or '') if c.isdigit())
    if len(d) < 6:
        return "KPI"
    yy, mm, dd = int(d[0:2]), int(d[2:4]), int(d[4:6])
    return "KPI" + _B36[yy % 10] + _B36[mm] + _B36[dd]

def _qr_code(item: str, ymd6: str, seq: int) -> str:
    """QR 전체 = 도번 + 날짜코드 + 일련4자리.  예 AJR30095101KPI68J0145"""
    return f"{item}{_qr_datecode(ymd6)}{int(seq):04d}"

@router.get("/api/prodsheet/label-preview")
def prodsheet_label_preview(sheet_no: str = Query(...), qty: float = Query(0)):
    """제품스티커(라벨) 발행 팝업 미리보기 — 출력수량·용접사·검사자·QR 범위.
       ★일련번호 = (도번 × 출력일자) 단위로 0001부터, 같은 날 추가발행 시 이어붙임.
         (실측: AJR30125602/260818 → 0001~2, 0003~5, 0006~8 … / 날짜 바뀌면 0001 리셋)"""
    sn = str(sheet_no or "").strip()
    if not sn:
        return {"ok": False, "detail": "전표번호 필수"}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT h.ITEM_CODE, h.PLAN_QTY, h.PLAN_YMD, ISNULL(h.LINE_NO,''),
                          ISNULL(i.item_name,''), ISNULL(s.PROD_WORKER,''), ISNULL(s.INSP_WORKER,''),
                          ISNULL(s.STICKER_COLOR,'')
                        FROM nx.PR_T_INDI_WELD_SHEET h WITH(NOLOCK)
                        LEFT JOIN nx.item i WITH(NOLOCK) ON i.ITEM_CODE=h.ITEM_CODE
                        LEFT JOIN nx.PR_M_ITEM_SUB s WITH(NOLOCK) ON s.ITEM_CODE=h.ITEM_CODE
                       WHERE h.SHEET_NO=?""", sn)
        r = cur.fetchone()
        if not r:
            return {"ok": False, "detail": f"전표 {sn} 없음"}
        item = str(r[0] or '').strip(); plan_qty = float(r[1] or 0)
        today6 = datetime.now().strftime('%y%m%d')
        # 그 도번·오늘자로 이미 나간 마지막 일련번호
        cur.execute("""SELECT ISNULL(SUM(PRINT_QTY),0) FROM nx.PR_T_PRINT_STICKER WITH(NOLOCK)
                        WHERE ITEM_CODE=? AND PRINT_YMD=?""", item, today6)
        used = int(float(cur.fetchone()[0] or 0))
        # 이 전표로 이미 발행한 수량
        cur.execute("""SELECT ISNULL(SUM(PRINT_QTY),0), COUNT(*) FROM nx.PR_T_PRINT_STICKER WITH(NOLOCK)
                        WHERE SHEET_NO=?""", sn)
        x = cur.fetchone()
        issued = float(x[0] or 0); issued_cnt = int(x[1] or 0)
        want = float(qty) if float(qty or 0) > 0 else max(plan_qty - issued, 0)
        frm, to = used + 1, used + int(want)
        return {"ok": True, "sheet_no": sn, "item": item, "nm": str(r[4] or '').strip(),
                "plan_ymd": str(r[2] or '').strip(), "plan_qty": plan_qty,
                "line": str(r[3] or '').strip(),
                "prod_worker": str(r[5] or '').strip(), "insp_worker": str(r[6] or '').strip(),
                "sticker_color": str(r[7] or '').strip(),
                "print_ymd": today6, "issued_qty": issued, "issued_cnt": issued_cnt,
                "remain": round(plan_qty - issued, 4), "qty": want,
                "seq_from": frm, "seq_to": to,
                "qr_from": _qr_code(item, today6, frm) if want > 0 else "",
                "qr_to": _qr_code(item, today6, to) if want > 0 else "",
                "datecode": _qr_datecode(today6)}
    finally:
        nx.close()

@router.post("/api/prodsheet/label-issue")
def prodsheet_label_issue(payload: dict = Body(...)):
    """제품스티커(라벨) 발행 → nx.PR_T_PRINT_STICKER.
       PRINT_SEQ = 전역 MAX+1(실측 185,461대) · START_NO=1(레거시 고정)
       QR_BARCODE_FROM/TO = 도번+날짜코드+일련4  (도번×출력일자 단위 누적)
       재고/실적 무변동."""
    sn = str(payload.get("sheet_no", "") or "").strip()
    qty = int(float(payload.get("qty") or 0))
    worker = str(payload.get("worker", "") or "").strip()[:10]      # 용접사
    inspector = str(payload.get("inspector", "") or "").strip()[:10]  # 검사자
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    if not sn:
        return {"ok": False, "detail": "전표번호 필수"}
    if qty <= 0:
        return {"ok": False, "detail": "출력수량을 입력하세요."}
    tx = _nx_tx(); cur = tx.cursor()
    try:
        cur.execute("SELECT ITEM_CODE, PLAN_QTY FROM nx.PR_T_INDI_WELD_SHEET WHERE SHEET_NO=?", sn)
        h = cur.fetchone()
        if not h:
            tx.rollback(); return {"ok": False, "detail": f"전표 {sn} 없음"}
        item = str(h[0] or '').strip()
        today6 = datetime.now().strftime('%y%m%d')
        cur.execute("""SELECT ISNULL(SUM(PRINT_QTY),0) FROM nx.PR_T_PRINT_STICKER
                        WHERE ITEM_CODE=? AND PRINT_YMD=?""", item, today6)
        used = int(float(cur.fetchone()[0] or 0))
        frm, to = used + 1, used + qty
        cur.execute("SELECT ISNULL(MAX(PRINT_SEQ),0)+1 FROM nx.PR_T_PRINT_STICKER")
        pseq = int(cur.fetchone()[0] or 1)
        qf, qt = _qr_code(item, today6, frm), _qr_code(item, today6, to)
        cur.execute("""INSERT INTO nx.PR_T_PRINT_STICKER(PRINT_SEQ,PRINT_YMD,ITEM_CODE,WORK_CODE,PROD_TAG,
                          WORKER_CODE,START_NO,PRINT_QTY,PRINT_USER_ID,PRINT_DATETIME,SHEET_NO,
                          QR_BARCODE_FROM,QR_BARCODE_TO)
                        VALUES(?,?,?,?,'1',?,1,?,?,GETDATE(),?,?,?)""",
                    pseq, today6, item, (worker or None), (inspector or None),
                    qty, user, sn, qf, qt)
        tx.commit()
        return {"ok": True, "sheet_no": sn, "item": item, "print_seq": pseq,
                "print_ymd": today6, "qty": qty, "seq_from": frm, "seq_to": to,
                "qr_from": qf, "qr_to": qt}
    except Exception as e:
        try: tx.rollback()
        except Exception: pass
        return {"ok": False, "detail": str(e)[:300]}
    finally:
        tx.close()

@router.get("/api/prodsheet/label-print")
def prodsheet_label_print(print_seq: str = Query(...), start_no: int = Query(0), end_no: int = Query(0),
                          worker: str = Query(""), inspector: str = Query("")):
    """라벨 인쇄 데이터 — 낱장 목록.
       양식(QR3 실측, 40×20mm): 좌측 QR / PNC Industry / {출력일자} {PRINT_SEQ}-{일련4}
                                / n / 전체 / 도번 / 용접사(생산자)/검사자
       ★재발행: start_no~end_no 로 범위 지정(레거시 w_pr_input_469 재발행 팝업).
         미지정이면 발행 당시 전체 범위. worker/inspector 를 주면 그 값으로 덮어씀."""
    ps = ''.join(c for c in str(print_seq or '') if c.isdigit())
    if not ps:
        return {"ok": False, "detail": "라벨번호 필수"}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT s.PRINT_SEQ, s.PRINT_YMD, s.ITEM_CODE, s.PRINT_QTY,
                          ISNULL(s.QR_BARCODE_FROM,''), ISNULL(s.QR_BARCODE_TO,''),
                          ISNULL(s.WORK_CODE,''), ISNULL(s.WORKER_CODE,''),
                          s.SHEET_NO, ISNULL(s.PRINT_USER_ID,''), s.PRINT_DATETIME,
                          ISNULL(i.item_name,''), ISNULL(m.PROD_WORKER,''), ISNULL(m.INSP_WORKER,'')
                        FROM nx.PR_T_PRINT_STICKER s WITH(NOLOCK)
                        LEFT JOIN nx.item i WITH(NOLOCK) ON i.ITEM_CODE=s.ITEM_CODE
                        LEFT JOIN nx.PR_M_ITEM_SUB m WITH(NOLOCK) ON m.ITEM_CODE=s.ITEM_CODE
                       WHERE s.PRINT_SEQ=?""", int(ps))
        r = cur.fetchone()
        if not r:
            return {"ok": False, "detail": f"라벨 {ps} 없음"}
        item = str(r[2] or '').strip(); ymd = str(r[1] or '').strip()
        qty = int(float(r[3] or 0))
        qf = str(r[4] or '').strip()
        # QR From 끝 4자리 = 시작 일련번호
        start = int(qf[-4:]) if len(qf) >= 4 and qf[-4:].isdigit() else 1
        end = start + qty - 1
        # ★재발행 범위 = **순번(1부터)** 기준(2026-08-28 사용자 확정).
        #   "1~50 이면 50장, 30~50 이면 30번째부터 50번째까지 21장(양끝 포함)".
        #   ⛔종전엔 절대 QR번호(예 35~134)로 클램프해서 1~50 을 넣으면 35~50(16장)이 됐다.
        #   내부 계산은 절대번호(abs = start + 순번-1)로 하고, 화면에는 순번을 돌려준다.
        n1 = int(start_no) if int(start_no or 0) > 0 else 1
        n2 = int(end_no) if int(end_no or 0) > 0 else qty
        n1 = max(1, min(n1, qty)); n2 = max(n1, min(n2, qty))
        s2 = start + n1 - 1          # 절대 QR 시작번호
        e2 = start + n2 - 1          # 절대 QR 종료번호
        w2 = str(worker or '').strip() or str(r[6] or '').strip() or str(r[12] or '').strip()
        i2 = str(inspector or '').strip() or str(r[7] or '').strip() or str(r[13] or '').strip()
        n_out = n2 - n1 + 1
        # ★n(현재)/tot(전체)는 발행 전체 기준. 부분 재발행해도 원래 번호를 유지해야
        #   현장에서 몇 번째 라벨인지 알 수 있음(예 4~6 재출력 → 4/6, 5/6, 6/6).
        labels = [{"n": n1 + i, "seq": s2 + i,
                   "qr": _qr_code(item, ymd, s2 + i),
                   "disp": f"{ymd} {int(r[0])}-{s2 + i:04d}"}
                  for i in range(n_out)]
        return {"ok": True, "print_seq": int(r[0]), "print_ymd": ymd, "item": item,
                "qty": n_out, "org_qty": qty, "nm": str(r[11] or '').strip(),
                # 화면 입력칸은 순번(1~qty). abs_* 는 실제 QR 번호(참고용).
                "start_no": n1, "end_no": n2, "org_start": 1, "org_end": qty,
                "abs_start": s2, "abs_end": e2, "abs_org_start": start, "abs_org_end": end,
                "worker": w2, "inspector": i2,
                "sheet_no": str(r[8] or '').strip(),
                "print_user": str(r[9] or '').strip(),
                "print_dt": (str(r[10])[:19] if r[10] else ""),
                # ★QR 범위 = 지금 선택한 구간(labels 의 처음/끝). 종전엔 발행 전체 범위를
                #   그대로 보여줘 30~50 을 골라도 35~134 로 표시됐다(2026-08-28).
                "qr_from": (labels[0]["qr"] if labels else qf),
                "qr_to": (labels[-1]["qr"] if labels else str(r[5] or '').strip()),
                "qr_org_from": qf, "qr_org_to": str(r[5] or '').strip(),
                "labels": labels}
    finally:
        nx.close()

@router.post("/api/prodsheet/issue")
def prodsheet_issue(payload: dict = Body(...)):
    """발행 채번 → nx.sheet_issue. kind J전표/G간판/L라벨. box_no/print_seq/sheet_no=nx max+1."""
    kind = str(payload.get("kind", "")).strip()
    rows = payload.get("rows", []) or []
    if kind not in ("J", "G", "L"):
        raise HTTPException(400, "kind 오류(J전표/G간판/L라벨)")
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT ISNULL(MAX(box_no),0), ISNULL(MAX(print_seq),0), ISNULL(MAX(sheet_no),0) FROM nx.sheet_issue")
        mx = cur.fetchone(); box = int(mx[0] or 0); seq = int(mx[1] or 0); sheet = int(mx[2] or 0)
        issued = 0
        for r in rows:
            ic = str(r.get("item_code", "") or "").strip()
            if not ic:
                continue
            qty = float(r.get("plan_qty") or 0)
            sheet += 1; bx = ps = qf = qt = None
            if kind == "G":
                box += 1; bx = box
            elif kind == "L":
                seq += 1; ps = seq
                qf = f"{ic}{sheet:08d}0001"; qt = f"{ic}{sheet:08d}{int(max(qty,1)):04d}"
            cur.execute("""INSERT INTO nx.sheet_issue(kind,item_code,assy_code,work_order,line_no,plan_ymd,plan_qty,
                box_no,print_seq,qr_from,qr_to,sheet_no,issue_user,issue_dt)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,GETDATE())""",
                kind, ic, (r.get("assy") or None), (r.get("work_order") or None), (r.get("work_center") or None),
                (r.get("plan_ymd") or None), qty, bx, ps, qf, qt, sheet, user)
            issued += 1
        return {"ok": True, "issued": issued, "kind": kind}
    finally:
        nx.close()

# ===================== 공정별 바코드생산실적 (w_pr_input_520 / _pop / 526) =====================
# ★2026-08-19 재구성 — 레거시 실측 역산(스크린샷 + PR_T_PROD_DTL 3,351건 분석).
#   [구조] 상단에서 기준일자·파트코드·공정코드·작업자·설비를 먼저 고정 → 그 공정의 바코드만 스캔.
#          (공정을 미리 고정하므로 "용접전표로 조립 실적" 같은 오등록이 원천 차단됨)
#   [실적 기록처] ★nx.PR_T_PROD_DTL (레거시 미러). 웹 자체 nx.proc_barcode 아님.
#          실측: UPDATE_WINDOW='w_pr_input_520' 3,351건 / '_pop' 47건 — 이 화면이 쓰는 유일한 원장.
#          ※PR_T_INDI_WELD_SHEET_DTL.PROD_QTY 는 w_pr_input_467(다른 화면)이 채우는 값 — 여기와 무관.
#   [채우는 필드] ITEM_CODE·PROD_YMD·PROD_HMS·PROD_QTY·PROD_USER_ID(작업자)
#                ·PART_CODE(파트)·S_WORK_CODE(공정)·FINISH_FLAG='0'
#                나머지(WORK_ORDER/LINE_NO/PROD_TAG/IN_PART_CODE)는 레거시도 비움(실측 0%).
#   [520 vs 팝업] 520=전량 한번에(바코드 2회 스캔=확인절차, 기록은 1건)
#                 팝업(526)=부분수량 처리. 잔여 남으면 재스캔 시 "처리/총계"로 이어짐.
def _bom_expand(cur, item, gpc_like):
    """BOM 전개 — ★레거시 dw_pr_input_520_2 SQL 이식.
       가상도번(VIR_ITEM_FLAG='1')은 재귀로 펼치고, 사급부품(SAGUB_FLAG='1')·전개제외는 뺀다.
       ※레거시는 pr_m_item_bom_sub 서브쿼리로 사급을 봤으나 nx에 그 테이블이 없고
         PR_M_ITEM_BOM.SAGUB_FLAG 가 직접 있어 그것을 사용(2026-08-19 확인).
       반환: [(mat_code, work_code, mat_use_qty, gagong_proc_code)]
             ※use_qty=누적(cum_use_qty) 합계, gpc=그 자재를 투입하는 파트."""
    cur.execute("""
    WITH CTE_BOM(mat_code, cum_use_qty, work_code, sagub_flag, GAGONG_PROC_CODE, vir_item_flag)
    AS (
        SELECT b.mat_code, b.use_qty, m.work_code, ISNULL(b.SAGUB_FLAG,'0'),
               b.GAGONG_PROC_CODE, b.vir_item_flag
          FROM nx.pr_m_item_bom b
          JOIN nx.item i ON b.item_code=i.item_code
          JOIN nx.item m ON b.mat_code =m.item_code
         WHERE b.item_code=? AND ISNULL(b.except_flag,'0')<>'1'
        UNION ALL
        SELECT b.mat_code, cb.cum_use_qty*b.use_qty, m.work_code, ISNULL(b.SAGUB_FLAG,'0'),
               b.GAGONG_PROC_CODE, b.vir_item_flag
          FROM CTE_BOM cb
          JOIN nx.pr_m_item_bom b ON cb.mat_code=b.item_code
          JOIN nx.item i ON b.item_code=i.item_code
          JOIN nx.item m ON b.mat_code =m.item_code
         WHERE ISNULL(b.except_flag,'0')<>'1' AND cb.vir_item_flag='1'
    )
    SELECT mat_code, MAX(ISNULL(work_code,'')) work_code, SUM(cum_use_qty) mat_use_qty,
           ISNULL(gagong_proc_code,'') gpc
      FROM CTE_BOM a
     WHERE ISNULL(a.sagub_flag,'0')='0' AND a.GAGONG_PROC_CODE LIKE ?
       AND ISNULL(a.vir_item_flag,'0')<>'1'
     GROUP BY mat_code, ISNULL(gagong_proc_code,'') OPTION(MAXRECURSION 0)""", item, gpc_like)
    return [(str(r[0]).strip(), str(r[1] or '').strip(), float(r[2] or 0), str(r[3] or '').strip())
            for r in cur.fetchall()]

def _prod_dest(cur, item, upper_item=None):
    """★2026-08-25 생산실적 입고처 판정 (사용자 확정 규칙).

       ★판정 근거는 오직 전표의 UPPER_ITEM_CODE(upper_item 인자).
         · upper 가 비었거나 자기 자신 → 영업창고(ASSY). 최종품이거나 단품/직납분.
         · upper 가 다른 품번(=서브품)  → 그 상위를 보고 결정
             - 상위가 업체(IN_CUST_CODE 있음) → 자재창고
             - 상위가 사내                     → 생산창고 = **상위의 파트**
             - 상위에 파트가 없으면(가상 등)   → 더 위로 올라가 재판정

       왜 상위 파트인가: 서브품 실적은 그 상위를 만드는 파트의 재고가 되어야
       나중에 상위 실적을 잡을 때 그 파트에서 차감된다. 자기 파트에 쌓으면
       상위 실적 시 차감할 재고가 없다.
       (구버전은 GC_GUBUN W/K 만 자재창고, 나머지 전부 ASSY → 서브품이 영업창고로
        새어나갔다.)

       ★BOM 역추적 폴백은 쓰지 않는다. 같은 품번이 서브품으로도, 단품/직납으로도
         쓰이는 경우가 있어(5006AR4091G·AJR74482401 등) "BOM 에 상위가 있다"는
         이유로 생산창고에 보내면 직납분이 영업창고에서 사라진다.
         이번 실적이 어느 상위를 위한 것인지는 전표만 안다.
         (실측: 최근 전표 6,792건 중 4,955건이 upper=자기자신)

       반환: ('ASSY', None) | ('PART', 파트코드) | ('MAT', None)
    """
    it = str(item or "").strip()
    if not it:
        return ("ASSY", None)
    seen = set()
    # ★전표 상위품번이 자기 자신이 아니면 그것이 곧 상위 — 그 상위부터 판정한다.
    _up = str(upper_item or "").strip()
    if _up and _up != it:
        cur.execute("""SELECT ISNULL(m.in_cust,''),
                              ISNULL((SELECT TOP 1 b.VIR_ITEM_FLAG FROM nx.CS_M_ITEM_BOM b WITH(NOLOCK)
                                       WHERE b.MAT_CODE=? ),'0')
                         FROM nx.item m WITH(NOLOCK) WHERE m.ITEM_CODE=?""", _up, _up)
        _r = cur.fetchone()
        _ic = str(_r[0] or '').strip() if _r else ''
        if _ic:
            return ("MAT", None)                 # 상위가 업체
        cur.execute("""SELECT TOP 1 GAGONG_PROC_CODE FROM nx.PR_M_ITEM_PROC_GAGONG
                        WHERE ITEM_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')<>''
                        ORDER BY PROC_SEQ DESC""", _up)
        _r2 = cur.fetchone()
        _gp = str(_r2[0] or '').strip() if _r2 else ''
        if _gp:
            return ("PART", _gp)                 # 상위의 파트
        seen.add(_up)
        stack = [_up]                            # 상위가 가상 등으로 파트가 없으면 더 위로
        depth = 0
        while stack and depth <= 8:
            depth += 1
            _c = stack.pop(0)
            cur.execute("""SELECT b.ITEM_CODE, ISNULL(b.VIR_ITEM_FLAG,'0'), ISNULL(m.in_cust,'')
                             FROM nx.CS_M_ITEM_BOM b WITH(NOLOCK)
                             LEFT JOIN nx.item m WITH(NOLOCK) ON m.ITEM_CODE=b.ITEM_CODE
                            WHERE b.MAT_CODE=?""", _c)
            for p, vir, incust in [(str(r[0] or '').strip(), str(r[1] or '0'), str(r[2] or '').strip())
                                   for r in cur.fetchall()]:
                if incust:
                    return ("MAT", None)
                cur.execute("""SELECT TOP 1 GAGONG_PROC_CODE FROM nx.PR_M_ITEM_PROC_GAGONG
                                WHERE ITEM_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')<>''
                                ORDER BY PROC_SEQ DESC""", p)
                _r3 = cur.fetchone()
                _g3 = str(_r3[0] or '').strip() if _r3 else ''
                if _g3:
                    return ("PART", _g3)
                if p not in seen:
                    seen.add(p); stack.append(p)
        return ("ASSY", None)
    # ★2026-08-25 전표에 상위가 없거나 자기 자신이면 ASSY(영업창고).
    #   BOM 역추적 폴백을 쓰지 않는다 — 같은 품번이 서브품으로도, 단품/직납으로도
    #   쓰이는 경우가 있어(예: 5006AR4091G, AJR74482401) BOM 에 상위가 있다는 이유로
    #   생산창고로 보내면 직납분이 영업창고에서 사라진다.
    #   "이번 실적이 어느 상위를 위한 것인가"는 전표만 알고, 전표가 자기 자신이면
    #   그 자체로 출하 대상이다. (실측: 최근 전표 6,792건 중 4,955건이 upper=자기자신)
    return ("ASSY", None)


def _set_mat_stock_wh(cur, win, part_code, mat_code, qty, user):
    """파트창고 재고 가감 — 레거시 f_pr_set_mat_stock_wh (PART_CODE 기준)."""
    cur.execute("""UPDATE nx.PR_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                    WHERE MAT_CODE=? AND PART_CODE=?""", qty, user, win, mat_code, part_code)
    if cur.rowcount == 0:
        cur.execute("""INSERT INTO nx.PR_T_MAT_STOCK_WH(MAT_CODE,PART_CODE,STOCK_QTY,
                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?,?,GETDATE(),?)""", mat_code, part_code, qty, user, win)

def _set_mat_stock(cur, win, work_code, mat_code, qty, user):
    """품목별 자재재고 가감 — 레거시 f_pr_set_mat_stock (CUST_CODE=''+WORK_CODE 기준).
       ※nx에 없던 테이블이라 2026-08-19 라이브 구조 복제 후 잔량 이관하여 생성."""
    cur.execute("""UPDATE nx.PR_T_MAT_STOCK SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                    WHERE CUST_CODE='' AND WORK_CODE=? AND MAT_CODE=?""",
                qty, user, win, work_code, mat_code)
    if cur.rowcount == 0:
        cur.execute("""INSERT INTO nx.PR_T_MAT_STOCK(CUST_CODE,WORK_CODE,MAT_CODE,STOCK_QTY,
                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES('',?,?,?,?,GETDATE(),?)""", work_code, mat_code, qty, user, win)

def _set_pu_mat_stock(cur, win, mat_code, cust_code, qty, user):
    """자재창고 재고 가감 — 레거시 f_pu_set_mat_stock (자재창고 입고 케이스)."""
    cur.execute("""UPDATE nx.PU_T_MAT_STOCK SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                    WHERE MAT_CODE=? AND CUST_CODE=?""", qty, user, win, mat_code, cust_code)
    if cur.rowcount == 0:
        cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK(MAT_CODE,CUST_CODE,STOCK_QTY,
                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?,?,GETDATE(),?)""", mat_code, cust_code, qty, user, win)

def _set_pu_mat_stock_wh(cur, win, mat_code, cust_code, gpc, qty, user):
    """자재 파트창고 재고 가감 — 레거시 f_pu_set_mat_stock_wh."""
    cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                    WHERE MAT_CODE=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                qty, user, win, mat_code, cust_code, gpc)
    if cur.rowcount == 0:
        cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK_WH(MAT_CODE,CUST_CODE,GAGONG_PROC_CODE,STOCK_QTY,
                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?,?,?,GETDATE(),?)""", mat_code, cust_code, gpc, qty, user, win)

def _set_ready_stock(cur, win, item, cust, proc_gubun, qty, user):
    """준비재고 잔량 가감 — 레거시 f_pu_set_ready_stock."""
    cur.execute("""UPDATE nx.PU_T_READY_STOCK SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                    WHERE ITEM_CODE=? AND CUST_CODE=? AND PROC_GUBUN=?""",
                qty, user, win, item, cust, proc_gubun)
    if cur.rowcount == 0:
        cur.execute("""INSERT INTO nx.PU_T_READY_STOCK(ITEM_CODE,CUST_CODE,PROC_GUBUN,STOCK_QTY,
                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?,?,?,GETDATE(),?)""", item, cust, proc_gubun, qty, user, win)

def _set_item_stock(cur, win, item, qty, user):
    """ASSY(완제품) 재고 가감 — 레거시 f_sa_set_item_stock. 영업창고 재고."""
    cur.execute("""UPDATE nx.SA_T_ITEM_STOCK SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                    WHERE ITEM_CODE=?""", qty, user, win, item)
    if cur.rowcount == 0:
        cur.execute("""INSERT INTO nx.SA_T_ITEM_STOCK(ITEM_CODE,STOCK_QTY,
                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?,GETDATE(),?)""", item, qty, user, win)

@router.get("/api/procbc/masters")
def procbc_masters(part: str = Query("")):
    """상단 드롭다운 소스 — 파트 목록 / (파트 선택시) 공정코드·설비·작업자.
       파트↔공정(S_WORK_CODE)↔설비 = nx.PR_M_ITEM_PROC_GAGONG 실측 조합
       작업자 = nx.PR_M_PROC_GAGONG_WORKER (WORK_FLAG='1')"""
    nx = _nx(); cur = nx.cursor()
    cn = _conn(); c2 = cn.cursor()
    try:
        # 파트 목록(생산파트만 — 가공파트 P00xx는 별도 화면 소관)
        cur.execute("""SELECT DISTINCT GAGONG_PROC_CODE FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)
                        WHERE ISNULL(GAGONG_PROC_CODE,'')<>'' AND GAGONG_PROC_CODE NOT LIKE 'P00%'""")
        codes = [str(r[0]).strip() for r in cur.fetchall() if r[0]]
        nm = {}
        if codes:
            ph = ",".join("?" * len(codes))
            c2.execute(f"SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE IN ({ph})", *codes)
            for a, b in c2.fetchall(): nm[str(a).strip()] = b
        parts = sorted(({"code": c, "nm": nm.get(c, c)} for c in codes), key=lambda x: x["nm"])
        out = {"parts": parts, "procs": [], "machs": [], "workers": []}
        p = str(part or "").strip()
        if p:
            # 공정코드(S_WORK_CODE) + 설비 — 그 파트에서 실제 쓰이는 조합
            cur.execute("""SELECT S_WORK_CODE, ISNULL(MACH_CODE,''), COUNT(*) c
                             FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)
                            WHERE GAGONG_PROC_CODE=? AND ISNULL(S_WORK_CODE,'')<>''
                            GROUP BY S_WORK_CODE, ISNULL(MACH_CODE,'')
                            ORDER BY COUNT(*) DESC""", p)
            seen_p = {}; machs = []
            for sw, mc, c in cur.fetchall():
                sw = str(sw or '').strip(); mc = str(mc or '').strip()
                if sw and sw not in seen_p:
                    seen_p[sw] = True
                    out["procs"].append({"code": sw, "nm": f"{sw} {nm.get(p, p)}"})
                if mc and mc not in [m["code"] for m in machs]:
                    machs.append({"code": mc, "nm": mc, "cnt": int(c or 0)})
            out["machs"] = machs
            cur.execute("""SELECT WORKER_CODE FROM nx.PR_M_PROC_GAGONG_WORKER WITH(NOLOCK)
                            WHERE GAGONG_PROC_CODE=? AND ISNULL(WORK_FLAG,'1')='1'
                            ORDER BY WORKER_CODE""", p)
            out["workers"] = [{"code": str(r[0]).strip(), "nm": str(r[0]).strip()} for r in cur.fetchall() if r[0]]
        return out
    finally:
        nx.close(); cn.close()

@router.get("/api/procbc/lookup")
def procbc_lookup(barcode: str = Query(...), proc_code: str = Query("")):
    """바코드 스캔 → 품번·총수량·기처리수량·전표처리구분 반환.
       인식 대상(레거시 3종):
         · J 용접전표 : 8자리 전표번호      → nx.PR_T_INDI_WELD_SHEET
         · G 가간판   : GP + BOX_NO 8자리   → nx.PR_T_INDI_SHEET2
         · L 라벨     : 도번+KPI…+일련4     → nx.PR_T_PRINT_STICKER (QR From~To 범위)
       ★기처리수량 = nx.PR_T_PROD_DTL 누적(이 화면이 쓰는 유일한 실적원장).
         잔여가 남으면 팝업에서 부분처리 가능(레거시 526 '실적/총계')."""
    bc = barcode.strip()
    if not bc:
        raise HTTPException(400, "바코드가 필요합니다.")
    item = None; qty = 0.0; sheet = None; kind = None; meth = ""; box = None; lseq = None
    nx = _nx(); cur = nx.cursor()
    cn = _conn(); c2 = cn.cursor()
    try:
        up = bc.upper()
        # ① G 가간판 — GP + BOX_NO
        if up.startswith("GP") and bc[2:].isdigit():
            cur.execute("""SELECT TOP 1 ITEM_CODE, PLAN_QTY, SHEET_NO, BOX_NO
                             FROM nx.PR_T_INDI_SHEET2 WITH(NOLOCK)
                            WHERE BOX_NO=? AND ISNULL(DELETE_FLAG,'0')<>'1'""", int(bc[2:]))
            r = cur.fetchone()
            if r:
                item, qty, sheet = str(r[0]).strip(), float(r[1] or 0), str(r[2] or '').strip()
                box = int(r[3] or 0); kind, meth = "가간판", "G"
        # ② L 라벨 — QR 범위 안에 드는지
        if not item:
            cur.execute("""SELECT TOP 1 ITEM_CODE, PRINT_QTY, SHEET_NO, PRINT_SEQ
                             FROM nx.PR_T_PRINT_STICKER WITH(NOLOCK)
                            WHERE ? BETWEEN QR_BARCODE_FROM AND QR_BARCODE_TO
                              AND LEN(ISNULL(QR_BARCODE_FROM,''))=LEN(?)""", bc, bc)
            r = cur.fetchone()
            if r:
                item, qty, sheet = str(r[0]).strip(), float(r[1] or 0), str(r[2] or '').strip()
                lseq = int(r[3] or 0); kind, meth = "라벨", "L"
        # ③ J 용접전표 — 8자리 전표번호(0패딩 허용)
        if not item:
            _d = bc.lstrip("0") or "0"
            if _d.isdigit():
                cur.execute("""SELECT TOP 1 ITEM_CODE, PLAN_QTY, SHEET_NO
                                 FROM nx.PR_T_INDI_WELD_SHEET WITH(NOLOCK) WHERE SHEET_NO=?""", _d)
                r = cur.fetchone()
                if r:
                    item, qty, sheet = str(r[0]).strip(), float(r[1] or 0), str(r[2] or '').strip()
                    kind, meth = "용접전표", "J"
        if not item:
            return {"found": False, "msg": "바코드를 찾을 수 없습니다 (전표 8자리 / 간판 GP… / 라벨 QR)"}
        c2.execute("SELECT ISNULL(item_name,'') FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE=?", item)
        rr = c2.fetchone(); nm = rr[0] if rr else ""
        # ★기처리수량 = 이 바코드+공정의 STICKER 누적(레거시 w_pr_input_527 동일 기준).
        #   취소분(음수)이 함께 합산되므로 취소하면 자동으로 잔여가 늘어남.
        p = str(proc_code or "").strip()
        if p:
            cur.execute("""SELECT ISNULL(SUM(PROD_QTY),0) FROM nx.PR_T_PROD_DTL_STICKER WITH(NOLOCK)
                            WHERE BARCODE=? AND ISNULL(PROC_CODE,'')=?""", bc, p)
        else:
            cur.execute("""SELECT ISNULL(SUM(PROD_QTY),0) FROM nx.PR_T_PROD_DTL_STICKER WITH(NOLOCK)
                            WHERE BARCODE=?""", bc)
        done = float(cur.fetchone()[0] or 0)
        # 그 공정의 전표처리구분(품목 공정마스터) + PROC_SEQ(구간기록용)
        gmeth = ""; pseq = None
        if p:
            cur.execute("""SELECT TOP 1 ISNULL(JP_PROC_METHOD,''), PROC_SEQ FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)
                            WHERE ITEM_CODE=? AND GAGONG_PROC_CODE=?""", item, p)
            g = cur.fetchone()
            if g:
                gmeth = str(g[0]).strip() if g[0] else ""
                pseq = int(g[1] or 0) or None
        # ★★파트 불일치 차단(2026-08-19) — 선택한 파트가 이 바코드(전표)의 공정이 아니면 실적 불가.
        #   기존엔 pseq=None 이어도 그냥 통과해 무관한 파트(S1·S6…)에서 실적이 잡혔음.
        #   판정 = 그 전표의 DTL 공정목록(정본). 전표가 없으면 품목 공정마스터로 대체 판정.
        if p:
            _procs = []
            if sheet:
                cur.execute("""SELECT ISNULL(d.GAGONG_PROC_CODE,''), ISNULL(g.GAGONG_PROC_DESC,'')
                                 FROM nx.PR_T_INDI_WELD_SHEET_DTL d WITH(NOLOCK)
                                 LEFT JOIN nx.PR_M_PROC_GAGONG g WITH(NOLOCK)
                                        ON g.GAGONG_PROC_CODE=d.GAGONG_PROC_CODE
                                WHERE d.SHEET_NO=? ORDER BY d.PROC_SEQ""", sheet)
                _procs = [(str(x[0] or '').strip(), str(x[1] or '').strip()) for x in cur.fetchall()]
            if not _procs:
                cur.execute("""SELECT ISNULL(m.GAGONG_PROC_CODE,''), ISNULL(g.GAGONG_PROC_DESC,'')
                                 FROM nx.PR_M_ITEM_PROC_GAGONG m WITH(NOLOCK)
                                 LEFT JOIN nx.PR_M_PROC_GAGONG g WITH(NOLOCK)
                                        ON g.GAGONG_PROC_CODE=m.GAGONG_PROC_CODE
                                WHERE m.ITEM_CODE=? ORDER BY m.PROC_SEQ""", item)
                _procs = [(str(x[0] or '').strip(), str(x[1] or '').strip()) for x in cur.fetchall()]
            _codes = [c for c, _ in _procs if c]
            _lst = ", ".join((f"{c} {n}" if n else c) for c, n in _procs if c)
            _hdr = (f"· 바코드 {bc} ({kind})\n"
                    f"· 품번 {item} {nm}\n"
                    + (f"· 전표 {sheet}\n" if sheet else ""))
            # (a) 그 전표/품목의 공정목록에 아예 없는 파트
            if _codes and p not in _codes:
                return {"found": False, "mismatch": True, "barcode": bc, "kind": kind,
                        "item_code": item, "item_name": nm, "sheet_no": sheet,
                        "sel_proc": p, "procs": _codes,
                        "msg": (f"이 바코드는 [{p}] 공정의 것이 아닙니다.\n\n" + _hdr
                                + f"· 해당 공정 : {_lst}\n\n"
                                f"파트코드를 [{_lst}] 중에서 선택한 뒤 다시 스캔하세요.")}
            # (b) ★공정목록엔 있으나 실적수단이 다름 — 예: S5(전표)에서 가간판 스캔.
            #     JP_PROC_METHOD 가 공정별 실적수단 정본(J=전표 / G=가간판). 경고가 아니라 차단.
            #     (2026-08-19: 경고로만 두었더니 S5-2 간판이 S5 로 등록돼 계획6 전표에 9가 잡힘)
            if gmeth and meth and gmeth != meth:
                _own = ""      # 이 바코드가 원래 속한 공정(같은 품목에서 실적수단이 일치하는 공정)
                cur.execute("""SELECT TOP 1 ISNULL(m.GAGONG_PROC_CODE,''), ISNULL(g.GAGONG_PROC_DESC,'')
                                 FROM nx.PR_M_ITEM_PROC_GAGONG m WITH(NOLOCK)
                                 LEFT JOIN nx.PR_M_PROC_GAGONG g WITH(NOLOCK)
                                        ON g.GAGONG_PROC_CODE=m.GAGONG_PROC_CODE
                                WHERE m.ITEM_CODE=? AND ISNULL(m.JP_PROC_METHOD,'')=?
                                ORDER BY m.PROC_SEQ""", item, meth)
                _o = cur.fetchone()
                if _o:
                    _own = (f"{str(_o[0]).strip()} {str(_o[1] or '').strip()}").strip()
                return {"found": False, "mismatch": True, "barcode": bc, "kind": kind,
                        "item_code": item, "item_name": nm, "sheet_no": sheet,
                        "sel_proc": p, "procs": ([_own.split(' ')[0]] if _own else _codes),
                        "msg": (f"[{p}] 공정은 {_METH_NM.get(gmeth, gmeth)}(으)로 실적을 잡는 공정입니다.\n"
                                f"{kind} 바코드로는 실적을 잡을 수 없습니다.\n\n" + _hdr
                                + (f"· 이 {kind}의 공정 : {_own}\n\n" if _own else "\n")
                                + (f"파트코드를 [{_own}](으)로 바꾼 뒤 다시 스캔하세요."
                                   if _own else "파트코드를 확인하세요."))}
        warn = ""
        # ★앞공정 실적 확인 — 앞공정이 안 끝났으면 뒷공정 실적을 잡으면 안 됨.
        #   전표 단위로 공정 진행이 관리되므로 DTL(PROC_SEQ) 실적으로 판정.
        #   (레거시 220 에도 '앞공정 재고가 모자랍니다' 체크가 있으나 구형 공정코드(1000/2000)
        #    기준이라 현 체계(S5→S5-2)에 맞게 DTL 기준으로 재구성. 2026-08-19)
        #   ※차단이 아니라 경고 — 실무상 예외가 있어(실측 위반 90/3,608) 사용자가 확인 후 진행 가능.
        prior = None
        if sheet and pseq and pseq > 1:
            cur.execute("""SELECT TOP 1 d.PROC_SEQ, ISNULL(d.GAGONG_PROC_CODE,''),
                                  ISNULL(g.GAGONG_PROC_DESC,''), ISNULL(d.PROD_QTY,0),
                                  ISNULL(d.PROD_FIN_FLAG,'0')
                             FROM nx.PR_T_INDI_WELD_SHEET_DTL d WITH(NOLOCK)
                             LEFT JOIN nx.PR_M_PROC_GAGONG g WITH(NOLOCK)
                                    ON g.GAGONG_PROC_CODE=d.GAGONG_PROC_CODE
                            WHERE d.SHEET_NO=? AND d.PROC_SEQ<?
                            ORDER BY d.PROC_SEQ DESC""", sheet, pseq)
            pr = cur.fetchone()
            if pr:
                prior = {"proc_seq": int(pr[0] or 0), "gpc": str(pr[1] or '').strip(),
                         "nm": str(pr[2] or '').strip(), "qty": float(pr[3] or 0),
                         "fin": str(pr[4] or '0').strip()}
        return {"found": True, "barcode": bc, "kind": kind, "method": meth,
                "item_code": item, "item_name": nm, "qty": qty, "sheet_no": sheet,
                "box_no": box, "label_seq": lseq, "proc_seq": pseq,
                "done_qty": done, "remain": round(qty - done, 4),
                "proc_method": gmeth, "warn": warn, "prior": prior}
    finally:
        nx.close(); cn.close()

@router.post("/api/procbc/save")
def procbc_save(payload: dict = Body(...)):
    """★바코드 생산실적 저장 — 레거시 w_pr_input_520.ue_save_after_sub() 이식(2026-08-19).

       [항상 수행]
         ① PR_T_PROD_DTL_STICKER  : 스캔 1건 = 1행. STA_DATETIME(시작)/PROD_DATETIME(종료)
                                    → 분할처리 시 구간마다 시작·종료가 각각 남음
         ② PR_T_INDI_WELD_SHEET_DTL : PROD_QTY = STICKER 합계로 재계산,
                                    계획 도달 시 FIN_DATETIME + PROD_FIN_FLAG='1'
         ③ PR_T_INDI_WELD_SHEET   : 마지막 공정 완료여부로 헤더 PROD_FIN_FLAG 갱신
         ④ PR_T_PROD_DTL_PROC     : (도번·일자·분·S_WORK·작업처·공정·TAG) 키로 누적

       [마지막 공정(proc_seq = max)에서만]
         ⑤ PR_T_PROD_DTL          : (도번·일자·분) 키로 누적
         ⑥ 입고처리 — STOCK_GAGONG_PROC_CODE 유무로 분기
            · 있고 GC_GUBUN in (W,K) : 자재창고 입고(PU_T_STOCK_MAINT tag='P' + 자재/파트재고 증가)
            · 있고 그 외             : 중간공정 → 파트창고 재고 증가
            · 없음                   : ASSY → SA_T_STOCK_MAINT tag='P' + 영업창고(SA_T_ITEM_STOCK) 증가
         ⑦ BOM 전개 → 파트별 자재 차감(PR_T_STOCK_MAINT_MAT tag='4' + 품목/파트 재고)
         ⑧ 준비재고 차감(PU_T_READY_STOCK_MAINT tag='A' + PU_T_READY_STOCK)

       [PROD_HMS] left(hms,4)+'00' — 분 단위 절삭(같은 분이면 누적)
       [취소] 수량을 음수로 보내면 위 전부가 반대로 적용되어 원복.
       [제외] Q1000(용접봉 공용창고)·Q2000 은 운영방침 변경으로 처리하지 않음.
       ※쓰기는 nx만. 라이브 PARTNER_ERP 무변경."""
    p = payload
    bc = str(p.get("barcode", "") or "").strip()
    proc = str(p.get("proc_code", "") or "").strip()        # 파트(GAGONG_PROC_CODE) 예 S5-2
    swork = str(p.get("s_work_code", "") or "").strip()     # 공정(S_WORK_CODE) 예 386
    item = str(p.get("item_code", "") or "").strip()
    qty = float(p.get("qty") or 0)
    worker = str(p.get("worker_code", "") or "").strip()[:20]
    line_user = str(p.get("line_user", "") or "").strip()[:20]
    user = (str(p.get("user") or "웹사용자")[:20])
    win = str(p.get("window", "") or "").strip() or "w_pr_input_520"
    work_code = str(p.get("work_code", "") or "").strip()
    prod_tag = str(p.get("prod_tag", "") or "").strip()
    sheet_ref = str(p.get("sheet_no") or "").strip()
    sta_at = str(p.get("sta_at") or "").strip()
    who = (line_user or user)
    if not bc or not item:
        raise HTTPException(400, "바코드·품번이 필요합니다.")
    if not proc:
        raise HTTPException(400, "파트를 선택하세요.")
    if qty == 0:
        return {"ok": False, "errors": ["처리수량을 입력하세요."]}
    nx = _nx_tx(); cur = nx.cursor()
    try:
        tot = float(p.get("total_qty") or 0)
        now = datetime.now()
        today6 = now.strftime('%y%m%d')
        hms = now.strftime('%H%M') + '00'      # ★분 단위 절삭(레거시 left(gs_hms,4)+'00')
        # ★★파트 불일치 차단(2026-08-19) — lookup 과 동일 판정을 저장에서도 수행(서버측 최종 방어).
        #   lookup 만 막으면 API 직접호출·화면 상태 꼬임으로 우회 가능. 실제로 S5-2 간판이
        #   S5 로 실적 등록되어 계획6 전표에 9가 잡히는 오염이 발생했음.
        #   취소(qty<0)는 이미 등록된 실적을 되돌리는 것이므로 이 검증에서 제외.
        if qty > 0:
            _codes = []
            if sheet_ref:
                cur.execute("""SELECT ISNULL(GAGONG_PROC_CODE,'') FROM nx.PR_T_INDI_WELD_SHEET_DTL WITH(NOLOCK)
                                WHERE SHEET_NO=? ORDER BY PROC_SEQ""", sheet_ref)
                _codes = [str(x[0] or '').strip() for x in cur.fetchall() if str(x[0] or '').strip()]
            if not _codes:
                cur.execute("""SELECT ISNULL(GAGONG_PROC_CODE,'') FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)
                                WHERE ITEM_CODE=? ORDER BY PROC_SEQ""", item)
                _codes = [str(x[0] or '').strip() for x in cur.fetchall() if str(x[0] or '').strip()]
            if _codes and proc not in _codes:
                nx.rollback()
                return {"ok": False, "mismatch": True, "procs": _codes,
                        "errors": [f"이 바코드는 [{proc}] 공정의 것이 아닙니다. "
                                   f"해당 공정: {', '.join(_codes)}"]}
            # ★실적수단 검증 — 바코드 종류(전표/가간판/라벨)와 그 공정의 JP_PROC_METHOD 가 맞아야 함.
            #   바코드 종류는 bc 형태로 판정(GP…=가간판 G / 8자리 숫자=전표 J / 그 외=라벨 L).
            _bcm = "G" if (bc.upper().startswith("GP") and bc[2:].isdigit()) else \
                   ("J" if (bc.lstrip("0") or "0").isdigit() else "L")
            cur.execute("""SELECT TOP 1 ISNULL(JP_PROC_METHOD,'') FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)
                            WHERE ITEM_CODE=? AND GAGONG_PROC_CODE=?""", item, proc)
            _g = cur.fetchone()
            _gm = str(_g[0]).strip() if (_g and _g[0]) else ""
            if _gm and _gm != _bcm:
                cur.execute("""SELECT TOP 1 ISNULL(GAGONG_PROC_CODE,'') FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)
                                WHERE ITEM_CODE=? AND ISNULL(JP_PROC_METHOD,'')=? ORDER BY PROC_SEQ""", item, _bcm)
                _o = cur.fetchone(); _own = str(_o[0]).strip() if _o else ""
                nx.rollback()
                return {"ok": False, "mismatch": True, "procs": ([_own] if _own else _codes),
                        "errors": [f"[{proc}] 공정은 {_METH_NM.get(_gm, _gm)}(으)로 실적을 잡는 공정입니다. "
                                   f"{_METH_NM.get(_bcm, _bcm)} 바코드로는 실적을 잡을 수 없습니다."
                                   + (f" 이 바코드의 공정: {_own}" if _own else "")]}
        # 잔여/취소 검증 — 이 바코드+공정 누적 기준
        cur.execute("""SELECT ISNULL(SUM(PROD_QTY),0) FROM nx.PR_T_PROD_DTL_STICKER
                        WHERE BARCODE=? AND ISNULL(PROC_CODE,'')=?""", bc, proc)
        done = float(cur.fetchone()[0] or 0)
        if qty > 0 and tot > 0 and done + qty > tot + 0.0001:
            nx.rollback()
            return {"ok": False, "errors": [f"잔여 초과 — 총계 {tot:g} · 기처리 {done:g} · 요청 {qty:g}"]}
        if qty < 0 and done + qty < -0.0001:
            nx.rollback()
            return {"ok": False, "errors": [f"취소 초과 — 기처리 {done:g} · 취소요청 {abs(qty):g}"]}

        proc_seq = int(p.get("proc_seq")) if str(p.get("proc_seq") or "").strip().isdigit() else None
        swork_i = int(swork) if swork.isdigit() else None

        # ① 스티커/가간판 실적등록 — 구간별 시작·종료
        cur.execute("""INSERT INTO nx.PR_T_PROD_DTL_STICKER(BARCODE,PROC_SEQ,PROC_CODE,ITEM_CODE,
                          S_WORK_CODE,WORK_CODE,PROD_TAG,MACH_CODE,WORKER_CODE,SHEET_NO,
                          STA_DATETIME,PROD_DATETIME,PROD_QTY,SHEET_BARCODE,PART_PROD_FLAG,
                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,GETDATE(),?,?,'0',?,GETDATE(),?)""",
                    bc, proc_seq, proc, item, swork_i, (work_code or None), (prod_tag or None),
                    (str(p.get("mach_code") or "").strip() or None), (worker or None),
                    (int(sheet_ref) if sheet_ref.isdigit() else None),
                    (sta_at or None), int(qty), (sheet_ref or None), who, win)

        # ②③ 전표 공정 실적 = STICKER 합계로 재계산 → 완료플래그
        prog = None
        if sheet_ref and proc_seq:
            cur.execute("""UPDATE B SET PROD_QTY=(SELECT ISNULL(SUM(PROD_QTY),0)
                                                    FROM nx.PR_T_PROD_DTL_STICKER WITH(NOLOCK)
                                                   WHERE SHEET_NO=B.SHEET_NO AND PROC_SEQ=B.PROC_SEQ),
                                  STA_DATETIME=ISNULL(B.STA_DATETIME,GETDATE()),
                                  UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                             FROM nx.PR_T_INDI_WELD_SHEET_DTL B
                            WHERE B.SHEET_NO=? AND B.PROC_SEQ=?""", who, win, sheet_ref, proc_seq)
            cur.execute("""UPDATE B SET FIN_DATETIME=CASE WHEN B.PROD_QTY>=A.PLAN_QTY THEN GETDATE() ELSE NULL END,
                                  PROD_FIN_FLAG=CASE WHEN B.PROD_QTY>=A.PLAN_QTY THEN '1' ELSE '0' END
                             FROM nx.PR_T_INDI_WELD_SHEET A WITH(NOLOCK)
                             JOIN nx.PR_T_INDI_WELD_SHEET_DTL B ON A.SHEET_NO=B.SHEET_NO
                            WHERE B.SHEET_NO=? AND B.PROC_SEQ=?""", sheet_ref, proc_seq)
            cur.execute("""UPDATE A SET PROD_FIN_FLAG=(SELECT TOP 1 CASE WHEN PROD_FIN_FLAG='1' THEN '1' ELSE '0' END
                                                         FROM nx.PR_T_INDI_WELD_SHEET_DTL WITH(NOLOCK)
                                                        WHERE SHEET_NO=A.SHEET_NO ORDER BY PROC_SEQ DESC)
                             FROM nx.PR_T_INDI_WELD_SHEET A WHERE A.SHEET_NO=?""", sheet_ref)
            cur.execute("""SELECT ISNULL(PROD_QTY,0), ISNULL(PROD_FIN_FLAG,'0')
                             FROM nx.PR_T_INDI_WELD_SHEET_DTL WHERE SHEET_NO=? AND PROC_SEQ=?""",
                        sheet_ref, proc_seq)
            r = cur.fetchone()
            if r: prog = {"proc_seq": proc_seq, "after": float(r[0] or 0), "fin_flag": str(r[1] or '0')}

        # ④ 공정별 생산실적 누적
        cur.execute("""SELECT COUNT(*) FROM nx.PR_T_PROD_DTL_PROC
                        WHERE WORK_ORDER='' AND SPLIT_WORK_ORDER='' AND ITEM_CODE=?
                          AND PROD_YMD=? AND PROD_HMS=? AND ISNULL(S_WORK_CODE,0)=?
                          AND ISNULL(WORK_CODE,'')=? AND ISNULL(PROC_CODE,'')=?
                          AND ISNULL(PROD_TAG,'')=?""",
                    item, today6, hms, (swork_i or 0), work_code, proc, prod_tag)
        if int(cur.fetchone()[0] or 0) == 0:
            cur.execute("""INSERT INTO nx.PR_T_PROD_DTL_PROC(WORK_ORDER,SPLIT_WORK_ORDER,ITEM_CODE,
                              PROD_YMD,PROD_HMS,LINE_NO,PROD_QTY,PROD_USER_ID,S_WORK_CODE,WORK_CODE,
                              PROC_CODE,PROD_TAG,FINISH_FLAG,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                            VALUES('','',?,?,?,'',?,?,?,?,?,?,'0',?,GETDATE(),?)""",
                        item, today6, hms, int(qty), (worker or None), (swork_i or 0),
                        work_code, proc, (prod_tag or None), who, win)
        else:
            cur.execute("""UPDATE nx.PR_T_PROD_DTL_PROC SET PROD_QTY=ISNULL(PROD_QTY,0)+?,
                              UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                            WHERE WORK_ORDER='' AND SPLIT_WORK_ORDER='' AND ITEM_CODE=?
                              AND PROD_YMD=? AND PROD_HMS=? AND ISNULL(S_WORK_CODE,0)=?
                              AND ISNULL(WORK_CODE,'')=? AND ISNULL(PROC_CODE,'')=?
                              AND ISNULL(PROD_TAG,'')=?""",
                        int(qty), who, win, item, today6, hms, (swork_i or 0), work_code, proc, prod_tag)

        # ─── 마지막 공정이 아니면 여기서 종료(레거시 동일) ───
        cur.execute("""SELECT ISNULL(MAX(PROC_SEQ),0) FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)
                        WHERE ITEM_CODE=?""", item)
        max_seq = int(cur.fetchone()[0] or 0)
        is_last = (proc_seq is not None and max_seq > 0 and proc_seq >= max_seq)
        if not is_last:
            nx.commit()
            return {"ok": True, "action": ("취소" if qty < 0 else "등록"), "qty": qty,
                    "prod_ymd": today6, "prod_hms": hms, "progress": prog,
                    "last_proc": False, "stock": None}

        # ⑤ 생산실적(도번·일자·분 누적)
        stock_gpc = str(p.get("stock_gpc") or "").strip()
        if not stock_gpc and sheet_ref:
            cur.execute("SELECT ISNULL(STOCK_GAGONG_PROC_CODE,'') FROM nx.PR_T_INDI_WELD_SHEET WHERE SHEET_NO=?", sheet_ref)
            r = cur.fetchone()
            stock_gpc = str(r[0] or '').strip() if r else ''
        cur.execute("""SELECT COUNT(*) FROM nx.PR_T_PROD_DTL
                        WHERE WORK_ORDER='' AND SPLIT_WORK_ORDER='' AND ITEM_CODE=?
                          AND PROD_YMD=? AND PROD_HMS=?""", item, today6, hms)
        if int(cur.fetchone()[0] or 0) == 0:
            cur.execute("""INSERT INTO nx.PR_T_PROD_DTL(WORK_ORDER,SPLIT_WORK_ORDER,ITEM_CODE,
                              PROD_YMD,PROD_HMS,LINE_NO,PROD_QTY,PROD_USER_ID,WORK_CODE,S_WORK_CODE,
                              PART_CODE,STOCK_PART_CODE,PROD_TAG,FINISH_FLAG,
                              UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                            VALUES('','',?,?,?,'',?,?,?,?,?,?,?,'0',?,GETDATE(),?)""",
                        item, today6, hms, int(qty), (worker or None), work_code, swork_i,
                        proc, (stock_gpc or None), (prod_tag or None), who, win)
        else:
            cur.execute("""UPDATE nx.PR_T_PROD_DTL SET PROD_QTY=ISNULL(PROD_QTY,0)+?,
                              UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                            WHERE WORK_ORDER='' AND SPLIT_WORK_ORDER='' AND ITEM_CODE=?
                              AND PROD_YMD=? AND PROD_HMS=?""",
                        int(qty), who, win, item, today6, hms)

        stock = {"kind": "", "assy": 0.0, "mats": [], "ready": []}
        # ⑥ 입고처리
        # ★2026-08-19 수정 — 완제품이 생산(파트)창고로 들어가던 버그.
        #   전표 헤더 STOCK_GAGONG_PROC_CODE 에 파트코드('S5')가 들어있는 전표가 있어
        #   "값이 있으면 중간공정" 판정이 완제품까지 파트창고로 보냈음(실측: AJR30117401 3개가
        #   PR_T_MAT_STOCK_WH(S5) 로 입고, SA_T_ITEM_STOCK 무변동).
        #   → 이 품목의 마지막 공정을 끝낸 것이면(=완제품 완성) STOCK_GPC 와 무관하게 ASSY 영업창고.
        #     중간공정 품목(자기 뒤에 공정이 더 있는 경우)만 파트/자재창고 입고.
        #   ※여기까지 온 시점에 이미 proc_seq == max_proc_seq (마지막 공정) 이 보장된다.
        # ★2026-08-25 재수정 — 위 판정(GC_GUBUN W/K 만 자재창고, 나머지 전부 ASSY)이
        #   서브품까지 영업창고로 보내고 있었다. 서브품 실적은 '상위를 만드는 파트'의
        #   생산재고가 되어야 나중에 상위 실적 시 그 파트에서 차감된다.
        #   → BOM 상위 유무로 판정(_prod_dest): 상위없음=ASSY / 사내상위=그 상위의 파트 /
        #     가상상위=더 위로 / 업체상위=자재창고.
        #   실측 피해: 서브품 31품번이 영업창고에 적재(5006AR4091G 11,219 등).
        # ★전표의 상위품번(UPPER_ITEM_CODE)을 우선 근거로 — 공용 자도번은 BOM 만으로
        #   상위를 특정할 수 없다(상위가 A·B 둘 다일 수 있음). 전표엔 이번 실적이
        #   어느 상위를 위한 것인지 남아 있다.
        _upper = ''
        if sheet_ref:
            try:
                cur.execute("SELECT ISNULL(UPPER_ITEM_CODE,'') FROM nx.PR_T_INDI_WELD_SHEET WHERE SHEET_NO=?", sheet_ref)
                _ru = cur.fetchone()
                _upper = str(_ru[0] or '').strip() if _ru else ''
            except Exception: pass
        _dk, _dp = _prod_dest(cur, item, _upper)
        _gc = ''
        if stock_gpc:
            cur.execute("SELECT ISNULL(GC_GUBUN,'') FROM nx.PR_M_PROC_GAGONG WITH(NOLOCK) WHERE GAGONG_PROC_CODE=?", stock_gpc)
            _r = cur.fetchone()
            _gc = str(_r[0] or '').strip() if _r else ''
        if _dk == "PART" and _dp:
            # ★서브품 → 상위 파트의 생산창고(PR_T_MAT_STOCK_WH). 영업창고 아님.
            #   ★2026-08-25 PR_T_STOCK_MAINT_MAT 에 별도 원장행을 넣지 않는다.
            #     생산입출고현황(live_api._prodinout)은 이미 pr_t_prod_dtl.STOCK_PART_CODE 를
            #     'SUB생산실적' 입고로 읽고 있어(833줄) 원장행을 또 넣으면 이중계상된다.
            #     게다가 그 화면은 PR_T_STOCK_MAINT_MAT tag='4' 를 무조건 '생산사용(출고)'로
            #     보고 부호를 뒤집어(*-1) 읽으므로, 입고를 tag='4' 로 넣으면 재고가 되레 늘었다
            #     (실측 AJR30027704-SUB1: 잔액 2인데 화면 4).
            #   → 잔액 테이블만 갱신하고, 이력은 PR_T_PROD_DTL(STOCK_PART_CODE)로 남긴다.
            _set_mat_stock_wh(cur, win, _dp, item, qty, who)
            stock["kind"] = f"생산창고입고({_dp})"
        elif _dk == "MAT" or (stock_gpc and _gc in ('W', 'K')):
            # 자재창고 입고(용접봉 등 자재성 공정 / 상위가 업체인 서브품)
            # ★상위가 업체라 여기로 온 경우엔 전표 STOCK_GPC 가 비어 있을 수 있다.
            #   그때는 기본 자재창고 파트(IS0001)로 넣는다 — 키팅 466 재고와 같은 버킷.
            if not stock_gpc:
                stock_gpc = 'IS0001'
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", today6)
            sq = int(cur.fetchone()[0] or 1)
            cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,
                              WORK_CODE,MAT_CODE,MAINT_QTY,REF_MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,
                              ITEM_CODE,OUT_WH_GUBUN,GAGONG_PROC_CODE,
                              INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                              UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                            VALUES(?,?,'P','','',?,?,0,0,0,'생산완료 후 자재창고 입고','','',?,?,GETDATE(),?,?,GETDATE(),?)""",
                        today6, sq, item, int(qty), stock_gpc, who, win, who, win)
            _set_pu_mat_stock(cur, win, item, 'Z99990', qty, who)
            _set_pu_mat_stock_wh(cur, win, item, 'Z99990', stock_gpc, qty, who)
            stock["kind"] = "자재창고입고"
        else:
            # ASSY → 영업창고
            # ★웹이 만든 행(SEQ>=20000)만 찾아 합산한다 — 레거시 행을 잡아 수정하면 안 된다.
            cur.execute("""SELECT MAX(MAINT_SEQ) FROM nx.SA_T_STOCK_MAINT
                            WHERE MAINT_YMD=? AND ITEM_CODE=? AND MAINT_TAG='P' AND WORK_ORDER='BARCODE'
                              AND MAINT_SEQ>=20000""",
                        today6, item)
            sseq = cur.fetchone()[0]
            if sseq:
                cur.execute("""UPDATE nx.SA_T_STOCK_MAINT SET MAINT_QTY=ISNULL(MAINT_QTY,0)+?,
                                  UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                                WHERE MAINT_YMD=? AND MAINT_SEQ=?""", int(qty), who, win, today6, int(sseq))
            else:
                cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.SA_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", today6)
                nseq = int(cur.fetchone()[0] or 1)
                cur.execute("""INSERT INTO nx.SA_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,MAINT_QTY,
                                  MAINT_COST,MAINT_AMT,REMARKS,ITEM_CODE,WORK_ORDER,SPLIT_WORK_ORDER,
                                  INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                                  UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                VALUES(?,?,'P',?,0,0,'',?,'BARCODE','BARCODE',?,GETDATE(),?,?,GETDATE(),?)""",
                            today6, nseq, int(qty), item, who, win, who, win)
            _set_item_stock(cur, win, item, qty, who)
            stock["kind"] = "ASSY"; stock["assy"] = qty

        # ⑦ BOM 전개 → 파트별 자재 차감 (Q1000/Q2000 공용창고는 제외 — 운영방침 변경)
        boms = _bom_expand(cur, item, '%')
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999) FROM nx.PR_T_STOCK_MAINT_MAT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", today6)
        mseq = int(cur.fetchone()[0] or 19999)
        # ★자재 재고부족 사전검증(2026-08-20) — 음수재고 금지.
        #   실적 수량 × BOM 소요 > 파트창고 재고 이면 실적을 잡지 않고 거부한다.
        #   (기존엔 검증 없이 차감해 파트창고가 0/음수가 됐고, 생산입출고현황에서
        #    해당 품번이 사라져 보였음 — 실측 AJR30038201 실적54 → 자재 216 차감)
        #   ※취소(qty<0)는 되돌리는 동작이므로 검증 제외.
        if qty > 0:
            # ★재고 판정기준 = 이력계산(라이브∪nx) — 재고표시 화면들과 동일.
            #   nx 잔액테이블(PR_T_MAT_STOCK_WH)만 읽으면 안 된다: 레거시가 만든 잔액은
            #   nx 에 행 자체가 없고 웹 델타만 담긴 '반쪽 값'이라 재고 0 으로 오판한다
            #   (2026-08-25 실사고: S4 에 SUB6 23개가 있는데 nx 행이 없어 "재고 0" 거부).
            _hist = _prod_stock_map(cur, by_part=True)
            _short = []
            for mat, mwc, use, mgpc in boms:
                if use <= 0 or (mgpc or '').upper() in ('Q1000', 'Q2000'):
                    continue
                _need = qty * use
                _pc = mgpc or proc
                _have = float(_hist.get((str(mat).upper(), _pc), 0.0))
                if _have < _need:
                    _short.append({"mat": mat, "part": _pc, "need": round(_need, 4),
                                   "have": round(_have, 4), "lack": round(_need - _have, 4)})
            if _short:
                nx.rollback()
                _msg = "자재 재고가 부족합니다.\n\n" + "\n".join(
                    f"· {s['mat']} ({s['part']})  필요 {s['need']:g} / 재고 {s['have']:g}  → 부족 {s['lack']:g}"
                    for s in _short[:10])
                if len(_short) > 10:
                    _msg += f"\n… 외 {len(_short)-10}건"
                return {"ok": False, "shortage": _short,
                        "errors": [_msg]}

        for mat, mwc, use, mgpc in boms:
            if use <= 0 or (mgpc or '').upper() in ('Q1000', 'Q2000'):
                continue
            dq = -(qty * use)
            part_code = mgpc or proc
            cur.execute("""SELECT MAINT_SEQ FROM nx.PR_T_STOCK_MAINT_MAT
                            WHERE MAINT_YMD=? AND MAINT_TAG='4' AND ISNULL(PART_CODE,'')=?
                              AND ITEM_CODE=? AND MAT_CODE=?""", today6, part_code, item, mat)
            ex = cur.fetchone()
            if ex:
                cur.execute("""UPDATE nx.PR_T_STOCK_MAINT_MAT SET MAINT_QTY=ISNULL(MAINT_QTY,0)+?,
                                  UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                                WHERE MAINT_YMD=? AND MAINT_SEQ=?""", dq, who, win, today6, int(ex[0]))
            else:
                mseq += 1
                cur.execute("""INSERT INTO nx.PR_T_STOCK_MAINT_MAT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,
                                  PART_CODE,WORK_CODE,PROD_WORK_CODE,MAT_CODE,MAINT_QTY,MAINT_COST,
                                  MAINT_AMT,REMARKS,STICKER_NO,ITEM_CODE,
                                  INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                                  UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                VALUES(?,?,'4',?,?,?,?,?,0,0,'',?,?,?,GETDATE(),?,?,GETDATE(),?)""",
                            today6, mseq, part_code, (mwc or None), (work_code or None), mat, dq,
                            bc, item, who, win, who, win)
            if mwc:
                _set_mat_stock(cur, win, mwc, mat, dq, who)      # 품목별 자재재고
            _set_mat_stock_wh(cur, win, part_code, mat, dq, who)  # 파트창고 재고
            stock["mats"].append({"mat": mat, "part": part_code, "qty": round(dq, 4)})

        # ⑧ 준비재고 차감 — 하위 자도번의 파트별
        cur.execute("""SELECT DISTINCT ISNULL(GAGONG_PROC_CODE,'') g FROM nx.PR_M_ITEM_BOM WITH(NOLOCK)
                        WHERE ITEM_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')<>''
                          AND ISNULL(EXCEPT_FLAG,'0')<>'1'""", item)
        parts = [str(r[0]).strip() for r in cur.fetchall()
                 if r[0] and str(r[0]).strip().upper() not in ('Q1000', 'Q2000')]
        if not parts:
            parts = [proc]
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.PU_T_READY_STOCK_MAINT WHERE MAINT_YMD=?", today6)
        rseq = int(cur.fetchone()[0] or 0)
        for pc in parts:
            cur.execute("""SELECT MAINT_SEQ FROM nx.PU_T_READY_STOCK_MAINT
                            WHERE MAINT_YMD=? AND MAINT_TAG='A' AND ITEM_CODE=? AND ISNULL(PROC_GUBUN,'')=?
                              AND ISNULL(WORK_ORDER,'')=? AND ISNULL(SPLIT_WORK_ORDER,'')=?""",
                        today6, item, pc, (sheet_ref or ''), bc)
            ex = cur.fetchone()
            if ex:
                cur.execute("""UPDATE nx.PU_T_READY_STOCK_MAINT SET MAINT_QTY=ISNULL(MAINT_QTY,0)+?,
                                  UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                                WHERE MAINT_YMD=? AND MAINT_SEQ=?""", -qty, who, win, today6, int(ex[0]))
            else:
                rseq += 1
                cur.execute("""INSERT INTO nx.PU_T_READY_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,
                                  CUST_CODE,ITEM_CODE,PROC_GUBUN,WORK_ORDER,SPLIT_WORK_ORDER,PLAN_YMD,
                                  MAINT_QTY,INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                                  UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                VALUES(?,?,'A','Z99990',?,?,?,?,'',?,?,GETDATE(),?,?,GETDATE(),?)""",
                            today6, rseq, item, pc, (sheet_ref or ''), bc, -qty, who, win, who, win)
            _set_ready_stock(cur, win, item, 'Z99990', pc, -qty, who)
            stock["ready"].append({"part": pc, "qty": round(-qty, 4)})

        nx.commit()
        return {"ok": True, "action": ("취소" if qty < 0 else "등록"), "qty": qty,
                "prod_ymd": today6, "prod_hms": hms, "progress": prog,
                "last_proc": True, "stock": stock}
    except Exception as e:
        try: nx.rollback()
        except Exception: pass
        return {"ok": False, "errors": [str(e)[:300]]}
    finally:
        nx.close()


@router.get("/api/procbc/list")
def procbc_list(ymd: str = Query(""), part: str = Query(""), swork: str = Query(""),
                item: str = Query(""), limit: int = Query(300)):
    """★실적 이력 = nx.PR_T_PROD_DTL_STICKER ⋈ PR_T_INDI_WELD_SHEET_DTL
       ★레거시 `dw_pr_list_090_l7` 원본쿼리 이식(사용자 제공 소스, 2026-08-19).
           select a.sheet_no, a.proc_seq, a.item_code, a.prod_tag,
                  s.gagong_proc_code, s.s_work_code as proc_code, a.mach_code, a.worker_code,
                  a.barcode, a.sta_datetime, a.prod_datetime as fin_datetime, a.prod_qty, …
             from PR_T_PROD_DTL_STICKER a
             join pr_m_item b on a.item_code=b.item_code
             join pr_t_indi_weld_sheet_dtl s on a.sheet_no=s.sheet_no and a.proc_seq=s.proc_seq
       → 스캔 1건 = 1행이므로 구간별 **생산시작(STA_DATETIME) / 생산종료(PROD_DATETIME)** 가 그대로 보임.
         파트(gagong_proc_code)·공정(s_work_code)은 전표 DTL 쪽 값을 정본으로 사용(레거시 동일).
       ※PR_T_PROD_DTL 은 '마지막 공정'에서만 쌓여 앞공정이 안 보이므로 이력원장으로 부적합."""
    def d6(s):
        d = ''.join(c for c in str(s or '') if c.isdigit())
        return d[2:8] if len(d) >= 8 else d
    nx = _nx(); cur = nx.cursor()
    cn = _conn(); c2 = cn.cursor()
    try:
        w = ["1=1"]; pr = []
        y = d6(ymd)
        if y: w.append("CONVERT(varchar(6),a.PROD_DATETIME,12)=?"); pr.append(y)
        # 파트 = 전표 DTL 의 GAGONG_PROC_CODE (레거시 정본). STICKER.PROC_CODE 는 보조.
        if part.strip():
            w.append("ISNULL(s.GAGONG_PROC_CODE,ISNULL(a.PROC_CODE,''))=?"); pr.append(part.strip())
        if swork.strip() and swork.strip().isdigit():
            w.append("ISNULL(s.S_WORK_CODE,ISNULL(a.S_WORK_CODE,0))=?"); pr.append(int(swork.strip()))
        if item.strip(): w.append("a.ITEM_CODE LIKE ?"); pr.append(f"%{item.strip()}%")
        cur.execute(f"""SELECT TOP {max(1,min(int(limit),2000))}
              CONVERT(varchar(6),a.PROD_DATETIME,12), CONVERT(varchar(8),a.PROD_DATETIME,108),
              a.ITEM_CODE, a.PROD_QTY, ISNULL(a.WORKER_CODE,''),
              ISNULL(s.GAGONG_PROC_CODE,ISNULL(a.PROC_CODE,'')),
              ISNULL(CAST(ISNULL(s.S_WORK_CODE,a.S_WORK_CODE) AS varchar(10)),''),
              ISNULL(a.UPDATE_USER_ID,''), a.UPDATE_DATETIME, ISNULL(a.UPDATE_WINDOW,''),
              ISNULL(a.WORK_CODE,''),
              CONVERT(varchar(8),a.STA_DATETIME,108), CONVERT(varchar(8),a.PROD_DATETIME,108),
              ISNULL(a.BARCODE,''), ISNULL(CAST(a.SHEET_NO AS varchar(20)),''),
              ISNULL(a.PROC_SEQ,0), ISNULL(a.MACH_CODE,''),
              DATEDIFF(second, a.STA_DATETIME, a.PROD_DATETIME)
            FROM nx.PR_T_PROD_DTL_STICKER a WITH(NOLOCK)
            LEFT JOIN nx.PR_T_INDI_WELD_SHEET_DTL s WITH(NOLOCK)
                   ON a.SHEET_NO=s.SHEET_NO AND a.PROC_SEQ=s.PROC_SEQ
            WHERE {' AND '.join(w)}
            ORDER BY a.PROD_DATETIME DESC""", *pr)
        rows = []; items = set()
        for r in cur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            rows.append({"ymd": g(0), "hms": g(1).replace(':', ''), "item_code": g(2),
                         "qty": float(r[3] or 0),
                         "worker": g(4), "part": g(5), "swork": g(6),
                         "user": g(7),
                         "dt": (r[8].isoformat() if hasattr(r[8], "isoformat") else ""),
                         "win": g(9), "work_code": g(10),
                         "sta": g(11), "fin": g(12),          # ★생산시작 / 생산종료
                         "barcode": g(13), "sheet_no": g(14),
                         "proc_seq": int(r[15] or 0), "mach": g(16),
                         "secs": (int(r[17]) if r[17] is not None else None)})
            items.add(g(2))
        nm = {}; il = [x for x in items if x]
        for i in range(0, len(il), 900):
            ch = il[i:i+900]; ph = ",".join("?" * len(ch))
            c2.execute(f"SELECT ITEM_CODE, ISNULL(item_name,'') FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE IN ({ph})", *ch)
            for a, b in c2.fetchall(): nm[str(a).strip()] = b
        for x in rows: x["nm"] = nm.get(x["item_code"], "")
        return {"rows": rows, "cnt": len(rows),
                "sum_qty": round(sum(x["qty"] for x in rows), 2)}
    finally:
        nx.close(); cn.close()


# ===================== 프린터 목록 (생산전표출력관리 490 · 프린터 2대 운용) =====================
# 웹(브라우저)은 보안상 PC에 설치된 프린터를 읽을 수 없다. 현장 프린터는 대부분
# 네트워크 공유프린터라 ERP서버에도 잡혀 있으므로, 서버에서 목록을 뽑아 드롭다운으로 제공한다.
# (목록에 없으면 화면에서 직접 타이핑도 가능 — 프론트에서 datalist 로 병행)
_PRN_CACHE = {"t": 0.0, "rows": []}

@router.get("/api/prodsheet/printers")
def prodsheet_printers(refresh: int = Query(0)):
    """ERP서버에 설치된 프린터 목록. 60초 캐시(매번 WMI 조회는 느림)."""
    now = time.time()
    if not refresh and _PRN_CACHE["rows"] and (now - _PRN_CACHE["t"] < 60):
        return {"rows": _PRN_CACHE["rows"], "cached": True}
    rows = []
    try:
        import subprocess
        # PowerShell Get-Printer (Windows). 이름/드라이버/포트만 CSV 로 받는다.
        ps = ("Get-Printer | Select-Object Name,DriverName,PortName | "
              "ConvertTo-Csv -NoTypeInformation")
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, timeout=20)
        txt = out.stdout.decode("cp949", "ignore") or out.stdout.decode("utf-8", "ignore")
        import csv as _csv
        lines = [l for l in txt.splitlines() if l.strip()]
        for r in list(_csv.DictReader(lines)):
            nm = (r.get("Name") or "").strip()
            if not nm:
                continue
            rows.append({"name": nm,
                         "driver": (r.get("DriverName") or "").strip(),
                         "port": (r.get("PortName") or "").strip()})
    except Exception as e:
        return {"rows": [], "err": str(e)[:200]}
    rows.sort(key=lambda x: x["name"])
    _PRN_CACHE["t"] = now; _PRN_CACHE["rows"] = rows
    return {"rows": rows, "cached": False}
