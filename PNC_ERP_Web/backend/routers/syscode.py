# -*- coding: utf-8 -*-
"""시스템코드관리 — 레거시 「System별 코드별 상세」(w_cm_master_010) 웹 재구현.

3단 구조 (레거시와 동일)
    시스템코드   KIND_CODE 앞 2자        CM 공통관리 · PR 생산관리 · PU 구매관리 · QA 품질관리
    코드군       nx.code_kind(41종)      PR003 '생산추가입력라인' · 상세코드SIZE · 이력관리
    상세코드     nx.code_detail(334건)   AA=설치 · EZ=이지링크 …

★2026-09-09 미러 → 클린 (§1-9-1)
    원천이던 CM_M_MASTER_DETAIL(미러)은 **웹에 등록화면이 없어 읽기만** 했다.
    컷오버로 레거시가 은퇴하면 라인 하나 늘어도 웹에서 추가할 방법이 없다.
    ⟹ 클린으로 옮기고(41종 334건) 이 화면을 신설해 **웹에서 관리**한다.

★가져온 건 41종뿐이다(대표 확정 "필요한것만 가져오자").
    레거시 186종 3,837건 중 HR(인사)·EC(전자결재)·CS(원가)·ZI(이미지) 등
    **웹이 만들지 않는 모듈**은 옮기지 않았다 — 옮겨도 관리 주체가 없다.
    필요해지면 _migration/seed_syscode_260909.py 의 KINDS 에 추가하고 다시 돌린다(멱등).

★이력관리(history_flag='Y')인 코드군은 같은 코드가 apply_ymd 별로 여러 벌 존재한다.
    PK = (kind_code, detail_code, apply_ymd). 이력관리가 아니면 apply_ymd=''.

★조회는 뷰(nx.v_code_detail)를 쓰는 다른 화면과 같은 값을 본다 — 여기서 고치면 즉시 반영.
"""
from fastapi import APIRouter, Query, Body
from common import _conn, _nx

router = APIRouter()

SYSNAME = {"CM": "공통관리", "PR": "생산관리", "PU": "구매관리",
           "SA": "영업관리", "QA": "품질관리", "TT": "생산관리"}


