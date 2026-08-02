# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects")
from db_client import run_query

def show(title, q):
    print(f"\n===== {title} =====")
    try:
        print(run_query(q).to_string(index=False))
    except Exception as e:
        print("ERR:", e)

# 1. 무결성: PK/FK/제약 존재 여부 (표준 ERP는 PK/FK 필수)
show("1A. 테이블 총수 / PK 없는 테이블 수", """
SELECT
 (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE') AS total_tables,
 (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES t
    WHERE TABLE_TYPE='BASE TABLE'
      AND NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS c
                      WHERE c.TABLE_NAME=t.TABLE_NAME AND c.CONSTRAINT_TYPE='PRIMARY KEY')
 ) AS tables_without_pk
""")

show("1B. 제약조건 종류별 개수 (FK/PK/UNIQUE/CHECK)", """
SELECT CONSTRAINT_TYPE, COUNT(*) cnt
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
GROUP BY CONSTRAINT_TYPE ORDER BY cnt DESC
""")

show("1C. 외래키(FK) 총 개수", """
SELECT COUNT(*) AS foreign_keys
FROM sys.foreign_keys
""")

# 2. 백업/임시/한글/날짜본 테이블 난립 (표준 ERP엔 없음)
show("2A. 백업·스냅샷·임시 테이블 추정 개수", """
SELECT
 SUM(CASE WHEN LOWER(TABLE_NAME) LIKE '%bak%' THEN 1 ELSE 0 END) AS bak_tables,
 SUM(CASE WHEN TABLE_NAME LIKE '%[_]2[0-9][0-9][0-9][0-9][0-9]%' THEN 1 ELSE 0 END) AS dated_snapshot_tables,
 SUM(CASE WHEN LOWER(TABLE_NAME) LIKE 'temp%' OR LOWER(TABLE_NAME) LIKE '%temp%' OR LOWER(TABLE_NAME) LIKE 'tmp%' THEN 1 ELSE 0 END) AS temp_tables,
 SUM(CASE WHEN LOWER(TABLE_NAME) LIKE 'res[_]%' THEN 1 ELSE 0 END) AS res_helper_tables,
 SUM(CASE WHEN TABLE_NAME LIKE '%[가-힣]%' THEN 1 ELSE 0 END) AS korean_named_tables
FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'
""")

show("2B. 한글 명 테이블 샘플", """
SELECT TOP 20 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE' AND TABLE_NAME LIKE '%[가-힣]%' ORDER BY TABLE_NAME
""")

# 3. 데이터 타입 안티패턴: 날짜를 varchar로 저장
show("3A. 날짜성 컬럼(YMD/DATE/YM)인데 문자형으로 저장된 컬럼 수", """
SELECT COUNT(*) AS date_as_string_cols
FROM INFORMATION_SCHEMA.COLUMNS
WHERE (UPPER(COLUMN_NAME) LIKE '%YMD%' OR UPPER(COLUMN_NAME) LIKE '%_YM' OR UPPER(COLUMN_NAME) LIKE '%DATE%')
  AND DATA_TYPE IN ('varchar','nvarchar','char','nchar')
""")

show("3B. 전체 컬럼 대비 문자형(varchar) 비율", """
SELECT DATA_TYPE, COUNT(*) cols
FROM INFORMATION_SCHEMA.COLUMNS
GROUP BY DATA_TYPE ORDER BY cols DESC
""")

# 4. 감사컬럼(INSERT_IP/COMPUTER/WINDOW 등) 중복 만연 — 테이블마다 반복
show("4A. 감사성 컬럼이 몇 개 테이블에 반복되는가", """
SELECT COLUMN_NAME, COUNT(*) AS in_how_many_tables
FROM INFORMATION_SCHEMA.COLUMNS
WHERE COLUMN_NAME IN ('INSERT_IP','INSERT_COMPUTER','INSERT_WINDOW','INSERT_USER_ID','INSERT_DATETIME',
                      'UPDATE_IP','UPDATE_COMPUTER','UPDATE_WINDOW','UPDATE_USER_ID','UPDATE_DATETIME')
GROUP BY COLUMN_NAME ORDER BY in_how_many_tables DESC
""")

# 5. 반복그룹(비정규화): B1~B5_MAT_CODE 처럼 번호붙은 반복 컬럼
show("5A. 반복그룹 컬럼(번호 접미) 예: %1_/%2_ 패턴 상위", """
SELECT TOP 25 TABLE_NAME, COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE COLUMN_NAME LIKE 'B[1-5][_]MAT[_]CODE'
   OR COLUMN_NAME LIKE '%[1-9]_MAT_CODE'
ORDER BY TABLE_NAME, COLUMN_NAME
""")

# 6. 명명규칙 일관성: 대소문자 혼용 테이블
show("6A. 소문자로 시작하거나 대소문자 혼용된 테이블 수 (표준: 일관 규칙)", """
SELECT
 SUM(CASE WHEN TABLE_NAME COLLATE Latin1_General_CS_AS LIKE '[a-z]%' THEN 1 ELSE 0 END) AS starts_lowercase,
 SUM(CASE WHEN TABLE_NAME COLLATE Latin1_General_CS_AS LIKE '[A-Z]%' THEN 1 ELSE 0 END) AS starts_uppercase
FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'
""")

# 7. 도메인(접두어)별 테이블 분포 = 모듈 구성 파악
show("7A. 접두어(모듈)별 테이블 분포", """
SELECT LEFT(TABLE_NAME, CHARINDEX('_', TABLE_NAME+'_')-1) AS prefix, COUNT(*) cnt
FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'
GROUP BY LEFT(TABLE_NAME, CHARINDEX('_', TABLE_NAME+'_')-1)
HAVING COUNT(*) >= 5
ORDER BY cnt DESC
""")
