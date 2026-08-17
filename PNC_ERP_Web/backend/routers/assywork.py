"""체결 공정 매트릭스 — 담당자 품목별 체결 횟수 입력·수정 → 손익(가공비) 반영.
   ★단일 테이블: nx.routing (절삭·용접·체결 전부 여기). 별도 테이블 없음.
   체결 21공정 = nx.CS_M_PROC(FS01~FS21, item_lgroup='J' 전품목유효, use_flag='0' 공정별목록엔 숨김) 마스터.
   저장: nx.routing 행(proc_code=FS**, work_qty=횟수, prod_uph=3600/표준공수, calc_gubun='3') → 엔진 가공비 자동계상(임율/UPH×횟수=표준공수×횟수÷3600×임율)."""
from fastapi import APIRouter, Query, Body, HTTPException
from common import _nx

router = APIRouter()

# 체결 표준공수 21공정 (레거시 견적원가조회 체결보기 = PR_M_WORK_ASSY 체결계열, data.js DB.assemProc와 동일)
_FASTEN = [
    ("FS01", "Screw 체결", 6.0, 1), ("FS02", "Cap 삽입", 2.0, 2), ("FS03", "Coil 삽입", 7.0, 3),
    ("FS04", "Mesh/링 삽입", 4.0, 4), ("FS05", "Sensor 삽입", 5.0, 5), ("FS06", "Insulator 부착", 6.0, 6),
    ("FS07", "Spring", 6.0, 7), ("FS08", "뎀퍼,부틸부착", 7.0, 8), ("FS09", "Nut 체결", 10.0, 9),
    ("FS10", "비닐호스 삽입", 4.0, 10), ("FS11", "Cable 정리", 13.0, 11), ("FS12", "Tape 부착", 5.0, 12),
    ("FS13", "Tie 묶음,컷팅", 9.0, 13), ("FS14", "라벨 부착", 3.0, 14), ("FS15", "막힘검사", 3.0, 15),
    ("FS16", "동작검사", 67.0, 16), ("FS17", "변봉부체결", 15.0, 17), ("FS18", "구리스도포", 8.0, 18),
    ("FS19", "EEV헤드부틸부착", 30.0, 19), ("FS20", "서포터", 3.0, 20), ("FS21", "지그삽입켓/서포터", 5.0, 21),
]
_FCODES = [f[0] for f in _FASTEN]
_STD = {f[0]: f[2] for f in _FASTEN}
_seeded = False   # 프로세스 내 시드 완료 플래그(21회 왕복 회피). 재기동시 리셋.


def _prep(cur):
    """체결 21공정을 nx.CS_M_PROC에 시드(없을 때만). item_lgroup='J'(전품목 유효), use_flag='0'(공정별 목록 숨김·엔진은 계상).
       prod_uph=3600/표준공수 → 엔진 cg3(임율/UPH×횟수)=표준공수×횟수÷3600×임율.
       ★사외망 지연 대비: 21개 개별 SELECT→1회 배치조회, 시드 완료 후 완전 스킵."""
    global _seeded
    if _seeded:
        return
    ph = ",".join("?" * len(_FCODES))
    cur.execute(f"SELECT PROC_CODE FROM nx.CS_M_PROC WHERE PROC_CODE IN ({ph})", *_FCODES)
    have = {str(r[0]).strip() for r in cur.fetchall()}
    for fc, nm, st, sq in _FASTEN:
        if fc not in have:
            cur.execute("""INSERT INTO nx.CS_M_PROC(PROC_CODE,PROC_DESC,ITEM_LGROUP,SORT_SEQ,PROD_UPH,USE_FLAG)
                VALUES(?,?,?,?,?,'0')""", fc, nm, 'J', 900 + sq, round(3600.0 / st, 6))
    _seeded = True   # 이 호출로 21개 전부 존재 확정 → 이후 호출은 즉시 리턴


def _labor_rate(cur):
    try:
        cur.execute("SELECT TOP 1 rate FROM nx.labor_rate WHERE labor_tag='3' ORDER BY apply_ym DESC")
        r = cur.fetchone()
        if r and r[0]: return float(r[0])
    except Exception:
        pass
    return 20776.0


@router.get("/api/assywork/get")
def assywork_get(item: str = Query(...)):
    """체결 매트릭스: 21공정 표준공수 + 이 품목 현재 횟수(nx.routing) + 내부ST(=표준공수×횟수)."""
    it = item.strip()
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur); nx.commit()
        qm = {}
        if it:
            ph = ",".join("?" * len(_FCODES))
            cur.execute(f"SELECT proc_code, ISNULL(work_qty,0) FROM nx.routing WHERE item_code=? AND proc_code IN ({ph})", it, *_FCODES)
            for c, q in cur.fetchall(): qm[str(c).strip()] = float(q or 0)
        labor = _labor_rate(cur)
        rows = []
        for fc, nm, st, sq in _FASTEN:
            q = qm.get(fc, 0.0)
            rows.append({"fcode": fc, "fname": nm, "std_st": st, "qty": q, "inner_st": round(st * q, 2)})
        tot = sum(r["inner_st"] for r in rows)
        return {"item": it, "rows": rows, "labor_rate": labor,
                "total_inner_st": round(tot, 2), "gagong": round(tot / 3600.0 * labor, 0)}
    finally:
        nx.close()


@router.post("/api/assywork/save")
def assywork_save(payload: dict = Body(...)):
    """체결 횟수 저장 → nx.routing(체결 FS 행만 교체). qty>0만. 저장시 원가엔진 캐시 무효화."""
    it = str(payload.get("item", "")).strip()
    if not it:
        raise HTTPException(400, "item 필요")
    rows = payload.get("rows", []) or []
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur)
        # 이 품목의 체결(FS) routing 행만 삭제 후 재삽입 (절삭·용접·기타 공정 불변)
        ph = ",".join("?" * len(_FCODES))
        cur.execute(f"DELETE FROM nx.routing WHERE item_code=? AND proc_code IN ({ph})", it, *_FCODES)
        n = 0
        for r in rows:
            c = str(r.get("fcode", "")).strip()
            q = float(r.get("qty") or 0)
            if c not in _STD or q <= 0:
                continue
            uph = round(3600.0 / _STD[c], 6)
            cur.execute("""INSERT INTO nx.routing(p_item,item_code,proc_code,work_qty,prod_uph,calc_gubun,sort_seq)
                VALUES('',?,?,?,?,'3',?)""", it, c, q, uph, 900)
            n += 1
        nx.commit()
        try:
            from common import _reset_cost_engine
            _reset_cost_engine()
        except Exception:
            pass
        return {"ok": True, "count": n, "item": it}
    finally:
        nx.close()
