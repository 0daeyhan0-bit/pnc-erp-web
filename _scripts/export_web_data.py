# -*- coding: utf-8 -*-
"""신규 웹 ERP용 실데이터 스냅샷 → PNC_ERP_Web/js/data.js"""
import sys, io, os, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def q(sql):
    df = db_client.run_query(sql)
    return json.loads(df.to_json(orient='records', force_ascii=False))
def scalar(sql): return int(db_client.run_query(sql).iloc[0,0])
def q_live(sql):
    """라이브 PARTNER_ERP 를 '읽기 전용(SELECT)'으로만 조회 (쓰기 불가)."""
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
        f"DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    conn=pyodbc.connect(cs, readonly=True)
    try:
        df=pd.read_sql(sql, conn)
        return json.loads(df.to_json(orient='records', force_ascii=False))
    finally:
        conn.close()

DB = {}
DB['meta'] = {'db':'PARTNER_ERP_TEST2', 'note':'실데이터 스냅샷 (차세대 스키마)'}

# ---- 대시보드 집계 ----
DB['dashboard'] = {
  'items_total': scalar("SELECT COUNT(*) FROM CM_ITEM_MST"),
  'partners_total': scalar("SELECT COUNT(*) FROM CM_PARTNER"),
  'bom_revisions': scalar("SELECT COUNT(*) FROM PR_BOM"),
  'bom_comps': scalar("SELECT COUNT(*) FROM PR_BOM_COMP"),
  'price_records': scalar("SELECT COUNT(*) FROM CM_ITEM_PRICE_HIST"),
  'routes': scalar("SELECT COUNT(*) FROM PR_PROD_ROUTE"),
  'items_by_type': q("""SELECT item_type type, COUNT(*) cnt FROM CM_ITEM_MST GROUP BY item_type ORDER BY cnt DESC"""),
  'items_by_cat': q("""SELECT TOP 8 ISNULL(cat.category_nm,'(미분류)') name, COUNT(*) cnt
                        FROM CM_ITEM_MST m LEFT JOIN CM_ITEM_CATEGORY cat ON cat.category_cd=m.category_cd
                        GROUP BY cat.category_nm ORDER BY cnt DESC"""),
  'partners_by_class': q("""SELECT TOP 8 ISNULL(cl.class_nm,'(미분류)') name, COUNT(*) cnt
                        FROM CM_PARTNER p LEFT JOIN CM_PARTNER_CLASS cl ON cl.class_cd=p.class_cd
                        GROUP BY cl.class_nm ORDER BY cnt DESC"""),
  'partners_by_role': q("""SELECT role_type+ISNULL(' ('+vendor_type+')','') name, COUNT(*) cnt
                        FROM CM_PARTNER_ROLE GROUP BY role_type, vendor_type ORDER BY cnt DESC"""),
}

# ---- 품목 목록 (300, 유형 다양하게) ----
DB['items'] = q("""
SELECT TOP 300 m.item_cd cd, m.item_nm nm, m.item_type type,
       ISNULL(cat.category_nm,'') cat, m.base_uom_cd uom, m.use_yn useyn, pr.up price
FROM CM_ITEM_MST m
LEFT JOIN CM_ITEM_CATEGORY cat ON cat.category_cd=m.category_cd
OUTER APPLY (SELECT TOP 1 unit_price up FROM CM_ITEM_PRICE_HIST p
            WHERE p.item_cd=m.item_cd AND p.price_type='STD_COST' ORDER BY p.apply_ymd DESC) pr
ORDER BY m.item_type, m.item_cd
""")

# ---- 품목 상세(위 300건): 공급처 + 최근 단가 ----
codes = [r['cd'] for r in DB['items']]
inlist = ",".join("'"+c.replace("'","''")+"'" for c in codes)
sup = q(f"""SELECT s.item_cd cd, s.partner_cd pcd, ISNULL(p.partner_nm,'') pnm, s.sourcing_type stype, s.priority_num pri
            FROM CM_ITEM_SUPPLIER s LEFT JOIN CM_PARTNER p ON p.partner_cd=s.partner_cd
            WHERE s.item_cd IN ({inlist})""")
