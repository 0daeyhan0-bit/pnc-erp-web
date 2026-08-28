# -*- coding: utf-8 -*-
"""마감관리 스키마 (멱등) — nx.period_close(잠금) + nx.stock_snapshot(확정 스냅샷)

설계 근거(기록):
  · nextgen-erp-close-settlement : 마감=잠금 · 일마감⊂월마감 · 취소는 권한자+로그 · 마감상태 테이블(도메인/일월/기간/상태/마감일시자)
  · nextgen-erp-material-close   : "마감 시점에 스냅샷 생성 = 다음달 기초재고. 월마감·일마감 동일 개념."
                                   스냅샷=f(원장) → nx.stock_snapshot(period_type 일/월 통합) 확정 + nx.period_close 잠금
  · STOCK_GATING_CLOSE_LOCK_RULES: 규칙B 마감된 기간 CRUD 금지 · 공용 assert_open

검증 근거(2026-08-27, 읽기전용 전수대조):
  nx.mat_stock_daily 월말잔량 == 레거시 PU_T_MONTH_STOCK_WH  →  2606 2,342/2,342 · 2607 2,534/2,534 = 100.00%
  '레거시만' 1,195품목은 전부 재고0(금액0) → 커버리지 갭 무해
  ∴ 자재 마감 스냅샷은 mat_stock_daily 를 확정(freeze)하면 된다.

사용: python _migration/create_period_close.py [--commit]
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
from common import _nx

COMMIT = "--commit" in sys.argv

DDL = [
 ("nx.period_close", """
CREATE TABLE nx.period_close (
  domain      varchar(10)  NOT NULL,   -- MAT 자재 / PRD 생산 / SAL 영업
  ptype       char(1)      NOT NULL,   -- D 일마감 / M 월마감
  period      varchar(6)   NOT NULL,   -- D=YYMMDD · M=YYMM
  close_flag  bit          NOT NULL CONSTRAINT DF_period_close_flag DEFAULT(1),
  close_user  varchar(30)  NULL,
  close_dt    datetime     NULL,
  reopen_user varchar(30)  NULL,
  reopen_dt   datetime     NULL,
  note        varchar(200) NULL,
  CONSTRAINT PK_period_close PRIMARY KEY (domain, ptype, period)
)"""),
 ("nx.stock_snapshot", """
CREATE TABLE nx.stock_snapshot (
  domain     varchar(10)   NOT NULL,   -- MAT / PRD / SAL
  ptype      char(1)       NOT NULL,   -- D / M
  period     varchar(6)    NOT NULL,
  item_code  varchar(50)   NOT NULL,
  stock_qty  decimal(18,4) NOT NULL CONSTRAINT DF_snap_qty  DEFAULT(0),
  stock_amt  decimal(18,4) NOT NULL CONSTRAINT DF_snap_amt  DEFAULT(0),
  avg_cost   decimal(18,4) NULL,
  in_qty     decimal(18,4) NULL,
  out_qty    decimal(18,4) NULL,
  close_dt   datetime      NULL,
  CONSTRAINT PK_stock_snapshot PRIMARY KEY (domain, ptype, period, item_code)
)"""),
]
IDX = [("ix_snap_period", "CREATE INDEX ix_snap_period ON nx.stock_snapshot(domain, ptype, period)")]

cn = _nx(); cur = cn.cursor()
def exists(obj):
    cur.execute("SELECT OBJECT_ID(?)", obj); return cur.fetchone()[0] is not None
def idx_exists(nm, tbl):
    cur.execute("SELECT 1 FROM sys.indexes WHERE name=? AND object_id=OBJECT_ID(?)", nm, tbl)
    return cur.fetchone() is not None

todo = []
for name, ddl in DDL:
    if exists(name): print(f"  {name:<22} 이미 있음 — 생략(멱등)")
    else: todo.append((name, ddl)); print(f"  {name:<22} 신규 생성 대상")
for nm, ddl in IDX:
    if exists("nx.stock_snapshot") and idx_exists(nm, "nx.stock_snapshot"):
        print(f"  {nm:<22} 이미 있음 — 생략")
    else: todo.append((nm, ddl)); print(f"  {nm:<22} 신규 생성 대상")

if not todo:
    print("\n변경 없음(멱등).")
elif not COMMIT:
    print("\nDRY-RUN — --commit 으로 적용")
else:
    for name, ddl in todo:
        cur.execute(ddl); print(f"  생성: {name}")
    cn.commit()
    print("\n적용 완료. 확인:")
    for t in ("nx.period_close", "nx.stock_snapshot"):
        cur.execute(f"SELECT COUNT(*) FROM {t}"); print(f"  {t:<22} {cur.fetchone()[0]}행")
cn.close()
