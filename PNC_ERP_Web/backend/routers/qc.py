# -*- coding: utf-8 -*-
"""품질(qc) 도메인 라우터 — 불량관리·시방변경·IQC조회. 조회=레거시QA_+nx 합집합, 쓰기=nx.
   app.py에서 분리. 공유헬퍼는 common.py. ★_b·_d8은 이 도메인 로컬(common의 _b와 다름=FINISH_FLAG용)."""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException, UploadFile, File, Form
from common import _conn, _nx, _nx_tx, _d6, _num
# ★품질불량 첨부파일(3종) — 기존 문서저장소(nx.doc + NAS)를 그대로 재사용한다.
#   경로정책·백업이 도면첨부와 같아지도록 doc.py 와 동일한 DOC_STORAGE_PATH 를 쓴다.
import os as _os, hashlib as _hashlib
from routers.doc import DOC_STORAGE_PATH

router = APIRouter()

# ==================================================================================
# ============================  품질(QUALITY) 모듈  ================================
# 조회 = 레거시 QA_(읽기전용) + nx 사용자입력 합집합(src표시). 쓰기 = nx만.
# ==================================================================================
def _b(v):
    """FINISH_FLAG 등 다양한 참/거짓 표기를 0/1로 정규화."""
    s = str(v).strip().upper()
    return 1 if s in ("1", "Y", "T", "TRUE", "O", "OK", "완료") else 0

