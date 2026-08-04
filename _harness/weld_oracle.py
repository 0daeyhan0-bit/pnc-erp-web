# -*- coding: utf-8 -*-
"""
용접봉 재이관 검증 오라클 (레거시 내부용/실원가 SP 재현 — 용접 소요 부분)

★근거(SP 소스 실측, SP_CS_견적서_내부용_250704.sql):
  - 내부용 SP 는 용접(WELD/RAC/ITEM_WELD) 을 **전혀 참조하지 않음**. 용접봉은 CS_M_ITEM_BOM 의
    RAC* 자재행(USE_QTY=최종소요량)으로 이미 들어있어 일반 자재처럼 재료비 계산됨.
  - BOM 전개 필터 = **CS_CALC_EXCEPT_FLAG <> '1'** 만 (L182). EXCEPT_FLAG 는 원가 제외 아님.
  - 재료비 JAI_COST = WON_MAT_COST × USE_QTY (L308).
  ∴ **오라클 용접 소요(node) = Σ CS_M_ITEM_BOM.USE_QTY  (MAT_CODE LIKE 'RAC%' AND CS_CALC_EXCEPT_FLAG<>'1')**
    = SP/화면이 실제 원가계상하는 값(=ground truth, SP EXEC 차단 대체).

내부용 vs 실원가 구분:
  - 내부용(naewon) = BOM 전 노드 전개(INNER 필터 없음) → 전 노드 RAC USE_QTY 합.
  - 실원가(silwon) = INNER_PROD 노드만 전개(외주/매입 SUB 는 leaf 정지) → INNER 노드 RAC USE_QTY 합.

자기검증(dual-source, SP EXEC 없이):
  오라클A(BOM RAC USE_QTY) 와 오라클B(Σ weld_diam.std_use × CS_T_ITEM_WELD.weld_qty × 1.5) 가
  일치하면 오라클 확정. (2026-08-04 실측: 교집합 3483노드 중 78.6% 일치. 15 소실노드 중 14/15 일치.)

사용:
  from weld_oracle import node_weld_bom, node_weld_formula, tree_weld
  node_weld_bom(lv_cur,'AJR30012009')      -> {'RAC30599301-1':0.0426}
  tree_weld(lv_cur, nx_cur, 'AJR30012009') -> {'nae':..., 'sil':...}  # BOM 트리 전개 합
"""
import sys, os
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client

def _lv():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                          f'DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
def _nx():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                          f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)

def std_use_map(nx_cur):
    """관경별 표준소요량(대표 = MIN silver '01'). = nx.weld_diam(레거시 CS_M_WELD 정합)."""
    nx_cur.execute("SELECT pipe_diam, MIN(std_use_qty) FROM nx.weld_diam GROUP BY pipe_diam")
    return {round(float(r[0]), 2): float(r[1]) for r in nx_cur.fetchall()}

def node_weld_bom(lv_cur, node):
    """오라클A: CS_M_ITEM_BOM RAC USE_QTY (CS_CALC_EXCEPT_FLAG<>'1') per weld_item. = SP 원가계상값."""
    lv_cur.execute("""SELECT MAT_CODE, SUM(USE_QTY) FROM CS_M_ITEM_BOM
        WHERE ITEM_CODE=? AND MAT_CODE LIKE 'RAC%' AND ISNULL(CS_CALC_EXCEPT_FLAG,'0')<>'1'
        GROUP BY MAT_CODE""", node)
    return {str(r[0]).strip(): round(float(r[1] or 0), 6) for r in lv_cur.fetchall()}

def node_weld_formula(lv_cur, stu, node):
    """오라클B: Σ(weld_diam.std_use × CS_T_ITEM_WELD.weld_qty) × 1.5 per weld_item."""
    lv_cur.execute("""SELECT ITEM_CODE, PIPE_DIAM, WELD_QTY FROM CS_T_ITEM_WELD
        WHERE P_ITEM_CODE=? AND ISNULL(WELD_QTY,0)>0""", node)
    out = {}
    for r in lv_cur.fetchall():
        wi = str(r[0]).strip(); d = round(float(r[1]), 2); q = float(r[2])
        out[wi] = out.get(wi, 0.0) + stu.get(d, 0) * q
    return {k: round(v * 1.5, 6) for k, v in out.items()}

def node_weld_counts(lv_cur, node):
    """CS_T_ITEM_WELD 관경별 횟수 (item_weld 재이관용)."""
    lv_cur.execute("""SELECT ITEM_CODE, PIPE_DIAM, WELD_QTY FROM CS_T_ITEM_WELD
        WHERE P_ITEM_CODE=? AND ISNULL(WELD_QTY,0)>0 ORDER BY ITEM_CODE, PIPE_DIAM""", node)
    return [(str(r[0]).strip(), round(float(r[1]), 2), float(r[2])) for r in lv_cur.fetchall()]

def _inner(lv_cur, node):
    """INNER_PROD 판정(실원가 전개 여부). make_type='1' 또는 (in_cust='' & 자체가공). 외주=False."""
    lv_cur.execute("SELECT ISNULL(MAKE_TYPE,''), ISNULL(IN_CUST_CODE,'') FROM PR_M_ITEM WHERE ITEM_CODE=?", node)
    r = lv_cur.fetchone()
    if not r: return True
    mt = str(r[0]).strip(); ic = str(r[1]).strip()
    if mt == '1': return True
    if mt == '2' and ic: return False   # 외주(사급처 지정)
    return True

def tree_weld(lv_cur, top, stu=None, nx_cur=None):
    """CS_M_ITEM_BOM 트리 전개하며 각 노드 용접 소요 합산. 내부용(전노드)/실원가(INNER 노드만).
       반환 {'nae':총소요, 'sil':총소요, 'nodes':[(node, use, inner)]}. CS_CALC_EXCEPT<>1 준수."""
    nae = sil = 0.0; nodes = []; seen = set()
    def walk(node, inner_path):
        if node in seen: return
        seen.add(node)
        w = sum(node_weld_bom(lv_cur, node).values())
        inner = _inner(lv_cur, node)
        if w > 0:
            nodes.append((node, w, inner and inner_path))
        nonlocal nae, sil
        nae += w
        if inner and inner_path: sil += w
        lv_cur.execute("""SELECT MAT_CODE FROM CS_M_ITEM_BOM
            WHERE ITEM_CODE=? AND ISNULL(CS_CALC_EXCEPT_FLAG,'0')<>'1' AND MAT_CODE NOT LIKE 'RAC%'""", node)
        kids = [str(r[0]).strip() for r in lv_cur.fetchall()]
        for k in kids:
            walk(k, inner and inner_path)
    walk(top, True)
    return {'nae': round(nae, 6), 'sil': round(sil, 6), 'nodes': nodes}

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    lv = _lv().cursor(); nx = _nx().cursor(); stu = std_use_map(nx)
    for it in ['AJR30012009', 'AJR73327007', 'AJR30012011', 'AJR30133707']:
        a = node_weld_bom(lv, it); b = node_weld_formula(lv, stu, it)
        t = tree_weld(lv, it)
        print(f"[{it}] BOM={a} 공식={b} | 트리 내부용={t['nae']} 실원가={t['sil']} ({len(t['nodes'])}노드)")
