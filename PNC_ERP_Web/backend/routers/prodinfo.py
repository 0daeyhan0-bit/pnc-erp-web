# -*- coding: utf-8 -*-
"""prodinfo 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

import os as _os
from common import _valid_hhmm
router = APIRouter()

#  생산정보등록 (기준정보) — w_pr_master_090 우측 3패널 재구현
#  조회 = 라이브 PARTNER_ERP ∪ nx(nx우선).  편집/저장 = PARTNER_ERP_TEST3.nx 만.
#  원천/nx: PR_M_ITEM_ASSY_RT→nx.prodinfo_assy, PR_M_WORK_SINGLE→nx.prodinfo_single,
#          PR_M_ITEM_PROC_GAGONG→nx.prodinfo_proc, PR_M_ITEM_ST→nx.prodinfo_item_st
#  * _nx() 커넥션으로 크로스DB 조회(라이브는 PARTNER_ERP_TEST3.nx. 로 정규화, nx는 nx.).
# ==================================================================================
_JP_METHOD = {"J": "전표처리", "G": "가간판", "L": "라벨"}
_PROC_GUBUN_ASSY = {"1": "용접", "2": "검사", "3": "조립", "21": "검사1", "31": "조립1"}
# 단품 매트릭스 외경 컬럼(실재 9열, 6.35~28.00). ∅4.76/5.00은 원천 부재 → 프론트 표시만/공란.
_OD_COLS = [("st_635", "6.35"), ("st_794", "7.94"), ("st_952", "9.52"), ("st_127", "12.70"),
            ("st_1588", "15.88"), ("st_1905", "19.05"), ("st_22", "22.20"), ("st_254", "25.40"), ("st_28", "28.00")]

# 양산준비 문서 14종 고정목록(순서=화면 표시순). 코드=저장/경로 키, 이름=표시.
YANGSAN_DOCS = [
    ("SHIP_DWG1",    "(출하검사확인)도면1"),
    ("SHIP_DWG2",    "(출하검사확인)도면2"),
    ("QMAP",         "Q-map"),
    ("QC_FLOW",      "QC공정도"),
    ("HSMS",         "HSMS입력"),
    ("INSP_GUIDE",   "검사지도서"),
    ("XRF",          "XRF"),
    ("WORK_STD",     "작업표준서"),
    ("PROC_PHOTO1",  "(공정전표)사진1"),
    ("PROC_PHOTO2",  "(공정전표)사진2"),
    ("TEST_PLAN",    "시험기획서"),
    ("DEV_REPORT",   "개발완료보고서"),
    ("CHANGE_POINT", "변경점"),
    ("INSP_CERT",    "검사성적서"),
]
_YANGSAN_DOC_NM = dict(YANGSAN_DOCS)

@router.get("/api/prodinfo/search")
def prodinfo_search(q: str = Query("")):
    """품번 검색(라이브 PR_M_ITEM)."""
    cn = _nx(); cur = cn.cursor()
    try:
        like = f"%{q.strip()}%"
        cur.execute("""SELECT TOP 60 ITEM_CODE, ISNULL(ITEM_DESC,''), ISNULL(ITEM_SPEC,''),
              ISNULL(ITEM_DIAM,0), ISNULL(ITEM_THICK,0), ISNULL(ITEM_LENGTH,0), ISNULL(PROD_RATE,100)
            FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM
            WHERE ITEM_CODE LIKE ? OR ITEM_DESC LIKE ? ORDER BY ITEM_CODE""", like, like)
        rows = [{"item": r[0], "name": r[1], "spec": r[2], "diam": float(r[3] or 0),
                 "thick": float(r[4] or 0), "length": float(r[5] or 0), "prod_rate": float(r[6] or 0)}
                for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

def _pi_proc_rows(cur, item, use_nx):
    """생산공정순서 행 조회(use_nx=True→nx.prodinfo_proc, False→레거시). 마스터 조인으로 표시명·회수율 포함."""
    src = ("nx.prodinfo_proc a" if use_nx
           else "PARTNER_ERP_TEST3.nx.PR_M_ITEM_PROC_GAGONG a")
    C = (lambda c: c.lower()) if use_nx else (lambda c: c)  # nx는 소문자 컬럼
    cur.execute(f"""
        SELECT a.{C('PROC_SEQ')}, ISNULL(a.{C('WORK_CODE')},'') , ISNULL(a.{C('GAGONG_PROC_CODE')},''),
               ISNULL(a.{C('S_WORK_CODE')},0), ISNULL(a.{C('MACH_CODE')},''), ISNULL(a.{C('WORK_QTY')},0),
               ISNULL(a.{C('STD_SIZE')},''), ISNULL(a.{C('GAGONG_PROC_SEQ')},1), ISNULL(a.{C('READY_ST')},0),
               ISNULL(a.{C('MACH_CT')},0), ISNULL(a.{C('INWON')},0), ISNULL(a.{C('HUMAN_ST')},0),
               ISNULL(a.{C('TOT_ST')},0), ISNULL(a.{C('JP_PROC_METHOD')},'J'), ISNULL(a.{C('LT_HR')},0),
               ISNULL(w.WORK_DESC,''), ISNULL(g.GAGONG_PROC_DESC,''), ISNULL(s.WORK_DESC,''), ISNULL(m.MACH_DESC,''),
               ISNULL(g.PROD_RATE,0), ISNULL(w.PROD_RATE,0)
        FROM {src}
        LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK        w ON w.WORK_CODE        = a.{C('WORK_CODE')}
        LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG g ON g.GAGONG_PROC_CODE = a.{C('GAGONG_PROC_CODE')}
        LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK_SINGLE s ON s.S_WORK_CODE      = a.{C('S_WORK_CODE')}
        LEFT JOIN PARTNER_ERP_TEST3.nx.QA_M_MACHINE     m ON m.MACH_CODE        = a.{C('MACH_CODE')}
        WHERE a.{C('ITEM_CODE')}=? ORDER BY a.{C('PROC_SEQ')}""", item)
    out = []
    for r in cur.fetchall():
        out.append({"proc_seq": int(r[0]), "work_code": str(r[1]).strip(), "gagong_proc_code": str(r[2]).strip(),
                    "s_work_code": int(r[3] or 0), "mach_code": str(r[4]).strip(), "work_qty": float(r[5] or 0),
                    "std_size": str(r[6]), "gagong_proc_seq": int(r[7] or 1), "ready_st": float(r[8] or 0),
                    "mach_ct": float(r[9] or 0), "inwon": int(r[10] or 0), "human_st": float(r[11] or 0),
                    "tot_st": float(r[12] or 0), "jp_proc_method": str(r[13]).strip() or "J", "lt_hr": float(r[14] or 0),
                    "work_desc": str(r[15]).strip(), "part_desc": str(r[16]).strip(), "s_work_desc": str(r[17]).strip(),
                    "mach_desc": str(r[18]).strip(), "part_rate": float(r[19] or 0), "work_rate": float(r[20] or 0)})
    return out

@router.get("/api/prodinfo/get")
def prodinfo_get(item: str = Query(...), assyall: int = Query(0)):
    """품번의 3패널 + 하단 탭 데이터 로드(nx우선 병합)."""
    item = item.strip()
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT ISNULL(ITEM_DESC,''), ISNULL(ITEM_SPEC,''), ISNULL(ITEM_DIAM,0),
              ISNULL(ITEM_THICK,0), ISNULL(ITEM_LENGTH,0), ISNULL(PROD_RATE,100), ISNULL(JIG_CODE,''), ISNULL(JIG_KEEP_AREA,'')
            FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE=?""", item)
        pi = cur.fetchone()
        if not pi:
            raise HTTPException(404, f"품번 {item} 없음")
        head = {"item": item, "name": pi[0], "spec": pi[1], "diam": float(pi[2] or 0), "thick": float(pi[3] or 0),
                "length": float(pi[4] or 0), "prod_rate": float(pi[5] or 0), "jig_code": str(pi[6]).strip(),
                "jig_area": str(pi[7]).strip()}

        # ── 패널① 조립(공정수): 마스터 전량 LEFT JOIN 품목 work_qty(nx우선). 기본=사용공정(qty>0) ──
        flt = "" if assyall else "WHERE ISNULL(nx.work_qty, rt.WORK_QTY) > 0"
        cur.execute(f"""
            SELECT a.A_WORK_CODE, ISNULL(a.WORK_DESC,''), ISNULL(a.WORK_ST,0), ISNULL(a.PROC_GUBUN,''),
                   ISNULL(a.WELDING_GUBUN,0), ISNULL(a.SORT_SEQ,0),
                   ISNULL(nx.work_qty, rt.WORK_QTY) AS work_qty,
                   CASE WHEN nx.item_code IS NOT NULL THEN 1 ELSE 0 END nx_flag
            FROM PARTNER_ERP_TEST3.nx.PR_M_WORK_ASSY a
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM_ASSY_RT rt ON rt.A_WORK_CODE=a.A_WORK_CODE AND rt.ITEM_CODE=?
            LEFT JOIN nx.prodinfo_assy nx ON nx.a_work_code=a.A_WORK_CODE AND nx.item_code=?
            {flt}
            ORDER BY a.SORT_SEQ, a.A_WORK_CODE""", item, item)
        assy = []
        for r in cur.fetchall():
            pg = str(r[3]).strip()
            assy.append({"a_work_code": int(r[0]), "work_desc": str(r[1]).strip(), "work_st": float(r[2] or 0),
                         "proc_gubun": pg, "proc_gubun_nm": _PROC_GUBUN_ASSY.get(pg, pg), "welding_gubun": int(r[4] or 0),
                         "sort_seq": int(r[5] or 0), "work_qty": (None if r[6] is None else float(r[6])),
                         "nx_flag": int(r[7])})
        cur.execute("SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.PR_M_WORK_ASSY")
        assy_master_cnt = cur.fetchone()[0]

        # ── 패널② 단품(공정수) = 외경별 표준ST 매트릭스(전사 마스터, nx우선) ──
        stsel = ", ".join([f"ISNULL(n.{k}, s.{k.upper()})" for k, _ in _OD_COLS])
        cur.execute(f"""
            SELECT s.S_WORK_CODE, ISNULL(n.work_desc, s.WORK_DESC), ISNULL(s.WORK_CODE,''),
                   ISNULL(s.GAGONG_PROC_CODE,''), ISNULL(s.HOUR_PAY,0), ISNULL(s.CUTTING_PROC_FLAG,''),
                   ISNULL(s.SUB_WELD_FLAG,''), ISNULL(s.SORT_SEQ,0),
                   CASE WHEN n.s_work_code IS NOT NULL THEN 1 ELSE 0 END, {stsel}
            FROM PARTNER_ERP_TEST3.nx.PR_M_WORK_SINGLE s
            LEFT JOIN nx.prodinfo_single n ON n.s_work_code = s.S_WORK_CODE
            ORDER BY s.WORK_CODE, s.SORT_SEQ, s.S_WORK_CODE""")
        single = []
        for r in cur.fetchall():
            d = {"s_work_code": int(r[0]), "work_desc": str(r[1] or "").strip(), "work_code": str(r[2]).strip(),
                 "gagong_proc_code": str(r[3]).strip(), "hour_pay": int(r[4] or 0), "cutting_flag": str(r[5]).strip(),
                 "sub_weld_flag": str(r[6]).strip(), "sort_seq": int(r[7] or 0), "nx_flag": int(r[8])}
            for i, (k, _) in enumerate(_OD_COLS):
                v = r[9 + i]
                d[k] = (None if v is None else round(float(v), 3))
            single.append(d)

        # ── 패널③ 생산공정순서(nx우선 by item) ──
        cur.execute("SELECT COUNT(*) FROM nx.prodinfo_proc WHERE item_code=?", item)
        use_nx = cur.fetchone()[0] > 0
        proc = _pi_proc_rows(cur, item, use_nx)
        proc_src = "nx" if use_nx else "legacy"

        # ── 하단 탭: LOB(item_st, nx우선) ──
        cur.execute("""SELECT prod_gubun, ISNULL(member_qty,0), ISNULL(capa_qty,0), 'nx'
              FROM nx.prodinfo_item_st WHERE item_code=?
            UNION ALL
            SELECT ISNULL(PROD_GUBUN,''), ISNULL(MEMBER_QTY,0), ISNULL(CAPA_QTY,0), 'legacy'
              FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_ST
              WHERE ITEM_CODE=? AND ISNULL(PROD_GUBUN,'') NOT IN (SELECT prod_gubun FROM nx.prodinfo_item_st WHERE item_code=?)
            ORDER BY 1""", item, item, item)
        item_st = [{"prod_gubun": str(r[0]).strip(), "member_qty": int(r[1] or 0), "capa_qty": int(r[2] or 0),
                    "src": r[3]} for r in cur.fetchall()]

        # ── 하단 탭: 양산준비/지그(PR_M_ITEM_SUB 실측 후보 컬럼, 읽기전용 [재구성]) ──
        cur.execute("""SELECT ISNULL(PROD_STEP_MEMO,''), ISNULL(PROD_STEP_MEMO2,''), ISNULL(PROD_WORKER,''),
              ISNULL(INSP_WORKER,''), ISNULL(MAIN_MACH_CODE,''), ISNULL(ZIG_QTY,0), ISNULL(INSP_COUNT,0), ISNULL(ERR_RATE,0)
            FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_SUB WHERE ITEM_CODE=?""", item)
        sub = cur.fetchone()
        mach_nm = ""
        if sub and str(sub[4]).strip():
            cur.execute("SELECT ISNULL(MACH_DESC,'') FROM PARTNER_ERP_TEST3.nx.QA_M_MACHINE WHERE MACH_CODE=?", str(sub[4]).strip())
            mm = cur.fetchone(); mach_nm = str(mm[0]).strip() if mm else ""
        subd = ({"prod_step_memo": str(sub[0]), "prod_step_memo2": str(sub[1]), "prod_worker": str(sub[2]).strip(),
                 "insp_worker": str(sub[3]).strip(), "main_mach_code": str(sub[4]).strip(), "main_mach_nm": mach_nm,
                 "zig_qty": int(sub[5] or 0), "insp_count": int(sub[6] or 0), "err_rate": float(sub[7] or 0)}
                if sub else {})

        # ── 하단 탭 ⑦ 지그정보(nx 다행) + 레거시 단건 참조(읽기) ──
        cur.execute("""SELECT seq, ISNULL(jig_gubun,''), ISNULL(jig_qty,0), ISNULL(rack_loc,''), ISNULL(make_ymd,'')
            FROM nx.prodinfo_jig WHERE item_code=? ORDER BY seq""", item)
        jig = [{"seq": int(r[0]), "jig_gubun": str(r[1]), "jig_qty": int(r[2] or 0),
                "rack_loc": str(r[3]), "make_ymd": str(r[4]), "src": "nx"} for r in cur.fetchall()]
        jig_legacy = {"jig_code": head["jig_code"], "jig_area": head["jig_area"],
                      "zig_qty": (int(subd.get("zig_qty", 0)) if subd else 0)}

        # ── 하단 탭 ⑧ 수율(공정수) nx ──
        cur.execute("""SELECT seq, ISNULL(yield_proc,''), ISNULL(proc_qty,0), ISNULL(std_st,0), ISNULL(st,0)
            FROM nx.prodinfo_yield WHERE item_code=? ORDER BY seq""", item)
        yield_rows = [{"seq": int(r[0]), "yield_proc": str(r[1]), "proc_qty": float(r[2] or 0),
                       "std_st": float(r[3] or 0), "st": float(r[4] or 0)} for r in cur.fetchall()]

        # ── 하단 탭 ⑥ 양산준비 파일첨부(14종 × 첨부목록, nx) ──
        cur.execute("""SELECT doc_type, yid, orig_filename, byte_size, upd_user, upd_at
            FROM nx.prodinfo_yangsan WHERE item_code=? AND del_flag=0 ORDER BY doc_type, upd_at DESC""", item)
        yfiles = {}
        for r in cur.fetchall():
            yfiles.setdefault(str(r[0]), []).append({
                "yid": int(r[1]), "filename": r[2], "size": int(r[3] or 0), "user": r[4] or "",
                "dt": (r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5] or "")).replace("T", " ")[:19]})
        yangsan = [{"doc_type": c, "doc_nm": nm, "files": yfiles.get(c, [])} for c, nm in YANGSAN_DOCS]

        return {"head": head, "assy": assy, "assy_master_cnt": assy_master_cnt, "single": single,
                "proc": proc, "proc_src": proc_src, "item_st": item_st, "sub": subd,
                "jig": jig, "jig_legacy": jig_legacy, "yield": yield_rows, "yangsan": yangsan,
                "od_cols": [od for _, od in _OD_COLS]}
    finally:
        cn.close()