# ---------- 품질불량관리 (QA_T_ERROR ↔ nx.qc_error) ----------
@router.get("/api/qc/error/codes")
def qc_error_codes(level: int = Query(1)):
    """불량항목 드롭다운(대/중/소 = level 1/2/3). nx.qc_error_code."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT code, error_tag, descr FROM nx.qc_error_code WHERE level=? ORDER BY code", int(level))
        return {"rows": [{"code": r[0], "tag": r[1], "descr": r[2]} for r in cur.fetchall()]}
    finally:
        nx.close()

# 불량구분(error_tag)·작업처(work_code) 디코드 — 소스 dw_qa_input_020(정본)
_ERRTAG = {"1": "LQC불량", "2": "고객사불량", "3": "IQC불량", "4": "초품불량", "5": "OQC불량", "8": "가공", "A": "자주순차", "9": "기타"}
_WORKNM = {"P1": "용접", "P2": "가공", "D1": "직납"}
@router.get("/api/qc/opt")
def qc_opt(kind: str = Query("part"), q: str = Query("")):
    """자동완성 옵션(코드+이름). kind=part(생산파트)/mach(설비)/partner(협력사)/line(고객사라인)."""
    cn = _conn(); cur = cn.cursor()
    like = f"%{q.strip()}%"
    try:
        if kind == "part":
            cur.execute("""SELECT TOP 50 GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG
                WHERE GAGONG_PROC_CODE LIKE ? OR GAGONG_PROC_DESC LIKE ? ORDER BY SORT_KEY, GAGONG_PROC_CODE""", like, like)
        elif kind == "mach":
            cur.execute("""SELECT TOP 50 MACH_CODE, ISNULL(MACH_DESC,'') FROM PARTNER_ERP_TEST3.nx.QA_M_MACHINE
                WHERE ISNULL(USE_FLAG,'1')='1' AND (MACH_CODE LIKE ? OR MACH_DESC LIKE ?) ORDER BY MACH_DESC""", like, like)
        elif kind == "partner":
            cur.execute("""SELECT TOP 50 CUST_CODE, ISNULL(CUST_DESC,'') FROM PARTNER_ERP_TEST3.nx.CM_M_CUST
                WHERE CUST_CODE LIKE ? OR CUST_DESC LIKE ? ORDER BY CUST_DESC""", like, like)
        elif kind == "line":
            cur.execute("SELECT TOP 50 LINE_NO code, LINE_NO nm FROM PARTNER_ERP_TEST3.nx.PR_M_LINE_NO WHERE LINE_NO LIKE ? ORDER BY LINE_NO", like)
        elif kind == "item":
            cur.execute("""SELECT TOP 50 ITEM_CODE, ISNULL(item_name,'') FROM PARTNER_ERP_TEST3.nx.item
                WHERE ITEM_CODE LIKE ? OR item_name LIKE ? ORDER BY ITEM_CODE""", like, like)
        else:
            raise HTTPException(400, "알 수 없는 kind")
        return {"rows": [{"code": str(r[0]).strip(), "name": str(r[1]).strip()} for r in cur.fetchall()]}
    finally:
        cn.close()
@router.get("/api/qc/error/list")
def qc_error_list(from_ymd: str = Query(""), to_ymd: str = Query(""), item: str = Query(""),
                  tag: str = Query(""), cust_line: str = Query(""), division: str = Query(""),
                  work: str = Query(""), proc: str = Query(""), partner: str = Query(""),
                  finish: str = Query(""), eitem: str = Query(""), src: str = Query("all")):
    """품질불량 조회(레거시 dw_qa_input_020 전체 컬럼). src=all/legacy/nx."""
    cn = _conn(); cur = cn.cursor()
    try:
        # (legacy_col, nx_col, op, value) 필터 — 양쪽 WHERE 동시 생성
        flt = []
        if from_ymd: flt.append(("e.ERROR_YMD", "n.error_ymd", ">=", _d6(from_ymd)))
        if to_ymd:   flt.append(("e.ERROR_YMD", "n.error_ymd", "<=", _d6(to_ymd)))
        if item.strip():      flt.append(("e.ITEM_CODE", "n.item_code", "LIKE", f"%{item.strip()}%"))
        if tag.strip():       flt.append(("e.ERROR_TAG", "n.error_tag", "=", tag.strip()))
        if cust_line.strip(): flt.append(("e.CUST_LINE", "n.cust_line", "LIKE", f"%{cust_line.strip()}%"))
        if division.strip():  flt.append(("e.DIVISION_DESC", "n.division", "LIKE", f"%{division.strip()}%"))
        if work.strip():      flt.append(("e.WORK_CODE", "n.work_code", "=", work.strip()))
        if proc.strip():      flt.append(("e.PROC_CODE", "n.proc_code", "=", proc.strip()))
        if partner.strip():   flt.append(("e.WORK_CUST_CODE", "n.partner_code", "LIKE", f"%{partner.strip()}%"))
        if finish in ("0", "1"): flt.append(("ISNULL(e.FINISH_FLAG,'0')", "CAST(ISNULL(n.finish_flag,0) AS NVARCHAR(1))", "=", finish))
        if eitem.strip():     flt.append(("e.ERROR_ITEM", "n.error_item1", "LIKE", f"%{eitem.strip()}%"))
        wl = " AND ".join(["1=1"] + [f"{c[0]} {c[2]} ?" for c in flt])
        wn = " AND ".join(["1=1"] + [f"{c[1]} {c[2]} ?" for c in flt])
        pv = [c[3] for c in flt]
        # src=all일 때 nx 수정본이 있는 레거시 원본은 숨김(중복 방지)
        dedup = (" AND CAST(e.SEQ AS INT) NOT IN (SELECT legacy_seq FROM PARTNER_ERP_TEST3.nx.qc_error WHERE legacy_seq IS NOT NULL)"
                 if src == "all" else "")
        parts = []
        if src in ("all", "legacy"):
            parts.append(f"""SELECT 'legacy' src, CAST(e.SEQ AS NVARCHAR(20)) key_id, ISNULL(e.ERROR_TAG,'') tag,
                ISNULL(e.CUST_LINE,'') cust_line, ISNULL(e.DIVISION_DESC,'') division, ISNULL(e.PG_REG_INFO,'') pg_reg,
                e.ERROR_YMD error_ymd, e.ITEM_CODE item_code, ISNULL(i.item_name,'') item_desc,
                ISNULL(e.WORK_CODE,'') work_code, ISNULL(e.PROC_CODE,'') proc_code, ISNULL(pg.GAGONG_PROC_DESC,'') part_nm,
                ISNULL(e.MACH_CODE,'') mach_code, ISNULL(m.MACH_DESC,'') mach_nm, ISNULL(e.WORK_CUST_CODE,'') partner_code,
                ISNULL(c.CUST_DESC,'') partner_nm, ISNULL(e.INSPECTOR_MEMBER_NAME,'') inspector, ISNULL(e.ERROR_MEMBER_NAME,'') error_member,
                ISNULL(e.ERROR_ITEM,'') ei1, ISNULL(e.ERROR_ITEM2,'') ei2, ISNULL(e.ERROR_ITEM3,'') ei3,
                ISNULL(e.ERROR_DESC,'') error_desc, ISNULL(e.ERROR_COLOR,'') color, ISNULL(e.LOT_QTY,0) lot_qty,
                ISNULL(e.ERROR_QTY,0) error_qty, ISNULL(e.REAL_ERROR_QTY,0) real_qty, ISNULL(e.ERROR_CAUSE,'') error_cause,
                ISNULL(e.PROGRESS_STATS,'') progress, ISNULL(e.WATER_CHECK_FLAG,'') water_flag,
                ISNULL(e.RE_INSP_CHECK,'') reinsp_flag, ISNULL(e.FINISH_FLAG,'') finish_flag, ISNULL(e.CHARGE_NAME,'') charge,
                CAST(e.SEQ AS INT) lseq,
                0 f_attach, 0 f_plan1, 0 f_plan2   -- 레거시행은 웹첨부 대상 아님(nx 행에만 첨부 가능)
                FROM PARTNER_ERP_TEST3.nx.QA_T_ERROR e LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.ITEM_CODE=e.ITEM_CODE
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg ON pg.GAGONG_PROC_CODE=e.PROC_CODE
                LEFT JOIN PARTNER_ERP_TEST3.nx.QA_M_MACHINE m ON m.MACH_CODE=e.MACH_CODE
                LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=e.WORK_CUST_CODE WHERE {wl}{dedup}""")
        if src in ("all", "nx"):
            parts.append(f"""SELECT 'nx' src, CAST(n.id AS NVARCHAR(20)) key_id, ISNULL(n.error_tag,'') tag,
                ISNULL(n.cust_line,'') cust_line, ISNULL(n.division,'') division, ISNULL(n.pg_reg,'') pg_reg,
                n.error_ymd error_ymd, n.item_code item_code, ISNULL(i2.item_name,'') item_desc,
                ISNULL(n.work_code,'') work_code, ISNULL(n.proc_code,'') proc_code, ISNULL(pg2.GAGONG_PROC_DESC,'') part_nm,
                ISNULL(n.mach_code,'') mach_code, ISNULL(m2.MACH_DESC,'') mach_nm, ISNULL(n.partner_code,'') partner_code,
                ISNULL(c2.CUST_DESC,'') partner_nm, ISNULL(n.inspector,'') inspector, ISNULL(n.error_member,'') error_member,
                ISNULL(n.error_item1,'') ei1, ISNULL(n.error_item2,'') ei2, ISNULL(n.error_item3,'') ei3,
                ISNULL(n.error_desc,'') error_desc, ISNULL(n.color,'') color, ISNULL(n.lot_qty,0) lot_qty,
                ISNULL(n.error_qty,0) error_qty, ISNULL(n.real_error_qty,0) real_qty, ISNULL(n.error_cause,'') error_cause,
                ISNULL(n.progress_stats,'') progress, CAST(ISNULL(n.susu_flag,0) AS NVARCHAR(1)) water_flag,
                CAST(ISNULL(n.reinsp_flag,0) AS NVARCHAR(1)) reinsp_flag, CAST(ISNULL(n.finish_flag,0) AS NVARCHAR(1)) finish_flag,
                ISNULL(n.charge_name,'') charge, ISNULL(n.legacy_seq,0) lseq,
                ISNULL(n.attach_doc_id,0) f_attach, ISNULL(n.plan1_doc_id,0) f_plan1, ISNULL(n.plan2_doc_id,0) f_plan2
                FROM PARTNER_ERP_TEST3.nx.qc_error n LEFT JOIN PARTNER_ERP_TEST3.nx.item i2 ON i2.ITEM_CODE=n.item_code
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg2 ON pg2.GAGONG_PROC_CODE=n.proc_code
                LEFT JOIN PARTNER_ERP_TEST3.nx.QA_M_MACHINE m2 ON m2.MACH_CODE=n.mach_code
                LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c2 ON c2.CUST_CODE=n.partner_code WHERE {wn}""")
        plist = []
        for part in parts: plist += pv
        sql = "SELECT TOP 3000 * FROM (\n" + "\nUNION ALL\n".join(parts) + "\n) q ORDER BY error_ymd DESC, key_id DESC"
        cur.execute(sql, *plist)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            for k in ("lot_qty", "error_qty", "real_qty"): r[k] = float(r[k] or 0)
            for k in ("water_flag", "reinsp_flag", "finish_flag"): r[k] = _b(r[k])
            r["pg_reg"] = str(r["pg_reg"]).strip()   # 전산등록: 내부용/보고용 문자열(레거시 1/0은 그대로)
            r["tag_nm"] = _ERRTAG.get(str(r["tag"]).strip(), str(r["tag"]))
            r["work_nm"] = _WORKNM.get(str(r["work_code"]).strip(), str(r["work_code"]))
            r["ID"] = int(r["key_id"]) if r["src"] == "nx" and str(r["key_id"]).isdigit() else None
            # 첨부 3칸 중 몇 개가 붙어있나(그리드 📎 표시용)
            r["n_files"] = sum(1 for k in ("f_attach", "f_plan1", "f_plan2") if int(r.get(k) or 0))
        return {"rows": rows, "cnt": len(rows),
                "sum_err": sum(r["error_qty"] for r in rows), "sum_lot": sum(r["lot_qty"] for r in rows)}
    finally:
        cn.close()

@router.post("/api/qc/error/save")
def qc_error_save(payload: dict = Body(...)):
    p = payload
    # ★필수는 P/No 뿐(레거시 w_qa_input_025 동일). 불량일자 미입력 시 오늘로 채운다(2026-08-23)
    ymd = _d6(str(p.get("error_ymd", ""))) or datetime.now().strftime("%y%m%d")
    item = str(p.get("item_code", "")).strip()[:40]
    if not item:
        raise HTTPException(400, "P/No(품번)는 필수입니다.")
    def s(k, n): return str(p.get(k, "")).strip()[:n]
    def f(k):
        try: return float(p.get(k) or 0)
        except Exception: return 0.0
    # 전체 필드(레거시 dw_qa_input_026 대응)
    lseq = p.get("legacy_seq")
    lseq = int(lseq) if str(lseq).strip() not in ("", "None", "null") else None
    vals = (ymd, s("error_tag", 4), s("division", 10), s("cust_line", 20), s("pg_reg", 10),
            item, s("work_code", 10), s("proc_code", 20), s("mach_code", 20), s("partner_code", 20),
            s("inspector", 40), s("error_member", 40), s("error_item1", 60), s("error_item2", 60), s("error_item3", 100),
            s("error_desc", 400), s("error_cause", 400), s("error_position", 60), s("color", 10),
            f("lot_qty"), f("error_qty"), f("real_error_qty"), f("scrap_weight"),
            s("progress_stats", 200), s("charge_name", 40),
            _b(p.get("finish_flag")), _b(p.get("water_flag")), _b(p.get("reinsp_flag")), lseq,
            (s("user", 40) or "웹사용자"))
    mid = p.get("id")
    nx = _nx(); cur = nx.cursor()
    try:
        if mid:
            cur.execute("""UPDATE nx.qc_error SET error_ymd=?,error_tag=?,division=?,cust_line=?,pg_reg=?,
                item_code=?,work_code=?,proc_code=?,mach_code=?,partner_code=?,inspector=?,error_member=?,
                error_item1=?,error_item2=?,error_item3=?,error_desc=?,error_cause=?,error_position=?,color=?,
                lot_qty=?,error_qty=?,real_error_qty=?,scrap_weight=?,progress_stats=?,charge_name=?,
                finish_flag=?,susu_flag=?,reinsp_flag=?,legacy_seq=?,upd_user=?,upd_dt=getdate() WHERE id=?""", *vals, int(mid))
            return {"ok": True, "id": int(mid), "mode": "update"}
        cur.execute("""INSERT INTO nx.qc_error(error_ymd,error_tag,division,cust_line,pg_reg,item_code,work_code,
            proc_code,mach_code,partner_code,inspector,error_member,error_item1,error_item2,error_item3,error_desc,
            error_cause,error_position,color,lot_qty,error_qty,real_error_qty,scrap_weight,progress_stats,charge_name,
            finish_flag,susu_flag,reinsp_flag,legacy_seq,upd_user)
            OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", *vals)
        return {"ok": True, "id": int(cur.fetchone()[0]), "mode": "insert"}
    finally:
        nx.close()