pxs = q(f"""SELECT cd, price_type ptype, currency cur, CONVERT(varchar,apply_ymd,23) ymd, unit_price up FROM (
             SELECT item_cd cd, price_type, currency, apply_ymd, unit_price,
                    ROW_NUMBER() OVER (PARTITION BY item_cd, price_type ORDER BY apply_ymd DESC) rn
             FROM CM_ITEM_PRICE_HIST WHERE item_cd IN ({inlist})) t WHERE rn<=6""")
detail = {}
for c in codes: detail[c] = {'suppliers':[], 'prices':[]}
for s in sup: detail[s['cd']]['suppliers'].append(s)
for p in pxs: detail[p['cd']]['prices'].append(p)
DB['itemDetail'] = detail

# ---- 거래처 (전체 356) + 역할 ----
DB['partners'] = q("""
SELECT p.partner_cd cd, p.partner_nm nm, ISNULL(cl.class_nm,'') class, p.owner_nm owner,
       p.biz_reg_no biz, p.use_yn useyn,
       STUFF((SELECT ', '+r.role_type+ISNULL('('+r.vendor_type+')','') FROM CM_PARTNER_ROLE r
              WHERE r.partner_cd=p.partner_cd FOR XML PATH('')),1,2,'') roles
FROM CM_PARTNER p LEFT JOIN CM_PARTNER_CLASS cl ON cl.class_cd=p.class_cd
ORDER BY p.partner_nm
""")

# ---- BOM 예시 (SUB-ASSY 많은 완제품) ----
best = db_client.run_query("""
SELECT TOP 1 b.bom_id, b.parent_item_cd
FROM PR_BOM b JOIN PR_BOM_COMP c ON c.bom_id=b.bom_id
JOIN CM_ITEM_MST m ON m.item_cd=b.parent_item_cd AND m.item_type='PROD'
GROUP BY b.bom_id, b.parent_item_cd
HAVING COUNT(*) BETWEEN 8 AND 25 ORDER BY COUNT(*) DESC
""")
best_bom_id = int(best.iloc[0,0]); bom_parent = best.iloc[0,1]
DB['bomExample'] = {
  'parent': bom_parent,
  'parent_nm': db_client.run_query(f"SELECT item_nm FROM CM_ITEM_MST WHERE item_cd='{bom_parent}'").iloc[0,0],
  'revisions': q(f"""SELECT rev_no rev, CONVERT(varchar,valid_from,23) vf, CONVERT(varchar,valid_to,23) vt, status
                     FROM PR_BOM WHERE parent_item_cd='{bom_parent}' ORDER BY rev_no"""),
  'comps': q(f"""SELECT c.seq, c.child_item_cd cd, cm.item_nm nm, cm.item_type type, c.qty, c.uom_cd uom, c.sagub_yn sagub
                 FROM PR_BOM_COMP c JOIN CM_ITEM_MST cm ON cm.item_cd=c.child_item_cd
                 WHERE c.bom_id={best_bom_id} ORDER BY c.seq"""),
}