@router.get("/api/prodinfo/opts")
def prodinfo_opts(work_code: str = Query("")):
    """드롭다운 옵션 + 캐스케이드. work_code 지정 시 파트/가공공정/설비를 해당 작업처로 필터."""
    wc = work_code.strip()
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT WORK_CODE, ISNULL(WORK_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_WORK ORDER BY WORK_CODE")
        works = [{"code": str(r[0]).strip(), "name": str(r[1]).strip()} for r in cur.fetchall()]
        # 파트(PR_M_PROC_GAGONG) — work_code 포함(프론트 캐스케이드용)
        pw = "WHERE WORK_CODE=?" if wc else ""
        cur.execute(f"""SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,''), ISNULL(WORK_CODE,'') FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG
            {pw} ORDER BY SORT_KEY, GAGONG_PROC_CODE""", *( [wc] if wc else [] ))
        parts = [{"code": str(r[0]).strip(), "name": str(r[1]).strip(), "work_code": str(r[2]).strip()} for r in cur.fetchall()]
        # 가공공정(PR_M_WORK_SINGLE, nx우선 명칭)
        cur.execute(f"""SELECT s.S_WORK_CODE, ISNULL(n.work_desc, s.WORK_DESC), ISNULL(s.WORK_CODE,'')
            FROM PARTNER_ERP_TEST3.nx.PR_M_WORK_SINGLE s LEFT JOIN nx.prodinfo_single n ON n.s_work_code=s.S_WORK_CODE
            {('WHERE s.WORK_CODE=?' if wc else '')} ORDER BY s.SORT_SEQ, s.S_WORK_CODE""", *( [wc] if wc else [] ))
        singles = [{"code": int(r[0]), "name": (str(r[1] or "").strip() or str(r[0])), "work_code": str(r[2]).strip()} for r in cur.fetchall()]
        # 설비(QA_M_MACHINE) — 작업처 지정 시 해당 작업처 + 미지정 설비 포함
        if wc:
            cur.execute("""SELECT TOP 400 MACH_CODE, ISNULL(MACH_DESC,''), ISNULL(WORK_CODE,'') FROM PARTNER_ERP_TEST3.nx.QA_M_MACHINE
                WHERE ISNULL(USE_FLAG,'1')='1' AND (ISNULL(WORK_CODE,'')='' OR WORK_CODE=?) ORDER BY MACH_DESC""", wc)
        else:
            cur.execute("""SELECT TOP 400 MACH_CODE, ISNULL(MACH_DESC,''), ISNULL(WORK_CODE,'') FROM PARTNER_ERP_TEST3.nx.QA_M_MACHINE
                WHERE ISNULL(USE_FLAG,'1')='1' ORDER BY MACH_DESC""")
        machs = [{"code": str(r[0]).strip(), "name": str(r[1]).strip(), "work_code": str(r[2]).strip()} for r in cur.fetchall()]
        return {"works": works, "parts": parts, "singles": singles, "machs": machs, "jp_methods": _JP_METHOD}
    finally:
        cn.close()

@router.post("/api/prodinfo/proc/save")
def prodinfo_proc_save(payload: dict = Body(...)):
    """생산공정순서 저장(nx.prodinfo_proc replace-all by item). 편집=nx만."""
    item = str(payload.get("item", "")).strip()
    if not item: return {"ok": False, "detail": "품번 필수"}
    rows = payload.get("rows", []) or []
    user = (payload.get("user") or "웹")[:30]
    cn = _nx(); cur = cn.cursor()
    try:
        seqs = set()
        for r in rows:
            s = int(r.get("proc_seq") or 0)
            if s <= 0: return {"ok": False, "detail": "공정SEQ는 1 이상 필수"}
            if s in seqs: return {"ok": False, "detail": f"공정SEQ 중복: {s}"}
            seqs.add(s)
        cur.execute("DELETE FROM nx.prodinfo_proc WHERE item_code=?", item)
        def n(r, k, d=0):
            v = r.get(k)
            try: return float(v) if v not in (None, "") else d
            except: return d
        for r in rows:
            cur.execute("""INSERT INTO nx.prodinfo_proc
                (item_code, proc_seq, work_code, gagong_proc_code, s_work_code, mach_code, work_qty, std_size,
                 mix_gagong, gagong_proc_flag, gagong_proc_seq, ready_st, mach_ct, inwon, human_st, tot_st,
                 jp_proc_method, lt_hr, key_id, upd_user, upd_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,getdate())""",
                item, int(r.get("proc_seq")), (r.get("work_code") or "")[:4], (r.get("gagong_proc_code") or "")[:10],
                int(n(r, "s_work_code")), (r.get("mach_code") or "")[:10], n(r, "work_qty"), (r.get("std_size") or "")[:100],
                int(n(r, "mix_gagong")), (r.get("gagong_proc_flag") or "")[:1], int(n(r, "gagong_proc_seq", 1)),
                n(r, "ready_st"), n(r, "mach_ct"), int(n(r, "inwon")), n(r, "human_st"), n(r, "tot_st"),
                (r.get("jp_proc_method") or "J")[:1], n(r, "lt_hr"), int(n(r, "key_id")), user)
        cn.commit()
        return {"ok": True, "saved": len(rows)}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.post("/api/prodinfo/assy/save")
def prodinfo_assy_save(payload: dict = Body(...)):
    """조립(공정수) 저장(nx.prodinfo_assy replace-all by item, work_qty>0만 보존)."""
    item = str(payload.get("item", "")).strip()
    if not item: return {"ok": False, "detail": "품번 필수"}
    rows = payload.get("rows", []) or []
    user = (payload.get("user") or "웹")[:30]
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.prodinfo_assy WHERE item_code=?", item)
        saved = 0
        for r in rows:
            try: q = int(float(r.get("work_qty")))
            except: q = 0
            aw = int(r.get("a_work_code") or 0)
            if aw and q > 0:
                cur.execute("""INSERT INTO nx.prodinfo_assy(item_code,a_work_code,work_qty,upd_user,upd_at)
                    VALUES(?,?,?,?,getdate())""", item, aw, q, user)
                saved += 1
        cn.commit()
        return {"ok": True, "saved": saved}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.post("/api/prodinfo/single/save")
def prodinfo_single_save(payload: dict = Body(...)):
    """단품 외경별 표준ST 마스터 저장(nx.prodinfo_single upsert by s_work_code). 전사 공유 마스터."""
    rows = payload.get("rows", []) or []
    user = (payload.get("user") or "웹")[:30]
    cn = _nx(); cur = cn.cursor()
    try:
        saved = 0
        for r in rows:
            sw = int(r.get("s_work_code") or 0)
            if not sw: continue
            def st(k):
                v = r.get(k)
                try: return float(v) if v not in (None, "") else None
                except: return None
            stvals = [st(k) for k, _ in _OD_COLS]
            cur.execute("SELECT 1 FROM nx.prodinfo_single WHERE s_work_code=?", sw)
            setclause = ", ".join([f"{k}=?" for k, _ in _OD_COLS])
            if cur.fetchone():
                cur.execute(f"""UPDATE nx.prodinfo_single SET work_desc=?, work_code=?, gagong_proc_code=?,
                    hour_pay=?, cutting_proc_flag=?, sub_weld_flag=?, sort_seq=?, {setclause},
                    upd_user=?, upd_at=getdate() WHERE s_work_code=?""",
                    (r.get("work_desc") or None), (r.get("work_code") or None), (r.get("gagong_proc_code") or None),
                    int(float(r.get("hour_pay") or 0)), (r.get("cutting_flag") or None), (r.get("sub_weld_flag") or None),
                    int(float(r.get("sort_seq") or 0)), *stvals, user, sw)
            else:
                cols = ", ".join([k for k, _ in _OD_COLS])
                ph = ", ".join(["?"] * len(_OD_COLS))
                cur.execute(f"""INSERT INTO nx.prodinfo_single
                    (s_work_code, work_desc, work_code, gagong_proc_code, hour_pay, cutting_proc_flag, sub_weld_flag, sort_seq, {cols}, upd_user, upd_at)
                    VALUES (?,?,?,?,?,?,?,?,{ph},?,getdate())""",
                    sw, (r.get("work_desc") or None), (r.get("work_code") or None), (r.get("gagong_proc_code") or None),
                    int(float(r.get("hour_pay") or 0)), (r.get("cutting_flag") or None), (r.get("sub_weld_flag") or None),
                    int(float(r.get("sort_seq") or 0)), *stvals, user)
            saved += 1
        cn.commit()
        return {"ok": True, "saved": saved}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.post("/api/prodinfo/itemst/save")
def prodinfo_itemst_save(payload: dict = Body(...)):
    """LOB분석(생산구분별 인원/CAPA) 저장(nx.prodinfo_item_st replace-all by item)."""
    item = str(payload.get("item", "")).strip()
    if not item: return {"ok": False, "detail": "품번 필수"}
    rows = payload.get("rows", []) or []
    user = (payload.get("user") or "웹")[:30]
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.prodinfo_item_st WHERE item_code=?", item)
        saved = 0
        for r in rows:
            pg = (r.get("prod_gubun") or "").strip()[:2]
            if not pg: continue
            cur.execute("""INSERT INTO nx.prodinfo_item_st(item_code,prod_gubun,member_qty,capa_qty,upd_user,upd_at)
                VALUES(?,?,?,?,?,getdate())""", item, pg, int(float(r.get("member_qty") or 0)),
                int(float(r.get("capa_qty") or 0)), user)
            saved += 1
        cn.commit()
        return {"ok": True, "saved": saved}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.post("/api/prodinfo/jig/save")
def prodinfo_jig_save(payload: dict = Body(...)):
    """지그정보 저장(nx.prodinfo_jig replace-all by item). 편집=nx만."""
    item = str(payload.get("item", "")).strip()
    if not item: return {"ok": False, "detail": "품번 필수"}
    rows = payload.get("rows", []) or []
    user = (payload.get("user") or "웹")[:30]
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.prodinfo_jig WHERE item_code=?", item)
        saved = 0
        for r in rows:
            gb = (r.get("jig_gubun") or "").strip()
            rk = (r.get("rack_loc") or "").strip()
            my = (r.get("make_ymd") or "").strip().replace("-", "")[:8]
            try: q = int(float(r.get("jig_qty") or 0))
            except: q = 0
            if not (gb or rk or my or q):
                continue
            cur.execute("""INSERT INTO nx.prodinfo_jig(item_code,seq,jig_gubun,jig_qty,rack_loc,make_ymd,upd_user,upd_at)
                VALUES(?,?,?,?,?,?,?,getdate())""", item, saved + 1, (gb[:40] or None), q,
                (rk[:40] or None), (my or None), user)
            saved += 1
        cn.commit()
        return {"ok": True, "saved": saved}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()


@router.post("/api/prodinfo/yield/save")
def prodinfo_yield_save(payload: dict = Body(...)):
    """수율(공정수) 저장(nx.prodinfo_yield replace-all by item). 편집=nx만."""
    item = str(payload.get("item", "")).strip()
    if not item: return {"ok": False, "detail": "품번 필수"}
    rows = payload.get("rows", []) or []
    user = (payload.get("user") or "웹")[:30]
    def fnum(v):
        try: return float(v) if v not in (None, "") else 0.0
        except: return 0.0
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.prodinfo_yield WHERE item_code=?", item)
        saved = 0
        for r in rows:
            nm = (r.get("yield_proc") or "").strip()
            pq, ss, s = fnum(r.get("proc_qty")), fnum(r.get("std_st")), fnum(r.get("st"))
            if not nm and not (pq or ss or s):
                continue
            cur.execute("""INSERT INTO nx.prodinfo_yield(item_code,seq,yield_proc,proc_qty,std_st,st,upd_user,upd_at)
                VALUES(?,?,?,?,?,?,?,getdate())""", item, saved + 1, (nm[:60] or None), pq, ss, s, user)
            saved += 1
        cn.commit()
        return {"ok": True, "saved": saved}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()


@router.get("/api/prodinfo/yangsan/list")
def prodinfo_yangsan_list(item: str = Query(...)):
    """양산준비 14종 문서 × 첨부파일 목록(nx.prodinfo_yangsan)."""
    it = item.strip()
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT doc_type, yid, orig_filename, byte_size, upd_user, upd_at
            FROM nx.prodinfo_yangsan WHERE item_code=? AND del_flag=0 ORDER BY doc_type, upd_at DESC""", it)
        m = {}
        for r in cur.fetchall():
            m.setdefault(str(r[0]), []).append({"yid": int(r[1]), "filename": r[2], "size": int(r[3] or 0),
                "user": r[4] or "", "dt": (r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5] or "")).replace("T", " ")[:19]})
        return {"rows": [{"doc_type": c, "doc_nm": nm, "files": m.get(c, [])} for c, nm in YANGSAN_DOCS]}
    finally:
        cn.close()


@router.post("/api/prodinfo/yangsan/upload")
async def prodinfo_yangsan_upload(file: UploadFile = File(...), item: str = Form(...),
                                  doc_type: str = Form(...), user: str = Form("웹")):
    """양산준비 문서 업로드(DOC_STORAGE_PATH\\YANGSAN\\item\\doc_type 저장 + nx.prodinfo_yangsan 메타)."""
    dt = doc_type.strip()
    if dt not in _YANGSAN_DOC_NM: raise HTTPException(400, f"문서구분 오류: {dt}")
    it = item.strip()
    if not it: raise HTTPException(400, "품번 필수")
    raw = await file.read()
    if not raw: raise HTTPException(400, "빈 파일입니다.")
    fname = file.filename or "file"
    ext = ((fname.rsplit(".", 1)[-1] if "." in fname else "") or "").lower()[:10]
    sha = _hashlib.sha256(raw).hexdigest()
    sub = _os.path.join("YANGSAN", it, dt)
    d = _os.path.join(DOC_STORAGE_PATH, sub)
    try:
        _os.makedirs(d, exist_ok=True)
    except Exception as e:
        raise HTTPException(500, f"저장경로 생성 실패({DOC_STORAGE_PATH}): {e}")
    safe = f"{sha[:12]}_{fname}"
    with open(_os.path.join(d, safe), "wb") as fp: fp.write(raw)
    rel = _os.path.join(sub, safe)
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""INSERT INTO nx.prodinfo_yangsan(item_code,doc_type,orig_filename,storage_uri,ext,byte_size,sha256,del_flag,upd_user,upd_at)
            OUTPUT INSERTED.yid VALUES(?,?,?,?,?,?,?,0,?,getdate())""",
            it, dt, fname, rel, ext, len(raw), sha, (user or "웹")[:30])
        yid = cur.fetchone()[0]
        cn.commit()
        return {"ok": True, "yid": int(yid), "size": len(raw), "path": rel}
    finally:
        cn.close()


