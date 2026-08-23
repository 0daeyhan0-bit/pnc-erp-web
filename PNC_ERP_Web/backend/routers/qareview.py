# -*- coding: utf-8 -*-
"""qareview 도메인 라우터 — 품질 반성회일지 (w_pr_input_590 조회 + w_pr_input_595 등록/수정).

★레거시 원천(2026-08-23, dw 조회쿼리 3종 실물 확보)
  · 목록  dw_pr_input_590_l01 : PR_T_DAILY_ISSUE_REVIEW, ISSUE_YMD between
  · 상세  dw_pr_input_590_p   : ISSUE_SEQ 단건 + 가공공정명 + 작성자명(CM_M_USERS_INFO)
  · 첨부  dw_pr_input_590_l03 : PR_T_DAILY_ISSUE_REVIEW_FILE

★조회 = 라이브(PARTNER_ERP) + nx(웹 등록분) 합산 / 쓰기 = nx 만 (§1 절대규칙)
  ISSUE_SEQ 는 라이브와 겹치지 않게 nx 전용 대역(9000000+)에서 채번한다.

★레거시 버그 미복제(§7): 상세쿼리의 가공공정명 조인이
    (SELECT GAGONG_PROC_DESC FROM PR_M_PROC_GAGONG WHERE WORK_CODE = A.GAGONG_PROC_CODE)
  인데 저장값은 공정코드(S1·S4·S6…)라 항상 '전체'만 나온다. 웹은 GAGONG_PROC_CODE 로 조인해
  '03라인' 처럼 제대로 표시한다.
"""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException

from common import _conn, _nx, _d6

router = APIRouter()

LIVE = "PARTNER_ERP.dbo"
NXS = "PARTNER_ERP_TEST3.nx"
NX_SEQ_BASE = 9000000     # nx 채번 시작 — 라이브 SEQ(현재 995)와 절대 겹치지 않게


def _f(v):
    try: return float(v or 0)
    except Exception: return 0.0


def _i(v):
    try: return int(float(v or 0))
    except Exception: return 0


def _row(r, cols):
    g = dict(zip(cols, r))
    return g


@router.get("/api/qareview/opts")
def qareview_opts():
    """구분(가공공정) 드롭다운 — 레거시 화면의 '구 분' 콤보. '전체'(%) 포함."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""SELECT GAGONG_PROC_CODE, GAGONG_PROC_DESC
              FROM {LIVE}.PR_M_PROC_GAGONG
             WHERE ISNULL(GAGONG_PROC_CODE,'')<>''
             ORDER BY SORT_KEY, GAGONG_PROC_CODE""")
        procs = [{"code": "%", "nm": "전체"}]
        for r in cur.fetchall():
            procs.append({"code": r[0], "nm": r[1] or r[0]})
        return {"procs": procs}
    finally:
        cn.close()