# ---- 품목단가 (구매 BUY + 판매 SALE) : 품목별 그룹 + 히스토리 (기준정보 관리) ----
DB['priceTotal'] = scalar("SELECT COUNT(*) FROM (SELECT DISTINCT item_cd FROM CM_ITEM_PRICE_HIST) t")
# 거래처(매입처/매출처) 있는 단가만 (거래처 없는 레거시 행 제외 — 현행 화면과 동일)
_HAS_P = "ISNULL(LTRIM(RTRIM(partner_cd)),'')<>''"
DB['priceItems'] = q(f"""
SELECT TOP 700 m.item_cd cd, m.item_nm nm, m.item_type type, ISNULL(cat.category_nm,'') cat, m.base_uom_cd uom,
  (SELECT COUNT(DISTINCT partner_cd) FROM CM_ITEM_PRICE_HIST p WHERE p.item_cd=m.item_cd AND p.price_type='BUY' AND {_HAS_P}) buyv,
  (SELECT COUNT(DISTINCT partner_cd) FROM CM_ITEM_PRICE_HIST p WHERE p.item_cd=m.item_cd AND p.price_type='SALE' AND {_HAS_P}) salec,
  (SELECT MIN(unit_price) FROM CM_ITEM_PRICE_HIST p WHERE p.item_cd=m.item_cd AND p.price_type='BUY' AND p.main_flag='Y' AND {_HAS_P}) curbuy,
  (SELECT MAX(unit_price) FROM CM_ITEM_PRICE_HIST p WHERE p.item_cd=m.item_cd AND p.price_type='SALE' AND p.main_flag='Y' AND {_HAS_P}) cursale,
  (SELECT CONVERT(varchar,MAX(apply_ymd),23) FROM CM_ITEM_PRICE_HIST p WHERE p.item_cd=m.item_cd AND {_HAS_P}) lastymd
FROM CM_ITEM_MST m LEFT JOIN CM_ITEM_CATEGORY cat ON cat.category_cd=m.category_cd
WHERE EXISTS(SELECT 1 FROM CM_ITEM_PRICE_HIST p WHERE p.item_cd=m.item_cd AND {_HAS_P})
ORDER BY CASE WHEN EXISTS(SELECT 1 FROM CM_ITEM_PRICE_HIST p WHERE p.item_cd=m.item_cd AND p.price_type='BUY' AND {_HAS_P})
              AND EXISTS(SELECT 1 FROM CM_ITEM_PRICE_HIST p WHERE p.item_cd=m.item_cd AND p.price_type='SALE' AND {_HAS_P}) THEN 0 ELSE 1 END,
         m.item_cd
""")
_codes=[r['cd'] for r in DB['priceItems']]
_in=",".join("'"+c.replace("'","''")+"'" for c in _codes)
def _histrows(ptype):
    return q(f"""SELECT ph.item_cd cd, LTRIM(RTRIM(ph.partner_cd)) pcd, ISNULL(pt.partner_nm,'') pnm,
       ISNULL(ph.market_gubun,'') mkt, ph.currency cur, ph.mat_cost mat, ph.proc_cost pcost, ph.other_cost oth,
       ph.unit_price up, CONVERT(varchar,ph.apply_ymd,23) ymd, ph.main_flag main
       FROM CM_ITEM_PRICE_HIST ph LEFT JOIN CM_PARTNER pt ON pt.partner_cd=ph.partner_cd
       WHERE ph.price_type='{ptype}' AND ISNULL(LTRIM(RTRIM(ph.partner_cd)),'')<>'' AND ph.item_cd IN ({_in})
       ORDER BY ph.item_cd, ph.partner_cd, ph.apply_ymd DESC""")
_buy=_histrows('BUY'); _sale=_histrows('SALE')
DB['priceBuyHist']={c:[] for c in _codes}; DB['priceSaleHist']={c:[] for c in _codes}
for h in _buy: DB['priceBuyHist'][h['cd']].append(h)
for h in _sale: DB['priceSaleHist'][h['cd']].append(h)

# ---- 라인/공정 코드→이름 (PR_M_PROC_GAGONG) ----
DB['lineNames'] = {r['cd']:r['nm'] for r in q("SELECT LTRIM(RTRIM(GAGONG_PROC_CODE)) cd, GAGONG_PROC_DESC nm FROM PR_M_PROC_GAGONG WHERE LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))<>''")}

# ---- 재고 (창고 + 단계별 통합 현재고) ----
DB['warehouses'] = q("SELECT wh_code cd, wh_name nm FROM CM_WAREHOUSE ORDER BY wh_code")
DB['stock'] = q("""
SELECT s.item_cd cd, m.item_nm nm, m.item_type type, s.stock_stage stage, s.wh_code wh, w.wh_name whnm,
  s.location_cd loc, s.stock_qty qty, s.uom_cd uom, s.stock_cost cost, s.stock_amt amt, CONVERT(varchar,s.last_in_ymd,23) lastin
FROM PR_ITEM_STOCK s JOIN CM_ITEM_MST m ON m.item_cd=s.item_cd JOIN CM_WAREHOUSE w ON w.wh_code=s.wh_code
WHERE s.stock_qty<>0 ORDER BY s.stock_stage, ABS(s.stock_amt) DESC, ABS(s.stock_qty) DESC
""")
# ---- 용접 BOM풀기 (SP를 TEST3에서 실행 후 결과 추출) ----
db_client.execute_query("EXEC dbo.[SP_PR_생산재고수불현황_BOM풀기] '260701','260715','1'")
DB['weldBom'] = q("""
SELECT NULLIF(LTRIM(RTRIM(item_code)),'') assy, LTRIM(RTRIM(mat_code)) mat, item_desc nm, item_class cls,
  cust_desc cust, basic_qty basic, in_qty inq, out_qty outq, etc_qty adj,
  stock_qty qty, item_cost2 cost, CAST(ROUND(stock_qty*ISNULL(item_cost2,0),0) AS DECIMAL(18,0)) amt
FROM PR_T_TEMP_STOCK_480_T3
ORDER BY ABS(ROUND(stock_qty*ISNULL(item_cost2,0),0)) DESC, ABS(stock_qty) DESC
""")