@router.get("/api/prodinfo/yangsan/download")
def prodinfo_yangsan_download(yid: int = Query(...), disp: str = Query("attach")):
    """양산준비 첨부 다운로드/열기(disp=inline이면 브라우저 뷰)."""
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT orig_filename, storage_uri FROM nx.prodinfo_yangsan WHERE yid=? AND del_flag=0", int(yid))
        r = cur.fetchone()
        if not r: raise HTTPException(404, "첨부 없음")
        path = _os.path.join(DOC_STORAGE_PATH, r[1]); fname = r[0] or "file"
        if not _os.path.exists(path): raise HTTPException(404, f"파일 없음: {r[1]}")
        with open(path, "rb") as fp: data = fp.read()
    finally:
        cn.close()
    mime = _mimetypes.guess_type(fname)[0] or "application/octet-stream"
    cd = "inline" if str(disp).lower() == "inline" else "attachment"
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f"{cd}; filename*=UTF-8''{_urlquote(fname)}"})


@router.post("/api/prodinfo/yangsan/delete")
def prodinfo_yangsan_delete(payload: dict = Body(...)):
    """양산준비 첨부 삭제(soft delete + 파일 제거)."""
    yid = payload.get("yid")
    if not yid: return {"ok": False, "detail": "yid 필요"}
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT storage_uri FROM nx.prodinfo_yangsan WHERE yid=? AND del_flag=0", int(yid))
        r = cur.fetchone()
        if not r: return {"ok": False, "detail": "첨부 없음"}
        cur.execute("UPDATE nx.prodinfo_yangsan SET del_flag=1, upd_at=getdate() WHERE yid=?", int(yid))
        cn.commit()
        try:
            fp = _os.path.join(DOC_STORAGE_PATH, r[0])
            if _os.path.exists(fp): _os.remove(fp)
        except Exception: pass
        return {"ok": True}
    finally:
        cn.close()