@router.get("/api/qareview/list")
def qareview_list(from_ymd: str = Query(""), to_ymd: str = Query(""),
                  q: str = Query(""), limit: int = Query(1000)):
    """좌측 목록(dw_pr_input_590_l01) — 라이브 + nx 합산."""
    d6a = _d6(from_ymd) if from_ymd else ""
    d6b = _d6(to_ymd) if to_ymd else ""
    w = ["1=1"]; p = []
    if d6a: w.append("A.ISSUE_YMD>=?"); p.append(d6a)
    if d6b: w.append("A.ISSUE_YMD<=?"); p.append(d6b)
    kw = q.strip()
    if kw:
        w.append("(A.WRITE_USER_ID LIKE ? OR A.PLACE_DESC LIKE ? OR A.TARGET_DESC LIKE ?)")
        p += [f"%{kw}%"] * 3
    wsql = " AND ".join(w)
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""SELECT TOP {max(1, min(int(limit), 5000))}
              u.ISSUE_SEQ, u.ISSUE_YMD, u.ISSUE_HHMM, u.WRITE_USER_ID, u.PLACE_DESC, u.TARGET_DESC,
              u.TODAY_PROC_TARGET_QTY, u.TODAY_PROC_RESULT_QTY, u.TODAY_QA_TARGET_PPM, u.TODAY_QA_RESULT_PPM,
              u.TODAY_ERROR_QTY, u.TODAY_INWON, u.TODAY_HOLIDAY_INWON, u.TODAY_ATTEND_INWON,
              u.GAGONG_PROC_CODE, u.UPDATE_USER_ID, u.UPDATE_DATETIME, u.SRC
            FROM (
              SELECT A.ISSUE_SEQ,A.ISSUE_YMD,A.ISSUE_HHMM,A.WRITE_USER_ID,A.PLACE_DESC,A.TARGET_DESC,
                     A.TODAY_PROC_TARGET_QTY,A.TODAY_PROC_RESULT_QTY,A.TODAY_QA_TARGET_PPM,A.TODAY_QA_RESULT_PPM,
                     A.TODAY_ERROR_QTY,A.TODAY_INWON,A.TODAY_HOLIDAY_INWON,A.TODAY_ATTEND_INWON,
                     A.GAGONG_PROC_CODE,A.UPDATE_USER_ID,A.UPDATE_DATETIME,'라이브' SRC
                FROM {LIVE}.PR_T_DAILY_ISSUE_REVIEW A WITH(NOLOCK) WHERE {wsql}
              UNION ALL
              SELECT A.ISSUE_SEQ,A.ISSUE_YMD,A.ISSUE_HHMM,A.WRITE_USER_ID,A.PLACE_DESC,A.TARGET_DESC,
                     A.TODAY_PROC_TARGET_QTY,A.TODAY_PROC_RESULT_QTY,A.TODAY_QA_TARGET_PPM,A.TODAY_QA_RESULT_PPM,
                     A.TODAY_ERROR_QTY,A.TODAY_INWON,A.TODAY_HOLIDAY_INWON,A.TODAY_ATTEND_INWON,
                     A.GAGONG_PROC_CODE,A.UPDATE_USER_ID,A.UPDATE_DATETIME,'nx' SRC
                FROM {NXS}.PR_T_DAILY_ISSUE_REVIEW A WITH(NOLOCK) WHERE {wsql}
            ) u
            ORDER BY u.ISSUE_YMD DESC, u.ISSUE_HHMM DESC, u.ISSUE_SEQ DESC""", *(p + p))
        rows = []
        for r in cur.fetchall():
            rows.append({
                "seq": _i(r[0]), "ymd": r[1] or "", "hhmm": r[2] or "",
                "writer": r[3] or "", "place": r[4] or "", "target": r[5] or "",
                "t_target": _f(r[6]), "t_result": _f(r[7]),
                "ppm_target": _f(r[8]), "ppm_result": _f(r[9]),
                "err": _f(r[10]), "inwon": _f(r[11]), "holiday": _f(r[12]), "attend": _f(r[13]),
                "proc": r[14] or "", "upd_user": r[15] or "", "upd_dt": str(r[16] or "")[:19],
                "src": r[17]})
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()


@router.get("/api/qareview/detail")
def qareview_detail(seq: int = Query(...)):
    """우측 상세(dw_pr_input_590_p) + 첨부목록(dw_pr_input_590_l03)."""
    src = f"{NXS}" if seq >= NX_SEQ_BASE else f"{LIVE}"
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""SELECT A.ISSUE_SEQ,A.ISSUE_YMD,A.ISSUE_HHMM,A.WRITE_USER_ID,A.PLACE_DESC,A.TARGET_DESC,
              A.TODAY_PROC_TARGET_QTY,A.TODAY_PROC_RESULT_QTY,A.TODAY_QA_TARGET_PPM,A.TODAY_QA_RESULT_PPM,
              A.TODAY_ERROR_QTY,A.TODAY_INWON,A.TODAY_HOLIDAY_INWON,A.TODAY_ATTEND_INWON,
              A.QA_ISSUE_DESC,A.RTN_ERROR_DESC,
              A.CONTENTS_01_DESC,A.CONTENTS_02_DESC,A.CONTENTS_03_DESC,A.CONTENTS_04_DESC,
              A.GAGONG_PROC_CODE,
              -- ★레거시는 WORK_CODE 로 조인해 항상 '전체'가 나오는 버그. 웹은 코드로 조인(§7 버그 미복제)
              ISNULL((SELECT TOP 1 GAGONG_PROC_DESC FROM {LIVE}.PR_M_PROC_GAGONG WITH(NOLOCK)
                       WHERE GAGONG_PROC_CODE=A.GAGONG_PROC_CODE),'전체') proc_nm,
              ISNULL((SELECT TOP 1 USER_NAME FROM {LIVE}.CM_M_USERS_INFO WITH(NOLOCK)
                       WHERE USER_ID=A.WRITE_USER_ID),'') user_name,
              A.INSERT_USER_ID,A.INSERT_DATETIME,A.UPDATE_USER_ID,A.UPDATE_DATETIME
            FROM {src}.PR_T_DAILY_ISSUE_REVIEW A WITH(NOLOCK) WHERE A.ISSUE_SEQ=?""", seq)
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "해당 일지를 찾을 수 없습니다.")
        d = {"seq": _i(r[0]), "ymd": r[1] or "", "hhmm": r[2] or "", "writer": r[3] or "",
             "place": r[4] or "", "target": r[5] or "",
             "t_target": _f(r[6]), "t_result": _f(r[7]),
             "ppm_target": _f(r[8]), "ppm_result": _f(r[9]),
             "err": _f(r[10]), "inwon": _f(r[11]), "holiday": _f(r[12]), "attend": _f(r[13]),
             "qa_issue": r[14] or "", "rtn_err": r[15] or "",
             "c1": r[16] or "", "c2": r[17] or "", "c3": r[18] or "", "c4": r[19] or "",
             "proc": r[20] or "", "proc_nm": r[21] or "", "user_name": r[22] or "",
             "ins_user": r[23] or "", "ins_dt": str(r[24] or "")[:19],
             "upd_user": r[25] or "", "upd_dt": str(r[26] or "")[:19],
             "editable": seq >= NX_SEQ_BASE}   # 라이브 원본은 웹에서 수정 불가
        cur.execute(f"""SELECT FILE_NAME, FILE_SIZE FROM {src}.PR_T_DAILY_ISSUE_REVIEW_FILE
                        WHERE ISSUE_SEQ=? ORDER BY FILE_NAME""", seq)
        d["files"] = [{"name": fr[0] or "", "size": _i(fr[1])} for fr in cur.fetchall()]
        return d
    finally:
        cn.close()


