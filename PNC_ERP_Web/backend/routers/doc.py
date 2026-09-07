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
# ★로컬 개발 폴백(2026-08-26) — 지정 경로의 드라이브가 아예 없으면(개발 PC에 F: 없음)
#   레포 옆 _files 로 떨어뜨린다. 운영(F: 존재)에서는 아무 영향 없음.
#   ※환경변수 DOC_STORAGE_PATH 가 설정돼 있으면 폴백하지 않는다(명시 설정 우선).
#   ⚠2026-09-04 보강 — 종전엔 「환경변수가 있으면 무조건 그대로」였다. 그런데 운영에서
#     그 값이 **깨진 채로** 들어오면(콘솔 코드페이지/서비스 등록 시 CP949↔UTF-8 오독)
#     그대로 mkdir 을 시도해 업로드가 통째로 실패한다.
#     실측 2026-09-04(운영 184): 'D:\ERP\꿈(₩)' → WinError 123 (구문이 잘못된 경로).
#   ⟹ 환경변수라도 **쓸 수 있는 경로인지 검사**하고, 못 쓰면 폴백한다.
def _bad_path(p: str) -> bool:
    """윈도우에서 만들 수 없는 경로인가(깨진 문자·금지문자·없는 드라이브)."""
    if not p or not p.strip():
        return True
    try:
        # 드라이브 문자 뒤(경로 본문)에 윈도우 금지문자가 있으면 못 만든다
        _drv, _rest = _os.path.splitdrive(p)
        if any(ch in _rest for ch in '<>:"|?*') or any(ord(ch) < 32 for ch in _rest):
            return True
        # 인코딩이 깨져 왕복이 안 되는 문자열(U+FFFD 등)
        if "\ufffd" in p:
            return True
        if _drv and not _os.path.isdir(_drv + "\\"):
            return True
    except Exception:
        return True
    return False

_FALLBACK_DOC_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "_files")
if _bad_path(DOC_STORAGE_PATH):
    try:
        print(f"[doc] ⚠DOC_STORAGE_PATH 사용불가({DOC_STORAGE_PATH!r}) → 폴백 {_FALLBACK_DOC_DIR}")
    except Exception:
        pass
    DOC_STORAGE_PATH = _FALLBACK_DOC_DIR
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
        # ★도면만 — 품질불량 첨부(QC_ERROR)·시방서(SPEC_SHEET)는 여기 나오지 않는다(2026-09-07).
        #   ① QC_ERROR — 「설계도면조회」에 품질불량관리에서 올린 카톡 사진·md 가 섞여 나왔다
        #      (실측 10건). doc_kind 필터가 아예 없었고, _DOC_KIND 에도 없어 코드가 그대로 노출됐다.
        #   ② SPEC_SHEET — 시방서는 **품목시방 탭**(itemspec_list)이 보여준다.
        #      양쪽에 다 넣었더니 같은 파일이 두 탭에 중복으로 나왔다(사용자 신고).
        #      이 화면은 레거시 w_pr_master_200 = 도면 조회 자리이므로 도면만 남긴다.
        _KINDS = ("GENERAL_DWG", "SPEC_DWG")
        _kph = ",".join("?" * len(_KINDS))
        if item:
            ncur.execute(f"""SELECT doc_id,doc_kind,orig_filename,ext,byte_size,insert_user,insert_dt,rev_yymd,rev_no
                FROM nx.doc WHERE del_flag=0 AND doc_kind IN ({_kph})
                  AND (item_code=? OR orig_filename LIKE ?) ORDER BY insert_dt DESC""", *_KINDS, item, like)
        else:
            ncur.execute(f"""SELECT doc_id,doc_kind,orig_filename,ext,byte_size,insert_user,insert_dt,rev_yymd,rev_no
                FROM nx.doc WHERE del_flag=0 AND doc_kind IN ({_kph}) ORDER BY insert_dt DESC""", *_KINDS)
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
    # ★바로보기(2026-09-04) — 텍스트류는 guess_type 이 못 알아보는 확장자가 많다(.md/.log/.csv…).
    #   octet-stream 으로 나가면 브라우저가 무조건 다운로드해서 미리보기가 안 된다.
    #   inline 요청일 때만 text/plain 으로 보정한다(다운로드 동작은 건드리지 않는다).
    if cd == "inline" and mime == "application/octet-stream":
        if (fname.rsplit(".", 1)[-1] if "." in fname else "").lower() in (
                "md", "txt", "log", "csv", "json", "xml", "ini", "sql", "yml", "yaml"):
            mime = "text/plain; charset=utf-8"
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f"{cd}; filename*=UTF-8''{_urlquote(fname)}"})