@router.post("/api/qc/error/delete")
def qc_error_delete(payload: dict = Body(...)):
    ids = [int(x) for x in (payload.get("ids", []) or []) if str(x).strip()]
    if not ids: return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"DELETE FROM nx.qc_error WHERE id IN ({','.join('?'*len(ids))})", *ids)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()

# ---------- 품질불량관리 첨부파일 3종 (레거시 w_qa_input_025: 첨부파일#1·대책서#1·대책서#2) ----------
# ★파일 실체는 기존 문서저장소(nx.doc + NAS DOC_STORAGE_PATH)를 그대로 재사용한다.
#   qc_error 에는 doc_id 만 들고, 다운로드는 기존 /api/doc/download?src=doc&key=<doc_id> 로 처리.
#   → 저장소를 새로 만들지 않으므로 백업·경로정책이 도면첨부와 동일하게 유지된다.
_QC_SLOT = {"attach": "attach_doc_id", "plan1": "plan1_doc_id", "plan2": "plan2_doc_id"}
_QC_SLOT_NM = {"attach": "첨부파일#1", "plan1": "대책서#1", "plan2": "대책서#2"}

@router.get("/api/qc/error/files")
def qc_error_files(id: int = Query(...)):
    """그 불량건의 첨부 3칸 현황(슬롯별 파일명·크기·업로더)."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT ISNULL(e.attach_doc_id,0), ISNULL(e.plan1_doc_id,0), ISNULL(e.plan2_doc_id,0)
                         FROM nx.qc_error e WHERE e.id=?""", int(id))
        r = cur.fetchone()
        if not r: raise HTTPException(404, "불량건 없음")
        out = {}
        for slot, did in zip(("attach", "plan1", "plan2"), r):
            info = {"slot": slot, "label": _QC_SLOT_NM[slot], "doc_id": None,
                    "filename": "", "size": 0, "user": "", "dt": ""}
            if did:
                cur.execute("""SELECT orig_filename, byte_size, insert_user, insert_dt
                                 FROM nx.doc WHERE doc_id=? AND del_flag=0""", int(did))
                d = cur.fetchone()
                if d:
                    info.update({"doc_id": int(did), "filename": d[0], "size": int(d[1] or 0),
                                 "user": d[2] or "",
                                 "dt": (d[3].isoformat() if hasattr(d[3], "isoformat") else str(d[3] or "")).replace("T", " ")[:19]})
            out[slot] = info
        return {"ok": True, "id": int(id), "files": out}
    finally:
        nx.close()