@router.post("/api/qareview/save")
def qareview_save(payload: dict = Body(...)):
    """등록/수정(w_pr_input_595). 쓰기는 nx 만. seq 가 nx 대역이면 UPDATE, 없으면 INSERT."""
    p = payload
    seq = _i(p.get("seq"))
    ymd = _d6(str(p.get("ymd") or "").strip()) or datetime.now().strftime("%y%m%d")
    hhmm = str(p.get("hhmm") or "").strip().replace(":", "")[:4] or "0000"
    writer = str(p.get("writer") or "").strip()
    if not writer:
        raise HTTPException(400, "작성자를 입력하세요.")
    vals = (ymd, hhmm, writer,
            str(p.get("place") or "")[:100], str(p.get("target") or "")[:100],
            _f(p.get("t_target")), _f(p.get("t_result")),
            _f(p.get("ppm_target")), _f(p.get("ppm_result")),
            _f(p.get("err")), _f(p.get("inwon")), _f(p.get("holiday")), _f(p.get("attend")),
            str(p.get("qa_issue") or ""), str(p.get("rtn_err") or ""),
            str(p.get("c1") or "")[:3000], str(p.get("c2") or "")[:3000],
            str(p.get("c3") or "")[:3000], str(p.get("c4") or "")[:3000],
            str(p.get("proc") or "%")[:10])
    user = str(p.get("user") or "web").strip()
    cn = _nx(); cur = cn.cursor()
    try:
        if seq and seq >= NX_SEQ_BASE:
            cur.execute("""UPDATE nx.PR_T_DAILY_ISSUE_REVIEW SET
                  ISSUE_YMD=?,ISSUE_HHMM=?,WRITE_USER_ID=?,PLACE_DESC=?,TARGET_DESC=?,
                  TODAY_PROC_TARGET_QTY=?,TODAY_PROC_RESULT_QTY=?,TODAY_QA_TARGET_PPM=?,TODAY_QA_RESULT_PPM=?,
                  TODAY_ERROR_QTY=?,TODAY_INWON=?,TODAY_HOLIDAY_INWON=?,TODAY_ATTEND_INWON=?,
                  QA_ISSUE_DESC=?,RTN_ERROR_DESC=?,
                  CONTENTS_01_DESC=?,CONTENTS_02_DESC=?,CONTENTS_03_DESC=?,CONTENTS_04_DESC=?,
                  GAGONG_PROC_CODE=?,
                  UPDATE_USER_ID=?,UPDATE_DATETIME=GETDATE(),UPDATE_WINDOW='w_pr_input_595_web'
                WHERE ISSUE_SEQ=?""", *vals, user, seq)
            if cur.rowcount == 0:
                raise HTTPException(404, "수정할 일지를 찾을 수 없습니다.")
            cn.commit()
            return {"ok": True, "seq": seq, "mode": "update", "msg": "반성회일지 수정됨"}
        # 신규 — nx 전용 대역에서 채번
        cur.execute("SELECT ISNULL(MAX(ISSUE_SEQ),0) FROM nx.PR_T_DAILY_ISSUE_REVIEW")
        mx = _i((cur.fetchone() or [0])[0])
        seq = max(mx + 1, NX_SEQ_BASE)
        cur.execute("""INSERT INTO nx.PR_T_DAILY_ISSUE_REVIEW
            (ISSUE_SEQ,ISSUE_YMD,ISSUE_HHMM,WRITE_USER_ID,PLACE_DESC,TARGET_DESC,
             TODAY_PROC_TARGET_QTY,TODAY_PROC_RESULT_QTY,TODAY_QA_TARGET_PPM,TODAY_QA_RESULT_PPM,
             TODAY_ERROR_QTY,TODAY_INWON,TODAY_HOLIDAY_INWON,TODAY_ATTEND_INWON,
             QA_ISSUE_DESC,RTN_ERROR_DESC,
             CONTENTS_01_DESC,CONTENTS_02_DESC,CONTENTS_03_DESC,CONTENTS_04_DESC,
             GAGONG_PROC_CODE,
             INSERT_USER_ID,INSERT_DATETIME,INSERT_IP,INSERT_COMPUTER,INSERT_WINDOW,
             UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_IP,UPDATE_COMPUTER,UPDATE_WINDOW)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,GETDATE(),'','','w_pr_input_595_web',?,GETDATE(),'','','w_pr_input_595_web')""",
            seq, *vals, user, user)
        cn.commit()
        return {"ok": True, "seq": seq, "mode": "insert", "msg": "반성회일지 등록됨"}
    except HTTPException:
        cn.rollback(); raise
    except Exception as e:
        cn.rollback()
        raise HTTPException(500, f"저장 실패: {e}")
    finally:
        cn.close()