@router.post("/api/doc/upload")
async def doc_upload(file: UploadFile = File(...), doc_kind: str = Form("GENERAL_DWG"),
                     item_code: str = Form(""), rev_yymd: str = Form(""), rev_no: str = Form(""),
                     rev_ymd: str = Form(""),
                     user: str = Form("웹사용자")):
    """업로드: NAS경로(DOC_STORAGE_PATH) 저장 + nx.doc 메타. sha256 중복검사.

    ★rev_ymd / rev_yymd 를 **둘 다** 받는다(2026-09-07 교정).
      실사용 오류 — 시방변경관리에서 올린 도면·시방서가 그 시방 건에 연결되지 않았다.
      업로드는 200 으로 성공하고 파일도 저장되는데 조회하면 0건이었고, 에러도 안 났다.
      원인 = **파라미터 이름이 한 글자 달랐다.**
        · 서버(여기)          rev_yymd   ← y 두 개(DB 컬럼명과 동일)
        · 화면(screens.qc.js) rev_ymd    ← y 하나
        · 품질팀 RPA          rev_ymd
      FastAPI 는 못 받은 Form 을 기본값('')으로 채우므로 조용히 NULL 이 저장됐다.
      rev_no 는 이름이 같아 정상 저장돼, "번호는 있는데 일자만 NULL" 인 상태가 됐다.
      (실측 doc_id 13~22 전건 rev_yymd=NULL · rev_no=9907)
      ⟹ 호출자를 고치지 않고 서버가 두 이름을 모두 받는다 — 이미 배포된 RPA 도 함께 산다.
    """
    rev_yymd = (rev_yymd or "").strip() or (rev_ymd or "").strip()
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
    """삭제 — nx.doc 의 일반도면·시방도면·시방서. 레거시 BLOB 첨부는 대상 아님.

    ★2026-09-07 — 시방도면/시방서도 지울 수 있게 한다.
      종전엔 GENERAL_DWG 만 허용하고 "시방도면은 시방변경관리에서 삭제하세요" 로 거부했는데,
      정작 **시방변경관리 화면이 이 API 를 부른다**(screens.qc.js:520, editable=true 로 ✖ 버튼 표시).
      즉 안내대로 그 화면에 가도 같은 곳으로 돌아와 거부되는 자기모순이었고,
      프론트가 응답의 ok 를 안 보고 목록만 새로고침해 **실패가 조용히 묻혔다**.
      ⟹ 잘못 올린 파일을 지울 방법이 없어 고아 파일이 계속 쌓였다(실측 doc_id 13~22).
      레거시 BLOB(src='spec')은 여기로 오지 않으므로 영향 없다.
    """
    did = payload.get("doc_id")
    if not did: return {"ok": False, "errors": ["doc_id 필요"]}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT doc_kind, storage_uri FROM nx.doc WHERE doc_id=? AND del_flag=0", int(did))
        r = cur.fetchone()
        if not r: return {"ok": False, "errors": ["문서 없음"]}
        if r[0] not in ("GENERAL_DWG", "SPEC_DWG", "SPEC_SHEET"):
            return {"ok": False, "errors": [f"이 종류({r[0]})는 여기서 삭제할 수 없습니다."]}
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
        # ★시방변경관리에서 올린 시방서(SPEC_SHEET)도 함께 보인다(2026-09-07).
        #   이 화면은 「품목시방관리」 — 그 품번의 시방 문서를 모아 보는 자리인데,
        #   종전엔 ITEM_ATTACH 만 읽어 시방변경관리 첨부가 안 나왔다(사용자 신고).
        #   ※도면(SPEC_DWG)은 여기 대상이 아니다 — 설계도면 탭에서 본다.
        if item:
            ncur.execute("""SELECT doc_id,orig_filename,ext,byte_size,insert_user,insert_dt,ISNULL(file_tag,''),doc_kind
                FROM nx.doc WHERE del_flag=0 AND doc_kind IN ('ITEM_ATTACH','SPEC_SHEET')
                  AND item_code=? ORDER BY insert_dt DESC""", item)
        else:
            ncur.execute("""SELECT doc_id,orig_filename,ext,byte_size,insert_user,insert_dt,ISNULL(file_tag,''),doc_kind
                FROM nx.doc WHERE del_flag=0 AND doc_kind IN ('ITEM_ATTACH','SPEC_SHEET')
                ORDER BY insert_dt DESC""")
        for r in ncur.fetchall():
            _sp = (r[7] == 'SPEC_SHEET')
            rows.append({"src": "doc", "key": str(r[0]), "atype": r[6],
                         "atype_nm": ("시방서" if _sp else "신규첨부"),
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
    # ★키가 온전할 때만 조회한다(2026-09-07 교정).
    #   종전엔 rn 이 숫자가 아니면 rev_no 에 **None(=SQL NULL)** 을 바인딩했다.
    #   SQL 3값 논리에서 `rev_no = NULL` 은 UNKNOWN 이라 **항상 0건**이다(IS NULL 이 아니다).
    #   레거시 블록(위 L306)은 이미 `if ry and rn.isdigit()` 로 막고 있었는데 여기만 빠져 있었다.
    if ry and rn.isdigit():
        nx = _nx(); cur = nx.cursor()
        try:
            cur.execute("""SELECT doc_id, doc_kind, orig_filename, byte_size FROM nx.doc
                WHERE del_flag=0 AND doc_kind IN ('SPEC_DWG','SPEC_SHEET') AND rev_yymd=? AND rev_no=?""",
                ry, int(rn))
            for r in cur.fetchall():
                out.append({"kind": ("도면" if r[1] == 'SPEC_DWG' else "시방서"), "src": "doc", "key": str(r[0]),
                            "filename": r[2], "size": int(r[3] or 0), "editable": True})
        finally: nx.close()
    return {"rows": out, "cnt": len(out)}