@router.post("/api/qc/error/file_upload")
async def qc_error_file_upload(file: UploadFile = File(...), id: int = Form(...),
                               slot: str = Form("attach"), user: str = Form("웹사용자")):
    """첨부 업로드 — 슬롯(attach/plan1/plan2) 1칸당 파일 1개. 재업로드하면 이전 것은 삭제표시."""
    slot = str(slot).strip()
    if slot not in _QC_SLOT:
        raise HTTPException(400, "slot 은 attach/plan1/plan2 중 하나여야 합니다.")
    raw = await file.read()
    if not raw: raise HTTPException(400, "빈 파일입니다.")
    fname = file.filename or "file"
    ext = ((fname.rsplit(".", 1)[-1] if "." in fname else "") or "").lower()[:10]
    sha = _hashlib.sha256(raw).hexdigest()
    sub = _os.path.join("QC_ERROR", str(int(id)))
    d = _os.path.join(DOC_STORAGE_PATH, sub)
    try:
        _os.makedirs(d, exist_ok=True)
    except Exception as e:
        raise HTTPException(500,
            f"저장경로 생성 실패({DOC_STORAGE_PATH}): {e} — "
            f"서버 환경변수 DOC_STORAGE_PATH 를 확인하세요"
            f"(한글이 깨졌거나 없는 드라이브면 저장이 안 됩니다).")
    # ★파일명에 윈도우 금지문자·제어문자가 있으면 못 쓴다(한글은 그대로 둔다).
    #   업로드 파일명은 브라우저가 준 값이라 무엇이든 올 수 있다.
    _fn = "".join(("_" if (ch in '\\/:*?"<>|' or ord(ch) < 32) else ch) for ch in fname)[:120] or "file"
    safe = f"{slot}_{sha[:12]}_{_fn}"
    with open(_os.path.join(d, safe), "wb") as fp: fp.write(raw)
    rel = _os.path.join(sub, safe)
    nx = _nx(); cur = nx.cursor()
    try:
        col = _QC_SLOT[slot]
        cur.execute(f"SELECT ISNULL({col},0) FROM nx.qc_error WHERE id=?", int(id))
        r = cur.fetchone()
        if not r: raise HTTPException(404, "불량건 없음 — 먼저 저장한 뒤 첨부하세요.")
        old = int(r[0] or 0)
        cur.execute("""INSERT INTO nx.doc(doc_kind,item_code,orig_filename,storage_uri,ext,byte_size,sha256,insert_user,insert_dt)
            OUTPUT INSERTED.doc_id VALUES('QC_ERROR',?,?,?,?,?,?,?,GETDATE())""",
            str(int(id)), fname, rel, ext, len(raw), sha, (user or "웹사용자")[:20])
        did = int(cur.fetchone()[0])
        cur.execute(f"UPDATE nx.qc_error SET {col}=?, upd_user=?, upd_dt=getdate() WHERE id=?",
                    did, (user or "웹사용자")[:40], int(id))
        if old:      # 같은 칸의 이전 파일은 삭제표시(실파일은 남겨 복구 가능)
            cur.execute("UPDATE nx.doc SET del_flag=1 WHERE doc_id=?", old)
        return {"ok": True, "doc_id": did, "slot": slot, "filename": fname, "size": len(raw)}
    finally:
        nx.close()