@router.post("/api/line/save")
def line_save(payload: dict = Body(...)):
    p = payload
    code = str(p.get("line_no", "")).strip()[:20]
    if not code:
        raise HTTPException(400, "라인번호는 필수입니다.")
    if not _valid_hhmm(p.get("maint_hhmm")):
        raise HTTPException(400, "변경시각은 HHMM(4자리, 시<24·분<60) 형식이어야 합니다.")
    link = str(p.get("link_cust_code", "") or "").strip()[:10]
    def num(k):
        try: return int(float(p.get(k) or 0))
        except Exception: return 0
    nx = _nx(); cur = nx.cursor()
    try:
        if link:
            cur.execute("SELECT 1 FROM nx.cust WHERE cust_code=?", link)
            if not cur.fetchone(): raise HTTPException(400, "등록되어 있지 않은 거래처입니다.")
        vals = (str(p.get("apply_ymd", "") or "").strip()[:6], num("maint_day"), str(p.get("maint_hhmm", "") or "").strip()[:4],
                link, num("cust_maint_day"), str(p.get("user", "") or "웹사용자")[:40])
        if not p.get("_edit"):
            cur.execute("SELECT 1 FROM nx.line_no WHERE line_no=?", code)
            if cur.fetchone(): raise HTTPException(400, "이미 등록된 라인번호입니다.")
            cur.execute("INSERT INTO nx.line_no(line_no,apply_ymd,maint_day,maint_hhmm,link_cust_code,cust_maint_day,upd_user,upd_dt) VALUES(?,?,?,?,?,?,?,getdate())", code, *vals)
            return {"ok": True, "mode": "insert", "line_no": code}
        cur.execute("UPDATE nx.line_no SET apply_ymd=?,maint_day=?,maint_hhmm=?,link_cust_code=?,cust_maint_day=?,upd_user=?,upd_dt=getdate() WHERE line_no=?", *vals, code)
        return {"ok": True, "mode": "update", "line_no": code}
    finally:
        nx.close()

