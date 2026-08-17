"""체결/조립공정 매트릭스 — 담당자 품목별 체결 공정횟수 입력·수정 → 손익(가공비) 반영.
   ★단일 테이블: nx.item_fasten(품목별 횟수) + nx.fasten_std(21공정 표준공수 마스터).
   내부원가 가공비의 체결분은 이 매트릭스가 정본(기존 CS라우팅 체결과 이중계상 방지=엔진에서 CS체결 제외)."""
from fastapi import APIRouter, Query, Body, HTTPException
from common import _nx, _conn

router = APIRouter()

# 체결 표준공수 마스터 (레거시 견적원가조회 체결보기 21공정, data.js DB.assemProc와 동일)
_FASTEN_SEED = [
    ("01", "Screw 체결", 6.0, 1), ("02", "Cap 삽입", 2.0, 2), ("03", "Coil 삽입", 7.0, 3),
    ("17", "Mesh/링 삽입", 4.0, 4), ("04", "Sensor 삽입", 5.0, 5), ("05", "Insulator 부착", 6.0, 6),
    ("06", "Spring", 6.0, 7), ("07", "뎀퍼,부틸부착", 7.0, 8), ("08", "Nut 체결", 10.0, 9),
    ("09", "비닐호스 삽입", 4.0, 10), ("10", "Cable 정리", 13.0, 11), ("11", "Tape 부착", 5.0, 12),
    ("12", "Tie 묶음,컷팅", 9.0, 13), ("13", "라벨 부착", 3.0, 14), ("14", "막힘검사", 3.0, 15),
    ("15", "동작검사", 67.0, 16), ("16", "변봉부체결", 15.0, 17), ("18", "구리스도포", 8.0, 18),
    ("19", "EEV헤드부틸부착", 30.0, 19), ("20", "서포터", 3.0, 20), ("21", "지그삽입켓/서포터", 5.0, 21),
]

_DDL_STD = """IF OBJECT_ID('nx.fasten_std') IS NULL
CREATE TABLE nx.fasten_std(fcode varchar(4) PRIMARY KEY, fname nvarchar(60), std_st float, sort_seq int, use_flag char(1) DEFAULT '1')"""
_DDL_ITEM = """IF OBJECT_ID('nx.item_fasten') IS NULL
CREATE TABLE nx.item_fasten(item_code varchar(50), fcode varchar(4), qty float,
  update_user_id varchar(30), update_datetime datetime DEFAULT getdate(), CONSTRAINT pk_item_fasten PRIMARY KEY(item_code,fcode))"""


def _prep(cur):
    cur.execute(_DDL_STD); cur.execute(_DDL_ITEM)
    # 마스터 시드(없을 때만)
    cur.execute("SELECT COUNT(*) FROM nx.fasten_std")
    if (cur.fetchone()[0] or 0) == 0:
        for c, n, st, sq in _FASTEN_SEED:
            cur.execute("INSERT INTO nx.fasten_std(fcode,fname,std_st,sort_seq,use_flag) VALUES(?,?,?,?,'1')", c, n, st, sq)


# ★내부원가 임율(가공비 환산) — 엔진과 동일 소스. 없으면 legacy HOUR_PAY 11850.
def _labor_rate(cur):
    try:
        cur.execute("SELECT TOP 1 rate FROM nx.labor_rate WHERE labor_tag='3' ORDER BY apply_ym DESC")
        r = cur.fetchone()
        if r and r[0]: return float(r[0])
    except Exception:
        pass
    return 11850.0


@router.get("/api/assywork/get")
def assywork_get(item: str = Query(...)):
    """체결 매트릭스: 21공정 표준공수 + 이 품목 현재 횟수 + 내부ST(=표준공수×횟수)."""
    it = item.strip()
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur); nx.commit()
        cur.execute("SELECT fcode,fname,std_st,sort_seq FROM nx.fasten_std WHERE ISNULL(use_flag,'1')<>'0' ORDER BY sort_seq,fcode")
        std = [(str(r[0]), str(r[1]), float(r[2] or 0), int(r[3] or 0)) for r in cur.fetchall()]
        qm = {}
        if it:
            cur.execute("SELECT fcode,qty FROM nx.item_fasten WHERE item_code=?", it)
            for c, q in cur.fetchall(): qm[str(c)] = float(q or 0)
        labor = _labor_rate(cur)
        rows = []
        for c, n, st, sq in std:
            q = qm.get(c, 0.0)
            rows.append({"fcode": c, "fname": n, "std_st": st, "qty": q, "inner_st": round(st * q, 2)})
        tot_st = sum(r["inner_st"] for r in rows)
        return {"item": it, "rows": rows, "labor_rate": labor,
                "total_inner_st": round(tot_st, 2), "gagong": round(tot_st / 3600.0 * labor, 0)}
    finally:
        nx.close()


@router.post("/api/assywork/save")
def assywork_save(payload: dict = Body(...)):
    """체결 횟수 저장(품목별). rows=[{fcode,qty}] — qty>0만 저장(전체교체). 저장시 원가엔진 캐시 무효화."""
    it = str(payload.get("item", "")).strip()
    if not it:
        raise HTTPException(400, "item 필요")
    rows = payload.get("rows", []) or []
    user = str(payload.get("user", "웹사용자"))[:30]
    nx = _nx(); cur = nx.cursor()
    try:
        _prep(cur)
        cur.execute("DELETE FROM nx.item_fasten WHERE item_code=?", it)
        n = 0
        for r in rows:
            c = str(r.get("fcode", "")).strip()
            q = float(r.get("qty") or 0)
            if not c or q <= 0:
                continue
            cur.execute("INSERT INTO nx.item_fasten(item_code,fcode,qty,update_user_id) VALUES(?,?,?,?)", it, c, q, user)
            n += 1
        nx.commit()
        try:
            from common import _reset_cost_engine
            _reset_cost_engine()   # 체결 변경 → 가공비 재계산
        except Exception:
            pass
        return {"ok": True, "count": n, "item": it}
    finally:
        nx.close()
