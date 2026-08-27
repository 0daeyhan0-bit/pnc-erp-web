/* nx.v_prod_plan_input_new — 웹 생산계획추가입력(nx.prod_plan_input) → 레거시 PR_T_PLAN_INPUT 호환 뷰.

   용도: 가공이동580 SP(nx.SP_PR_가공창고_이동계획_WEBPLAN)의 ③예외생산 앵커.
         SP 는 A.PLAN_YMD / A.ITEM_CODE 처럼 **대문자**로 참조하는데
         웹 테이블은 컬럼이 소문자라 직접 참조하면 깨진다 → 이름만 맞춰 노출한다.

   ★2026-08-27 신설. 배경:
     화면 소스='신규DB(웹계획)' 인데 계획 3갈래 중 ①파트별만 웹이고
     ②품목별·③예외생산은 레거시라 혼합 결과가 나왔다(사용자: "계획이 다르다").
     ③ 전환의 전제였던 데이터 공백(웹 260814 까지만)은 같은 날 이관으로 해소:
     오늘 이후 782행·수량 443,596 양쪽 동일·누락 0.

   SP 가 이 뷰에서 쓰는 컬럼 = PLAN_YMD · WORK_ORDER · ITEM_CODE · OUTPUT_HM · LINE_NO · PLAN_QTY.
   나머지는 레거시 원본과 형태를 맞추기 위해 함께 노출한다(값이 없으면 '' / 0).
*/
CREATE VIEW nx.v_prod_plan_input_new AS
SELECT
    CAST(p.plan_ymd   AS varchar(6))   AS PLAN_YMD,
    CAST(p.work_order AS varchar(20))  AS WORK_ORDER,
    CAST(p.item_code  AS varchar(20))  AS ITEM_CODE,
    CAST(ISNULL(p.output_hm,'') AS varchar(4))  AS OUTPUT_HM,
    CAST(ISNULL(p.line_no,'')   AS varchar(10)) AS LINE_NO,
    CAST(ISNULL(p.plan_qty,0)   AS int)         AS PLAN_QTY,
    CAST(ISNULL(p.work_code,'') AS varchar(10)) AS WORK_CODE,
    CAST(ISNULL(p.prod_tag,'')  AS varchar(1))  AS PROD_TAG,
    CAST(ISNULL(p.remarks,'')   AS varchar(255)) AS REMARKS,
    CAST('' AS varchar(2))  AS AM_PM,
    CAST('' AS varchar(1))  AS PROD_FINISH_FLAG,
    CAST(0  AS int)         AS PROD_FINISH_QTY,
    CAST(0  AS int)         AS WORK_QTY
  FROM nx.prod_plan_input p
