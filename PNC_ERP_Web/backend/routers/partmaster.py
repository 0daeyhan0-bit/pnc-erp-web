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

@router.get("/api/partmaster/list")
def partmaster_list(q: str = Query(""), grp: str = Query("")):
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if q.strip():   w.append("(g.GAGONG_PROC_CODE LIKE ? OR g.GAGONG_PROC_DESC LIKE ?)"); p += [f"%{q.strip()}%", f"%{q.strip()}%"]
        if grp.strip(): w.append("ISNULL(g.PART_GROUP_CODE,'')=?"); p.append(grp.strip())
        cur.execute(f"""SELECT g.GAGONG_PROC_CODE code, g.GAGONG_PROC_DESC nm, ISNULL(g.GC_GUBUN,'') gubun,
              ISNULL(g.WORK_CODE,'') wc, ISNULL(w.WORK_DESC,'') wcnm, ISNULL(g.IN_CUST_CODE,'') wh, ISNULL(c.CUST_DESC,'') whnm,
              ISNULL(g.SORT_KEY,0) sortkey, ISNULL(g.PROD_RATE,0) rate, ISNULL(g.PART_GROUP_CODE,'') grp,
              ISNULL(g.WH_IP_ADDRESS,'') ip, ISNULL(g.RACK_NUMBER,0) rack, ISNULL(g.UPDATE_USER_ID,'') uid, g.UPDATE_DATETIME udt
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
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE=?", code)
        exists = cur.fetchone()[0] > 0
        args = (r.get('nm', '') or '', (r.get('gubun', '') or '')[:1], (r.get('grp', '') or '')[:2], (r.get('wc', '') or '')[:4],
                (r.get('wh', '') or '')[:10], int(r.get('sortkey') or 0), float(r.get('rate') or 0),
                (r.get('ip', '') or '')[:30], int(r.get('rack') or 0), user)
        if exists:
            cur.execute("""UPDATE PR_M_PROC_GAGONG SET GAGONG_PROC_DESC=?, GC_GUBUN=?, PART_GROUP_CODE=?, WORK_CODE=?,
                  IN_CUST_CODE=?, SORT_KEY=?, PROD_RATE=?, WH_IP_ADDRESS=?, RACK_NUMBER=?,
                  UPDATE_USER_ID=?, UPDATE_DATETIME=getdate(), UPDATE_WINDOW='web_partmaster'
                WHERE GAGONG_PROC_CODE=?""", *args, code)
        else:
            cur.execute("""INSERT INTO PR_M_PROC_GAGONG(GAGONG_PROC_CODE, GAGONG_PROC_DESC, GC_GUBUN, PART_GROUP_CODE, WORK_CODE,
                  IN_CUST_CODE, SORT_KEY, PROD_RATE, WH_IP_ADDRESS, RACK_NUMBER, UPDATE_USER_ID, UPDATE_DATETIME, UPDATE_WINDOW)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,getdate(),'web_partmaster')""", code, *args)
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
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE=?", code); cn.commit()
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