@router.get("/api/syscode/systems")
def syscode_systems():
    """시스템코드 드롭다운 — KIND_CODE 앞 2자로 묶는다(레거시엔 CM_M_SYSTEM 이 있으나
       (PROJECT_CODE, SYSTEM_CODE) 축이라 그대로 쓰면 중복이다)."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT LEFT(kind_code,2) sys, COUNT(*) FROM PARTNER_ERP_TEST3.nx.code_kind
                        GROUP BY LEFT(kind_code,2) ORDER BY LEFT(kind_code,2)""")
        rows = [{"code": str(r[0]).strip(),
                 "nm": SYSNAME.get(str(r[0]).strip(), str(r[0]).strip()),
                 "cnt": r[1]} for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()


@router.get("/api/syscode/kinds")
def syscode_kinds(sys: str = Query("", description="시스템코드(PR·CM…), 빈값=전체"),
                  q: str = Query("")):
    """코드군 목록 (레거시 상단 그리드 — CODE · MASTER명칭 · 상세코드SIZE · SYSTEM · 이력관리)."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if sys.strip():
            w.append("LEFT(k.kind_code,2)=?"); p.append(sys.strip())
        if q.strip():
            w.append("(k.kind_code LIKE ? OR k.kind_desc LIKE ?)")
            p += ["%{}%".format(q.strip())] * 2
        cur.execute("""SELECT k.kind_code, ISNULL(k.kind_desc,''), ISNULL(k.detail_size,0),
                  ISNULL(k.system_tag,''), ISNULL(k.history_flag,''),
                  (SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.code_detail d WHERE d.kind_code=k.kind_code),
                  ISNULL(k.char1_desc,''), ISNULL(k.char2_desc,''), ISNULL(k.char3_desc,''),
                  ISNULL(k.num1_desc,''), ISNULL(k.flag1_desc,''),
                  ISNULL(k.upd_user,''), CONVERT(varchar(19),k.upd_dt,120)
                FROM PARTNER_ERP_TEST3.nx.code_kind k
               WHERE {} ORDER BY k.kind_code""".format(" AND ".join(w)), *p)
        rows = [{"kind": str(r[0]).strip(), "nm": r[1], "size": int(r[2] or 0),
                 "systag": r[3], "hist": r[4], "cnt": r[5],
                 "c1": r[6], "c2": r[7], "c3": r[8], "n1": r[9], "f1": r[10],
                 "upd_user": r[11], "upd_dt": r[12] or ""} for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()


@router.get("/api/syscode/details")
def syscode_details(kind: str = Query(..., description="코드군(PR003 등)")):
    """상세코드 목록 (레거시 하단 그리드 — 상세CODE · 상세명칭 · 조회순서 · 적용일자 · 사용여부)."""
    kind = (kind or "").strip()
    if not kind:
        return {"kind": kind, "rows": [], "cnt": 0, "head": {}}
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT ISNULL(kind_desc,''), ISNULL(detail_size,0), ISNULL(history_flag,''),
                  ISNULL(char1_desc,''), ISNULL(char2_desc,''), ISNULL(char3_desc,''),
                  ISNULL(char4_desc,''), ISNULL(char5_desc,''),
                  ISNULL(num1_desc,''), ISNULL(num2_desc,''), ISNULL(num3_desc,''),
                  ISNULL(flag1_desc,''), ISNULL(flag2_desc,''), ISNULL(flag3_desc,'')
                FROM PARTNER_ERP_TEST3.nx.code_kind WHERE kind_code=?""", kind)
        h = cur.fetchone()
        # 기타항목은 **헤더에 라벨이 있는 것만** 화면에 띄운다(레거시 동일 — 빈 라벨=미사용)
        head = {}
        if h:
            head = {"nm": h[0], "size": int(h[1] or 0), "hist": h[2],
                    "labels": {"char1": h[3], "char2": h[4], "char3": h[5], "char4": h[6], "char5": h[7],
                               "num1": h[8], "num2": h[9], "num3": h[10],
                               "flag1": h[11], "flag2": h[12], "flag3": h[13]}}
        cur.execute("""SELECT detail_code, ISNULL(detail_desc,''), ISNULL(detail_descs,''),
                  ISNULL(sort_seq,0), ISNULL(apply_ymd,''), ISNULL(use_flag,'1'),
                  ISNULL(char1,''), ISNULL(char2,''), ISNULL(char3,''), ISNULL(char4,''), ISNULL(char5,''),
                  ISNULL(num1,0), ISNULL(num2,0), ISNULL(num3,0),
                  ISNULL(flag1,''), ISNULL(flag2,''), ISNULL(flag3,''),
                  ISNULL(upd_user,''), CONVERT(varchar(19),upd_dt,120)
                FROM PARTNER_ERP_TEST3.nx.code_detail WHERE kind_code=?
               ORDER BY sort_seq, detail_code, apply_ymd""", kind)
        rows = [{"code": str(r[0]).strip(), "nm": r[1], "nms": r[2],
                 "seq": float(r[3] or 0), "ymd": str(r[4] or "").strip(),
                 "use": str(r[5] or "1").strip(),
                 "char1": r[6], "char2": r[7], "char3": r[8], "char4": r[9], "char5": r[10],
                 "num1": float(r[11] or 0), "num2": float(r[12] or 0), "num3": float(r[13] or 0),
                 "flag1": r[14], "flag2": r[15], "flag3": r[16],
                 "upd_user": r[17], "upd_dt": r[18] or ""} for r in cur.fetchall()]
        return {"kind": kind, "head": head, "rows": rows, "cnt": len(rows)}
    finally:
        cn.close()


@router.post("/api/syscode/detail_save")
def syscode_detail_save(payload: dict = Body(...)):
    """상세코드 추가/수정. PK=(kind_code, detail_code, apply_ymd).
       orig 가 오면 코드변경(=PK변경) → 기존삭제 + 신규."""
    kind = (payload.get("kind") or "").strip()
    code = (payload.get("code") or "").strip()
    ymd = (payload.get("ymd") or "").strip()
    orig = (payload.get("orig") or "").strip()          # 수정 전 코드('' = 신규)
    orig_ymd = (payload.get("orig_ymd") or "").strip()
    user = (payload.get("user") or "웹")[:20]
    if not kind: return {"ok": False, "detail": "코드군 선택 필수"}
    if not code: return {"ok": False, "detail": "상세코드 필수"}

    cn = _nx(); cur = cn.cursor()
    try:
        # 자릿수 검증 — 레거시 '상세코드SIZE'
        cur.execute("SELECT ISNULL(detail_size,0), ISNULL(history_flag,'') FROM nx.code_kind WHERE kind_code=?", kind)
        h = cur.fetchone()
        if not h: return {"ok": False, "detail": "없는 코드군: {}".format(kind)}
        size, hist = int(h[0] or 0), str(h[1] or "").strip().upper()
        if size and len(code) > size:
            return {"ok": False, "detail": "상세코드는 {}자 이내입니다 (입력값 '{}' = {}자)".format(size, code, len(code))}
        # 이력관리가 아니면 적용일자를 받지 않는다(레거시 동일)
        if hist != "Y":
            ymd = ""

        if orig and (orig != code or orig_ymd != ymd):
            cur.execute("DELETE FROM nx.code_detail WHERE kind_code=? AND detail_code=? AND apply_ymd=?",
                        kind, orig, orig_ymd)

        cur.execute("SELECT COUNT(*) FROM nx.code_detail WHERE kind_code=? AND detail_code=? AND apply_ymd=?",
                    kind, code, ymd)
        exists = cur.fetchone()[0] > 0
        args = (payload.get("nm") or "", payload.get("nms") or "",
                float(payload.get("seq") or 0),
                "0" if str(payload.get("use", "1")) in ("0", "false", "False", "N") else "1",
                payload.get("char1") or "", payload.get("char2") or "", payload.get("char3") or "",
                payload.get("char4") or "", payload.get("char5") or "",
                float(payload.get("num1") or 0), float(payload.get("num2") or 0), float(payload.get("num3") or 0),
                (payload.get("flag1") or "")[:1], (payload.get("flag2") or "")[:1], (payload.get("flag3") or "")[:1],
                user)
        if exists:
            cur.execute("""UPDATE nx.code_detail SET detail_desc=?, detail_descs=?, sort_seq=?, use_flag=?,
                      char1=?, char2=?, char3=?, char4=?, char5=?, num1=?, num2=?, num3=?,
                      flag1=?, flag2=?, flag3=?, upd_user=?, upd_dt=getdate()
                    WHERE kind_code=? AND detail_code=? AND apply_ymd=?""", *args, kind, code, ymd)
            mode = "update"
        else:
            cur.execute("""INSERT INTO nx.code_detail(detail_desc, detail_descs, sort_seq, use_flag,
                      char1, char2, char3, char4, char5, num1, num2, num3,
                      flag1, flag2, flag3, upd_user, upd_dt, kind_code, detail_code, apply_ymd)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,getdate(),?,?,?)""", *args, kind, code, ymd)
            mode = "insert"
        cn.commit()
        return {"ok": True, "mode": mode}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()


