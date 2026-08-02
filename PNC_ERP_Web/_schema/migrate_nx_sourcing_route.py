# -*- coding: utf-8 -*-
"""조달경로 통합검토 재설계 — nx.sourcing_route(경로 헤더) + nx.sourcing_route_line(경로별 BOM 라인).
멱등(IF OBJECT_ID). 기존 nx.sourcing_path(include 토글)/nx.procgroup_alloc/nx.sub_variant_map 는 건드리지 않음(하위호환).
헤더: item_code·route_no·vendor·구분·현행flag·approve_flag(개발 승인 게이트)·유효일자.
라인: 하위품번·품명·소요량·구분(제작/매입/사급)·공급처·소재계산(외경/두께/길이/재질)·규격/비고.
approve_flag=1 후보만 조달프로파일에 노출(단일 소스 정합)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc

cs = (f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
      f"DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
cn = pyodbc.connect(cs, autocommit=True); cur = cn.cursor()

cur.execute("""IF OBJECT_ID('nx.sourcing_route','U') IS NULL CREATE TABLE nx.sourcing_route(
    route_id     INT IDENTITY(1,1) PRIMARY KEY,
    item_code    NVARCHAR(60) NOT NULL,     -- 우리 기준 품목(모품번)
    route_no     INT NOT NULL,              -- 1=현행 baseline, 2..=대안 후보
    route_name   NVARCHAR(80),
    vendor_code  NVARCHAR(20),              -- 공급처(구분!=자체면 필수)
    gubun        NVARCHAR(20),              -- 자체/매입/외주유상/외주무상
    current_flag BIT DEFAULT 0,            -- 현행 여부(baseline)
    approve_flag BIT DEFAULT 0,            -- 개발 승인(=1 이라야 조달프로파일 후보로 노출)
    apply_from   DATE,                      -- 적용시작(유효일자)
    note         NVARCHAR(200),
    ins_user     NVARCHAR(30), ins_dt datetime DEFAULT getdate(),
    upd_user     NVARCHAR(30), upd_dt datetime DEFAULT getdate())""")

cur.execute("""IF OBJECT_ID('nx.sourcing_route_line','U') IS NULL CREATE TABLE nx.sourcing_route_line(
    line_id     INT IDENTITY(1,1) PRIMARY KEY,
    route_id    INT NOT NULL,
    sort_seq    INT DEFAULT 0,
    child_item  NVARCHAR(60),               -- 하위품번(필수)
    child_name  NVARCHAR(120),              -- 품명(필수)
    qty         FLOAT,                       -- 소요량(계산 필수, >0)
    gubun       NVARCHAR(20),               -- 제작/매입/사급(필수)
    vendor_code NVARCHAR(20),               -- 공급처(매입/외주면 필수)
    is_rawmat   BIT DEFAULT 0,             -- 소재계산 대상(=1 이면 아래 4필드 필수)
    diam        FLOAT, thick FLOAT, len_val FLOAT, material NVARCHAR(40),
    spec        NVARCHAR(80),               -- 규격(선택)
    note        NVARCHAR(200))""")           # 비고(선택)

# 인덱스(조회 최적화)
cur.execute("""IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_sr_item')
    CREATE INDEX IX_sr_item ON nx.sourcing_route(item_code, route_no)""")
cur.execute("""IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_srl_route')
    CREATE INDEX IX_srl_route ON nx.sourcing_route_line(route_id, sort_seq)""")

for t in ("nx.sourcing_route", "nx.sourcing_route_line"):
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"{t}: {cur.fetchone()[0]} rows")
print("migrate_nx_sourcing_route OK")
cn.close()