# ---- 생산재고 집계/파트별 (가공 P0001 / 용접 그외) — 기초·입고·출고·조정 포함 (dw 로직) ----
_U = """
SELECT a.gagong_proc_code gpc, A.MAT_CODE mat, A.STOCK_QTY basic,0 inq,0 outq,0 etc FROM PR_T_MONTH_STOCK_WH A WHERE A.STOCK_YYMM='2502'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.maint_ymd<'260701',-A.MAINT_QTY,0),iif(a.maint_ymd<'260701',0,-A.MAINT_QTY),0,0 FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND a.maint_tag='B' AND isnull(a.out_wh_gubun,'1')='1'
UNION ALL SELECT A.gagong_proc_code,a.mat_code,iif(a.cut_ymd<'260701',a.cut_QTY,0),iif(a.cut_ymd<'260701',0,a.cut_QTY),0,0 FROM pu_t_cut_dtl a WHERE A.cut_ymd>'250299' and A.cut_ymd<='260715'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'260701',0,-a.MAINT_QTY),0 FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND a.maint_tag='T' and isnull(a.out_wh_gubun,'3')='3'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'260701',-a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY),0 FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND a.maint_tag='C'
UNION ALL SELECT A.stock_part_code,a.item_code,iif(a.prod_ymd<'260701',a.prod_qty,0),iif(a.prod_ymd<'260701',0,a.prod_qty),0,0 FROM pr_t_prod_dtl a WHERE A.prod_ymd>'250299' and A.prod_ymd<='260715' and a.stock_part_code>'' and not exists (select 1 from sa_t_stock_maint where maint_ymd=a.prod_ymd and item_code=a.item_code and in_part_code=a.stock_part_code)
UNION ALL SELECT A.IN_PART_CODE,a.item_code,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY),0,0 FROM sa_t_stock_maint a WHERE A.maint_ymd>'250299' and A.MAINT_YMD<='260715' and a.in_part_code>''
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY),0,0 FROM PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND A.MAINT_TAG='3'
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),0,0,iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY) FROM PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND A.MAINT_TAG in ('2','1')
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'260701',0,-a.MAINT_QTY),0 FROM PR_T_STOCK_MAINT_MAT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND A.MAINT_TAG='4'
"""
_C2 = "(select top 1 q.item_cost from pr_m_item_cost q where q.item_code=agg.mat and q.cost_tag='1' and q.cost_apply_ymd<='260701' and q.cust_code=case when pi.work_code='P2' then '2228' else pi.in_cust_code end order by q.cost_apply_ymd desc)"
DB['prodStock'] = q(f"""
;WITH agg AS (
  SELECT LTRIM(RTRIM(t.mat)) mat, ISNULL(LTRIM(RTRIM(t.gpc)),'') line,
     SUM(basic) basic, SUM(inq) inq, SUM(outq) outq, SUM(etc) adj,
     SUM(basic)+SUM(inq)-SUM(outq)+SUM(etc) qty
  FROM ({_U}) t GROUP BY LTRIM(RTRIM(t.mat)), ISNULL(LTRIM(RTRIM(t.gpc)),'')
  HAVING (SUM(basic)<>0 OR SUM(inq)<>0 OR SUM(outq)<>0 OR SUM(etc)<>0)
)
SELECT CASE WHEN agg.line='P0001' THEN 'GAGONG' ELSE 'WELD' END stage,
  CASE WHEN agg.line='P0001' THEN '' ELSE agg.line END loc,
  agg.mat cd, m.item_nm nm, m.item_type type,
  agg.basic, agg.inq, agg.outq, agg.adj, agg.qty,
  {_C2} cost, CAST(ROUND(agg.qty*ISNULL({_C2},0),0) AS DECIMAL(18,0)) amt
FROM agg JOIN CM_ITEM_MST m ON m.item_cd=agg.mat JOIN PR_M_ITEM pi ON pi.item_code=agg.mat
""")