@router.post("/api/qareview/delete")
def qareview_delete(payload: dict = Body(...)):
    """선택 삭제 — nx 등록분만(라이브 원본은 웹에서 삭제 불가)."""
    seqs = [_i(x) for x in (payload.get("seqs") or [])]
    seqs = [s for s in seqs if s]
    if not seqs:
        raise HTTPException(400, "삭제할 일지를 선택하세요.")
    tgt = [s for s in seqs if s >= NX_SEQ_BASE]
    skipped = len(seqs) - len(tgt)
    if not tgt:
        return {"ok": False, "deleted": 0, "skipped": skipped,
                "msg": "레거시에서 작성된 일지는 웹에서 삭제할 수 없습니다."}
    cn = _nx(); cur = cn.cursor()
    try:
        ph = ",".join("?" * len(tgt))
        cur.execute(f"DELETE FROM nx.PR_T_DAILY_ISSUE_REVIEW_FILE WHERE ISSUE_SEQ IN ({ph})", *tgt)
        cur.execute(f"DELETE FROM nx.PR_T_DAILY_ISSUE_REVIEW WHERE ISSUE_SEQ IN ({ph})", *tgt)
        n = cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(tgt)
        cn.commit()
        msg = f"{n}건 삭제"
        if skipped: msg += f" · 레거시 작성분 {skipped}건 제외"
        return {"ok": True, "deleted": n, "skipped": skipped, "msg": msg}
    except Exception as e:
        cn.rollback()
        raise HTTPException(500, f"삭제 실패: {e}")
    finally:
        cn.close()
