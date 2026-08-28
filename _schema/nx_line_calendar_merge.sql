/* ══════════════════════════════════════════════════════════════════════════
   nx.line_calendar 통합 — 라인별 달력 정본화 (2026-08-27)

   문제: 라인 달력이 두 테이블로 갈려 있었다.
     nx.PR_M_LINE_CALENDAR  레거시 미러(18,264행·37라인) — 편성(planrev.py)이 읽음
     nx.line_calendar       웹 자체(650행·8라인)         — LG 엑셀 업로드 대상
   → LG 엑셀을 업로드해도 편성에 반영되지 않았다.

   조치: 웹 자체 테이블 nx.line_calendar 를 **정본**으로 삼고 미러분을 이관.
         (CLAUDE.md §1-9 ★마스터 정본 = 재구축 클린본, 레거시 미러 아님)

   컬럼 의미가 서로 달라 분리해서 담는다:
     work_code   = LG 라인스케줄 가동시간 (8 · 11 · 10.5 · 9.5 · 7.5 …) — LG 엑셀 업로드분
     work_stats  = 근무유형 코드 1~7 — 레거시 미러 이관분·수기 입력분
       1 잔업2시간 19:30 · 2 정상근무 17:00 · 3 일요일 · 4 휴무
       5 잔업3시간 20:30 · 6 잔업4시간 21:30 · 7 4시간근무 12:00
     src         = 'LG'(엑셀) | 'MIRROR'(레거시 이관) | 'MANUAL'(수기)

   종업시각 우선순위(planrev.py _end_of):
     work_code(가동시간) → work_stats(코드) → 공통달력 → 기본 19:30
   ══════════════════════════════════════════════════════════════════════════ */

-- 1) 컬럼 추가 (멱등)
IF COL_LENGTH('nx.line_calendar','work_stats') IS NULL
    ALTER TABLE nx.line_calendar ADD work_stats varchar(1) NULL;
GO
IF COL_LENGTH('nx.line_calendar','src') IS NULL
    ALTER TABLE nx.line_calendar ADD src varchar(8) NULL;
GO

-- 2) 기존 650행(LG 엑셀 업로드분) 출처 표시
UPDATE nx.line_calendar SET src='LG' WHERE src IS NULL;
GO

-- 3) 레거시 미러 → 정본 이관 (없는 (라인,일자)만)
INSERT INTO nx.line_calendar(line_no, cal_ymd, work_code, work_stats, note, src, upd_dt)
SELECT RTRIM(m.LINE_NO),
       CONVERT(date, '20' + m.CALENDAR_YMD, 112),
       NULL,                                    -- 가동시간은 미러에 없다
       RTRIM(m.WORK_STATS),
       NULLIF(RTRIM(ISNULL(m.REMARKS,'')), ''),
       'MIRROR',
       GETDATE()
  FROM nx.PR_M_LINE_CALENDAR m
 WHERE LEN(RTRIM(ISNULL(m.CALENDAR_YMD,''))) = 6
   AND ISDATE('20' + m.CALENDAR_YMD) = 1
   AND NOT EXISTS (SELECT 1 FROM nx.line_calendar c
                    WHERE c.line_no = RTRIM(m.LINE_NO)
                      AND c.cal_ymd = CONVERT(date, '20' + m.CALENDAR_YMD, 112));
GO

-- 4) 인덱스 (조회·편성용)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_lcal_ymd' AND object_id=OBJECT_ID('nx.line_calendar'))
    CREATE INDEX ix_lcal_ymd ON nx.line_calendar(cal_ymd, line_no) INCLUDE(work_code, work_stats);
GO

-- 5) 검증
SELECT src, COUNT(*) rows_, COUNT(DISTINCT line_no) lines_,
       MIN(cal_ymd) from_, MAX(cal_ymd) to_
  FROM nx.line_calendar GROUP BY src ORDER BY src;