@router.post("/api/qc/error/file_delete")
def qc_error_file_delete(payload: dict = Body(...)):
    """첨부 삭제(파일삭제 체크) — 슬롯을 비운다. 실파일은 남기고 doc 만 삭제표시."""
    try: rid = int(payload.get("id"))
    except Exception: raise HTTPException(400, "id 필요")
    slot = str(payload.get("slot", "")).strip()
    if slot not in _QC_SLOT:
        raise HTTPException(400, "slot 은 attach/plan1/plan2 중 하나여야 합니다.")
    col = _QC_SLOT[slot]
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"SELECT ISNULL({col},0) FROM nx.qc_error WHERE id=?", rid)
        r = cur.fetchone()
        if not r: return {"ok": False, "errors": ["불량건 없음"]}
        did = int(r[0] or 0)
        cur.execute(f"UPDATE nx.qc_error SET {col}=NULL, upd_dt=getdate() WHERE id=?", rid)
        if did: cur.execute("UPDATE nx.doc SET del_flag=1 WHERE doc_id=?", did)
        return {"ok": True, "slot": slot, "deleted_doc_id": (did or None)}
    finally:
        nx.close()

# ---------- 시방상태(품번→시방변경 경보): 거래화면 마커/팝업용 ----------
# 적용대상(QA_T_SPEC_REV_APPLY) 확장: 베이스 시방(AJR301337)을 접미 전체(AJR30133701~09) 풀품번으로 전개
_SPEC_APPLY_SQL = """SELECT a.ITEM_CODE item, s.REV_YYMD rev_ymd, s.ISSUE_YYMD issue_ymd, s.APPLY_YYMD apply_ymd,
                s.REV_NO rev_no, ISNULL(s.ECO_NO,'') eco_no, ISNULL(s.REV_DESC,'') rev_desc
              FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV_APPLY a JOIN PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV s ON s.REV_YYMD=a.REV_YYMD AND s.REV_NO=a.REV_NO WHERE a.ITEM_CODE>''"""
@router.get("/api/spec/status")
def spec_status(items: str = Query("", description="품번 콤마구분(배치)"), item: str = Query("")):
    """품번별 최신 시방변경 상태. 적용일<=오늘=red(구시방/적용됨), 미래=orange(예정). 레거시 QA_T_SPEC_REV ∪ nx."""
    codes = [x.strip() for x in (items + "," + item).split(",") if x.strip()]
    if not codes:
        return {"map": {}}
    codes = list(dict.fromkeys(codes))[:500]
    cn = _conn(); cur = cn.cursor()
    try:
        ph = ",".join("?" * len(codes))
        cur.execute("SELECT CONVERT(NVARCHAR(8),GETDATE(),112)")
        today = cur.fetchone()[0]
        # 레거시 + nx 합쳐 품번별 최신(적용일 우선, 접수일 차순) 1건
        cur.execute(f"""
          WITH S AS (
            SELECT ITEM_CODE item, REV_YYMD rev_ymd, ISSUE_YYMD issue_ymd, APPLY_YYMD apply_ymd,
                   REV_NO rev_no, ISNULL(ECO_NO,'') eco_no, ISNULL(REV_DESC,'') rev_desc
              FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV WHERE ITEM_CODE IN ({ph})
            UNION ALL
            SELECT a.ITEM_CODE, s.REV_YYMD, s.ISSUE_YYMD, s.APPLY_YYMD, s.REV_NO, ISNULL(s.ECO_NO,''), ISNULL(s.REV_DESC,'')
              FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV_APPLY a JOIN PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV s ON s.REV_YYMD=a.REV_YYMD AND s.REV_NO=a.REV_NO WHERE a.ITEM_CODE IN ({ph})
            UNION ALL
            SELECT item_code, rev_ymd, issue_ymd, apply_ymd, rev_no, ISNULL(eco_no,''), ISNULL(rev_desc,'')
              FROM PARTNER_ERP_TEST3.nx.qc_spec_rev WHERE item_code IN ({ph})),
          R AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY item ORDER BY ISNULL(apply_ymd,rev_ymd) DESC, rev_ymd DESC) rn FROM S)
          SELECT item, rev_ymd, issue_ymd, apply_ymd, rev_no, eco_no, rev_desc FROM R WHERE rn=1""",
                    *codes, *codes, *codes)
        m = {}
        for r in cur.fetchall():
            ap = str(r[3] or "").strip()
            sev = "red" if (ap and ap <= today) else ("orange" if ap else "orange")
            m[str(r[0]).strip()] = {"sev": sev, "rev_ymd": str(r[1] or "").strip(),
                                    "issue_ymd": str(r[2] or "").strip(), "apply_ymd": ap,
                                    "rev_no": r[4], "eco_no": str(r[5] or "").strip(),
                                    "rev_desc": str(r[6] or "").strip(), "applied": bool(ap and ap <= today)}
        return {"map": m, "today": today}
    finally:
        cn.close()