# ---- 제품재고 (영업, dw_pr_stock_040) — 기초/입고/출고/조정/현재고 ----
_S040 = """
select /*생산입고*/ UPPER(a.item_code) mat,0 basic,a.maint_qty inq,0 outq,0 etc
  from sa_t_stock_maint a
 where a.maint_ymd between '260701' and '260715' and a.maint_tag='P' and a.maint_qty<>0 and ISNULL(a.in_part_code,'')=''
union all
select UPPER(a.item_code),0,a.maint_qty,0,0 from sa_t_stock_maint a
 where a.maint_ymd between '260701' and '260715' and a.maint_tag in ('B','V') and a.maint_qty<>0
union all
select /*직납 자재입고*/ UPPER(a.mat_code),0,a.maint_qty*-1,0,0 from pu_t_stock_maint a
 where a.maint_ymd between '260701' and '260715' and isnull(a.out_wh_gubun,'1')='2'
union all
select /*창고출하*/ UPPER(a.item_code),0,0,a.maint_qty*-1,0 from sa_t_stock_maint a
 where a.maint_ymd between '260701' and '260715' and a.maint_tag in ('J','8','R') and a.maint_qty<>0
union all
select /*재고조정*/ UPPER(a.item_code),0,0,0,a.maint_qty*-1 from sa_t_stock_maint a
 where a.maint_ymd between '260701' and '260715' and a.maint_tag='2' and a.maint_qty<>0
union all
select /*월기초*/ item_code,stock_qty,0,0,0 from sa_t_month_stock where stock_yymm='2502'
union all
select /*이전 생산*/ item_code,maint_qty,0,0,0 from sa_t_stock_maint
 where maint_ymd>'250299' and maint_ymd<'260701' and maint_tag='P' and ISNULL(in_part_code,'')=''
union all
select item_code,maint_qty,0,0,0 from sa_t_stock_maint
 where maint_ymd>'250299' and maint_ymd<'260701' and maint_tag in ('B','V','J','2','R')
union all
select UPPER(a.mat_code),a.maint_qty*-1,0,0,0 from pu_t_stock_maint a
 where a.maint_ymd>'250299' and a.maint_ymd<'260701' and isnull(a.out_wh_gubun,'1')='2'
"""
DB['salesStock'] = q(f"""
;WITH t AS ({_S040})
SELECT t.mat cd, max(m.item_desc) nm, max(m.item_spec) spec, max(m.item_class) cls,
   sum(t.basic) basic, sum(t.inq) inq, sum(t.outq) outq, sum(t.etc) adj,
   sum(t.basic+t.inq-t.etc-t.outq) qty,
   (select top 1 item_cost from pr_m_item_cost where item_code=t.mat and cost_apply_ymd<='260715' and cost_tag in ('S','E') order by cost_apply_ymd desc) cost,
   case when max(m.work_code)>'' then max(m.work_code) else max(m.in_cust_code) end wc_cd,
   case when max(m.work_code)>'' then (select work_desc from pr_m_work where work_code=max(m.work_code))
        else (select cust_desc from cm_m_cust where cust_code=max(m.in_cust_code)) end wc
FROM t JOIN pr_m_item m ON t.mat=m.item_code
GROUP BY t.mat
""")
for r in DB['salesStock']:
    c = r.get('cost') or 0
    r['amt'] = round((r.get('qty') or 0) * c)
DB['salesStock'].sort(key=lambda r: -abs(r.get('amt') or 0))
_agg=lambda k: sum((r.get(k) or 0) for r in DB['salesStock'])
print(f"salesStock(제품재고): {len(DB['salesStock'])}건  기초={_agg('basic'):,.0f} 입고={_agg('inq'):,.0f} 출고={_agg('outq'):,.0f} 기타출고={_agg('adj'):,.0f} 재고={_agg('qty'):,.0f} 금액={_agg('amt'):,.0f}")