@router.post("/api/line/delete")
def line_delete(payload: dict = Body(...)):
    codes = [str(x).strip() for x in (payload.get("codes", []) or []) if str(x).strip()]
    if not codes: return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"DELETE FROM nx.line_no WHERE line_no IN ({','.join('?'*len(codes))})", *codes)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()

# ---------- 라인별달력 (LG 라인스케줄 엑셀 업로드 → nx.line_calendar) : 생산계획 가동캘린더 ----------
_WD_KO = ['월', '화', '수', '목', '금', '토', '일']
def _ensure_linecal():
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.line_calendar') IS NULL CREATE TABLE nx.line_calendar (line_no NVARCHAR(20), cal_ymd DATE, work_code NVARCHAR(20), note NVARCHAR(50), upd_dt DATETIME DEFAULT GETDATE(), CONSTRAINT pk_lcal PRIMARY KEY(line_no,cal_ymd))")
        cur.execute("IF OBJECT_ID('nx.line_cal_event') IS NULL CREATE TABLE nx.line_cal_event (cal_ymd DATE, event NVARCHAR(50), CONSTRAINT pk_lcev PRIMARY KEY(cal_ymd,event))")
        cur.execute("IF OBJECT_ID('nx.line_cal_meta') IS NULL CREATE TABLE nx.line_cal_meta (line_no NVARCHAR(20) PRIMARY KEY, sort_ord INT, gubun NVARCHAR(20), model_no NVARCHAR(20), jindo NVARCHAR(30), upd_dt DATETIME DEFAULT GETDATE())")
    finally:
        nx.close()