@router.post("/api/syscode/detail_delete")
def syscode_detail_delete(payload: dict = Body(...)):
    """상세코드 삭제. PK=(kind_code, detail_code, apply_ymd)."""
    kind = (payload.get("kind") or "").strip()
    code = (payload.get("code") or "").strip()
    ymd = (payload.get("ymd") or "").strip()
    if not kind or not code: return {"ok": False, "detail": "코드군/상세코드 필수"}
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.code_detail WHERE kind_code=? AND detail_code=? AND apply_ymd=?",
                    kind, code, ymd)
        cn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()


@router.post("/api/syscode/kind_save")
def syscode_kind_save(payload: dict = Body(...)):
    """코드군 추가/수정 (레거시 상단 그리드). PK=kind_code.
       ★코드군 신설은 신중히 — 이걸 읽는 프로그램이 없으면 만들어도 아무 데도 안 쓰인다."""
    kind = (payload.get("kind") or "").strip().upper()
    user = (payload.get("user") or "웹")[:20]
    if not kind: return {"ok": False, "detail": "코드군 필수"}
    if len(kind) > 5: return {"ok": False, "detail": "코드군은 5자 이내입니다"}
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM nx.code_kind WHERE kind_code=?", kind)
        exists = cur.fetchone()[0] > 0
        args = (payload.get("nm") or "", int(payload.get("size") or 0),
                (payload.get("systag") or "M")[:1],
                "Y" if str(payload.get("hist", "")).upper() in ("Y", "TRUE", "1") else "N",
                payload.get("c1") or "", payload.get("c2") or "", payload.get("c3") or "",
                payload.get("n1") or "", payload.get("f1") or "", user)
        if exists:
            cur.execute("""UPDATE nx.code_kind SET kind_desc=?, detail_size=?, system_tag=?, history_flag=?,
                      char1_desc=?, char2_desc=?, char3_desc=?, num1_desc=?, flag1_desc=?,
                      upd_user=?, upd_dt=getdate() WHERE kind_code=?""", *args, kind)
            mode = "update"
        else:
            cur.execute("""INSERT INTO nx.code_kind(kind_desc, detail_size, system_tag, history_flag,
                      char1_desc, char2_desc, char3_desc, num1_desc, flag1_desc,
                      upd_user, upd_dt, kind_code)
                    VALUES(?,?,?,?,?,?,?,?,?,?,getdate(),?)""", *args, kind)
            mode = "insert"
        cn.commit()
        return {"ok": True, "mode": mode}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()


@router.post("/api/syscode/kind_delete")
def syscode_kind_delete(payload: dict = Body(...)):
    """코드군 삭제 — 상세코드가 남아 있으면 거부한다(고아 방지)."""
    kind = (payload.get("kind") or "").strip()
    if not kind: return {"ok": False, "detail": "코드군 필수"}
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM nx.code_detail WHERE kind_code=?", kind)
        n = cur.fetchone()[0]
        if n:
            return {"ok": False, "detail": "상세코드 {}건이 남아 있습니다. 먼저 삭제하세요.".format(n)}
        cur.execute("DELETE FROM nx.code_kind WHERE kind_code=?", kind)
        cn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close()