# ---- 자재 일수불장 (구매/자재, dw_pu_stock_260) — 기초/입고/출고/기타/재고 × 수량·금액 ----
# 일수불장은 클라이언트가 계산하는 구조(DB SP 없음). 라이브 PU_T_MONTH_STOCK_WH_DAILY 는 당일 스냅샷(현재 260717)만 유지 → 라이브를 '읽기전용'으로 가져옴.
DB['sgroupNames'] = {r['cd']:r['nm'] for r in q("SELECT DETAIL_CODE cd, REPLACE(REPLACE(DETAIL_DESC,CHAR(13),''),CHAR(10),'') nm FROM CM_M_MASTER_DETAIL WHERE KIND_CODE='PR006'")}
# 거래처분류(조달구분) PR011: 1유상사급/4절삭-원자재/6절삭-협력사/7절삭-부자재 ...
DB['custTypeNames'] = {r['cd']:r['nm'] for r in q("SELECT DETAIL_CODE cd, REPLACE(REPLACE(DETAIL_DESC,CHAR(13),''),CHAR(10),'') nm FROM CM_M_MASTER_DETAIL WHERE KIND_CODE='PR011'")}
# 자재 담당자 = 매입처별 별도 관리 매핑(퇴사/변경 대비 하드코딩 금지). 지금은 매입처 담당자로 시드 → 추후 편집가능 테이블(예: CM_M_CHARGE_ASSIGN).
DB['chargeMap'] = {r['custcd']:r['nm'] for r in q("""
  SELECT cust_code custcd, LTRIM(RTRIM(ISNULL(NULLIF(CHARGE_USER_ID,''),ISNULL(CHARGE_NAME,'')))) nm
  FROM cm_m_cust WHERE LTRIM(RTRIM(ISNULL(NULLIF(CHARGE_USER_ID,''),ISNULL(CHARGE_NAME,''))))<>''""")}
_daily_ymd = db_client.run_query("SELECT MAX(STOCK_YMD) d FROM PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990'")  # 참고용(TEST3)
_live_ymd = None
try:
    import pyodbc as _pdb
    _cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    _cn=_pdb.connect(_cs, readonly=True)
    _live_ymd=str(pd.read_sql("SELECT MAX(STOCK_YMD) d FROM PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990'", _cn).iloc[0,0]); _cn.close()
except Exception as e:
    print("[warn] 라이브 일수불 날짜 조회 실패:", str(e)[:100])
_live_ymd = _live_ymd or '260717'
DB['matLedgerDate'] = f"20{_live_ymd[0:2]}-{_live_ymd[2:4]}-{_live_ymd[4:6]}"
DB['matLedger'] = q_live(f"""
select t.mat_code cd, max(m.item_desc) nm, max(m.item_spec) spec,
  isnull(max(m.item_sgroup),'') sg, max(m.unit) unit,
  isnull(max(m.in_cust_code),'') custcd, isnull(max(c.cust_desc),'') cust, isnull(max(c.cust_type),'') ctype,
  max(t.last_in_ymd) lastin,
  sum(t.basic_qty) bq,  sum(t.basic_amt) ba,
  sum(t.input_qty) iq,  sum(t.input_amt) ia,
  sum(t.output_qty) oq, sum(t.output_amt) oa,
  sum(t.trans_qty) tq,  sum(t.trans_amt) ta,
  sum(t.stock_qty) sq,  sum(t.stock_amt) sa
from PU_T_MONTH_STOCK_WH_DAILY t
join pr_m_item m on t.mat_code=m.item_code
join pr_m_proc_gagong g on t.gagong_proc_code=g.gagong_proc_code
left join cm_m_cust c on m.in_cust_code=c.cust_code
where t.cust_code='Z99990' and t.STOCK_YMD='{_live_ymd}'
group by t.mat_code
order by t.mat_code
""")
_ml=lambda k: sum((r.get(k) or 0) for r in DB['matLedger'])
print(f"matLedger(자재일수불 {_live_ymd}): {len(DB['matLedger'])}건  기초={_ml('ba'):,.0f} 입고={_ml('ia'):,.0f} 출고={_ml('oa'):,.0f} 기타={_ml('ta'):,.0f} 재고={_ml('sa'):,.0f}")

# ---- 자재 월수불장 (dw_pu_stock_160) — 라이브 PU_T_MONTH_STOCK_WH 최신 마감월(읽기전용) ----
# TEST3 복사본은 2605까지만 마감 → 라이브는 2606 마감 완료. 라이브 최신 마감월을 읽어옴(ERP 화면과 일치).
_mym = None
try:
    _cn=_pdb.connect(_cs, readonly=True)
    _mym=str(pd.read_sql("SELECT MAX(STOCK_YYMM) y FROM PU_T_MONTH_STOCK_WH WHERE cust_code='Z99990'", _cn).iloc[0,0]); _cn.close()
except Exception as e:
    print("[warn] 라이브 월수불 마감월 조회 실패:", str(e)[:100])