@router.post("/api/linecal/upload")
async def linecal_upload(file: UploadFile = File(...), anchor_ymd: str = Form(...)):
    """LG 라인스케줄 엑셀 업로드. anchor_ymd(YYYY-MM-DD, 기준일)로 날짜 앵커링 → '잔업' 시트 파싱 → 덮어쓰기."""
    import sys as _sys, os as _os, datetime as _dt
    # _schema는 프로젝트 루트(NEW_ERP_1/_schema): routers→backend→PNC_ERP_Web→NEW_ERP_1 (..×3)
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..', '_schema'))
    try:
        from linecal_parser import parse_line_schedule
    except Exception as e:
        raise HTTPException(500, f"파서 로드 실패(_schema 경로 확인): {e}")
    d = "".join(ch for ch in str(anchor_ymd) if ch.isdigit())
    if len(d) != 8: raise HTTPException(400, "기준일(YYYY-MM-DD)을 입력하세요.")
    anchor = _dt.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
    data = await file.read()
    try:
        res = parse_line_schedule(data, anchor)
    except Exception as e:
        raise HTTPException(400, f"엑셀 파싱 실패: {e}")
    _ensure_linecal()
    nx = _nx(); cur = nx.cursor()
    try:
        df, dt = res["date_from"].isoformat(), res["date_to"].isoformat()
        cur.execute("DELETE FROM nx.line_calendar WHERE cal_ymd BETWEEN ? AND ?", df, dt)
        cur.execute("DELETE FROM nx.line_cal_event WHERE cal_ymd BETWEEN ? AND ?", df, dt)
        for x in res["recs"]:
            cur.execute("INSERT INTO nx.line_calendar(line_no,cal_ymd,work_code) VALUES(?,?,?)", x["line_no"], x["ymd"].isoformat(), x["code"])
        for x in res["events"]:
            cur.execute("INSERT INTO nx.line_cal_event(cal_ymd,event) VALUES(?,?)", x["ymd"].isoformat(), x["event"])
        for x in res["meta"]:
            cur.execute("DELETE FROM nx.line_cal_meta WHERE line_no=?", x["line_no"])
            cur.execute("INSERT INTO nx.line_cal_meta(line_no,sort_ord,gubun,model_no,jindo) VALUES(?,?,?,?,?)", x["line_no"], x["sort_ord"], x["gubun"], x["model_no"], x["jindo"])
        return {"ok": True, "recs": len(res["recs"]), "events": len(res["events"]), "lines": len(res["meta"]),
                "date_from": df, "date_to": dt, "anchor": anchor.isoformat()}
    finally:
        nx.close()