@router.get("/api/spec/all")
def spec_all():
    """시방변경 있는 전체 품번의 최신 상태맵(1회 로드·캐시용). 마커/경보 전화면 공용."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT CONVERT(NVARCHAR(8),GETDATE(),112)"); today = cur.fetchone()[0]
        cur.execute(f"""
          WITH S AS (
            SELECT ITEM_CODE item, REV_YYMD rev_ymd, ISSUE_YYMD issue_ymd, APPLY_YYMD apply_ymd,
                   REV_NO rev_no, ISNULL(ECO_NO,'') eco_no, ISNULL(REV_DESC,'') rev_desc FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV WHERE ITEM_CODE>''
            UNION ALL {_SPEC_APPLY_SQL}
            UNION ALL SELECT item_code, rev_ymd, issue_ymd, apply_ymd, rev_no, ISNULL(eco_no,''), ISNULL(rev_desc,'')
              FROM PARTNER_ERP_TEST3.nx.qc_spec_rev),
          R AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY item ORDER BY ISNULL(apply_ymd,rev_ymd) DESC, rev_ymd DESC) rn FROM S)
          SELECT item, rev_ymd, issue_ymd, apply_ymd, rev_no, eco_no, rev_desc FROM R WHERE rn=1 AND item>''""")
        m = {}
        for r in cur.fetchall():
            ap = str(r[3] or "").strip()
            m[str(r[0]).strip()] = {"sev": "red" if (ap and ap <= today) else "orange",
                "rev_ymd": str(r[1] or "").strip(), "issue_ymd": str(r[2] or "").strip(), "apply_ymd": ap,
                "rev_no": r[4], "eco_no": str(r[5] or "").strip(), "rev_desc": str(r[6] or "").strip(),
                "applied": bool(ap and ap <= today)}
        return {"map": m, "today": today, "cnt": len(m)}
    finally:
        cn.close()

# ---------- 시방변경관리 (QA_T_SPEC_REV ↔ nx.qc_spec_rev) ----------
@router.get("/api/qc/spec/list")
def qc_spec_list(from_ymd: str = Query(""), to_ymd: str = Query(""), item: str = Query(""), src: str = Query("all")):
    cn = _conn(); cur = cn.cursor()
    try:
        def d8(x):
            d = ''.join(ch for ch in str(x or '') if ch.isdigit())
            return d if len(d) == 8 else (("20"+d) if len(d) == 6 else d)
        w = ["1=1"]; p = []
        if from_ymd: w.append("s.REV_YYMD>=?"); p.append(d8(from_ymd))
        if to_ymd:   w.append("s.REV_YYMD<=?"); p.append(d8(to_ymd))
        if item.strip(): w.append("s.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        wl = " AND ".join(w)
        wn = wl.replace("s.REV_YYMD", "n.rev_ymd").replace("s.ITEM_CODE", "n.item_code")
        parts = []
        if src in ("all", "legacy"):
            parts.append(f"""SELECT 'legacy' src, s.REV_YYMD+'-'+CAST(s.REV_NO AS NVARCHAR(10)) key_id, s.REV_YYMD rev_ymd, s.REV_NO rev_no,
                ISNULL(s.CST_REV_NO,'') cst_no, ISNULL(s.ECO_NO,'') eco, s.ITEM_CODE item_code, ISNULL(i.item_name,'') nm, ISNULL(s.REV_MARK,'') mark,
                ISNULL(s.REV_DESC,'') rdesc, ISNULL(s.ISSUE_YYMD,'') issue, ISNULL(s.DEPT_NAME,'') dept,
                ISNULL(s.CHARGE_NAME,'') charge, ISNULL(s.APPLY_YYMD,'') apply_ymd, ISNULL(s.APPLY_TYPE,'') atype,
                ISNULL(s.APPLY_STOCK,'') apply_stock, ISNULL(s.DRAWING_FILE,'') drawing, ISNULL(s.SPECS_FILE,'') specs,
                ISNULL(s.COST_CHANGE_FLAG,'') cost_f, ISNULL(s.LG_COST_CHANGE_FLAG,'') lg_cost_f, ISNULL(s.BOM_FLAG,'') bom_f, ISNULL(s.REMARKS,'') remarks
                FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV s LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.ITEM_CODE=s.ITEM_CODE WHERE {wl}""")
        if src in ("all", "nx"):
            parts.append(f"""SELECT 'nx' src, CAST(n.id AS NVARCHAR(20)) key_id, n.rev_ymd rev_ymd, n.rev_no rev_no,
                ISNULL(n.cst_rev_no,'') cst_no, ISNULL(n.eco_no,'') eco, n.item_code item_code, ISNULL(i2.item_name,'') nm, ISNULL(n.rev_mark,'') mark,
                ISNULL(n.rev_desc,'') rdesc, ISNULL(n.issue_ymd,'') issue, ISNULL(n.dept_name,'') dept, ISNULL(n.charge_name,'') charge,
                ISNULL(n.apply_ymd,'') apply_ymd, ISNULL(n.apply_type,'') atype, ISNULL(n.apply_stock,'') apply_stock,
                ISNULL(n.drawing_file,'') drawing, ISNULL(n.specs_file,'') specs, CAST(ISNULL(n.cost_change,0) AS NVARCHAR(4)) cost_f,
                CAST(ISNULL(n.lg_cost_change,0) AS NVARCHAR(4)) lg_cost_f, CAST(ISNULL(n.bom_change,0) AS NVARCHAR(4)) bom_f, ISNULL(n.remarks,'') remarks
                FROM PARTNER_ERP_TEST3.nx.qc_spec_rev n LEFT JOIN PARTNER_ERP_TEST3.nx.item i2 ON i2.ITEM_CODE=n.item_code WHERE {wn}""")
        sql = "SELECT TOP 3000 * FROM (\n" + "\nUNION ALL\n".join(parts) + "\n) q ORDER BY rev_ymd DESC, rev_no DESC"
        cur.execute(sql, *(p * len(parts)))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["cost_f"] = _b(r["cost_f"]); r["bom_f"] = _b(r["bom_f"]); r["lg_cost_f"] = _b(r["lg_cost_f"])
            r["ID"] = int(r["key_id"]) if r["src"] == "nx" and str(r["key_id"]).isdigit() else None
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.post("/api/qc/spec/save")
def qc_spec_save(payload: dict = Body(...)):
    p = payload
    def d8(x):
        d = ''.join(ch for ch in str(x or '') if ch.isdigit())
        return d if len(d) == 8 else (("20"+d) if len(d) == 6 else d)
    ymd = d8(p.get("rev_ymd"))
    item = str(p.get("item_code", "")).strip()[:40]
    if not ymd or not item:
        raise HTTPException(400, "시방변경일자·품번은 필수입니다.")
    def s(k, n): return str(p.get(k, "")).strip()[:n]
    try: rev_no = int(float(p.get("rev_no") or 0))
    except Exception: rev_no = 0
    vals = (ymd, rev_no, s("eco_no", 30), item, s("rev_mark", 10), s("rev_desc", 400),
            d8(p.get("issue_ymd")), s("dept_name", 40), s("charge_name", 40), d8(p.get("apply_ymd")),
            s("apply_type", 4), _b(p.get("cost_change")), _b(p.get("bom_change")), s("remarks", 200),
            (s("user", 40) or "웹사용자"))
    mid = p.get("id")
    nx = _nx(); cur = nx.cursor()
    try:
        if mid:
            cur.execute("""UPDATE nx.qc_spec_rev SET rev_ymd=?,rev_no=?,eco_no=?,item_code=?,rev_mark=?,rev_desc=?,
                issue_ymd=?,dept_name=?,charge_name=?,apply_ymd=?,apply_type=?,cost_change=?,bom_change=?,
                remarks=?,upd_user=?,upd_dt=getdate() WHERE id=?""", *vals, int(mid))
            return {"ok": True, "id": int(mid), "mode": "update"}
        cur.execute("""INSERT INTO nx.qc_spec_rev(rev_ymd,rev_no,eco_no,item_code,rev_mark,rev_desc,issue_ymd,
            dept_name,charge_name,apply_ymd,apply_type,cost_change,bom_change,remarks,upd_user)
            OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", *vals)
        return {"ok": True, "id": int(cur.fetchone()[0]), "mode": "insert"}
    finally:
        nx.close()