_mym = _mym or '2606'
DB['monthLedgerYm'] = f"20{_mym[0:2]}-{_mym[2:4]}"
DB['monthLedger'] = q_live(f"""
select t.mat_code cd, max(m.item_desc) nm, max(m.item_spec) spec,
  isnull(max(m.item_sgroup),'') sg, max(m.unit) unit,
  isnull(max(m.in_cust_code),'') custcd, isnull(max(c.cust_desc),'') cust, isnull(max(c.cust_type),'') ctype,
  '' lastin,
  sum(t.basic_qty) bq,  sum(t.basic_amt) ba,
  sum(t.input_qty) iq,  sum(t.input_amt) ia,
  sum(t.output_qty) oq, sum(t.output_amt) oa,
  sum(t.trans_qty) tq,  sum(t.trans_amt) ta,
  sum(t.stock_qty) sq,  sum(t.stock_amt) sa
from PU_T_MONTH_STOCK_WH t
join pr_m_item m on t.mat_code=m.item_code
join pr_m_proc_gagong g on t.gagong_proc_code=g.gagong_proc_code
left join cm_m_cust c on m.in_cust_code=c.cust_code
where t.cust_code='Z99990' and t.STOCK_YYMM='{_mym}'
group by t.mat_code order by t.mat_code
""")
_mo=lambda k: sum((r.get(k) or 0) for r in DB['monthLedger'])
print(f"monthLedger(자재월수불 {_mym}): {len(DB['monthLedger'])}건  기초={_mo('ba'):,.0f} 입고={_mo('ia'):,.0f} 출고={_mo('oa'):,.0f} 기타={_mo('ta'):,.0f} 재고={_mo('sa'):,.0f}")

# ---- 자재불출집계표 (영업, dw_pu_input_140) — LG外 전 매출(유상사급 포함) ----
# 라인 그레인=t2(cust,item,mat,cost,lgroup,sgroup,rate,cur). 창고별/품목별/업체별은 프론트에서 재집계.
DB['lgroupNames'] = {r['cd']:r['nm'] for r in q("SELECT DETAIL_CODE cd, REPLACE(REPLACE(DETAIL_DESC,CHAR(13),''),CHAR(10),'') nm FROM CM_M_MASTER_DETAIL WHERE KIND_CODE='PR005'")}
DB['custInfo'] = {r['cc']:{'biz':r['biz'],'tel':r['tel'],'fax':r['fax']} for r in q("""
  SELECT cust_code cc, isnull(BUSINESS_NO,'') biz, isnull(PHONE_NO,'') tel, isnull(FAX_NO,'') fax FROM cm_m_cust""")}