@router.get("/api/linecal/matrix")
def linecal_matrix(from_ymd: str = Query(""), weeks: int = Query(4)):
    """라인별달력 매트릭스(라인×날짜). from_ymd 없으면 데이터 최신 앵커 주 월요일부터."""
    import datetime as _dt
    _ensure_linecal()
    nx = _nx(); cur = nx.cursor()
    try:
        dd = "".join(ch for ch in from_ymd if ch.isdigit())
        if len(dd) >= 8:
            start = _dt.date(int(dd[:4]), int(dd[4:6]), int(dd[6:8]))
        else:
            cur.execute("SELECT MIN(cal_ymd) FROM nx.line_calendar WHERE cal_ymd >= DATEADD(day,-7,CAST(GETDATE() AS DATE))")
            base = cur.fetchone()[0]
            base = base if base else _dt.date.today()
            if not isinstance(base, _dt.date): base = _dt.date.fromisoformat(str(base)[:10])
            start = base - _dt.timedelta(days=base.weekday())
        weeks = max(1, min(int(weeks or 4), 8))
        dates = [start + _dt.timedelta(days=i) for i in range(weeks * 7)]
        end = dates[-1]
        cur.execute("SELECT CONVERT(varchar(10),cal_ymd,120),event FROM nx.line_cal_event WHERE cal_ymd BETWEEN ? AND ?", start.isoformat(), end.isoformat())
        ev = {}
        for r in cur.fetchall(): ev.setdefault(r[0], []).append(r[1])
        cur.execute("SELECT line_no,ISNULL(sort_ord,0),ISNULL(gubun,''),ISNULL(model_no,''),ISNULL(jindo,'') FROM nx.line_cal_meta ORDER BY sort_ord,line_no")
        metas = [{"line_no": r[0], "gubun": r[2], "model_no": r[3], "jindo": r[4]} for r in cur.fetchall()]
        cur.execute("SELECT line_no,CONVERT(varchar(10),cal_ymd,120),work_code FROM nx.line_calendar WHERE cal_ymd BETWEEN ? AND ?", start.isoformat(), end.isoformat())
        cells = {}
        for r in cur.fetchall(): cells.setdefault(r[0], {})[r[1]] = r[2]
        for m in metas: m["cells"] = cells.get(m["line_no"], {})
        return {"dates": [{"ymd": d.isoformat(), "dow": _WD_KO[d.weekday()], "day": d.day, "mon": d.month,
                           "events": ev.get(d.isoformat(), [])} for d in dates],
                "lines": metas, "from": start.isoformat(), "to": end.isoformat(), "weeks": weeks}
    finally:
        nx.close()