@router.post("/api/qc/spec/delete")
def qc_spec_delete(payload: dict = Body(...)):
    ids = [int(x) for x in (payload.get("ids", []) or []) if str(x).strip()]
    if not ids: return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"DELETE FROM nx.qc_spec_rev WHERE id IN ({','.join('?'*len(ids))})", *ids)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()

def _d8(x):
    d = ''.join(ch for ch in str(x or '') if ch.isdigit())
    return d if len(d) == 8 else (("20" + d) if len(d) == 6 else d)
@router.get("/api/qc/spec/apply")
def qc_spec_apply(rev_ymd: str = Query(...), rev_no: str = Query(...), item: str = Query(""), src: str = Query("legacy")):
    """시방 적용대상(우측 패널): 베이스→접미 확장 풀품번 + 최초입고/생산/출하일. src=legacy(QA_T_SPEC_REV_APPLY)/nx(nx.qc_spec_rev_apply)."""
    y = _d8(rev_ymd)
    try: no = int(float(rev_no or 0))
    except Exception: no = 0
    cn = _conn(); cur = cn.cursor()
    try:
        if src == "nx":
            cur.execute("""SELECT a.item_code item, ISNULL(i.item_name,'') nm, ISNULL(a.apply_flag,0) apply_flag,
                  ISNULL(a.input_ymd,'') input_ymd, ISNULL(a.prod_ymd,'') prod_ymd, ISNULL(a.output_ymd,'') output_ymd
                FROM PARTNER_ERP_TEST3.nx.qc_spec_rev_apply a LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.ITEM_CODE=a.item_code
                WHERE a.rev_ymd=? AND a.rev_no=? ORDER BY a.item_code""", y, no)
        else:
            cur.execute("""SELECT a.ITEM_CODE item, ISNULL(i.item_name,'') nm, ISNULL(a.APPLY_FLAG,'') apply_flag,
                  ISNULL(a.INPUT_YYMD,'') input_ymd, ISNULL(a.PROD_YYMD,'') prod_ymd, ISNULL(a.OUTPUT_YYMD,'') output_ymd
                FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV_APPLY a LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.ITEM_CODE=a.ITEM_CODE
                WHERE a.REV_YYMD=? AND a.REV_NO=? ORDER BY a.ITEM_CODE""", y, no)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows: r["apply_flag"] = _b(r["apply_flag"])
        if not rows and item.strip() and src != "nx":
            cur.execute("SELECT ISNULL(item_name,'') FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE=?", item.strip())
            g = cur.fetchone()
            rows = [{"item": item.strip(), "nm": (g[0] if g else ""), "apply_flag": 1,
                     "input_ymd": "", "prod_ymd": "", "output_ymd": ""}]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.post("/api/qc/spec/apply/save")
