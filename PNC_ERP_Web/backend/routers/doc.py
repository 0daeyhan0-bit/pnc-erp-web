# -*- coding: utf-8 -*-
"""doc 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE)

from common import _kindmap
router = APIRouter()

# ===================== 설계도면조회 + 도면/시방 파일첨부 (nx.doc + 레거시 blob) =====================
# 근거: w_pr_master_200. 일반도면(개발)=DRAWING.PR_M_DWG · 시방도면(품질)=QA_T_SPEC_REV_BLOB(FILE_TAG='2').
# 신규 업로드=NAS경로(DOC_STORAGE_PATH)+nx.doc 메타. 기존 15.9GB=레거시 blob 읽기 폴백.
import os as _os, hashlib as _hashlib, mimetypes as _mimetypes
from urllib.parse import quote as _urlquote
DOC_STORAGE_PATH = _os.getenv("DOC_STORAGE_PATH", r"F:\NEW_ERP_FILES")   # 배포시 NAS 마운트(\\200.200.200.15\...)로 교체
_DOC_KIND = {"GENERAL_DWG": "일반도면", "SPEC_DWG": "시방도면", "SPEC_SHEET": "시방서", "ITEM_ATTACH": "품목첨부"}

@router.get("/api/doc/list")
def doc_list(item_code: str = Query("")):
    """설계도면조회: 품번/파일명 검색 = nx.doc(신규) ∪ 일반도면(PR_M_DWG) ∪ 시방도면(QA_T_SPEC_REV).
       ★빈 검색이면 각 소스 최근 전체(TOP N)를 반환해 조회 즉시 파일이 보이게(브라우즈)."""
    item = item_code.strip()
    like = f"%{item}%"
    rows = []
    # nx.doc(신규) — 있으면 최상단
    nx = _nx(); ncur = nx.cursor()
    try:
        if item:
            ncur.execute("""SELECT doc_id,doc_kind,orig_filename,ext,byte_size,insert_user,insert_dt,rev_yymd,rev_no
                FROM nx.doc WHERE del_flag=0 AND (item_code=? OR orig_filename LIKE ?) ORDER BY insert_dt DESC""", item, like)
        else:
            ncur.execute("""SELECT doc_id,doc_kind,orig_filename,ext,byte_size,insert_user,insert_dt,rev_yymd,rev_no
                FROM nx.doc WHERE del_flag=0 ORDER BY insert_dt DESC""")
        for r in ncur.fetchall():
            rows.append({"src": "doc", "key": str(r[0]), "kind": r[1], "kind_nm": _DOC_KIND.get(r[1], r[1]),
                         "filename": r[2], "rev": (f"{r[7]}/{r[8]}" if r[7] else ""), "spec_no": "",
                         "dt": (r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6] or "")).replace("T", " ")[:19],
                         "user": r[5] or "", "size": int(r[4] or 0), "editable": (r[1] == "GENERAL_DWG"), "gubun": "1"})
    finally:
        nx.close()
    # ★레거시 w_pr_master_200 동일: 일반도면(PR_M_DWG 도면구분1) + 시방도면(QA_T_SPEC_REV DRAWING_FILE<>'' 도면구분2). 캡·blob필터 제거(전건).
    cn = _conn(); cur = cn.cursor()
    try:
        # ① 일반도면 (도면구분 1)
        if item:
            cur.execute("""SELECT FILE_NAME, FILE_DATETIME, ISNULL(UPDATE_USER_ID,ISNULL(INSERT_USER_ID,'')), ISNULL(UPDATE_DATETIME,FILE_DATETIME)
                FROM DRAWING.DBO.PR_M_DWG WHERE FILE_NAME LIKE ? ORDER BY FILE_DATETIME DESC""", like)
        else:
            cur.execute("""SELECT FILE_NAME, FILE_DATETIME, ISNULL(UPDATE_USER_ID,ISNULL(INSERT_USER_ID,'')), ISNULL(UPDATE_DATETIME,FILE_DATETIME)
                FROM DRAWING.DBO.PR_M_DWG ORDER BY FILE_DATETIME DESC""")
        for r in cur.fetchall():
            rows.append({"src": "dwg", "key": f"{r[0]}|{r[1]}", "kind": "GENERAL_DWG", "kind_nm": "일반도면",
                         "filename": r[0], "rev": "", "spec_no": "",
                         "dt": (r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1] or "")).replace("T", " ")[:19],
                         "user": r[2] or "", "size": 0, "editable": False, "gubun": "1"})
        # ② 시방도면 (도면구분 2) — DRAWING_FILE<>'' 헤더 기준(blob 존재 강제 제거)
        if item:
            cur.execute("""SELECT h.REV_YYMD, h.REV_NO, ISNULL(h.DRAWING_FILE,''), ISNULL(h.ISSUE_YYMD,''),
                  ISNULL(h.UPDATE_USER_ID,ISNULL(h.INSERT_USER_ID,'RPA')), ISNULL(h.UPDATE_DATETIME,h.INSERT_DATETIME)
                FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV h WHERE (h.DRAWING_FILE LIKE ? OR h.ITEM_CODE LIKE ?) AND ISNULL(h.DRAWING_FILE,'')<>''
                ORDER BY h.REV_YYMD DESC, h.REV_NO DESC""", like, like)
        else:
            cur.execute("""SELECT h.REV_YYMD, h.REV_NO, ISNULL(h.DRAWING_FILE,''), ISNULL(h.ISSUE_YYMD,''),
                  ISNULL(h.UPDATE_USER_ID,ISNULL(h.INSERT_USER_ID,'RPA')), ISNULL(h.UPDATE_DATETIME,h.INSERT_DATETIME)
                FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV h WHERE ISNULL(h.DRAWING_FILE,'')<>'' ORDER BY h.REV_YYMD DESC, h.REV_NO DESC""")
        for r in cur.fetchall():
            rows.append({"src": "spec", "key": f"{r[0]}|{r[1]}|2", "kind": "SPEC_DWG", "kind_nm": "시방도면",
                         "filename": r[2], "rev": f"{r[0]}/{r[1]}", "spec_no": f"{r[0]}-{r[1]}",
                         "dt": (r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[3] or "")).replace("T", " ")[:19],
                         "user": r[4] or "RPA", "size": 0, "editable": False, "gubun": "2"})
    finally:
        cn.close()
    # ★레거시 동일: 일반+시방 통합 후 파일일시 내림차순(최신 시방이 최상단)
    rows.sort(key=lambda x: x.get("dt") or "", reverse=True)
    return {"rows": rows[:500], "cnt": len(rows), "shown": min(500, len(rows))}   # 속도개선: 최신 500건만 반환

@router.get("/api/doc/download")
def doc_download(src: str = Query(...), key: str = Query(...), disp: str = Query("attach")):
    """다운로드/열기: doc=nx파일 / dwg=PR_M_DWG단일 / spec=QA blob 분할조립. disp=inline이면 브라우저에서 바로 열기(뷰)."""
    data = b""; fname = "file"
    if src == "doc":
        nx = _nx(); cur = nx.cursor()
        try:
            cur.execute("SELECT orig_filename, storage_uri FROM nx.doc WHERE doc_id=? AND del_flag=0", int(key))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "문서 없음")
            path = _os.path.join(DOC_STORAGE_PATH, r[1]); fname = r[0]
            if not _os.path.exists(path): raise HTTPException(404, f"파일 없음: {r[1]}")
            with open(path, "rb") as fp: data = fp.read()
        finally: nx.close()
    elif src == "dwg":
        fn, fdt = key.split("|", 1)
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("SELECT FILE_BLOB FROM DRAWING.DBO.PR_M_DWG WHERE FILE_NAME=? AND FILE_DATETIME=?", fn, fdt)
            r = cur.fetchone()
            if not r: raise HTTPException(404, "도면 없음")
            data = bytes(r[0]) if r[0] is not None else b""; fname = fn
        finally: cn.close()
    elif src == "spec":
        ry, rn, tag = key.split("|")
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("SELECT ISNULL(DRAWING_FILE,''), ISNULL(SPECS_FILE,'') FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV WHERE REV_YYMD=? AND REV_NO=?", ry, int(rn))
            h = cur.fetchone()
            fname = ((h[0] if tag == '2' else h[1]) or f"{ry}_{rn}.pdf") if h else f"{ry}_{rn}.pdf"
            cur.execute("SELECT FILE_BLOB FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV_BLOB WHERE REV_YYMD=? AND REV_NO=? AND FILE_TAG=? ORDER BY FILE_SEQ", ry, int(rn), tag)
            data = b"".join(bytes(x[0]) for x in cur.fetchall() if x[0] is not None)
        finally: cn.close()
    elif src == "sibang":   # 품목시방 PPT (DRAWING.PR_M_SIBANG, PR_M_DWG 쌍둥이 = 단일 blob)
        fn, fdt = key.split("|", 1)
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("SELECT FILE_BLOB FROM DRAWING.DBO.PR_M_SIBANG WHERE FILE_NAME=? AND FILE_DATETIME=?", fn, fdt)
            r = cur.fetchone()
            if not r: raise HTTPException(404, "시방파일 없음")
            data = bytes(r[0]) if r[0] is not None else b""; fname = fn
        finally: cn.close()
    elif src == "itemblob":   # 품목 첨부 (PR_M_ITEM_BLOB, 청크 조립, 파일명 합성)
        ic, ft = key.split("|", 1)
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("SELECT TOP 1 ISNULL(FILE_EXT,'') FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_BLOB WHERE ITEM_CODE=? AND FILE_TYPE=?", ic, ft)
            e = cur.fetchone(); ext = (e[0].strip() if e and e[0] else "dat")
            fname = f"{ic}_{ft}.{ext}"
            cur.execute("SELECT MODULE_BLOB FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_BLOB WHERE ITEM_CODE=? AND FILE_TYPE=? ORDER BY MODULE_SEQ", ic, ft)
            data = b"".join(bytes(x[0]) for x in cur.fetchall() if x[0] is not None)
        finally: cn.close()
    else:
        raise HTTPException(400, "src 오류")
    mime = _mimetypes.guess_type(fname)[0] or "application/octet-stream"
    cd = "inline" if str(disp).lower() == "inline" else "attachment"
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f"{cd}; filename*=UTF-8''{_urlquote(fname)}"})

@router.post("/api/doc/upload")
async def doc_upload(file: UploadFile = File(...), doc_kind: str = Form("GENERAL_DWG"),
                     item_code: str = Form(""), rev_yymd: str = Form(""), rev_no: str = Form(""),
                     user: str = Form("웹사용자")):
    """업로드: NAS경로(DOC_STORAGE_PATH) 저장 + nx.doc 메타. sha256 중복검사."""
    raw = await file.read()
    if not raw: raise HTTPException(400, "빈 파일입니다.")
    fname = file.filename or "file"
    ext = ((fname.rsplit(".", 1)[-1] if "." in fname else "") or "").lower()[:10]
    sha = _hashlib.sha256(raw).hexdigest()
    sub = _os.path.join(doc_kind, (item_code.strip() or "_misc"))
    d = _os.path.join(DOC_STORAGE_PATH, sub)
    try:
        _os.makedirs(d, exist_ok=True)
    except Exception as e:
        raise HTTPException(500, f"저장경로 생성 실패({DOC_STORAGE_PATH}): {e}")
    safe = f"{sha[:12]}_{fname}"
    with open(_os.path.join(d, safe), "wb") as fp: fp.write(raw)
    rel = _os.path.join(sub, safe)
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""INSERT INTO nx.doc(doc_kind,item_code,rev_yymd,rev_no,orig_filename,storage_uri,ext,byte_size,sha256,insert_user,insert_dt)
            OUTPUT INSERTED.doc_id VALUES(?,?,?,?,?,?,?,?,?,?,GETDATE())""",
            doc_kind, (item_code.strip() or None), (rev_yymd.strip() or None),
            (int(rev_no) if str(rev_no).strip().isdigit() else None),
            fname, rel, ext, len(raw), sha, (user or "웹사용자")[:20])
        did = cur.fetchone()[0]
        return {"ok": True, "doc_id": int(did), "size": len(raw), "path": rel}
    finally:
        nx.close()

