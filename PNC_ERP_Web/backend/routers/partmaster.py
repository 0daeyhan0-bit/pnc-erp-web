# -*- coding: utf-8 -*-
"""partmaster 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE)

router = APIRouter()

# ================= 파트MASTER (기준정보, w_pr_master_280) — nx.part_master CRUD =================
# 파트(가공공정)마스터. PROD_RATE=생산효율(=키팅 회수율). 원가·계획·키팅이 함께 읽는 공유마스터.
# 권한게이트=프론트.
#
# ★2026-09-09 미러 → 클린 전환 (§1-9-1 컷오버 후 단일 테이블)
#   쓰기 = nx.part_master (실테이블, 소문자)
#   조회 = nx.v_part_master (호환뷰 — 미러 컬럼명 그대로 노출해 나머지 80곳 SQL 무수정)
#
#   ★왜 옮겼나 — 미러(nx.PR_M_PROC_GAGONG)에 ALTER 로 얹었던 웹 고유 컬럼이
#     레거시 재적재 때 **값째로** 날아갔다. 실제로 두 번 겪었다:
#       2026-08-30 컬럼 소실 → 화면 "백엔드 연결 실패", 드래그 실적 전면 불가
#       2026-09-09 값 전멸  → S8·S10 준비재고 설정을 대표님이 다시 입력
#     예전 _ensure_result_cols() 는 컬럼만 되살릴 뿐 **값은 복구하지 못했다**.
#     클린 테이블은 재적재 대상이 아니라 이 사고가 구조적으로 사라진다.
#     (이관 = _migration/seed_part_master_260909.py, 코드 = switch_part_master_260909.py)
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
              ISNULL(g.WH_IP_ADDRESS,'') ip, ISNULL(g.RACK_NUMBER,0) rack,
              -- ★실적처리방법 (2026-08-30 신설)
              --   bc = 바코드실적 허용('1')  · 독립. 미설정도 허용(기존 동작 유지)
              --   pt = 생산실적 방식  ''없음 / 'R'준비재고 / 'W'자재창고출고  · 한 컬럼이라 택1 강제
              ISNULL(g.BARCODE_FLAG,'1') bc, ISNULL(g.PROD_RESULT_TYPE,'') pt,
              ISNULL(g.UPDATE_USER_ID,'') uid, g.UPDATE_DATETIME udt
            FROM PARTNER_ERP_TEST3.nx.v_part_master g
            LEFT JOIN PARTNER_ERP_TEST3.nx.v_work_place w ON w.WORK_CODE=g.WORK_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.v_cm_m_cust c ON c.CUST_CODE=g.IN_CUST_CODE
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
    cn = _nx(); cur = cn.cursor()   # ★클린 쓰기 — nx.part_master (뷰가 아니라 실테이블)
    try:
        cur.execute("SELECT COUNT(*) FROM nx.part_master WHERE part_code=?", code)
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
            cur.execute("""UPDATE nx.part_master SET part_name=?, gc_gubun=?, part_group=?, work_code=?,
                  wh_cust_code=?, sort_key=?, prod_rate=?, wh_ip=?, rack_no=?,
                  barcode_flag=?, prod_result_type=?,
                  upd_user=?, upd_dt=getdate()
                WHERE part_code=?""", *args, code)
        else:
            cur.execute("""INSERT INTO nx.part_master(part_code, part_name, gc_gubun, part_group, work_code,
                  wh_cust_code, sort_key, prod_rate, wh_ip, rack_no,
                  barcode_flag, prod_result_type, upd_user, upd_dt, use_yn)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,getdate(),'1')""", code, *args)
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
    cn = _nx(); cur = cn.cursor()   # ★클린 쓰기 — nx.part_master
    try:
        cur.execute("DELETE FROM nx.part_master WHERE part_code=?", code); cn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.get("/api/partmaster/workers")
def partmaster_workers(part: str = Query(..., description="파트코드(GAGONG_PROC_CODE)")):
    """파트별 작업자 목록 (레거시 w_pr_master_350 하단그리드). 원천 nx.part_worker(클린).
       worker_name=작업자명(코드가 아니다), work_flag='1'=실작업자. 실작업자 우선·이름순.

       ★2026-09-09 미러 → 클린 — 파트마스터(nx.part_master)의 짝인데 여기만 미러로 남아
         한 화면이 두 계보로 갈려 있었다. 쓰기가 있는 그리드라 컷오버에 그대로 죽는다(§1-9-1)."""
    part = (part or '').strip()
    if not part:
        return {"part": part, "rows": [], "cnt": 0}
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT ISNULL(worker_name,''), ISNULL(work_flag,''),
              ISNULL(ins_user,''), CONVERT(varchar(19),ins_dt,120),
              ISNULL(upd_user,''), CONVERT(varchar(19),upd_dt,120)
            FROM PARTNER_ERP_TEST3.nx.part_worker WHERE part_code=?
            ORDER BY work_flag DESC, worker_name""", part)
        rows = [{"worker": str(r[0]).strip(), "real": str(r[1]).strip() == '1',
                 "ins_user": str(r[2] or '').strip(), "ins_dt": str(r[3] or '').strip(),
                 "upd_user": str(r[4] or '').strip(), "upd_dt": str(r[5] or '').strip()} for r in cur.fetchall()]
        return {"part": part, "rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.post("/api/partmaster/worker_save")
def partmaster_worker_save(payload: dict = Body(...)):
    """파트별 작업자 추가/수정 (레거시 w_pr_master_350 하단그리드 추가·수정 버튼).
       PK=(part_code, worker_name). orig≠worker면 이름변경(=PK변경) → 기존삭제+신규.
       work_flag='1'=실작업자. ★클린 nx.part_worker 쓰기(2026-09-09 전환)."""
    part = (payload.get('part') or '').strip()
    worker = (payload.get('worker') or '').strip()
    orig = (payload.get('orig') or '').strip()   # 수정 전 이름(''=신규)
    real = '1' if payload.get('real') else '0'
    user = (payload.get('user') or '웹')[:20]
    if not part:   return {"ok": False, "detail": "파트 선택 필수"}
    if not worker: return {"ok": False, "detail": "작업자명 필수"}
    if len(worker) > 30: return {"ok": False, "detail": "작업자명 30자 이내"}
    cn = _nx(); cur = cn.cursor()   # ★클린 쓰기 — nx.part_worker
    try:
        # 이름변경(PK변경): 기존 (part, orig) 제거
        if orig and orig != worker:
            cur.execute("DELETE FROM nx.part_worker WHERE part_code=? AND worker_name=?", part, orig)
        cur.execute("SELECT COUNT(*) FROM nx.part_worker WHERE part_code=? AND worker_name=?", part, worker)
        exists = cur.fetchone()[0] > 0
        if exists:
            cur.execute("""UPDATE nx.part_worker SET work_flag=?, upd_user=?, upd_dt=getdate()
                WHERE part_code=? AND worker_name=?""", real, user, part, worker)
            mode = "update"
        else:
            cur.execute("""INSERT INTO nx.part_worker(part_code, worker_name, work_flag,
                  ins_user, ins_dt, upd_user, upd_dt)
                VALUES(?,?,?,?,getdate(),?,getdate())""", part, worker, real, user, user)
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
        cur.execute("SELECT worker_name, ISNULL(work_flag,'') FROM nx.part_worker WHERE part_code=?", part)
        existing = {str(r[0]).strip(): str(r[1]).strip() for r in cur.fetchall()}
        newset = {w for w, _ in norm}
        ndel = nins = nupd = 0
        for w in (set(existing) - newset):
            cur.execute("DELETE FROM nx.part_worker WHERE part_code=? AND worker_name=?", part, w); ndel += 1
        for w, flag in norm:
            if w in existing:
                if existing[w] != flag:
                    cur.execute("""UPDATE nx.part_worker SET work_flag=?, upd_user=?, upd_dt=getdate()
                        WHERE part_code=? AND worker_name=?""", flag, user, part, w); nupd += 1
            else:
                cur.execute("""INSERT INTO nx.part_worker(part_code, worker_name, work_flag,
                      ins_user, ins_dt, upd_user, upd_dt)
                    VALUES(?,?,?,?,getdate(),?,getdate())""", part, w, flag, user, user); nins += 1
        cn.commit()
        return {"ok": True, "ins": nins, "upd": nupd, "del": ndel, "cnt": len(norm)}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()

@router.post("/api/partmaster/worker_delete")
def partmaster_worker_delete(payload: dict = Body(...)):
    """파트별 작업자 삭제. PK=(part_code, worker_name)."""
    part = (payload.get('part') or '').strip()
    worker = (payload.get('worker') or '').strip()
    if not part or not worker: return {"ok": False, "detail": "파트/작업자 필수"}
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.part_worker WHERE part_code=? AND worker_name=?", part, worker); cn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()