def qc_spec_apply_save(payload: dict = Body(...)):
    """nx 적용대상 품번 추가. items=[코드] 직접 또는 base+n1~n2 접미확장. nx.qc_spec_rev_apply."""
    p = payload
    y = _d8(p.get("rev_ymd"))
    try: no = int(float(p.get("rev_no") or 0))
    except Exception: no = 0
    if not y or not no:
        raise HTTPException(400, "시방(rev_ymd·rev_no)이 필요합니다.")
    items = [str(x).strip() for x in (p.get("items") or []) if str(x).strip()]
    base = str(p.get("base", "")).strip()
    if base:
        try: n1 = int(p.get("from") or 1); n2 = int(p.get("to") or 9)
        except Exception: n1, n2 = 1, 9
        items += [f"{base}{i:02d}" for i in range(n1, n2 + 1)]
    items = list(dict.fromkeys(items))[:300]
    if not items:
        raise HTTPException(400, "추가할 품번이 없습니다.")
    user = (str(p.get("user", "")).strip() or "웹사용자")[:40]
    nx = _nx(); cur = nx.cursor()
    try:
        added = 0
        for it in items:
            cur.execute("""IF NOT EXISTS(SELECT 1 FROM nx.qc_spec_rev_apply WHERE rev_ymd=? AND rev_no=? AND item_code=?)
                INSERT INTO nx.qc_spec_rev_apply(rev_ymd,rev_no,item_code,apply_flag,upd_user)
                VALUES(?,?,?,1,?)""", y, no, it, y, no, it, user)
            added += cur.rowcount
        return {"ok": True, "added": added, "items": items}
    finally:
        nx.close()

@router.post("/api/qc/spec/apply/delete")
def qc_spec_apply_delete(payload: dict = Body(...)):
    p = payload
    y = _d8(p.get("rev_ymd"))
    try: no = int(float(p.get("rev_no") or 0))
    except Exception: no = 0
    items = [str(x).strip() for x in (p.get("items") or []) if str(x).strip()]
    if not (y and no and items): return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        ph = ",".join("?" * len(items))
        cur.execute(f"DELETE FROM nx.qc_spec_rev_apply WHERE rev_ymd=? AND rev_no=? AND item_code IN ({ph})", y, no, *items)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()

# ---------- 수입검사(IQC) 조회 (QA_T_CUST_IQC_HEAD/DTL, 읽기전용 조회) ----------
@router.get("/api/qc/iqc/list")
def qc_iqc_list(from_ymd: str = Query(""), to_ymd: str = Query(""), item: str = Query(""), cust: str = Query("")):
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("h.OQC_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("h.OQC_YMD<=?"); p.append(_d6(to_ymd))
        if item.strip(): w.append("h.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if cust.strip(): w.append("h.CUST_CODE LIKE ?"); p.append(f"%{cust.strip()}%")
        cur.execute(f"""SELECT TOP 2000 h.OQC_YMD oqc_ymd, h.OQC_SEQ oqc_seq, h.ITEM_CODE item_code, ISNULL(i.item_name,'') nm,
            ISNULL(h.MAT_CODE,'') mat, ISNULL(h.CUST_CODE,'') cust, ISNULL(c.CUST_DESC,'') cust_nm,
            ISNULL(h.LINE,'') line, ISNULL(h.INSP_QTY,0) insp_qty, ISNULL(h.ERR_TEXT,'') err_text,
            ISNULL(h.RESULT_OK,0) ok
            FROM PARTNER_ERP_TEST3.nx.QA_T_CUST_IQC_HEAD h LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.ITEM_CODE=h.ITEM_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=h.CUST_CODE
            WHERE {' AND '.join(w)} ORDER BY h.OQC_YMD DESC, h.OQC_SEQ DESC""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["insp_qty"] = float(r["insp_qty"] or 0); r["ok"] = _b(r["ok"])
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.get("/api/qc/iqc/detail")
def qc_iqc_detail(ymd: str = Query(...), seq: str = Query(...)):
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT SPEC_SEQ, ISNULL(OQC_SPEC1,'') spec1, ISNULL(OQC_SPEC2,'') spec2,
            ISNULL(INSP_VAL1,'') v1, ISNULL(INSP_VAL2,'') v2, ISNULL(INSP_VAL3,'') v3,
            ISNULL(INSP_VAL4,'') v4, ISNULL(INSP_VAL5,'') v5, ISNULL(ERROR_QTY,0) err, ISNULL(RESULT_OK,0) ok
            FROM PARTNER_ERP_TEST3.nx.QA_T_CUST_IQC_DTL WHERE OQC_YMD=? AND OQC_SEQ=? ORDER BY SPEC_SEQ""", _d6(ymd), int(seq))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows: r["err"] = float(r["err"] or 0); r["ok"] = _b(r["ok"])
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()