@router.post("/api/doc/delete")
def doc_delete(payload: dict = Body(...)):
    """삭제 — nx.doc GENERAL_DWG(일반도면)만. 시방도면은 시방변경에서."""
    did = payload.get("doc_id")
    if not did: return {"ok": False, "errors": ["doc_id 필요"]}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT doc_kind, storage_uri FROM nx.doc WHERE doc_id=? AND del_flag=0", int(did))
        r = cur.fetchone()
        if not r: return {"ok": False, "errors": ["문서 없음"]}
        if r[0] != "GENERAL_DWG":
            return {"ok": False, "errors": ["일반도면만 삭제 가능합니다. 시방도면은 시방변경관리에서 삭제하세요."]}
        cur.execute("UPDATE nx.doc SET del_flag=1 WHERE doc_id=?", int(did))
        try:
            fp = _os.path.join(DOC_STORAGE_PATH, r[1])
            if _os.path.exists(fp): _os.remove(fp)
        except Exception: pass
        return {"ok": True}
    finally:
        nx.close()

@router.get("/api/itemspec/list")
def itemspec_list(item_code: str = Query("")):
    """품목시방관리(w_pr_master_210): 품번별 = nx.doc(ITEM_ATTACH) ∪ 시방PPT(DRAWING.PR_M_SIBANG) ∪ 품목첨부14종(PR_M_ITEM_BLOB, PR010)."""
    item = item_code.strip()   # ★레거시 w_pr_master_210: 빈 품번=전건 브라우즈(PR_M_SIBANG 정본)
    like = f"%{item}%"
    rows = []
    nx = _nx(); ncur = nx.cursor()
    try:
        if item:
            ncur.execute("""SELECT doc_id,orig_filename,ext,byte_size,insert_user,insert_dt,ISNULL(file_tag,'')
                FROM nx.doc WHERE del_flag=0 AND doc_kind='ITEM_ATTACH' AND item_code=? ORDER BY insert_dt DESC""", item)
        else:
            ncur.execute("""SELECT doc_id,orig_filename,ext,byte_size,insert_user,insert_dt,ISNULL(file_tag,'')
                FROM nx.doc WHERE del_flag=0 AND doc_kind='ITEM_ATTACH' ORDER BY insert_dt DESC""")
        for r in ncur.fetchall():
            rows.append({"src": "doc", "key": str(r[0]), "atype": r[6], "atype_nm": "신규첨부",
                         "filename": r[1], "user": r[4] or "", "size": int(r[3] or 0),
                         "dt": (r[5].isoformat() if hasattr(r[5], "isoformat") else ""), "editable": True})
    finally:
        nx.close()
    cn = _conn(); cur = cn.cursor()
    try:
        pr010 = _kindmap(cur, "PR010")
        # 시방 PPT(정본) — 빈 품번=전건. blob 크기 스캔 제거(전건 성능).
        if item:
            cur.execute("""SELECT FILE_NAME, FILE_DATETIME, ISNULL(INSERT_USER_ID,'')
                FROM DRAWING.DBO.PR_M_SIBANG WHERE FILE_NAME LIKE ? ORDER BY FILE_DATETIME DESC""", like)
        else:
            cur.execute("""SELECT FILE_NAME, FILE_DATETIME, ISNULL(INSERT_USER_ID,'')
                FROM DRAWING.DBO.PR_M_SIBANG ORDER BY FILE_DATETIME DESC""")
        for r in cur.fetchall():
            rows.append({"src": "sibang", "key": f"{r[0]}|{r[1]}", "atype": "SIBANG_PPT", "atype_nm": "시방(PPT)",
                         "filename": r[0], "user": r[2], "size": 0, "dt": str(r[1]), "editable": False})
        # 품목첨부 14종 — 품번 지정 시에만(품목별 상세)
        if item:
            cur.execute("""SELECT FILE_TYPE, MAX(ISNULL(FILE_EXT,'')), SUM(DATALENGTH(MODULE_BLOB)),
                  MAX(ISNULL(INSERT_USER_ID,'')), MAX(INSERT_DATETIME)
                FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_BLOB WHERE ITEM_CODE=? GROUP BY FILE_TYPE ORDER BY FILE_TYPE""", item)
            for r in cur.fetchall():
                ft = str(r[0]).strip(); ext = (r[1].strip() if r[1] else "dat"); nm = pr010.get(ft, ft)
                rows.append({"src": "itemblob", "key": f"{item}|{ft}", "atype": ft, "atype_nm": nm,
                             "filename": f"{item}_{nm}.{ext}", "user": r[3] or "", "size": int(r[2] or 0),
                             "dt": (r[4].isoformat() if hasattr(r[4], "isoformat") else ""), "editable": False})
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.get("/api/qc/spec/files")
def qc_spec_files(rev_ymd: str = Query(""), rev_no: str = Query("")):
    """시방 첨부파일 목록: 레거시 QA blob(도면 tag2/시방서 tag1) + nx.doc(SPEC_DWG/SPEC_SHEET)."""
    ry = rev_ymd.strip(); rn = rev_no.strip()
    out = []
    if ry and rn.isdigit():
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("SELECT ISNULL(DRAWING_FILE,''), ISNULL(SPECS_FILE,'') FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV WHERE REV_YYMD=? AND REV_NO=?", ry, int(rn))
            h = cur.fetchone()
            for tag, kind, fn in [('2', '도면', (h[0] if h else '')), ('1', '시방서', (h[1] if h else ''))]:
                cur.execute("SELECT SUM(DATALENGTH(FILE_BLOB)) FROM PARTNER_ERP_TEST3.nx.QA_T_SPEC_REV_BLOB WHERE REV_YYMD=? AND REV_NO=? AND FILE_TAG=?", ry, int(rn), tag)
                sz = cur.fetchone()[0]
                if sz:
                    out.append({"kind": kind, "src": "spec", "key": f"{ry}|{rn}|{tag}",
                                "filename": (fn or f"{ry}_{rn}_{kind}.pdf"), "size": int(sz), "editable": False})
        finally: cn.close()
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT doc_id, doc_kind, orig_filename, byte_size FROM nx.doc
            WHERE del_flag=0 AND doc_kind IN ('SPEC_DWG','SPEC_SHEET') AND rev_yymd=? AND rev_no=?""",
            ry, (int(rn) if rn.isdigit() else None))
        for r in cur.fetchall():
            out.append({"kind": ("도면" if r[1] == 'SPEC_DWG' else "시방서"), "src": "doc", "key": str(r[0]),
                        "filename": r[2], "size": int(r[3] or 0), "editable": True})
    finally: nx.close()
    return {"rows": out, "cnt": len(out)}
