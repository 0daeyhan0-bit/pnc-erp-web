# -*- coding: utf-8 -*-
"""partmaster 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE)

router = APIRouter()

# ================= 파트MASTER (기준정보, w_pr_master_280) — PR_M_PROC_GAGONG 라이브 CRUD =================
# 파트(가공공정)마스터. PROD_RATE=생산효율(=키팅 회수율). 공유마스터라 라이브 직접편집(원가·계획·키팅 즉시 일관). 권한게이트=프론트.
_GC_GUBUN = {'W': '자재창고', 'P': '생산파트', 'V': '생산창고', 'Q': '가공파트'}


def _ensure_result_cols(cur):
    """★실적처리방법 컬럼 멱등 보장 (2026-08-31 신설).

       nx.PR_M_PROC_GAGONG 은 **대문자 미러**라 레거시 동기화·재이관이 돌면
       우리가 추가한 컬럼이 통째로 날아간다(2026-08-30 실측: nx 초기화 후 2컬럼 소실
       → 파트마스터 화면 "백엔드 연결 실패", 파트별 생산계획 드래그 실적 전면 불가).
       조회·저장 진입마다 확인해 없으면 다시 만든다. 있으면 아무 일도 하지 않는다.

         BARCODE_FLAG     '1'=바코드실적 허용(기본). 독립 플래그.
         PROD_RESULT_TYPE ''=미지정 / 'R'=생산실적(준비재고) / 'W'=생산실적(자재창고출고). 택1.
    """
    try:
        cur.execute("""IF COL_LENGTH('PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG','BARCODE_FLAG') IS NULL
                         ALTER TABLE PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG ADD BARCODE_FLAG varchar(1) NULL""")
        cur.execute("""IF COL_LENGTH('PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG','PROD_RESULT_TYPE') IS NULL
                         ALTER TABLE PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG ADD PROD_RESULT_TYPE varchar(1) NULL""")
        cur.execute("""UPDATE PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG SET BARCODE_FLAG='1'
                        WHERE ISNULL(BARCODE_FLAG,'')=''""")
    except Exception:
        pass   # 권한 등으로 실패해도 조회 자체는 막지 않는다(ISNULL 로 방어됨)


@router.get("/api/partmaster/list")
def partmaster_list(q: str = Query(""), grp: str = Query("")):
    cn = _conn(); cur = cn.cursor()
    try:
        _ensure_result_cols(cur)
        w = ["1=1"]; p = []
        if q.strip():   w.append("(g.GAGONG_PROC_CODE LIKE ? OR g.GAGONG_PROC_DESC LIKE ?)"); p += [f"%{q.strip()}%", f"%{q.strip()}%"]
        if grp.strip(): w.append("ISNULL(g.PART_GROUP_CODE,'')=?"); p.append(grp.strip())
        cur.execute(f"""SELECT g.GAGONG_PROC_CODE code, g.GAGONG_PROC_DESC nm, ISNULL(g.GC_GUBUN,'') gubun,
              ISNULL(g.WORK_CODE,'') wc, ISNULL(w.WORK_DESC,'') wcnm, ISNULL(g.IN_CUST_CODE,'') wh, ISNULL(c.CUST_DESC,'') whnm,
              ISNULL(g.SORT_KEY,0) sortkey, ISNULL(g.PROD_RATE,0) rate, ISNULL(g.PART_GROUP_CODE,'') grp,
              ISNULL(g.WH_IP_ADDRESS,'') ip, ISNULL(g.RACK_NUMBER,0) rack,
              -- ★실적처리방법 (2026-08-30 신설)
              --   bc = 바코드실적 허용('1')  · 독립. 미설정도 허용(기존 동작 유지)
              --   pt = 생산실적 방식  ''없음 / 'R'준비재고 / 'W'자재창고출고  · 한 컬럼이라 택1 강제
              ISNULL(g.BARCODE_FLAG,'1') bc, ISNULL(g.PROD_RESULT_TYPE,'') pt,
              ISNULL(g.UPDATE_USER_ID,'') uid, g.UPDATE_DATETIME udt
            FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG g
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w ON w.WORK_CODE=g.WORK_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=g.IN_CUST_CODE
            WHERE {' AND '.join(w)} ORDER BY g.WORK_CODE, g.SORT_KEY, g.GAGONG_PROC_CODE""", *p)
        cols = [d[0] for d in cur.description]; rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r['gubunnm'] = _GC_GUBUN.get(r['gubun'], r['gubun'])
            r['rate'] = float(r['rate'] or 0); r['sortkey'] = int(r['sortkey'] or 0); r['rack'] = int(r['rack'] or 0)
            r['udt'] = str(r['udt'])[:19] if r['udt'] else ''
        return {"rows": rows, "cnt": len(rows), "gubuns": _GC_GUBUN}
    finally:
        cn.close()

@router.post("/api/partmaster/save")
def partmaster_save(payload: dict = Body(...)):
    r = payload.get('row', {}); user = (payload.get('user') or '웹')[:20]
    code = (r.get('code') or '').strip()
    if not code: return {"ok": False, "detail": "파트코드 필수"}
    cn = _nx(); cur = cn.cursor()   # ★nx전환: 가공공정 마스터 편집=nx.PR_M_PROC_GAGONG 복제본에 쓰기
    try:
        _ensure_result_cols(cur)    # ★미러 재이관으로 컬럼이 날아갔으면 다시 만든다
        cur.execute("SELECT COUNT(*) FROM nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE=?", code)
        exists = cur.fetchone()[0] > 0
        # ★실적처리방법 — bc(바코드) 는 독립, pt(생산실적)는 R/W 택1
        _bc = '1' if str(r.get('bc', '1')) in ('1', 'true', 'True', 'Y') else '0'
        _pt = str(r.get('pt', '') or '').strip().upper()
        if _pt not in ('R', 'W'):
            _pt = ''
        args = (r.get('nm', '') or '', (r.get('gubun', '') or '')[:1], (r.get('grp', '') or '')[:2], (r.get('wc', '') or '')[:4],
                (r.get('wh', '') or '')[:10], int(r.get('sortkey') or 0), float(r.get('rate') or 0),
                (r.get('ip', '') or '')[:30], int(r.get('rack') or 0), _bc, _pt, user)
        if exists:
            cur.execute("""UPDATE nx.PR_M_PROC_GAGONG SET GAGONG_PROC_DESC=?, GC_GUBUN=?, PART_GROUP_CODE=?, WORK_CODE=?,
                  IN_CUST_CODE=?, SORT_KEY=?, PROD_RATE=?, WH_IP_ADDRESS=?, RACK_NUMBER=?,
                  BARCODE_FLAG=?, PROD_RESULT_TYPE=?,
                  UPDATE_USER_ID=?, UPDATE_DATETIME=getdate(), UPDATE_WINDOW='web_partmaster'
                WHERE GAGONG_PROC_CODE=?""", *args, code)
        else:
            cur.execute("""INSERT INTO nx.PR_M_PROC_GAGONG(GAGONG_PROC_CODE, GAGONG_PROC_DESC, GC_GUBUN, PART_GROUP_CODE, WORK_CODE,
                  IN_CUST_CODE, SORT_KEY, PROD_RATE, WH_IP_ADDRESS, RACK_NUMBER,
                  BARCODE_FLAG, PROD_RESULT_TYPE, UPDATE_USER_ID, UPDATE_DATETIME, UPDATE_WINDOW)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,getdate(),'web_partmaster')""", code, *args)
        cn.commit()
        return {"ok": True, "mode": "update" if exists else "insert"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.post("/api/partmaster/delete")
def partmaster_delete(payload: dict = Body(...)):
    code = (payload.get('code') or '').strip()
    if not code: return {"ok": False, "detail": "코드 필수"}
    cn = _nx(); cur = cn.cursor()   # ★nx전환: 마스터 삭제=nx 복제본
    try:
        cur.execute("DELETE FROM nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE=?", code); cn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.get("/api/partmaster/workers")
def partmaster_workers(part: str = Query(..., description="파트코드(GAGONG_PROC_CODE)")):
    """파트별 작업자 목록 (레거시 w_pr_master_350 하단그리드). 원천 PR_M_PROC_GAGONG_WORKER.
       WORKER_CODE=작업자명, WORK_FLAG='1'=실작업자. 실작업자 우선·이름순."""
    part = (part or '').strip()
    if not part:
        return {"part": part, "rows": [], "cnt": 0}
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT ISNULL(WORKER_CODE,''), ISNULL(WORK_FLAG,''),
              ISNULL(INSERT_USER_ID,''), CONVERT(varchar(19),INSERT_DATETIME,120),
              ISNULL(UPDATE_USER_ID,''), CONVERT(varchar(19),UPDATE_DATETIME,120)
            FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG_WORKER WHERE GAGONG_PROC_CODE=?
            ORDER BY WORK_FLAG DESC, WORKER_CODE""", part)
        rows = [{"worker": str(r[0]).strip(), "real": str(r[1]).strip() == '1',
                 "ins_user": str(r[2] or '').strip(), "ins_dt": str(r[3] or '').strip(),
                 "upd_user": str(r[4] or '').strip(), "upd_dt": str(r[5] or '').strip()} for r in cur.fetchall()]
        return {"part": part, "rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.post("/api/partmaster/worker_save")
def partmaster_worker_save(payload: dict = Body(...)):
    """파트별 작업자 추가/수정 (레거시 w_pr_master_350 하단그리드 추가·수정 버튼).
       PK=(GAGONG_PROC_CODE, WORKER_CODE). orig≠worker면 이름변경(=PK변경) → 기존삭제+신규.
       WORK_FLAG='1'=실작업자. nx.PR_M_PROC_GAGONG_WORKER 쓰기."""
    part = (payload.get('part') or '').strip()
    worker = (payload.get('worker') or '').strip()
    orig = (payload.get('orig') or '').strip()   # 수정 전 이름(''=신규)
    real = '1' if payload.get('real') else '0'
    user = (payload.get('user') or '웹')[:20]
    if not part:   return {"ok": False, "detail": "파트 선택 필수"}
    if not worker: return {"ok": False, "detail": "작업자명 필수"}
    if len(worker) > 30: return {"ok": False, "detail": "작업자명 30자 이내"}
    cn = _nx(); cur = cn.cursor()   # ★nx전환: 작업자 마스터 편집=nx 복제본
    try:
        # 이름변경(PK변경): 기존 (part, orig) 제거
        if orig and orig != worker:
            cur.execute("DELETE FROM nx.PR_M_PROC_GAGONG_WORKER WHERE GAGONG_PROC_CODE=? AND WORKER_CODE=?", part, orig)
        cur.execute("SELECT COUNT(*) FROM nx.PR_M_PROC_GAGONG_WORKER WHERE GAGONG_PROC_CODE=? AND WORKER_CODE=?", part, worker)
        exists = cur.fetchone()[0] > 0
        if exists:
            cur.execute("""UPDATE nx.PR_M_PROC_GAGONG_WORKER SET WORK_FLAG=?,
                  UPDATE_USER_ID=?, UPDATE_DATETIME=getdate(), UPDATE_WINDOW='web_partmaster'
                WHERE GAGONG_PROC_CODE=? AND WORKER_CODE=?""", real, user, part, worker)
            mode = "update"
        else:
            cur.execute("""INSERT INTO nx.PR_M_PROC_GAGONG_WORKER(GAGONG_PROC_CODE, WORKER_CODE, WORK_FLAG,
                  INSERT_USER_ID, INSERT_DATETIME, INSERT_WINDOW, UPDATE_USER_ID, UPDATE_DATETIME, UPDATE_WINDOW)
                VALUES(?,?,?,?,getdate(),'web_partmaster',?,getdate(),'web_partmaster')""", part, worker, real, user, user)
            mode = "insert"
        cn.commit()
        return {"ok": True, "mode": mode}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.post("/api/partmaster/worker_save_all")
def partmaster_worker_save_all(payload: dict = Body(...)):
    """파트별 작업자 리스트 통째 저장 (레거시 w_pr_master_350 하단그리드 일괄편집).
       payload={part, rows:[{worker, real}], user}. 새 리스트에 없는 기존작업자=삭제, 변경분만 upsert."""
    part = (payload.get('part') or '').strip()
    rows = payload.get('rows') or []
    user = (payload.get('user') or '웹')[:20]
    if not part: return {"ok": False, "detail": "파트 선택 필수"}
    seen = set(); norm = []
    for r in rows:
        w = (r.get('worker') or '').strip()
        if not w:          return {"ok": False, "detail": "빈 작업자명이 있습니다"}
        if len(w) > 30:    return {"ok": False, "detail": f"작업자명 30자 초과: {w}"}
        if w in seen:      return {"ok": False, "detail": f"중복 작업자명: {w}"}
        seen.add(w); norm.append((w, '1' if r.get('real') else '0'))
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT WORKER_CODE, ISNULL(WORK_FLAG,'') FROM nx.PR_M_PROC_GAGONG_WORKER WHERE GAGONG_PROC_CODE=?", part)
        existing = {str(r[0]).strip(): str(r[1]).strip() for r in cur.fetchall()}
        newset = {w for w, _ in norm}
        ndel = nins = nupd = 0
        for w in (set(existing) - newset):
            cur.execute("DELETE FROM nx.PR_M_PROC_GAGONG_WORKER WHERE GAGONG_PROC_CODE=? AND WORKER_CODE=?", part, w); ndel += 1
        for w, flag in norm:
            if w in existing:
                if existing[w] != flag:
                    cur.execute("""UPDATE nx.PR_M_PROC_GAGONG_WORKER SET WORK_FLAG=?,
                          UPDATE_USER_ID=?, UPDATE_DATETIME=getdate(), UPDATE_WINDOW='web_partmaster'
                        WHERE GAGONG_PROC_CODE=? AND WORKER_CODE=?""", flag, user, part, w); nupd += 1
            else:
                cur.execute("""INSERT INTO nx.PR_M_PROC_GAGONG_WORKER(GAGONG_PROC_CODE, WORKER_CODE, WORK_FLAG,
                      INSERT_USER_ID, INSERT_DATETIME, INSERT_WINDOW, UPDATE_USER_ID, UPDATE_DATETIME, UPDATE_WINDOW)
                    VALUES(?,?,?,?,getdate(),'web_partmaster',?,getdate(),'web_partmaster')""", part, w, flag, user, user); nins += 1
        cn.commit()
        return {"ok": True, "ins": nins, "upd": nupd, "del": ndel, "cnt": len(norm)}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.post("/api/partmaster/worker_delete")
def partmaster_worker_delete(payload: dict = Body(...)):
    """파트별 작업자 삭제. PK=(GAGONG_PROC_CODE, WORKER_CODE)."""
    part = (payload.get('part') or '').strip()
    worker = (payload.get('worker') or '').strip()
    if not part or not worker: return {"ok": False, "detail": "파트/작업자 필수"}
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.PR_M_PROC_GAGONG_WORKER WHERE GAGONG_PROC_CODE=? AND WORKER_CODE=?", part, worker); cn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()