# ---------- 근무달력(nx.work_calendar)·파트별달력(nx.part_calendar) 매트릭스 + 편집 ----------
_PR004 = {'1': '출근(잔업2시간)', '2': '출근(정상근무)', '3': '일요일', '4': '휴무',
          '5': '출근(잔업3시간)', '6': '출근(잔업4시간)', '7': '출근(4시간근무)'}
# 공장운영 달력 파트 순서(사용자 지정, 레거시 PR_M_PROC_GAGONG 참고) (코드, 표시명, 들여쓰기)
_PART_ORDER = [
    ("P0005", "제품물류파트", 0), ("P0006", "부품물류파트", 0),
    ("P0003", "이지링크", 0), ("P0002", "가공", 0),
    ("S5", "01라인(용접)", 0), ("S5-2", "01라인(조립)", 0), ("S1", "02라인", 0),
    ("S6", "03라인", 0), ("S4", "04라인", 0), ("S11", "05라인", 0), ("RAC", "06라인", 0),
    ("S8", "서포터(08)", 0), ("S10", "자동은납(10)", 0),
]
def _wcal_partnames():
    """PART_CODE→이름(PR_M_PROC_GAGONG), 이름 속 'PART'→'파트'."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT GAGONG_PROC_CODE, GAGONG_PROC_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG")
        return {str(r[0]).strip(): str(r[1] or '').strip().replace('PART', '파트') for r in cur.fetchall()}
    finally:
        cn.close()

@router.get("/api/wcal/matrix")
def wcal_matrix(kind: str = Query("part"), from_ymd: str = Query(""), weeks: int = Query(4)):
    """근무/파트 달력 매트릭스(엔티티×날짜, WORK_STATS 디코드). 파트=공통행(근무달력) + 파트행."""
    import datetime as _dt
    nx = _nx(); cur = nx.cursor()
    try:
        dd = "".join(ch for ch in from_ymd if ch.isdigit())
        if len(dd) >= 8:
            start = _dt.date(int(dd[:4]), int(dd[4:6]), int(dd[6:8]))
        else:
            t = _dt.date.today(); start = t - _dt.timedelta(days=t.weekday())
        weeks = max(1, min(int(weeks or 4), 8))
        dates = [start + _dt.timedelta(days=i) for i in range(weeks * 7)]
        s, e = start.isoformat(), dates[-1].isoformat()
        # 공통(근무달력 team=A)
        cur.execute("SELECT CONVERT(varchar(10),cal_ymd,120),work_stats FROM nx.work_calendar WHERE cal_ymd BETWEEN ? AND ?", s, e)
        common = {r[0]: r[1] for r in cur.fetchall()}
        rows = [{"ent": "공통", "name": "공통", "indent": 0, "cells": common, "common": True}]
        if kind == "part":
            cur.execute("SELECT part_code,CONVERT(varchar(10),cal_ymd,120),work_stats FROM nx.part_calendar WHERE cal_ymd BETWEEN ? AND ?", s, e)
            pc = {}
            for r in cur.fetchall(): pc.setdefault(r[0], {})[r[1]] = r[2]
            for code, nm, indent in _PART_ORDER:   # 사용자 지정 순서·이름(코드 아님)
                rows.append({"ent": code, "name": nm, "indent": indent, "cells": pc.get(code, {}), "common": False})
        return {"kind": kind, "from": s, "to": e, "weeks": weeks,
                "dates": [{"ymd": d.isoformat(), "dow": _WD_KO[d.weekday()], "day": d.day, "mon": d.month} for d in dates],
                "rows": rows, "decode": _PR004}
    finally:
        nx.close()

@router.post("/api/wcal/save")
def wcal_save(payload: dict = Body(...)):
    """셀 편집 저장(upsert). kind=work→nx.work_calendar(team=A), part→nx.part_calendar. cells=[{ent,ymd,ws}]."""
    kind = payload.get("kind", "part")
    cells = payload.get("cells", []) or []
    tbl = "nx.work_calendar" if kind == "work" else "nx.part_calendar"
    keycol = "team" if kind == "work" else "part_code"
    nx = _nx(); cur = nx.cursor()
    try:
        n = 0
        for x in cells:
            ent = "A" if kind == "work" else str(x.get("ent", "")).strip()
            if kind == "work": ent = "A"
            elif str(x.get("ent", "")).strip() == "공통": ent = None
            ymd = str(x.get("ymd", "")).strip()[:10]
            ws = str(x.get("ws", "")).strip()[:2]
            if not ymd: continue
            # 공통행 편집 → work_calendar
            t2, k2, e2 = ("nx.work_calendar", "team", "A") if (kind == "work" or x.get("ent") == "공통") else (tbl, keycol, ent)
            if e2 is None: e2 = "A"; t2 = "nx.work_calendar"; k2 = "team"
            cur.execute(f"DELETE FROM {t2} WHERE {k2}=? AND cal_ymd=?", e2, ymd)
            if ws:
                cur.execute(f"INSERT INTO {t2}({k2},cal_ymd,work_stats,upd_user) VALUES(?,?,?,?)", e2, ymd, ws, str(payload.get("user", "") or "웹사용자")[:40])
            n += 1
        return {"ok": True, "saved": n}
    finally:
        nx.close()