_DISPATCH_MAGAM = """WITH MAGAM (CUST_CODE, JUN_YYMM, JUN_MAGAM_DAY, MAGAM_DAY) AS (
  SELECT CUST_CODE
    ,format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') jun_yymm
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='2607' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM CM_M_CUST A )"""
def _dispatch_inner(dc):
    return f"""
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC) CUST_DESC, C2.CUST_TYPE, A.MAT_CODE, A.MAINT_COST, A.MAINT_COST KRW_MAINT_COST, A.ITEM_CODE,
     MAX(M.ITEM_DESC) ITEM_DESC, MAX(M.ITEM_SPEC) ITEM_SPEC, MAX(M.UNIT) UNIT, M.ITEM_LGROUP, M.ITEM_SGROUP,
     SUM(-A.MAINT_QTY) MAINT_QTY, SUM(-A.MAINT_AMT) MAINT_AMT, SUM(-A.MAINT_AMT) KRW_MAINT_AMT, SUM(-A.MAINT_VAT) MAINT_VAT, SUM(-A.MAINT_VAT) KRW_MAINT_VAT,
     1 EXCHANGE_RATE, MAX(M.IN_CUST_CODE) IN_CUST_CODE, 'KRW' CURRENCY, MAX(M.ITEM_WEIGHT) ITEM_WEIGHT
    FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.MAINT_TAG IN ('5')
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.GAGONG_PROC_CODE,A.MAT_CODE,A.ITEM_CODE,C2.CUST_TYPE,A.MAINT_COST,M.ITEM_LGROUP,M.ITEM_SGROUP
   UNION ALL
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC), C2.CUST_TYPE, A.ITEM_CODE, A.MAINT_COST, A.MAINT_COST, '',
     MAX(M.ITEM_DESC), MAX(M.ITEM_SPEC), MAX(M.UNIT), M.ITEM_LGROUP, M.ITEM_SGROUP,
     SUM(-A.MAINT_QTY), SUM(-A.MAINT_AMT), SUM(-A.MAINT_AMT), SUM(-A.MAINT_VAT), SUM(-A.MAINT_VAT), 1, MAX(M.IN_CUST_CODE), 'KRW', MAX(M.ITEM_WEIGHT)
    FROM SA_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.ITEM_CODE=M.ITEM_CODE JOIN CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.MAINT_TAG IN ('R')
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,M.ITEM_LGROUP,M.ITEM_SGROUP
   UNION ALL
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC), C2.CUST_TYPE, A.MAT_CODE, A.MAINT_COST, (A.MAINT_COST*A.EXCHANGE_RATE), A.ITEM_CODE,
     MAX(M.ITEM_DESC), MAX(M.ITEM_SPEC), MAX(M.UNIT), M.ITEM_LGROUP, M.ITEM_SGROUP,
     SUM(A.MAINT_QTY), SUM(A.MAINT_AMT), SUM(A.TAXPAYERS), 0, 0, A.EXCHANGE_RATE, MAX(M.IN_CUST_CODE), A.CURRENCY, MAX(M.ITEM_WEIGHT)
    FROM PU_T_STOCK_MAINT_C A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.DIVISION='Q'
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.MAT_CODE,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,A.EXCHANGE_RATE,M.ITEM_LGROUP,M.ITEM_SGROUP,A.CURRENCY"""
def _dispatch(dc):
    return q_live(f"""{_DISPATCH_MAGAM}
    SELECT T.CUST_CODE cc, MAX(T.CUST_DESC) cnm, T.CUST_TYPE ct, T.MAT_CODE mat, T.ITEM_CODE ic,
      MAX(T.ITEM_DESC) nm, MAX(T.ITEM_SPEC) spec, MAX(T.UNIT) unit, T.ITEM_LGROUP lg, T.ITEM_SGROUP sg,
      T.MAINT_COST cost, T.KRW_MAINT_COST kcost, T.EXCHANGE_RATE rate, T.CURRENCY cur,
      (SELECT CUST_DESC FROM CM_M_CUST WHERE CUST_CODE=MAX(T.IN_CUST_CODE)) incust, isnull(MAX(T.ITEM_WEIGHT),0) wt,
      SUM(T.MAINT_QTY) qty, SUM(T.MAINT_AMT) amt, SUM(T.MAINT_VAT) vat, SUM(T.KRW_MAINT_AMT) kamt, SUM(T.KRW_MAINT_VAT) kvat
    FROM ({_dispatch_inner(dc)}) T
    GROUP BY T.CUST_CODE,T.CUST_TYPE,T.ITEM_CODE,T.MAT_CODE,T.ITEM_LGROUP,T.ITEM_SGROUP,T.MAINT_COST,T.KRW_MAINT_COST,T.EXCHANGE_RATE,T.CURRENCY""")
DB['dispatchYm'] = '2026-07'
DB['dispatchClose'] = _dispatch("A.MAINT_YMD > mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD <= '2607'+mg.magam_day")
DB['dispatchIssue'] = _dispatch("A.MAINT_YMD between '260701' and '260718'")
for _lbl,_k in (("마감",'dispatchClose'),("불출",'dispatchIssue')):
    _q=sum((r.get('qty') or 0) for r in DB[_k]); _a=sum((r.get('amt') or 0) for r in DB[_k]); _cu=len(set(r['cc'] for r in DB[_k]))
    print(f"dispatch({_lbl}기준 2607): {len(DB[_k])}라인 {_cu}업체 수량={_q:,.2f} 금액={_a:,.0f}")

outdir = r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js"
os.makedirs(outdir, exist_ok=True)
with open(os.path.join(outdir,"data.js"), "w", encoding="utf-8") as f:
    f.write("// 실데이터 스냅샷 (PARTNER_ERP_TEST2, 차세대 스키마) — 자동생성\nconst DB = ")
    f.write(json.dumps(DB, ensure_ascii=False, indent=0))
    f.write(";\n")
print("data.js 생성완료")
print("items:", len(DB['items']), "partners:", len(DB['partners']), "bom comps:", len(DB['bomExample']['comps']), "parent:", bom_parent)
print("dashboard:", {k:v for k,v in DB['dashboard'].items() if not isinstance(v,list)})
