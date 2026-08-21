/* ===== PNC ERP screens.sales.js — 영업 SCREEN (app.js 분할, 순수이동) ===== */

/* 제품입출고현황 (영업, dw_pr_stock_110) — 좌:제품(P/N)재고(수불장) 우:선택품목 입출고이력. item기준(파트없음), 전월이월 2502기준 */
SCREEN.prodinvout=(c)=>{
  const API=API_BASE;
  let rows=[], mv={}, curYm='', loading=false, msg='';   // rows=[item,desc,workNm,stock,bf]
  const fmtYmd=y=>{y=(''+(y||'')).trim();return (y.length>=6&&y!=='000000')?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:'00/00/00';};
  // ★레거시 dw_pr_stock_110과 동일: 수불기간(frm~to) 일범위. 기본=이달1일~오늘.
  const _pad=n=>(''+n).padStart(2,'0');
  const _tod=(()=>{const d=new Date();return `${(''+d.getFullYear()).slice(2)}${_pad(d.getMonth()+1)}${_pad(d.getDate())}`;})();
  let frm=_tod.slice(0,4)+'01', to=_tod;   // YYMMDD 수불기간
  const ymd2d=y=>{y=(''+(y||'')).trim();return y.length>=6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';};
  const d2ymd=v=>{v=(''+(v||'')).trim();return v.length>=10?v.slice(2,4)+v.slice(5,7)+v.slice(8,10):'';};
  let sel=null, curL=[], source='live';   // ★Phase5 데이터원(기본 라이브 무변경)
  const load=async()=>{loading=true;msg='';sel=null;
    const st=c.querySelector('#lbody');if(st)st.innerHTML=spinRow(4);
    const qs=`frm=${encodeURIComponent(frm)}&to=${encodeURIComponent(to)}`;
    if(source==='nx'){loading=false;return nxDerivedView(c,`${API}/api/live/prodinvout?${qs}&source=nx`,{title:'제품입출고현황',onBack:()=>{source='live';load();}});}
    try{const r=await fetch(`${API}/api/live/prodinvout?${qs}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();curYm=j.ym||to.slice(0,4)||'';rows=j.stock||[];mv=j.moves||{};}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];mv={};}
    loading=false;
    const fi=c.querySelector('#frm'),ti=c.querySelector('#to');if(fi)fi.value=ymd2d(frm);if(ti)ti.value=ymd2d(to);
    const ws=[...new Set(rows.map(r=>r[2]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ko'));
    const wsel=c.querySelector('#work');if(wsel){const v=wsel.value;wsel.innerHTML='<option value="">전체</option>'+ws.map(w=>`<option value="${esc(w)}">${esc(w)}</option>`).join('');wsel.value=v;}
    const sub=c.querySelector('#piv-sub');if(sub)sub.innerHTML=`제품(P/N)별 재고 + 선택품목 입출고이력(누적재고) · 원본 <code>SA_T_STOCK_MAINT</code> 외 · 🟢 수불기간 ${esc(ymd2d(frm))}~${esc(ymd2d(to))}(이월기준 2502) · 0재고 숨김`;
    renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 품목을 클릭하세요</div>';};
  c.innerHTML=`
   <div class="page-title">🔁 제품입출고현황</div>
   <div class="page-sub" id="piv-sub">제품(P/N)별 재고 + 선택품목 입출고이력(누적재고) · 원본 <code>SA_T_STOCK_MAINT</code> 외 · 🟢 nx(이월기준 2502) · 0재고 숨김</div>
   <div class="toolbar">
     <label class="tl">수불기간</label><input type="date" class="inp" id="frm" value="${esc(ymd2d(frm))}" style="min-width:130px"><span style="color:var(--muted);align-self:center">~</span><input type="date" class="inp" id="to" value="${esc(ymd2d(to))}" style="min-width:130px">
     <label class="tl">작업처</label><select class="sel" id="work"><option value="">전체</option></select>
     <input class="inp" id="q" placeholder="P/N·품명">
     <select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
     <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
     <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
   </div>
   <div style="display:flex;gap:10px;align-items:flex-start">
     <div style="flex:0 0 46%;min-width:0">
       <div class="summary-bar" id="lsum"></div>
       <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead><tr><th>P/N</th><th>품명</th><th class="num">재고</th><th>작업처</th></tr></thead><tbody id="lbody"></tbody></table></div>
       <div class="rowcount" id="lcnt"></div>
     </div>
     <div style="flex:1;min-width:0">
       <div class="summary-bar" id="rhead"><div class="s-item">← 좌측에서 품목을 클릭하세요</div></div>
       <div class="grid-wrap" style="max-height:548px;overflow:auto"><table class="tbl fit"><thead><tr><th class="center">입출고일자</th><th class="num">기초재고</th><th class="num">입고</th><th class="num">기타출고</th><th class="num">출고</th><th class="num">재고수량</th><th>구분</th><th>사용이력</th></tr></thead><tbody id="rbody"></tbody></table></div>
     </div>
   </div>`;
  const renderRight=item=>{
    const row=rows.find(r=>r[0]===item)||[]; const bf=+row[4]||0;
    const lines=(mv[item]||[]).slice().sort((a,b)=>(''+a[0]).localeCompare(''+b[0],'ko'));
    let bal=bf, html=`<tr><td class="center">00/00/00</td><td class="num">${won(bf)}</td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num qty"><b>${won(bf)}</b></td><td>전월이월</td><td></td></tr>`;
    let si=0,se=0,so=0;
    lines.forEach(r=>{const prev=bal; const i=+r[1]||0,o=+r[2]||0,e=+r[3]||0; bal=prev+i-o-e; si+=i;so+=o;se+=e;  // 재고=기초+입고-출고-기타출고
      html+=`<tr><td class="center">${fmtYmd(r[0])}</td><td class="num">${won(prev)}</td><td class="num">${i?won(i):''}</td><td class="num">${e?won(e):''}</td><td class="num">${o?won(o):''}</td><td class="num qty"><b>${won(bal)}</b></td><td>${esc(r[4])||''}</td><td class="cap" title="${esc(r[5]||'')}">${esc(r[5]||'')}</td></tr>`;});
    html+=`<tr class="grandtot"><td class="center">총계</td><td class="num">${won(bf)}</td><td class="num">${won(si)}</td><td class="num">${won(se)}</td><td class="num">${won(so)}</td><td class="num">${won(bal)}</td><td colspan="2"></td></tr>`;
    c.querySelector('#rbody').innerHTML=html;
    c.querySelector('#rhead').innerHTML=`<div class="s-item">P/N <b>${esc(item)}</b></div><div class="s-item">${esc(row[1]||'')}</div><div class="s-item">현재고 <b>${won(bal)}</b></div>`;
    attachResizers(c);
  };
  const renderLeft=()=>{
    const q=c.querySelector('#q').value.trim().toLowerCase(), gb=c.querySelector('#gubun').value, wf=c.querySelector('#work').value;
    curL=rows.filter(r=>(!wf||r[2]===wf)&&(gb==='all'||(gb==='plus'?r[3]>0:r[3]<0))&&(!q||(''+r[0]).toLowerCase().includes(q)||(''+r[1]).toLowerCase().includes(q)))
      .sort((a,b)=>(''+a[0]).localeCompare(''+b[0],'ko'));
    const tot=curL.reduce((a,b)=>a+(+b[3]||0),0);
    let lb=curL.map(r=>`<tr data-item="${esc(r[0])}" class="${sel===r[0]?'sel':''}"><td><b>${esc(r[0])}</b></td><td class="cap" title="${esc(r[1])}">${esc(r[1])}</td><td class="num qty">${won(r[3])}</td><td class="cap" title="${esc(r[2])}">${esc(r[2])}</td></tr>`).join('');
    if(curL.length)lb+=`<tr class="grandtot"><td colspan="2" class="right">총계 (${won(curL.length)} 품목)</td><td class="num">${won(tot)}</td><td></td></tr>`;
    c.querySelector('#lbody').innerHTML=curL.length?lb:`<tr><td colspan="4" class="empty">결과 없음</td></tr>`;
    c.querySelector('#lbody').querySelectorAll('tr[data-item]').forEach(tr=>tr.onclick=()=>{sel=tr.dataset.item;c.querySelectorAll('#lbody tr').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');renderRight(sel);});
    c.querySelector('#lsum').innerHTML=`<div class="s-item">품목 <b>${won(curL.length)}</b></div><div class="s-item">재고 합계 <b>${won(tot)}</b></div>`;
    c.querySelector('#lcnt').textContent=`${curL.length}품목 (0재고 제외)`;
    attachResizers(c);
  };
  const _reload=()=>{frm=d2ymd(c.querySelector('#frm').value)||frm;to=d2ymd(c.querySelector('#to').value)||to;load();};
  c.querySelector('#go').onclick=_reload;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')renderLeft();};
  c.querySelector('#nxsrc').onclick=()=>{source='nx';load();};   // ★Phase5 nx 파생 보기
  c.querySelector('#gubun').onchange=renderLeft;c.querySelector('#work').onchange=renderLeft;
  c.querySelector('#frm').onchange=_reload;c.querySelector('#to').onchange=_reload;
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#gubun').value='all';c.querySelector('#work').value='';sel=null;renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 품목을 클릭하세요</div>';};
  c.querySelector('#xls').onclick=()=>downloadCSV('제품입출고현황.csv',['P/N','품명','재고','작업처'],curL.map(r=>[r[0],r[1],r[3],r[2]]));
  load();
};

/* 영업예상매출현황 (영업, dw_pr_plan_190) — 도번×일별 수량 피벗 + 하단 일별 금액줄. ★차감=LG리시빙(20일 백로그), 21일+ 라이브일치. 차감전/차감후 토글 */
SCREEN.salesforecast=(c)=>{
  const API=API_BASE;
  let F={days:[],rows:[],base:''}, loading=true, mode='net', cur=[], metric='sales', reqSeq=0, sortKey='', sortDir=1, cutf='';   // mode:net(차감후)|gross(차감전=라이브) · metric:sales(영업예상매출)|sagub(예상 LG사급금액) · sortKey/Dir:헤더더블클릭 정렬 · cutf:구분(절삭/설치)필터
  let sfTimer=null;   // ★날짜 재조회 디바운스 타이머(SCREEN레벨 유지). 두자리(08) 입력 중 재렌더로 input이 교체돼 편집 깨지는 버그 방지
  // ★기본 기간 = 당일 ~ 당월말
  const _p2=n=>(''+n).padStart(2,'0');
  const _defRange=()=>{const n=new Date();const e=new Date(n.getFullYear(),n.getMonth()+1,0);
    return [`${(''+n.getFullYear()).slice(2)}${_p2(n.getMonth()+1)}${_p2(n.getDate())}`,
            `${(''+e.getFullYear()).slice(2)}${_p2(e.getMonth()+1)}${_p2(e.getDate())}`];};
  const WD=['일','월','화','수','목','금','토'];
  const CUTCLR={'절삭':'#1c47a0','설치':'#1c7c3a','분지관':'#b8860b','이지링크':'#8e44ad'};   // 구분(절삭/설치) 색
  const cutBadge=v=>v?`<span style="font-size:11px;font-weight:700;color:${CUTCLR[v]||'#5a7597'}">${esc(v)}</span>`:'<span style="color:#c9d3e0">-</span>';
  const dlabel=y=>{y=''+y;const D=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));return `${y.slice(2,4)}/${y.slice(4,6)}<span class="wd">${WD[D.getDay()]}</span>`;};
  const load=async(base,to)=>{loading=true;const mySeq=++reqSeq, myMetric=metric;
    if(base!==undefined&&base!=='')F.base=base; if(to!==undefined)F.to=to;   // ★입력한 기간을 draw 전에 즉시 반영 — 로딩중 재렌더가 날짜 input을 옛값으로 되돌려 편집이 튕기는 버그 방지(08 입력→01 복귀)
    draw();   // ★race가드: 토글 왕복 시 늦게 온 이전 응답이 최신 데이터 덮어쓰기 방지(최신 mySeq만 반영)
    const qs=[];if(base)qs.push('base='+encodeURIComponent(base));if(to)qs.push('to='+encodeURIComponent(to));
    const ep=myMetric==='sagub'?'forecast_sagub':'forecast';
    let d;
    try{const r=await fetch(`${API}/api/sales/${ep}${qs.length?('?'+qs.join('&')):''}`);d=await r.json();if(!d||!d.rows)d={days:[],rows:[],base:''};}
    catch(e){d={days:[],rows:[],base:'',_err:'백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요'};}
    if(mySeq!==reqSeq)return;   // 더 최신 요청이 있으면 이 응답은 폐기
    F=d;loading=false;draw();};
  const draw=()=>{
    const days=F.days||[], rows=F.rows||[];
    const works=[...new Set(rows.map(r=>r.wc).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ko'));
    // 규칙17: 검색 autocomplete — 로드된 rows에서 도번(값)→품명(표시) datalist 생성
    const sfMap=new Map(); rows.forEach(r=>{if(r.item&&!sfMap.has(r.item))sfMap.set(r.item,r.nm||'');});
    const sfOpts=[...sfMap].sort((a,b)=>(''+a[1]).localeCompare(''+b[1],'ko')).map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');
    c.innerHTML=`
     <div class="page-title">📅 영업예상매출현황</div>
     <div class="page-sub">${metric==='sagub'
        ?'🟢 <b>라이브</b> LG 생산계획 기준 <b>예상 LG사급금액</b>(LG사급 2종 중 <b>사급부품</b>·원소재 동 별도) · 계획수량 × 개당 LG사급비(<b>품목별 원가분석과 동일</b>=엔진 material_split, 사급부품 최말단 leaf) · 원화(KRW)'
        :'🟢 <b>라이브</b> LG 생산계획 기준 일별 예상매출 · 원본 <code>sa_t_plan_item_dtl</code>+<code>pr_t_plan_input</code>×단가(<code>pr_m_item_cost</code> S/E=LG판매가) · 레거시 190 재현(차감전=완전일치 검증) · <b>차감후=첫계획일 pr_t_plan_input 과대분 제거</b> · 원화(KRW)'} · 기간 ${esc(F.base||'')}~${esc(F.to||'')}${metric==='sagub'&&F.asof?' · 사급가 기준일 '+esc(F.asof):''}${loading?' · <span style="color:#b8860b">불러오는 중…</span>':''}${F._err?' · <span style="color:#c0392b">'+esc(F._err)+'</span>':''}</div>
     <div class="toolbar">
       <label class="tl">종류</label>
       <div class="toggle-group"><button data-metric="sales" class="${metric==='sales'?'on':''}">영업 예상매출</button><button data-metric="sagub" class="${metric==='sagub'?'on':''}">예상 LG사급금액</button></div>
       <label class="tl">기간</label><input type="date" class="inp" id="sf-base" value="${F.base?('20'+F.base.slice(0,2)+'-'+F.base.slice(2,4)+'-'+F.base.slice(4,6)):''}" title="시작일" style="min-width:135px"><span style="color:var(--muted);margin:0 3px">~</span><input type="date" class="inp" id="sf-to" value="${F.to?('20'+F.to.slice(0,2)+'-'+F.to.slice(2,4)+'-'+F.to.slice(4,6)):''}" title="종료일(비우면 시작일 이후 전체)" style="min-width:135px">
       <label class="tl">구분</label>
       <div class="toggle-group"><button data-mode="net" class="${mode==='net'?'on':''}">차감후(순예상)</button><button data-mode="gross" class="${mode==='gross'?'on':''}">차감전(원계획=라이브)</button></div>
       <select class="sel" id="work"><option value="">전체작업처</option>${works.map(w=>`<option value="${esc(w)}">${esc(w)}</option>`).join('')}</select>
       <select class="sel" id="cutf"><option value="">전체구분</option>${['절삭','설치','분지관','이지링크'].map(g=>`<option value="${g}" ${cutf===g?'selected':''}>${g}</option>`).join('')}</select>
       <input class="inp" id="q" list="sf-ql" placeholder="도번/품명 입력" autocomplete="off"><datalist id="sf-ql">${sfOpts}</datalist>
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <span id="sf-err" style="color:#c0392b;font-size:12px;font-weight:600;display:none;margin-left:6px"></span>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    c.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;draw();});
    // ★날짜 = 네이티브 type=date (달력 아이콘 + 세그먼트 직접 타이핑, UI규칙). value "2026-08-14" → toY로 YYMMDD.
    const toY=el=>{const d=(el.value||'').replace(/\D/g,''); return d.length>=8?d.slice(2,8):(d.length===6?d:'');};
    c.querySelectorAll('[data-metric]').forEach(b=>b.onclick=()=>{if(metric===b.dataset.metric)return;metric=b.dataset.metric;load(toY(c.querySelector('#sf-base')),toY(c.querySelector('#sf-to')));});
    // ★날짜 조회: 검색버튼·날짜 변경·엔터 = 재조회. 시작일 필수·유효, 시작>종료 에러표시. (load가 draw전 F반영이라 08 입력도 안 튐)
    const setSfErr=(m)=>{const e=c.querySelector('#sf-err');if(e){e.textContent=m||'';e.style.display=m?'inline':'none';}};
    const doGo=()=>{const bEl=c.querySelector('#sf-base'),tEl=c.querySelector('#sf-to');const from=toY(bEl),to=toY(tEl);
      if(!from||from.length!==6){setSfErr('⚠ 시작일을 올바르게 입력하세요');return;}
      if((tEl.value||'').trim()&&(!to||to.length!==6)){setSfErr('⚠ 종료일이 올바르지 않습니다');return;}
      if(to&&from>to){setSfErr('⚠ 시작일이 종료일보다 늦습니다');return;}
      setSfErr('');load(from,to);};
    // ★날짜 onchange 자동재조회 제거 — 세그먼트(08) 입력 중 재렌더로 input이 교체돼 편집이 튕기던 버그. 검색버튼·Enter로만 재조회.
    c.querySelector('#sf-base').onkeyup=e=>{if(e.key==='Enter')doGo();}; c.querySelector('#sf-to').onkeyup=e=>{if(e.key==='Enter')doGo();};
    const dayQ=(r,d)=>(mode==='net'?r.ndays:r.gdays)[d]||0;
    const rowQ=r=>mode==='net'?r.nq:r.gq, rowA=r=>mode==='net'?r.namt:r.gamt;
    // ★헤더 더블클릭 정렬: 컬럼별 정렬값(도번/품명/작업처=문자, 합계=금액, 일자=그 날 수량)
    const sortVal=(r,k)=>{ if(k==='item'||k==='nm'||k==='wc'||k==='cut')return r[k]||''; if(k==='amt')return rowA(r); if(k&&k[0]==='d')return dayQ(r,k.slice(2)); return ''; };
    const arrow=k=>sortKey===k?(sortDir===1?' ▲':' ▼'):'';
    const render=()=>{
      const q=c.querySelector('#q').value.trim().toLowerCase(), wf=c.querySelector('#work').value, cf=c.querySelector('#cutf').value;
      cur=rows.filter(r=>(!wf||r.wc===wf)&&(!cf||r.cut===cf)&&(!q||(''+r.item).toLowerCase().includes(q)||(''+r.nm).toLowerCase().includes(q))&&rowQ(r)>0);
      if(sortKey){ cur.sort((a,b)=>{const x=sortVal(a,sortKey),y=sortVal(b,sortKey),nx=+x,ny=+y;
          return (typeof x==='number'||(x!==''&&y!==''&&!isNaN(nx)&&!isNaN(ny)))?(nx-ny)*sortDir:String(x).localeCompare(String(y),'ko')*sortDir;}); }
      else cur.sort((a,b)=>(''+a.item).localeCompare(''+b.item,'ko'));
      const dHdr=days.map(d=>`<th class="num" data-sk="d:${d}" title="더블클릭 정렬">${dlabel(d)}${arrow('d:'+d)}</th>`).join('');
      // ★단가 숨김, 합계·일별 모두 수량(위)/금액(아래) 스택 · th data-sk=더블클릭 정렬키
      c.querySelector('#th').innerHTML=`<tr><th data-sk="item" title="더블클릭 정렬">도번${arrow('item')}</th><th class="cap" data-sk="nm" title="더블클릭 정렬">품명${arrow('nm')}</th><th data-sk="wc" title="더블클릭 정렬">작업처${arrow('wc')}</th><th data-sk="cut" title="더블클릭 정렬">구분${arrow('cut')}</th><th class="num gstock" data-sk="amt" title="더블클릭 정렬(금액)">합계${arrow('amt')}<br><span class="wd">수량/금액</span></th>${dHdr}</tr>`;
      const stack=(q,a)=>`<b class="qty">${won(q)}</b><br><span class="famt">${wonI(a)}</span>`;
      let tb=cur.map(r=>`<tr><td><b>${esc(r.item)}</b></td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td class="cap" title="${esc(r.wc)}">${esc(r.wc)}</td><td class="center">${cutBadge(r.cut)}</td><td class="num gstock">${stack(rowQ(r),rowA(r))}</td>${days.map(d=>{const v=dayQ(r,d);return `<td class="num">${v?stack(v,Math.round(v*r.cost)):''}</td>`;}).join('')}</tr>`).join('');
      const gQ=cur.reduce((a,b)=>a+rowQ(b),0), gA=cur.reduce((a,b)=>a+rowA(b),0);
      const gdQ=days.map(d=>cur.reduce((a,b)=>a+dayQ(b,d),0));
      const gdA=days.map(d=>cur.reduce((a,b)=>a+dayQ(b,d)*b.cost,0));
      if(cur.length){
        // 하단 총계(sticky): 각 칸에 수량/금액 스택
        tb+=`<tr class="grandtot"><td colspan="4" class="right">총계 (${won(cur.length)} 도번)</td><td class="num gstock">${stack(gQ,gA)}</td>${gdQ.map((v,i)=>`<td class="num">${v?stack(v,Math.round(gdA[i])):''}</td>`).join('')}</tr>`;
      }
      c.querySelector('#body').innerHTML=cur.length?tb:`<tr><td colspan="${5+days.length}" class="empty">결과 없음</td></tr>`;
      const sumG=cur.reduce((a,b)=>a+b.gamt,0), sumN=cur.reduce((a,b)=>a+b.namt,0);
      const mlab=metric==='sagub'?'예상 LG사급금액':'예상매출';
      // 절삭/설치 소계(차감후 금액 기준)
      const cutSum=g=>cur.filter(r=>r.cut===g).reduce((a,b)=>a+rowA(b),0);
      const scut=cutSum('절삭'), sseol=cutSum('설치'), setc=rowATot()-scut-sseol;
      function rowATot(){return cur.reduce((a,b)=>a+rowA(b),0);}
      c.querySelector('#sum').innerHTML=`<div class="s-item">도번 <b>${won(cur.length)}</b></div>
        <div class="s-item">차감전(=라이브) <b>${wonI(sumG)} 원</b></div>
        <div class="s-item neg">첫계획일 과대분 제거 <b>-${wonI(sumG-sumN)} 원</b></div>
        <div class="s-item">차감후 ${mlab} <b>${wonI(sumN)} 원</b></div>
        <div class="s-item" style="color:${CUTCLR['절삭']}">절삭 <b>${wonI(scut)} 원</b></div>
        <div class="s-item" style="color:${CUTCLR['설치']}">설치 <b>${wonI(sseol)} 원</b></div>
        ${setc?`<div class="s-item" style="color:#8aa0bd">기타/미분류 <b>${wonI(setc)} 원</b></div>`:''}`;
      c.querySelector('#cnt').textContent=`${cur.length}도번 · ${metric==='sagub'?'예상 LG사급금액 · ':''}${mode==='net'?'차감후':'차감전(라이브)'} · 셀=수량, 하단=금액${metric==='sagub'?'(수량×개당LG사급비)':''} · 헤더 더블클릭=정렬`;
      attachResizers(c);
      // ★헤더 더블클릭 정렬 바인딩(리사이저는 자체 dblclick으로 stopPropagation → 충돌없음)
      c.querySelectorAll('#th th[data-sk]').forEach(th=>{th.style.cursor='pointer';th.ondblclick=()=>{const k=th.dataset.sk;sortDir=sortKey===k?-sortDir:1;sortKey=k;render();};});
    };
    c.querySelector('#go').onclick=doGo;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')render();};   // ★검색=기간 재조회(doGo). 품번검색은 클라이언트 필터(render)
    c.querySelector('#work').onchange=render; c.querySelector('#cutf').onchange=e=>{cutf=e.target.value;render();};
    c.querySelector('#reset').onclick=()=>{mode='net';sortKey='';sortDir=1;cutf='';const[b,t]=_defRange();load(b,t);};   // 초기화=기본기간(당일~당월말) 재조회
    c.querySelector('#xls').onclick=()=>{
      const amtcol=metric==='sagub'?'예상LG사급금액':'예상매출금액', unitcol=metric==='sagub'?'개당LG사급비':'단가';
      const hd=['도번','품명','작업처','구분',unitcol,'합계수량',amtcol].concat(days.map(d=>(''+d).slice(2)+'수량')).concat(days.map(d=>(''+d).slice(2)+'금액'));
      downloadCSV((metric==='sagub'?'예상LG사급금액_':'영업예상매출현황_')+mode+'.csv',hd,cur.map(r=>[r.item,r.nm,r.wc,r.cut||'',r.cost,rowQ(r),rowA(r)].concat(days.map(d=>dayQ(r,d))).concat(days.map(d=>Math.round(dayQ(r,d)*r.cost)))));};
    render();
  };
  { const[b,t]=_defRange(); load(b,t); }   // ★기본 기간 = 당일 ~ 당월말
};

/* LG리시빙관리 (영업, dw_sa_sale_110) — 도번 × 날짜(일자~일자 기간) 피벗. 수량/금액 토글, 내수/수출(mkt) */
SCREEN.lgrecv=(c)=>{
  const API=API_BASE;
  let cells=[], IM={}, curFr='', curTo='', loading=false, msg='';
  const WD=['일','월','화','수','목','금','토'];
  const MKT={'1':'수출','2':'내수'};  // mkt1=수출, mkt2=내수
  const ymdToInput=y=>{y=(''+(y||'')).trim();return y.length>=6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';};
  const inYmd=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const _tdy=(()=>{const d=new Date();return `${String(d.getFullYear()).slice(2)}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;})();
  let metric='amt', mkt='', cur=[];
  // 기간(fr~to, YYMMDD) 내 실제 날짜 컬럼 목록 — 월경계 넘어도 정확
  const dayList=()=>{
    const list=[]; if(curFr.length<6||curTo.length<6)return list;
    const d0=new Date(2000+(+curFr.slice(0,2)),(+curFr.slice(2,4))-1,+curFr.slice(4,6));
    const d1=new Date(2000+(+curTo.slice(0,2)),(+curTo.slice(2,4))-1,+curTo.slice(4,6));
    let guard=0;
    for(let d=new Date(d0);d<=d1&&guard<400;d.setDate(d.getDate()+1),guard++){
      const yy=String(d.getFullYear()).slice(2),mm=String(d.getMonth()+1).padStart(2,'0'),dd=String(d.getDate()).padStart(2,'0'),wd=d.getDay();
      list.push({ymd:yy+mm+dd,label:mm+'/'+dd,wd:WD[wd],we:(wd===0||wd===6)});
    }
    return list;
  };
  const load=async(fr,to)=>{loading=true;msg='';
    const bd=c.querySelector('#body');if(bd)bd.innerHTML=spinRow(20);
    try{const r=await fetch(`${API}/api/live/lgrecv?fr=${encodeURIComponent(fr||'')}&to=${encodeURIComponent(to||'')}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();cells=j.cells||[];IM={};(j.items||[]).forEach(x=>IM[x.item]=x);curFr=j.fr||fr||'';curTo=j.to||to||'';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';cells=[];IM={};}
    loading=false;draw();};
  const draw=()=>{
    const days=dayList();
    c.innerHTML=`<div style="display:flex;flex-direction:column;height:100%">
     <div class="page-title" style="flex:0 0 auto">🏢 LG리시빙관리</div>
     <div class="page-sub" style="flex:0 0 auto">LG 리시빙 도번×날짜 집계 · 원본 <code>SA_T_LG_RECEIVING_DTL</code> · 🟢 nx ${esc(ymdToInput(curFr)||'-')} ~ ${esc(ymdToInput(curTo)||'-')}</div>
     <div class="toolbar" style="flex:0 0 auto">
       <label class="tl">조회기간</label>
       <input type="date" class="inp" id="fr" value="${esc(ymdToInput(curFr))}" style="width:135px">
       <span style="color:var(--muted)">~</span>
       <input type="date" class="inp" id="to" value="${esc(ymdToInput(curTo))}" style="width:135px">
       <label class="tl">수량/금액</label>
       <div class="toggle-group"><button data-me="qty" class="${metric==='qty'?'on':''}">수량</button><button data-me="amt" class="${metric==='amt'?'on':''}">금액</button></div>
       <label class="tl">내수/수출</label>
       <select class="sel" id="mkt"><option value="" ${mkt===''?'selected':''}>전체</option><option value="2" ${mkt==='2'?'selected':''}>내수</option><option value="1" ${mkt==='1'?'selected':''}>수출</option></select>
       <input class="inp" id="iq" placeholder="도번/작업처" style="width:120px">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum" style="flex:0 0 auto"></div>
     <div class="grid-wrap lgrecv-grid" style="flex:1;min-height:0;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt" style="flex:0 0 auto"></div>
     <style>.lgrecv-grid thead th{position:sticky;top:0;z-index:3;background:#f4f7fc}.lgrecv-grid tr.grandtot td{position:sticky;bottom:0;background:#eaf1fb;font-weight:700;z-index:2;border-top:2px solid #cdd9ef}.lgrecv-grid th.wkend,.lgrecv-grid td.wkend{background:#ffe8d4}.lgrecv-grid tr.grandtot td.wkend{background:#f5d9be}</style></div>`;
    c.querySelectorAll('[data-me]').forEach(b=>b.onclick=()=>{metric=b.dataset.me;render();});
    c.querySelector('#mkt').onchange=e=>{mkt=e.target.value;render();};
    const render=()=>{
      const iq=c.querySelector('#iq').value.trim().toLowerCase();
      const map=new Map();
      cells.forEach(r=>{ if(mkt&&(''+r.mkt).trim()!==mkt)return;
        let o=map.get(r.item); if(!o){o={item:r.item,tot:0,dd:{}};map.set(r.item,o);}
        const v=metric==='qty'?(+r.q||0):(+r.amt||0); o.tot+=v; o.dd[(''+r.d).trim()]=(o.dd[(''+r.d).trim()]||0)+v; });
      cur=[...map.values()].map(o=>{const im=IM[o.item]||{};o.wcc=im.wcc||'';o.wc=im.wc||'';o.wt=im.wt||0;return o;})
        .filter(o=>!iq||(''+o.item).toLowerCase().includes(iq)||(''+o.wc).toLowerCase().includes(iq))
        .sort((a,b)=>(''+a.item).localeCompare(''+b.item,'ko'));
      const dHdr=days.map(x=>`<th class="num${x.we?' wkend':''}">${x.label}<br>${x.wd}</th>`).join('');
      c.querySelector('#th').innerHTML=`<tr><th>도번</th><th>작업장명</th><th class="num">합계</th>${dHdr}</tr>`;
      let tbody=cur.map(o=>`<tr><td><b>${esc(o.item)}</b></td><td class="cap" title="${esc(o.wc)}">${esc(o.wc)}</td><td class="num gstock"><b>${won(o.tot)}</b></td>${days.map(x=>`<td class="num${x.we?' wkend':''}">${o.dd[x.ymd]?won(o.dd[x.ymd]):''}</td>`).join('')}</tr>`).join('');
      const gt=cur.reduce((a,b)=>a+(+b.tot||0),0);
      const gd=days.map(x=>cur.reduce((a,b)=>a+(+b.dd[x.ymd]||0),0));
      if(cur.length)tbody+=`<tr class="grandtot"><td colspan="2" class="right">총계 (${won(cur.length)} 도번)</td><td class="num">${won(gt)}</td>${gd.map((v,i)=>`<td class="num${days[i].we?' wkend':''}">${v?won(v):''}</td>`).join('')}</tr>`;
      c.querySelector('#body').innerHTML=loading?spinRow(3+days.length):(msg?`<tr><td colspan="${3+days.length}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`:(cur.length?tbody:`<tr><td colspan="${3+days.length}" class="empty">결과 없음</td></tr>`));
      c.querySelector('#sum').innerHTML=`<div class="s-item">도번 <b>${won(cur.length)}</b></div><div class="s-item">${metric==='qty'?'수량':'금액'} 합계 <b>${wonI(gt)} ${metric==='qty'?'':'원'}</b></div>`;
      c.querySelector('#cnt').textContent=`${cur.length}도번 · ${days.length}일 · ${metric==='qty'?'수량':'금액'} 기준`;
      attachResizers(c);
    };
    const go=()=>{const f=inYmd(c.querySelector('#fr').value)||curFr,t=inYmd(c.querySelector('#to').value)||curTo;load(f,t);};
    c.querySelector('#go').onclick=go;
    c.querySelector('#fr').onchange=go;c.querySelector('#to').onchange=go;
    c.querySelector('#iq').onkeyup=e=>{if(e.key==='Enter')render();};
    c.querySelector('#reset').onclick=()=>{metric='amt';mkt='';c.querySelector('#iq').value='';render();};
    c.querySelector('#xls').onclick=()=>{
      const hd=['도번','작업장명','합계'].concat(days.map(x=>x.label));
      downloadCSV('LG리시빙관리_'+curFr+'_'+curTo+'_'+metric+(mkt?('_'+MKT[mkt]):'')+'.csv',hd,cur.map(o=>[o.item,o.wc,o.tot].concat(days.map(x=>o.dd[x.ymd]||0))));};
    render();
  };
  load('','');
};

/* 출하실적현황 (영업, dw_sa_list_010) — 출하 라인. 출력방식 제번별상세/도번별집계/일별집계 */
SCREEN.shipment=(c)=>{
  const API=API_BASE;
  let pool=[], loading=false, msg='', curFrom='', curTo='';   // 빈값 → 백엔드가 당월1일~오늘 기본
  const fmtYmd=y=>{y=(''+(y||'')).trim();return y.length>=6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:y;};
  const fmtHms=h=>{h=(''+(h||'')).trim().padStart(6,'0');return h.length>=6?`${h.slice(0,2)}:${h.slice(2,4)}:${h.slice(4,6)}`:h;};
  const S=(rs,k)=>rs.reduce((a,b)=>a+(+b[k]||0),0);
  const dToInput=d=>{d=(''+(d||'')).trim();return d.length>=6?`20${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4,6)}`:'';};
  const inD=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  let mode='detail', cur=[];
  const load=async()=>{loading=true;msg='';draw();
    try{const r=await fetch(`${API}/api/live/shipment?dfrom=${curFrom}&dto=${curTo}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();pool=j.rows||[];curFrom=j.dfrom||curFrom;curTo=j.dto||curTo;}
    catch(e){pool=[];msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';}
    loading=false;draw();};
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">🚚 출하실적현황</div>
     <div class="page-sub">출하(매출) 실적 라인 · 원본 <code>SA_T_SALE_DTL</code> · 🟢 nx ${esc(dToInput(curFrom)||'-')}~${esc(dToInput(curTo)||'-')}</div>
     <div class="toolbar">
       <label class="tl">출하기간</label>
       <input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom))}" style="min-width:130px"><span style="color:var(--muted)">~</span><input type="date" class="inp" id="dto" value="${esc(dToInput(curTo))}" style="min-width:130px">
       <label class="tl">출력방식</label>
       <select class="sel" id="mode"><option value="detail" ${mode==='detail'?'selected':''}>제번별 상세</option><option value="item" ${mode==='item'?'selected':''}>도번별 집계</option><option value="day" ${mode==='day'?'selected':''}>일별 집계</option></select>
       <input class="inp" id="iq" placeholder="도번/Work Order">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:510px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    c.querySelector('#mode').onchange=e=>{mode=e.target.value;render();};
    const filt=()=>{const q=c.querySelector('#iq').value.trim().toLowerCase();
      return pool.filter(r=>!q||(''+r.item).toLowerCase().includes(q)||(''+r.wo).toLowerCase().includes(q));};
    const render=()=>{
      let lines=filt(), thead='', tbody='', tq=0, ta=0, ncols;
      if(mode==='detail'){
        cur=lines.slice().sort((a,b)=>(''+a.item).localeCompare(''+b.item,'ko')||(''+a.ymd).localeCompare(''+b.ymd,'ko'));
        thead=`<tr><th>출하일자</th><th>Work Order</th><th>Split W/O</th><th>도번</th><th class="num">출하수량</th><th class="num">출하단가</th><th class="num">출하금액</th><th class="num">마스터단가</th><th>처리담당자</th><th class="center">처리시각</th><th>작업처</th><th>비고</th></tr>`;
        ncols=12;
        cur.forEach(r=>{tbody+=`<tr><td class="center">${fmtYmd(r.ymd)}</td><td>${esc(r.wo)}</td><td>${esc(r.swo)}</td><td><b>${esc(r.item)}</b></td><td class="num">${won(r.qty)}</td><td class="num">${won(r.cost)}</td><td class="num gstock">${wonI(r.amt)}</td><td class="num">${won(r.mcost)}</td><td>${esc(r.usr)||''}</td><td class="center">${fmtHms(r.hms)}</td><td class="cap" title="${esc(r.wc)||''}">${esc(r.wc)||''}</td><td class="cap" title="${esc(r.remarks)||''}">${esc(r.remarks)||''}</td></tr>`;});
        tq=S(cur,'qty');ta=S(cur,'amt');
        tbody+=`<tr class="grandtot"><td colspan="4" class="right">총계</td><td class="num">${won(tq)}</td><td colspan="1"></td><td class="num">${wonI(ta)}</td><td colspan="5"></td></tr>`;
      } else if(mode==='item'){
        const map=new Map();
        lines.forEach(r=>{if(!map.has(r.item))map.set(r.item,{item:r.item,qty:0,amt:0,n:0});const o=map.get(r.item);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.n++;});
        cur=[...map.values()].sort((a,b)=>-(a.amt-b.amt));
        thead=`<tr><th>도번</th><th class="num">건수</th><th class="num">출하수량</th><th class="num">출하금액</th><th class="num">평균단가</th></tr>`;
        ncols=5;
        cur.forEach(r=>{tbody+=`<tr><td><b>${esc(r.item)}</b></td><td class="num">${won(r.n)}</td><td class="num">${won(r.qty)}</td><td class="num gstock">${wonI(r.amt)}</td><td class="num">${won(r.qty?Math.round(r.amt/r.qty):0)}</td></tr>`;});
        tq=S(cur,'qty');ta=S(cur,'amt');
        tbody+=`<tr class="grandtot"><td class="right">총계 (${won(cur.length)} 도번)</td><td class="num">${won(S(cur,'n'))}</td><td class="num">${won(tq)}</td><td class="num">${wonI(ta)}</td><td></td></tr>`;
      } else {
        const map=new Map();
        lines.forEach(r=>{if(!map.has(r.ymd))map.set(r.ymd,{ymd:r.ymd,qty:0,amt:0,n:0});const o=map.get(r.ymd);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.n++;});
        cur=[...map.values()].sort((a,b)=>(''+a.ymd).localeCompare(''+b.ymd,'ko'));
        thead=`<tr><th>출하일자</th><th class="num">건수</th><th class="num">출하수량</th><th class="num">출하금액</th></tr>`;
        ncols=4;
        cur.forEach(r=>{tbody+=`<tr><td class="center">${fmtYmd(r.ymd)}</td><td class="num">${won(r.n)}</td><td class="num">${won(r.qty)}</td><td class="num gstock">${wonI(r.amt)}</td></tr>`;});
        tq=S(cur,'qty');ta=S(cur,'amt');
        tbody+=`<tr class="grandtot"><td class="right">총계 (${won(cur.length)} 일)</td><td class="num">${won(S(cur,'n'))}</td><td class="num">${won(tq)}</td><td class="num">${wonI(ta)}</td></tr>`;
      }
      c.querySelector('#th').innerHTML=thead;
      c.querySelector('#body').innerHTML=loading?spinRow(ncols):(msg?`<tr><td colspan="${ncols}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`:(cur.length?tbody:`<tr><td colspan="${ncols}" class="empty">결과 없음</td></tr>`));
      c.querySelector('#sum').innerHTML=`<div class="s-item">${mode==='detail'?'라인':mode==='item'?'도번':'일'} <b>${won(cur.length)}</b></div><div class="s-item">출하수량 합계 <b>${won(tq)}</b></div><div class="s-item ${ta<0?'neg':''}">출하금액 합계 <b>${wonI(ta)} 원</b></div>`;
      c.querySelector('#cnt').textContent=`${cur.length}${mode==='detail'?'라인':mode==='item'?'도번':'일'} / 대상 ${lines.length}라인`;
      attachResizers(c);
    };
    const go=()=>{curFrom=inD(c.querySelector('#dfrom').value);curTo=inD(c.querySelector('#dto').value);load();};
    c.querySelector('#go').onclick=go;c.querySelector('#iq').onkeyup=e=>{if(e.key==='Enter')render();};
    c.querySelector('#dfrom').onchange=go;c.querySelector('#dto').onchange=go;
    c.querySelector('#reset').onclick=()=>{mode='detail';curFrom='';curTo='';load();};
    c.querySelector('#xls').onclick=()=>{let hd,rows;
      if(mode==='detail'){hd=['출하일자','Work Order','Split W/O','도번','출하수량','출하단가','출하금액','마스터단가','처리담당자','처리시각','작업처','비고'];
        rows=cur.map(r=>[fmtYmd(r.ymd),r.wo,r.swo,r.item,r.qty,r.cost,Math.round(r.amt),r.mcost,r.usr,fmtHms(r.hms),r.wc,r.remarks]);}
      else if(mode==='item'){hd=['도번','건수','출하수량','출하금액','평균단가'];rows=cur.map(r=>[r.item,r.n,r.qty,Math.round(r.amt),r.qty?Math.round(r.amt/r.qty):0]);}
      else{hd=['출하일자','건수','출하수량','출하금액'];rows=cur.map(r=>[fmtYmd(r.ymd),r.n,r.qty,Math.round(r.amt)]);}
      downloadCSV('출하실적현황_'+mode+'.csv',hd,rows);};
    render();
  };
  load();
};

/* 제품재고조회 (영업, dw_pr_stock_040) — 기초/입고/출고/조정/현재고 · 작업장별 */
SCREEN.salesstock=(c)=>{
  const API=API_BASE;
  let pool=[], loading=false, msg='', curFrom='', curTo='', cur=[], source='live', incZero=false;   // ★Phase5 데이터원(기본 라이브 무변경) · incZero=0재고포함(레거시 gross 대조)
  const dToInput=d=>{d=(''+(d||'')).trim();return d.length>=6?`20${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4,6)}`:'';};
  const inD=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const load=async()=>{loading=true;msg='';
    const bd=c.querySelector('#body');if(bd)bd.innerHTML=spinRow(10);
    const zq=incZero?'&zero=1':'';
    if(source==='nx'){loading=false;return nxDerivedView(c,`${API}/api/live/salesstock?dfrom=${curFrom}&dto=${curTo}&source=nx`,{title:'제품재고조회',onBack:()=>{source='live';load();}});}
    try{const r=await fetch(`${API}/api/live/salesstock?dfrom=${curFrom}&dto=${curTo}${zq}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();pool=j.rows||[];curFrom=j.dfrom||curFrom;curTo=j.dto||curTo;}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';pool=[];}
    loading=false;
    const df=c.querySelector('#dfrom'),dt=c.querySelector('#dto');if(df)df.value=dToInput(curFrom);if(dt)dt.value=dToInput(curTo);
    const sub=c.querySelector('#ss-sub');if(sub)sub.innerHTML=`제품 수불(기초+입고−출고−기타출고) · 판매단가(S/E) 기준 · 원본 <code>SA_T_STOCK_MAINT</code> · 🟢 nx ${esc(dToInput(curFrom)||'-')}~${esc(dToInput(curTo)||'-')}`;
    const ws=[...new Set(pool.map(r=>r.wc).filter(Boolean))].sort();
    const wsel=c.querySelector('#wc');if(wsel){const v=wsel.value;wsel.innerHTML='<option value="">전체작업장</option>'+ws.map(w=>`<option value="${esc(w)}">${esc(w)}</option>`).join('');wsel.value=v;}
    apply();};
  c.innerHTML=`
   <div class="page-title">📦 제품재고조회</div>
   <div class="page-sub" id="ss-sub">제품 수불(기초+입고−출고−기타출고) · 판매단가(S/E) 기준 · 원본 <code>SA_T_STOCK_MAINT</code> · 🟢 nx</div>
   <div class="toolbar">
     <label style="font-size:12px;color:var(--muted);font-weight:600">수불기간</label>
     <input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom))}" style="min-width:135px">
     <span style="color:var(--muted)">~</span>
     <input type="date" class="inp" id="dto" value="${esc(dToInput(curTo))}" style="min-width:135px">
     <input class="inp" id="q" placeholder="품목코드/품명/규격">
     <select class="sel" id="wc"><option value="">전체작업장</option></select>
     <select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
     <label style="font-size:12px;color:var(--muted);font-weight:600;display:inline-flex;align-items:center;gap:3px" title="레거시 w_pr_stock_040처럼 최종재고 0인 품목까지 포함(gross 대조)"><input type="checkbox" id="zero" ${incZero?'checked':''}>0재고 포함</label>
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
     <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
     <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
   </div>
   <div class="summary-bar" id="sum"></div>
   <div class="grid-wrap" style="max-height:510px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
   <div class="rowcount" id="cnt"></div>`;
  c.querySelector('#th').innerHTML=`<tr><th>품목코드</th><th class="cap">품명</th><th class="num">기초재고</th><th class="num">입고</th><th class="num">출고</th><th class="num">기타출고</th><th class="num">재고수량</th><th class="num">단가</th><th class="num">금액</th><th class="center">작업처</th></tr>`;
  const sumbar=rows=>{const qty=rows.reduce((a,b)=>a+(+b.qty||0),0),amt=rows.reduce((a,b)=>a+(+b.amt||0),0);
    c.querySelector('#sum').innerHTML=`<div class="s-item">건수 <b>${won(rows.length)}</b></div>
      <div class="s-item">재고수량 합계 <b>${won(qty)}</b></div>
      <div class="s-item ${amt<0?'neg':''}">재고금액 합계 <b>${wonI(amt)} 원</b></div>`;};
  const gbf=r=>{const gb=c.querySelector('#gubun').value;return gb==='all'||(gb==='plus'?r.qty>0:r.qty<0);};
  const T=(rs,k)=>rs.reduce((a,b)=>a+(+b[k]||0),0);
  const render=rows=>{cur=rows;let body=rows.map(r=>`<tr><td><b>${esc(r.cd)}</b></td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td class="num">${won(r.basic)}</td><td class="num">${won(r.inq)}</td><td class="num">${won(r.outq)}</td><td class="num">${won(r.adj)}</td><td class="num qty"><b>${won(r.qty)}</b></td><td class="num">${won(r.cost)}</td><td class="num"><b>${wonI(r.amt)}</b></td><td class="center">${esc(r.wc)||'-'}</td></tr>`).join('');
    if(rows.length)body+=`<tr class="grandtot"><td colspan="2" class="right">총계</td><td class="num">${won(T(rows,'basic'))}</td><td class="num">${won(T(rows,'inq'))}</td><td class="num">${won(T(rows,'outq'))}</td><td class="num">${won(T(rows,'adj'))}</td><td class="num">${won(T(rows,'qty'))}</td><td></td><td class="num">${wonI(T(rows,'amt'))}</td><td></td></tr>`;
    c.querySelector('#body').innerHTML=rows.length?body:`<tr><td colspan="10" class="empty">결과 없음</td></tr>`;sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
  const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),w=c.querySelector('#wc').value;
    render(pool.filter(r=>gbf(r)&&(!w||r.wc===w)&&(!q||(r.cd||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q)||(r.spec||'').toLowerCase().includes(q))));};
  const go=()=>{curFrom=inD(c.querySelector('#dfrom').value);curTo=inD(c.querySelector('#dto').value);load();};
  c.querySelector('#go').onclick=go;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
  c.querySelector('#nxsrc').onclick=()=>{source='nx';load();};   // ★Phase5 nx 파생 보기
  c.querySelector('#dfrom').onchange=go;c.querySelector('#dto').onchange=go;
  c.querySelector('#zero').onchange=e=>{incZero=e.target.checked;load();};   // 0재고 포함=서버 재조회(레거시 gross 대조)
  c.querySelector('#wc').onchange=apply;c.querySelector('#gubun').onchange=apply;
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#wc').value='';c.querySelector('#gubun').value='all';curFrom='';curTo='';load();};
  c.querySelector('#xls').onclick=()=>downloadCSV('제품재고조회.csv',['품목코드','품명','기초재고','입고','출고','기타출고','재고수량','단가','금액','작업처'],cur.map(r=>[r.cd,r.nm,r.basic,r.inq,r.outq,r.adj,r.qty,r.cost,Math.round(r.amt),r.wc]));
  enableSort(c,['cd','nm','basic','inq','outq','adj','qty','cost','amt','wc'],()=>cur,render);
  load();
};

/* 구매/자재 > 판매및출고등록 (레거시 w_pu_output_010) — 구매→협력사(외주처) 판매출고 CRUD + 복사 + 이월처리. nx.sale_output. */
SCREEN.saleout=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const now=new Date();
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const d8=s=>s&&s.length===8?`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`:(s||"");
  const dt=s=>String(s||"").slice(0,19).replace("T"," ");
  let st={rows:[],custs:[],gubuns:{},cust:"",item:"",sheet:"",gubun:"",fr:iso(new Date(now.getFullYear(),now.getMonth(),1)),to:iso(now),
          carry:iso(now),sel:{},edit:null,sortKey:"",sortDir:1,loading:false,totqty:0,totamt:0,totvat:0,sheetcnt:0};
  const load=async()=>{st.loading=true;st.sel={};draw();
    try{const r=await fetch(`${API}/api/saleout/list?fr=${yy(st.fr)}&to=${yy(st.to)}&sheet=${encodeURIComponent(st.sheet)}&cust=${encodeURIComponent(st.cust)}&item=${encodeURIComponent(st.item)}&gubun=${st.gubun}`);
      const j=await r.json();st.rows=j.rows||[];st.custs=j.custs||[];st.gubuns=j.gubuns||{};st.totqty=j.totqty||0;st.totamt=j.totamt||0;st.totvat=j.totvat||0;st.sheetcnt=j.sheetcnt||0;}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const fetchCost=async()=>{const e=st.edit;if(!e||!e.item_code||!e.out_cust)return;
    try{const r=await fetch(`${API}/api/saleout/price?item=${encodeURIComponent(e.item_code)}&cust=${encodeURIComponent(e.out_cust)}`);
      const j=await r.json();e.cost=j.cost||0;draw();}catch(x){}};
  const save=async()=>{const e=st.edit;if(!e.out_cust||!e.item_code)return alert("외주처·품번을 입력하세요.");
    if(e.out_qty===""||isNaN(+e.out_qty))return alert("출고수량(숫자)을 입력하세요.");
    try{const r=await fetch(`${API}/api/saleout/save`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(e)});
      if(!r.ok)throw new Error((await r.json()).detail||r.status);st.edit=null;await load();}catch(x){alert("저장 실패: "+x.message);}};
  const delSel=async()=>{const ids=Object.keys(st.sel).filter(k=>st.sel[k]).map(Number);if(!ids.length)return alert("삭제할 행을 체크하세요.");
    if(!window.confirm(`${ids.length}건 삭제할까요?`))return;
    try{await fetch(`${API}/api/saleout/delete`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ids})});await load();}catch(x){alert("삭제 실패");}};
  const copy=async(id)=>{try{await fetch(`${API}/api/saleout/copy`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});await load();}catch(x){alert("복사 실패");}};
  const carryover=async()=>{const ids=Object.keys(st.sel).filter(k=>st.sel[k]).map(Number);if(!ids.length)return alert("이월할 행을 체크하세요.");
    if(!window.confirm(`${ids.length}건을 ${st.carry} 로 이월처리할까요?`))return;
    try{const r=await fetch(`${API}/api/saleout/carryover`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ids,carryover_ymd:yy(st.carry)})});
      const j=await r.json();if(!r.ok)throw new Error(j.detail||r.status);alert(`${j.carried}건 이월(${j.to})`);await load();}catch(x){alert("이월 실패: "+x.message);}};
  const draw=()=>{
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;st.rows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const selcnt=Object.values(st.sel).filter(Boolean).length;const e=st.edit;
    c.innerHTML=`
     <div class="page-title">📤 판매및출고등록</div>
     <div class="page-sub">구매 → 협력사(외주처) <b>판매출고</b>(구분 <b>5:협력업체판매</b>) · <b style="color:#c0392b">사급단가×수량=매출</b>, VAT 10% · 사급수불원장(nx.sagub_maint tag='5')=사급재고 반영 · 레거시 <code>w_pu_output_010</code></div>
     <div class="toolbar">
       <label class="tl">출고일자</label><input class="inp" type="date" id="o-fr" value="${esc(st.fr)}"> ~ <input class="inp" type="date" id="o-to" value="${esc(st.to)}">
       <label class="tl" style="margin-left:8px">출고증번호</label><input class="inp" id="o-sheet" value="${esc(st.sheet)}" placeholder="출고증번호" style="width:120px">
       <label class="tl" style="margin-left:8px">외주처</label>
       <select class="inp" id="o-cust"><option value="">전체</option>${st.custs.map(o=>`<option value="${esc(o.code)}" ${st.cust===o.code?"selected":""}>${esc(o.nm||o.code)}</option>`).join("")}</select>
       <label class="tl" style="margin-left:8px">품번</label><input class="inp" id="o-item" value="${esc(st.item)}" placeholder="품번" style="width:110px">
       <label class="tl" style="margin-left:8px">구분</label><select class="inp" id="o-gb"><option value="">전체</option>${Object.entries(st.gubuns).map(([k,v])=>`<option value="${esc(k)}" ${st.gubun===k?"selected":""}>${esc(k)}:${esc(v)}</option>`).join("")}</select>
       <button class="btn" id="o-go">🔍 조회</button>
     </div>
     <div class="toolbar" style="padding-top:0">
       <button class="btn" id="o-add" style="background:#2e86de;color:#fff">➕ 추가</button>
       <button class="btn" id="o-del">🗑 삭제${selcnt?`(${selcnt})`:""}</button>
       <span style="margin-left:16px;padding:4px 10px;background:var(--soft);border-radius:6px">
         <b>이월처리</b> 이월일자 <input class="inp" type="date" id="o-carry" value="${esc(st.carry)}" style="width:150px">
         <button class="btn" id="o-cv">📆 이월</button>
         <span style="font-size:11px;color:var(--muted);margin-left:6px">체크 선택 후 이월</span></span>
     </div>
     ${e?`<div class="panel" style="border:2px solid #2e86de"><div class="panel-h">${e.id?"수정":"신규"} 판매출고</div><div class="panel-b">
       <div class="toolbar" style="flex-wrap:wrap;gap:8px">
         <label class="tl">구분</label><select class="inp" id="e-gb">${Object.entries(st.gubuns).map(([k,v])=>`<option value="${esc(k)}" ${(e.gubun||'5')===k?"selected":""}>${esc(k)}:${esc(v)}</option>`).join("")}</select>
         <label class="tl">외주처<span style="color:red">*</span></label><input class="inp" id="e-cust" value="${esc(e.out_cust||"")}" placeholder="외주처코드" style="width:90px">
         <label class="tl">출고증번호</label><input class="inp" id="e-sheet" value="${esc(e.sheet_no||"")}" style="width:110px">
         <label class="tl">품번<span style="color:red">*</span></label><input class="inp" id="e-item" value="${esc(e.item_code||"")}" placeholder="품번" style="width:150px">
         <label class="tl">출고수량<span style="color:red">*</span></label><input class="inp" id="e-qty" value="${esc(e.out_qty??"")}" style="width:80px;text-align:right">
         <label class="tl">사급단가🔒</label><input class="inp" id="e-cost" value="${esc(e.cost??"")}" style="width:90px;text-align:right;background:#eef2f7;color:#555" readonly title="단가는 마스터 자동조회값이며 마감때만 변경 가능(자재 단가 수정금지 규칙)">
         <label class="tl">Work Order</label><input class="inp" id="e-wo" value="${esc(e.work_order||"")}" style="width:90px">
         <label class="tl">비고</label><input class="inp" id="e-rmk" value="${esc(e.remarks||"")}" style="width:130px">
         <button class="btn" id="e-save" style="background:#27ae60;color:#fff">💾 저장</button><button class="btn" id="e-cancel">취소</button>
       </div>
       <div style="font-size:12px;color:var(--muted);margin-top:6px">매출(예상) = 수량 × 사급단가 = <b style="color:#c0392b">${won((+e.out_qty||0)*(+e.cost||0))}</b> · 부가세 = <b>${won(Math.trunc((+e.out_qty||0)*(+e.cost||0)*0.1))}</b> · 단가 미입력시 PR_M_ITEM_COST(사급) 자동적용</div></div></div>`:""}
     <div class="panel"><div class="panel-h">판매출고 목록 ${st.loading?"(조회중…)":`(${st.rows.length}건)`}</div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th class="center" style="width:28px"><input type="checkbox" id="o-all"></th>
         <th data-key="out_ymd">출고일자</th><th class="center" data-key="gubunnm">구분</th><th data-key="out_cust">외주처</th><th data-key="custnm">외주처명</th>
         <th data-key="sheet_no">출고증번호</th><th class="num" data-key="out_seq">출고SEQ</th><th data-key="item_code">품번</th><th data-key="itemnm">품명</th><th class="num" data-key="out_qty">출고수량</th>
         <th class="num" data-key="cost">사급단가</th><th class="num" data-key="amt">금액(매출)</th><th class="num" data-key="vat">부가세</th>
         <th data-key="remarks">비고</th><th data-key="reg_user">등록자</th><th data-key="upd_user">수정자</th><th>작업일시</th>
         <th data-key="work_order">Work Order</th><th data-key="split_work_order">Split WO</th><th class="center">Sale Ymd</th><th class="center">Sale Hms</th><th class="center">관리</th></tr></thead>
       <tbody>${st.rows.map(r=>`<tr${r.editable?"":' style="background:#fafbfc"'}>
         <td class="center">${r.editable?`<input type="checkbox" class="o-ck" data-id="${r.id}" ${st.sel[r.id]?"checked":""}>`:""}</td>
         <td>${d8(r.out_ymd)}</td><td class="center">${r.gubun?esc(r.gubun)+":"+esc(r.gubunnm):""}</td><td>${esc(r.out_cust||"")}</td>
         <td class="cap" style="max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.custnm||"")}">${esc(r.custnm||"")}</td>
         <td>${esc(r.sheet_no||"")}</td><td class="num">${r.out_seq??""}</td>
         <td><b>${esc(r.item_code)}</b></td><td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.itemnm||"")}">${esc(r.itemnm||"")}</td><td class="num qty">${won(r.out_qty)}</td>
         <td class="num">${won(r.cost)}</td><td class="num" style="color:#c0392b">${won(r.amt)}</td><td class="num">${won(r.vat)}</td>
         <td class="cap" style="max-width:130px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.remarks||"")}">${esc(r.remarks||"")}</td>
         <td>${esc(r.reg_user||"")}</td><td>${esc(r.upd_user||"")}</td><td style="font-size:11px">${dt(r.work_dt)}</td>
         <td>${esc(r.work_order||"")}</td><td>${esc(r.split_work_order||"")}</td><td class="center">${d8(r.sale_ymd)}</td><td class="center">${esc(r.sale_hms||"")}</td>
         <td class="center">${r.editable?`<button class="btn xs o-ed" data-id="${r.id}">수정</button> <button class="btn xs o-cp" data-id="${r.id}">복사</button>`:'<span style="color:#9aa6b2;font-size:11px" title="기존 이력(nx미러)·읽기전용">📁이력</span>'}</td></tr>`).join("")||'<tr><td colspan="22" style="padding:16px;color:var(--muted)">판매출고 없음 — [추가]로 등록</td></tr>'}
       <tr class="grandtot"><td colspan="9" class="center">합계 ${st.rows.length}건 · 출고증 ${st.sheetcnt}건</td><td class="num">${won(st.totqty)}</td><td></td><td class="num">${won(st.totamt)}</td><td class="num">${won(st.totvat)}</td><td colspan="9"></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    g("#o-fr").onchange=x=>st.fr=x.target.value;g("#o-to").onchange=x=>st.to=x.target.value;
    g("#o-sheet").oninput=x=>st.sheet=x.target.value;g("#o-cust").onchange=x=>st.cust=x.target.value;
    g("#o-item").oninput=x=>st.item=x.target.value;g("#o-gb").onchange=x=>st.gubun=x.target.value;
    g("#o-go").onclick=load;g("#o-del").onclick=delSel;g("#o-cv").onclick=carryover;g("#o-carry").onchange=x=>st.carry=x.target.value;
    g("#o-add").onclick=()=>{st.edit={gubun:"5",out_cust:st.cust||"",sheet_no:"",item_code:"",out_qty:"",work_order:"",remarks:""};draw();};
    const all=g("#o-all");if(all)all.onclick=x=>{st.rows.forEach(r=>{if(r.editable)st.sel[r.id]=x.target.checked;});draw();};
    c.querySelectorAll(".o-ck").forEach(x=>x.onchange=()=>{st.sel[x.dataset.id]=x.checked;draw();});
    if(e){g("#e-gb").onchange=x=>e.gubun=x.target.value;
      g("#e-cust").oninput=x=>e.out_cust=x.target.value.trim();g("#e-cust").onblur=fetchCost;
      g("#e-sheet").oninput=x=>e.sheet_no=x.target.value.trim();
      g("#e-item").oninput=x=>e.item_code=x.target.value.trim();g("#e-item").onblur=fetchCost;
      g("#e-qty").oninput=x=>e.out_qty=x.target.value;g("#e-qty").onblur=()=>draw();
      // 사급단가=읽기전용(마스터 자동조회, 마감때만 변경) — 수동수정 핸들러 없음
      g("#e-wo").oninput=x=>e.work_order=x.target.value.trim();g("#e-rmk").oninput=x=>e.remarks=x.target.value;
      g("#e-save").onclick=save;g("#e-cancel").onclick=()=>{st.edit=null;draw();};}
    c.querySelectorAll(".o-ed").forEach(x=>x.onclick=()=>{const r=st.rows.find(v=>v.id==x.dataset.id);st.edit={id:r.id,gubun:r.gubun||"5",out_cust:r.out_cust,sheet_no:r.sheet_no||"",item_code:r.item_code,out_qty:r.out_qty,work_order:r.work_order||"",remarks:r.remarks||""};draw();});
    c.querySelectorAll(".o-cp").forEach(x=>x.onclick=()=>copy(+x.dataset.id));
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(k){th.style.cursor="pointer";th.title="더블클릭 정렬·경계드래그 너비조절";th.ondblclick=()=>{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};}});
  };
  load();
};

/* 영업 > 출하실적등록 (레거시 w_pr_input_040) — 제번단위 출하실적.
   드래그로 계획셀 선택 → 우클릭 [확인] = ASSY재고 있는 만큼만 출하처리(재고차감).
   구분 4종(전체/집계/제번/라인) · 라인 드롭다운 · 출하완료셀=살구색. */
SCREEN.lgsale=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const nf=v=>(+v||0).toLocaleString('ko-KR');
  const nf2=v=>(+v||0).toFixed(2);
  const cap=v=>(+v||0)?nf(v):'';
  const esc2=s=>String(s==null?'':s).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
  const _DW=['일','월','화','수','목','금','토'];
  const dcol=s=>{s=''+(s||'');if(s.length!==6)return s;
    const d=new Date(2000+ +s.slice(0,2),+s.slice(2,4)-1,+s.slice(4,6));
    return `${+s.slice(4,6)}(${_DW[d.getDay()]})`;};
  const dow=s=>{s=''+(s||'');if(s.length!==6)return -1;
    return new Date(2000+ +s.slice(0,2),+s.slice(2,4)-1,+s.slice(4,6)).getDay();};
  const dcls=s=>{const w=dow(s);return w===0?' s4sun':(w===6?' s4sat':'');};
  const T=new Date();
  const st={from:iso(T),gigan:4,line:'',wo:'',item:'',view:'전체',src:'nx',
            dates:[],rows:[],cnt:0,loading:false,msg:'',lines:[],sel:new Set()};

  const loadLines=async()=>{try{const r=await fetch(`${API}/api/sale040/lines?src=${st.src}`);
    st.lines=(await r.json()).rows||[];}catch(e){st.lines=[];}};
  const load=async()=>{st.loading=true;draw();
    const qs=new URLSearchParams({from_ymd:st.from,gigan:st.gigan,line:st.line,
                                  wo:st.wo,item:st.item,src:st.src,limit:4000});
    try{const r=await fetch(`${API}/api/sale040/grid?${qs}`);const d=await r.json();
      st.dates=d.dates||[];st.rows=d.rows||[];st.cnt=d.cnt||0;st.msg='';st.sel.clear();}
    catch(e){st.msg='백엔드 연결 실패';st.dates=[];st.rows=[];st.cnt=0;}
    st.loading=false;draw();};

  const draw=()=>{
    const dates=st.dates;
    // 필터(클라 즉시) — 제번·도번
    const q=s=>(s||'').trim().toUpperCase();
    const qw=q(st.wo), qi=q(st.item);
    let rows=st.rows.filter(r=>
      (!qw||((r.wo||'').toUpperCase().includes(qw)||(r.swo||'').toUpperCase().includes(qw)))
      &&(!qi||(r.item||'').toUpperCase().includes(qi)));
    if(st.line) rows=rows.filter(r=>(r.line_no||'')===st.line);
    // 정렬: 라인 → 제번 → 도번
    rows.sort((a,b)=>(a.line_no||'').localeCompare(b.line_no||'')
                   ||(a.swo||a.wo||'').localeCompare(b.swo||b.wo||'')
                   ||(a.item||'').localeCompare(b.item||''));
    const lnm={};(st.lines||[]).forEach(o=>{lnm[o.code]=o.nm;});
    // 셀 = 그 일자 계획. 출하완료분은 살구색.
    // ★del_flag(0=현재계획 / 1=전일 삭제계획)를 키에 포함 — 같은 제번·도번이 양쪽에 나올 수 있다.
    const ckey=(r,d)=>`${r.del_flag||'0'}|${r.wo}|${r.swo}|${r.item}|${d}`;
    // 살구 = 그 제번(제번·도번)이 전량출하. 조회기간과 무관하게 제번 전체계획 기준.
    const woDone=r=>{const p=+r.wo_plan||0, s=+r.sale_qty||0; return p>0&&s>=p;};
    // ASSY재고 충당(노랑) — 앞 일자부터, 계획을 전량 덮을 때만.
    const _cov={};
    (function(){const pool={};
      rows.forEach(r=>{if(!(r.item in pool))pool[r.item]=+r.stock_qty||0;});
      // 삭제계획(del_flag=1)은 실제 출하대상이 아니므로 재고를 소진시키지 않는다.
      dates.forEach(d=>rows.filter(r=>(r.del_flag||'0')!=='1').forEach(r=>{
        const pl=(r.days&&r.days[d])||0, sd=(r.sday&&r.sday[d])||0;
        const need=Math.max(0,pl-sd); if(need<=0)return;
        const av=pool[r.item]||0; if(av<=0)return;
        const take=Math.min(av,need); pool[r.item]=av-take;
        if(take>=need-1e-6)_cov[ckey(r,d)]=1;}));})();
    const cell=(r,d)=>{
      const pl=(r.days&&r.days[d])||0, sd=(r.sday&&r.sday[d])||0;
      const wk=(!pl&&!sd)?dcls(d).replace(/s4s(at|un)/,'s4wk'):'';
      if(!pl&&!sd)return `<td class="num${wk}"></td>`;      // 빈칸은 무조건 무색
      const rem=Math.max(0,pl-sd);
      const k=ckey(r,d);
      const del=(r.del_flag||'0')==='1';                    // 전일 삭제계획 = 참고용(출하대상 아님)
      const done=sd>0&&rem<=0;                              // 그 셀 전량출하 = 살구
      const bg=del?'#eceff1':(done?'#fac090':(_cov[k]?'#ffff00':''));  // 재고충당 = 노랑
      const lock=del||(rem<=0&&sd<=0);                      // 출하분은 취소해야 하므로 선택가능
      return `<td class="num s4c${lock?' s4lock':''}${st.sel.has(k)?' s4sel':''}"`
        +`${lock?'':` data-k="${esc2(k)}" data-rem="${rem}" data-sd="${sd}"`}`
        +` style="white-space:nowrap${bg?';background:'+bg:''}"`
        +` title="${del?'전일 삭제계획(참고용) — 출하대상 아님':(done?('출하 '+nf(sd)+'/'+nf(pl)+' — 우클릭: 확인/취소'):'우클릭: 확인/취소')}"`
        +`>${sd?nf(sd)+'/'+nf(pl):nf(pl)}</td>`;};

    const NC=16;   // 고정컬럼 17개 → colspan 은 NC+1+dates.length
    // Output = 계획일자 + 출력시각 (레거시 '26/08/21 21:00' 형식)
    const outHm=r=>{const y=String(r.org_ymd||''),h=String(r.ohm||'');
      if(!y&&!h)return '';
      const yy=y.length===6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:y;
      const hh=h.length===4?`${h.slice(0,2)}:${h.slice(2,4)}`:h;
      return (yy+' '+hh).trim();};
    // ── 고정컬럼 정의 (레거시 배치) ─────────────────────────────────────
    //   t=헤더명 · cls=정렬 · w=기본폭(px) · h(r)=행 셀 · s(blk,S)=집계행 셀
    //   도번은 툴팁으로 품명 제공(품명 컬럼은 레거시에 없어 제거)
    const CD={
      line_no:{t:'라인',cls:'center',w:78,
        h:r=>`<td class="center">${esc2((lnm[r.line_no]&&lnm[r.line_no]!==r.line_no)?(r.line_no+' '+lnm[r.line_no]):r.line_no)}</td>`,
        s:(b,S,r0)=>`<td class="center">${esc2(r0.line_no)}</td>`},
      wo:{t:'제번',cls:'center',w:96,
        h:r=>`<td class="center">${(r.del_flag||'0')==='1'?'<span style="color:#b0413e;font-weight:700" title="전일 삭제계획">✕</span> ':''}${esc2(r.swo||r.wo)}</td>`,
        s:(b,S,r0)=>`<td class="center">${esc2(r0.swo||r0.wo)}</td>`},
      model_no:{t:'Model No',cls:'center',w:150,h:r=>`<td class="center">${esc2(r.model_no)}</td>`},
      tools:{t:'Tools',cls:'center',w:78,h:r=>`<td class="center">${esc2(r.tools)}</td>`},
      item:{t:'도번',cls:'center',w:104,
        h:r=>`<td class="center" title="${esc2(r.itemnm)}"><b>${esc2(r.item)}</b></td>`},
      change_day:{t:'당김,변경',cls:'center',w:62,h:r=>`<td class="center mut">${esc2(r.change_day)}</td>`},
      rmk1:{t:'비고',cls:'center',w:70,
        h:r=>`<td class="center mut bcap" style="max-width:70px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc2(r.rmk1)}">${esc2(r.rmk1)}</td>`},
      prod_rate:{t:'비율',cls:'num',w:44,h:r=>`<td class="num mut">${cap(r.prod_rate)}</td>`},
      fseq:{t:'From',cls:'num',w:48,h:r=>`<td class="num">${cap(r.fseq)}</td>`},
      tseq:{t:'To',cls:'num',w:48,h:r=>`<td class="num">${cap(r.tseq)}</td>`},
      ohm:{t:'시간',cls:'center',w:52,
        h:r=>`<td class="center mut">${esc2(String(r.ohm||'').length===4?String(r.ohm).slice(0,2)+':'+String(r.ohm).slice(2,4):(r.ohm||''))}</td>`},
      output:{t:'Output',cls:'center',w:112,
        h:r=>`<td class="center mut" style="white-space:nowrap">${esc2(outHm(r))}</td>`},
      lot:{t:'LOT수량',cls:'num',w:64,h:r=>`<td class="num">${cap(r.lot)}</td>`,
        s:(b,S)=>`<td class="num"><b>${nf(S('lot'))}</b></td>`},
      prod_qty:{t:'생산실적',cls:'num',w:64,h:r=>`<td class="num">${cap(r.prod_qty)}</td>`,
        s:(b,S)=>`<td class="num">${cap(S('prod_qty'))}</td>`},
      sale_qty:{t:'출하실적',cls:'num',w:64,
        h:r=>`<td class="num"${woDone(r)?' style="background:#fac090"':''}>${cap(r.sale_qty)}</td>`,
        s:(b,S)=>`<td class="num"${(b.length&&b.every(woDone))?' style="background:#fac090"':''}>${cap(S('sale_qty'))}</td>`},
      stock_qty:{t:'ASSY재고',cls:'num',w:70,
        h:r=>`<td class="num"${(+r.stock_qty||0)>0?' style="font-weight:700;color:#1c47a0"':''}>${cap(r.stock_qty)}</td>`,
        s:(b,S)=>`<td class="num">${cap(S('stock_qty'))}</td>`},
      plan_qty:{t:'출하계획',cls:'num',w:64,h:r=>`<td class="num">${cap(r.plan_qty)}</td>`,
        s:(b,S)=>`<td class="num">${cap(S('plan_qty'))}</td>`},
    };
    const C_DEF=['line_no','wo','model_no','tools','item','change_day','rmk1','prod_rate',
                 'fseq','tseq','ohm','output','lot','prod_qty','sale_qty','stock_qty','plan_qty'];
    const C_LS='s4_colorder', W_LS='s4_colwidth';
    const cOrd=(()=>{try{const s=JSON.parse(localStorage.getItem(C_LS)||'null');
        if(Array.isArray(s)&&s.length){const v=s.filter(k=>CD[k]);C_DEF.forEach(k=>{if(!v.includes(k))v.push(k);});return v;}
      }catch(e){}
      return C_DEF.slice();})();
    const cW=(()=>{try{return JSON.parse(localStorage.getItem(W_LS)||'{}')||{};}catch(e){return {};}})();
    const thW=k=>`width:${cW[k]||CD[k].w}px;min-width:${cW[k]||CD[k].w}px;max-width:${cW[k]||CD[k].w}px`;
    const headHtml=()=>cOrd.map(k=>`<th class="${CD[k].cls}" draggable="true" data-tk="${k}"`
      +` title="드래그=순서 이동 · 우측경계 드래그=너비조절(내 브라우저에 저장)"`
      +` style="cursor:grab;${thW(k)}">${CD[k].t}</th>`).join('');

    // 열 이동은 헤더 인덱스 기준으로 <td>를 옮기므로 순서만 맞으면 된다.
    const rowHtml=r=>`<tr class="s4row"${(r.del_flag||'0')==='1'?' style="color:#78909c" title="전일 삭제계획(참고용)"':''}>`
      +cOrd.map(k=>CD[k].h(r)).join('')
      +dates.map(d=>cell(r,d)).join('')+'</tr>';

    // 집계행(제번 블록) — 구분=집계/전체 일 때. 컬럼 순서(cOrd)를 그대로 따른다.
    const subHtml=blk=>{const r0=blk[0];
      const S=k=>blk.reduce((s,x)=>s+(+x[k]||0),0);
      return `<tr style="background:#cdeef7;font-weight:600;border-bottom:1px solid #9fb3c8">
        ${cOrd.map(k=>CD[k].s?CD[k].s(blk,S,r0):'<td></td>').join('')}
        ${dates.map(d=>{const pl=blk.reduce((s,x)=>s+((x.days&&x.days[d])||0),0);
          const sd=blk.reduce((s,x)=>s+((x.sday&&x.sday[d])||0),0);
          if(!pl&&!sd)return '<td class="num"></td>';
          const done=sd>0&&pl-sd<=0;
          const cov=!done&&blk.some(x=>_cov[ckey(x,d)]);
          const bg=done?'#fac090':(cov?'#ffff00':'');
          return `<td class="num"${bg?` style="background:${bg}"`:''}>${nf(sd)+'/'+nf(pl)}</td>`;}).join('')}</tr>`;};

    const bodyHtml=()=>{
      if(!rows.length)return `<tr><td colspan="${NC+1+dates.length}" class="empty">조회 결과 없음</td></tr>`;
      let h='',i=0;
      while(i<rows.length){
        const k=(rows[i].swo||rows[i].wo);let j=i;const blk=[];
        while(j<rows.length&&(rows[j].swo||rows[j].wo)===k){blk.push(rows[j]);j++;}
        if(st.view!=='집계') blk.forEach(r=>{h+=rowHtml(r);});
        if(st.view==='전체'||st.view==='집계') h+=subHtml(blk);
        i=j;}
      return h;};

    const tLot=rows.reduce((s,r)=>s+(+r.lot||0),0);
    const tSale=rows.reduce((s,r)=>s+(+r.sale_qty||0),0);
    const tStk=rows.reduce((s,r)=>s+(+r.stock_qty||0),0);
    const selN=st.sel.size;
    let selQ=0;
    rows.forEach(r=>dates.forEach(d=>{if(st.sel.has(ckey(r,d))){
      const pl=(r.days&&r.days[d])||0,sd=(r.sday&&r.sday[d])||0;selQ+=Math.max(0,pl-sd);}}));

    c.innerHTML=`
     <style>
       .s4tbl td,.s4tbl th{text-align:center}
       .s4tbl th.s4sat{color:#1558d6}.s4tbl th.s4sun{color:#c0392b}
       .s4tbl td.s4wk{background:#f4f6f9}
       .s4c[data-k]{cursor:cell}
       .s4c.s4sel{background-image:linear-gradient(rgba(219,234,254,.72),rgba(219,234,254,.72));
                  outline:2px solid #4a86e8;outline-offset:-2px;font-weight:700}
       .s4c.s4lock{cursor:default}
       /* 드래그 선택은 계획셀(.s4c)에서만 막는다. 나머지 칸은 Ctrl+C 복사 가능 */
       .s4tbl tbody td{user-select:text;-webkit-user-select:text}
       .s4tbl tbody td.s4c{user-select:none;-webkit-user-select:none}
       /* 지정한 헤더 너비가 지켜지도록(내용이 길어도 밀지 않게) */
       .s4tbl{table-layout:fixed}
       .s4tbl th,.s4tbl td{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
       /* 헤더·본문 전부 가운데 정렬 (.tbl .num 우측정렬을 이김) */
       .tbl.s4tbl th,.tbl.s4tbl td,
       .tbl.s4tbl th.num,.tbl.s4tbl td.num{text-align:center}
       /* 헤더 고정 — 스크롤해도 항상 보이게(§3). 배경 불투명 필수 */
       .tbl.s4tbl thead th{position:sticky;top:0;z-index:5;background:var(--head,#eef4ff);
         padding-right:10px;box-shadow:inset 0 -1px 0 var(--line,#c9d3e0)}
     </style>
     <div style="display:flex;flex-direction:column;height:100%">
     <div class="page-title" style="flex:0 0 auto">🚚 출하실적등록 <span style="font-size:12px;color:var(--muted);font-weight:400">w_pr_input_040 · 제번단위 출하실적(ASSY재고 차감)</span></div>
     <div class="page-sub" style="flex:0 0 auto">계획셀 <b>드래그 선택 → 우클릭 [확인]</b> = 완제품(ASSY)재고 있는 만큼만 출하처리 · <span style="background:#fac090;padding:0 4px">살구</span>=출하완료 · ${st.src==='live'?'🔴 레거시(라이브 직독·대사용)':'🟢 nx'}</div>
     <div class="toolbar" style="flex:0 0 auto">
       <label class="tl">기준일자</label><input class="inp" type="date" id="s4-from" value="${st.from}">
       <label class="tl">라인</label>
       <select class="inp" id="s4-line" style="width:150px"><option value="">% 전체</option>
         ${(st.lines||[]).map(o=>`<option value="${esc2(o.code)}"${st.line===o.code?' selected':''}>${esc2(o.code)} ${esc2(o.nm)}</option>`).join('')}</select>
       <label class="tl">기간</label>
       <select class="inp" id="s4-gigan" style="max-width:72px">${[1,2,3,4,5,6,7,8,14].map(d=>`<option value="${d}"${st.gigan===d?' selected':''}>${d}일</option>`).join('')}</select>
       <label class="tl">구분</label>
       ${['전체','집계','제번'].map(v=>`<label class="rl"><input type="radio" name="s4-vw" value="${v}"${st.view===v?' checked':''}> ${v}</label>`).join('')}
       <label class="tl">소스</label>
       <select class="inp" id="s4-src" style="width:112px"><option value="nx"${st.src==='nx'?' selected':''}>우리(nx)</option><option value="live"${st.src==='live'?' selected':''}>레거시 대사</option></select>
       <button class="btn" id="s4-search">🔍 조회</button>
       <div class="spacer"></div>
       <span class="rowcount" id="s4-selinfo">${selN?`선택 <b>${nf(selN)}</b>칸 · 수량 <b>${nf(selQ)}</b>`:''}</span>
       <button class="btn" id="s4-ok" style="background:#1c7c3a;color:#fff">✔ 확인(출하처리)</button>
       <button class="btn" id="s4-cancel" style="background:#c0392b;color:#fff">↩ 출하취소</button>
     </div>
     <div class="toolbar" style="flex:0 0 auto;margin-top:2px">
       <label class="tl">제번</label><input class="inp" id="s4-wo" value="${esc2(st.wo)}" style="width:130px" placeholder="제번" autocomplete="off">
       <label class="tl">도번</label><input class="inp" id="s4-item" value="${esc2(st.item)}" style="width:130px" placeholder="도번" autocomplete="off">
       <div class="spacer"></div>
       <span class="rowcount">행 <b>${nf(rows.length)}</b> · LOT합 <b>${nf(tLot)}</b> · 출하합 <b>${nf(tSale)}</b> · ASSY재고합 <b>${nf(tStk)}</b></span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc2(st.msg)}</div>`:''}
     <div id="s4-msg" class="page-sub" style="flex:0 0 auto;margin:0;padding:0;line-height:1.5"></div>
     <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit s4tbl" style="font-size:11px"><thead><tr>
       ${headHtml()}
       ${dates.map(d=>`<th class="num${dcls(d)}" style="width:58px;min-width:58px">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${st.loading?`<tr><td colspan="${NC+1+dates.length}" class="empty">조회 중…</td></tr>`:bodyHtml()}</tbody>
      </table></div></div>`;

    const g=id=>c.querySelector(id);
    g('#s4-search').onclick=()=>{st.from=g('#s4-from').value;st.gigan=+g('#s4-gigan').value;
      st.line=g('#s4-line').value;st.src=g('#s4-src').value;load();};
    g('#s4-gigan').onchange=()=>g('#s4-search').click();
    g('#s4-src').onchange=()=>{st.src=g('#s4-src').value;loadLines().then(load);};
    g('#s4-line').onchange=()=>{st.line=g('#s4-line').value;draw();};
    c.querySelectorAll('input[name=s4-vw]').forEach(rd=>rd.onchange=()=>{st.view=rd.value;draw();});
    ['#s4-wo','#s4-item'].forEach(id=>{const el=g(id);if(!el)return;
      el.oninput=()=>{const v=el.value,ss=el.selectionStart;
        if(id==='#s4-wo')st.wo=v.trim(); else st.item=v.trim();
        draw();const n=c.querySelector(id);
        if(n){n.value=v;n.focus();try{n.setSelectionRange(ss,ss);}catch(e){}}};});

    // ── 컬럼 순서 이동 + 너비 조절 (410·420과 동일 · localStorage 저장) ──
    //   순서: 헤더 드래그앤드롭 → 재렌더 없이 DOM 열만 이동(버벅임 없음)
    //   너비: 헤더 우측경계 드래그 · 경계 더블클릭 = 기본폭 복귀
    (function(){
      let _dtk=null;
      c.querySelectorAll('th[data-tk]').forEach(th=>{
        const key=th.getAttribute('data-tk');
        // 너비 핸들
        const rz=document.createElement('div');
        rz.style.cssText='position:absolute;top:0;right:0;width:7px;height:100%;cursor:col-resize;z-index:2';
        // ★position:relative 를 주면 CSS 의 position:sticky 가 덮여 헤더고정이 풀린다.
        //   sticky 도 absolute 자식의 기준(containing block)이 되므로 그대로 둔다.
        rz.draggable=false;
        rz.addEventListener('mousedown',e=>{e.preventDefault();e.stopPropagation();
          const sx=e.pageX, sw=th.offsetWidth;
          const mv=ev=>{const w=Math.max(28,sw+ev.pageX-sx);
            th.style.width=th.style.minWidth=th.style.maxWidth=w+'px';};
          const up=()=>{document.removeEventListener('mousemove',mv);document.removeEventListener('mouseup',up);
            cW[key]=th.offsetWidth;try{localStorage.setItem(W_LS,JSON.stringify(cW));}catch(_){}};
          document.addEventListener('mousemove',mv);document.addEventListener('mouseup',up);});
        rz.addEventListener('dblclick',e=>{e.stopPropagation();
          const w=CD[key].w; th.style.width=th.style.minWidth=th.style.maxWidth=w+'px';
          delete cW[key];try{localStorage.setItem(W_LS,JSON.stringify(cW));}catch(_){}});
        th.appendChild(rz);
        // 순서 이동
        th.ondragstart=e=>{_dtk=key;th.style.opacity='.4';
          try{e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',key);}catch(_){}};
        th.ondragend=()=>{th.style.opacity='';
          c.querySelectorAll('th[data-tk]').forEach(x=>x.style.borderLeft='');};
        th.ondragover=e=>{e.preventDefault();
          if(_dtk&&_dtk!==key)th.style.borderLeft='3px solid #2563eb';};
        th.ondragleave=()=>{th.style.borderLeft='';};
        th.ondrop=e=>{th.style.borderLeft='';e.preventDefault();
          const from=_dtk,to=key;_dtk=null;
          if(!from||from===to)return;
          const arr=cOrd.filter(k=>k!==from);
          const at=arr.indexOf(to); arr.splice(at<0?arr.length:at,0,from);
          try{localStorage.setItem(C_LS,JSON.stringify(arr));}catch(_){}
          cOrd.length=0; arr.forEach(k=>cOrd.push(k));
          const tbl=th.closest('table'); if(!tbl)return;
          const hr=tbl.tHead?tbl.tHead.rows[0]:null; if(!hr)return;
          const idxOf=(row,k)=>{const cs=row.children;
            for(let i=0;i<cs.length;i++)if(cs[i].getAttribute&&cs[i].getAttribute('data-tk')===k)return i;
            return -1;};
          const fi=idxOf(hr,from), ti=idxOf(hr,to); if(fi<0||ti<0)return;
          const mv=row=>{const cs=row.children;if(fi>=cs.length||ti>=cs.length)return;
            row.insertBefore(cs[fi],cs[ti]);};
          mv(hr);
          [...tbl.tBodies,...(tbl.tFoot?[tbl.tFoot]:[])].forEach(tbd=>{
            for(const row of tbd.rows) if(row.children.length===hr.children.length) mv(row);});
        };
      });
    })();

    // ── 사각영역 드래그 선택(키팅·가공420과 동일) ──
    const tb=c.querySelector('.s4tbl tbody'), gw=c.querySelector('.grid-wrap');
    // 셀키 → 잔량 맵을 1회만 만들어 둔다(선택정보 계산이 rows×dates 순회를 반복하지 않게).
    const _remOf=new Map();
    rows.forEach(r=>dates.forEach(d=>{
      const pl=(r.days&&r.days[d])||0,sd=(r.sday&&r.sday[d])||0;
      if(pl||sd)_remOf.set(ckey(r,d),Math.max(0,pl-sd));}));
    // 드래그 중엔 매 프레임 DOM 을 건드리지 않도록 rAF 로 합친다.
    let _siReq=0;
    const selInfoNow=()=>{const e=g('#s4-selinfo');if(!e)return;
      let q=0; st.sel.forEach(k=>{q+=_remOf.get(k)||0;});
      e.innerHTML=st.sel.size?`선택 <b>${nf(st.sel.size)}</b>칸 · 수량 <b>${nf(q)}</b>`:'';};
    const selInfo=()=>{if(_siReq)return;
      _siReq=requestAnimationFrame(()=>{_siReq=0;selInfoNow();});};
    if(tb&&gw){
      // 계획셀(.s4c)에서 시작한 드래그만 선택을 막는다 — 그 외 칸은 Ctrl+C 복사 가능
      gw.onselectstart=e=>{const t=e.target;return !(t&&t.closest&&t.closest('td.s4c'));};
      const rcOf=td=>{const tr=td.parentElement;return {r:tr?tr.rowIndex:-1,c:td.cellIndex};};
      const cellAt=(x,y)=>{const e=document.elementFromPoint(x,y);if(!e)return null;
        const td=e.closest('td.s4c[data-k]');if(td)return td;
        const tr=e.closest('tr');
        if(tr){let best=null,bd=1e9;
          tr.querySelectorAll('td.s4c[data-k]').forEach(z=>{const r=z.getBoundingClientRect();
            const d=(x<r.left)?(r.left-x):((x>r.right)?(x-r.right):0);
            if(d<bd){bd=d;best=z;}});
          if(best)return best;}
        return e.closest('td');};
      let drag=false,_a=null,_cells=null,_own=null,_last=null,_byRow=null,_prev=null;
      // 셀을 행별로 색인해 둔다 → 드래그 중엔 '사각형에 걸친 행'만 훑으면 된다.
      const snap=()=>{_cells=[...tb.querySelectorAll('td.s4c[data-k]')]
          .map(x=>{const p=rcOf(x);return {td:x,r:p.r,c:p.c,k:x.getAttribute('data-k')};});
        _byRow=new Map();
        for(const it of _cells){let a=_byRow.get(it.r);if(!a){a=[];_byRow.set(it.r,a);}a.push(it);}
        _prev=null;};
      const clearAll=()=>{tb.querySelectorAll('td.s4c.s4sel').forEach(td=>{
        st.sel.delete(td.getAttribute('data-k'));td.classList.remove('s4sel');});};
      const applyRect=td=>{if(!_a||!_byRow)return;
        const b=rcOf(td);
        const r1=Math.min(_a.r,b.r),r2=Math.max(_a.r,b.r);
        const c1=Math.min(_a.c,b.c),c2=Math.max(_a.c,b.c);
        // 같은 사각형이면 아무것도 하지 않는다(마우스가 셀 안에서 미세하게 움직일 때).
        if(_prev&&_prev.r1===r1&&_prev.r2===r2&&_prev.c1===c1&&_prev.c2===c2)return;
        // 직전 사각형과의 합집합 행만 재평가 → 전체(수천 셀) 순회 제거
        const lo=_prev?Math.min(r1,_prev.r1):r1, hi=_prev?Math.max(r2,_prev.r2):r2;
        for(let r=lo;r<=hi;r++){
          const arr=_byRow.get(r); if(!arr)continue;
          const rowIn=(r>=r1&&r<=r2);
          for(const it of arr){
            const inR=rowIn&&it.c>=c1&&it.c<=c2, has=st.sel.has(it.k);
            if(inR&&!has){st.sel.add(it.k);it.td.classList.add('s4sel');_own.add(it.k);}
            else if(!inR&&has&&_own.has(it.k)){st.sel.delete(it.k);it.td.classList.remove('s4sel');}}}
        _prev={r1,r2,c1,c2};
        selInfo();};
      tb.addEventListener('mousedown',e=>{if(e.button!==0)return;
        const start=e.target.closest('td');if(!start||!start.closest('tr'))return;
        const hit=e.target.closest('td.s4c[data-k]');
        // 계획셀이 아니면 드래그선택을 걸지 않는다 → 도번·제번 등은 자유롭게 복사
        if(!hit){if(!e.ctrlKey&&!e.metaKey){clearAll();selInfo();}return;}
        e.preventDefault();
        if(hit&&!e.ctrlKey&&!e.metaKey&&st.sel.has(hit.getAttribute('data-k'))&&st.sel.size===1){
          st.sel.delete(hit.getAttribute('data-k'));hit.classList.remove('s4sel');selInfo();return;}
        if(!e.ctrlKey&&!e.metaKey)clearAll();
        drag=true;_own=new Set();snap();_a=rcOf(start);_last=start;
        if(hit)applyRect(hit); else selInfo();});
      // mousemove 는 프레임당 1회만 처리(마우스 이벤트는 프레임보다 훨씬 자주 온다)
      let _mvReq=0,_mvXY=null;
      const _stop=()=>{drag=false;_a=null;_cells=null;_byRow=null;_last=null;_prev=null;
        if(_mvReq){cancelAnimationFrame(_mvReq);_mvReq=0;}};
      tb.addEventListener('mousemove',e=>{if(!drag)return;
        if(!(e.buttons&1)){_stop();return;}
        _mvXY={x:e.clientX,y:e.clientY};
        if(_mvReq)return;
        _mvReq=requestAnimationFrame(()=>{_mvReq=0;
          if(!drag||!_mvXY)return;
          const td=cellAt(_mvXY.x,_mvXY.y)||_last;
          if(td){_last=td;applyRect(td);}});});
      document.addEventListener('mouseup',_stop);
      // 우클릭 = 확인/취소 메뉴(생산준비등록과 동일). body 에 렌더(§3)
      gw.oncontextmenu=(ev)=>{
        const td=ev.target.closest('td.s4c[data-k]'); if(!td)return;
        ev.preventDefault();
        if(!st.sel.has(td.getAttribute('data-k'))){clearAll();
          st.sel.add(td.getAttribute('data-k'));td.classList.add('s4sel');selInfo();}
        let qOk=0,qNo=0;
        rows.forEach(r=>dates.forEach(d=>{if(!st.sel.has(ckey(r,d)))return;
          const pl=(r.days&&r.days[d])||0, s2=(r.sday&&r.sday[d])||0;
          const rm=Math.max(0,pl-s2); if(rm>0)qOk+=rm; if(s2>0)qNo+=s2;}));
        const canC=qOk>0, canX=qNo>0;
        const old=document.getElementById('s4-ctxmenu'); if(old)old.remove();
        const mn=document.createElement('div'); mn.id='s4-ctxmenu';
        mn.style.cssText=`position:fixed;left:${ev.clientX}px;top:${ev.clientY}px;z-index:99999;background:#fff;border:1px solid #b8c4d4;border-radius:6px;box-shadow:0 3px 10px rgba(0,0,0,.25);font-size:12px;min-width:190px;overflow:hidden`;
        mn.innerHTML=`<div style="padding:5px 12px;background:#f2f6fb;color:#456;border-bottom:1px solid #e3e9f0">선택 ${nf(st.sel.size)}칸 · 출하가능 ${nf(qOk)} / 취소가능 ${nf(qNo)}</div>`
          +`<div class="s4m" data-a="ok" style="padding:7px 12px;cursor:${canC?'pointer':'not-allowed'};color:${canC?'#1c7c3a':'#c0c8d2'};font-weight:600;display:flex;justify-content:space-between;gap:14px"><span>✅ 확 인(출하처리) ${qOk?nf(qOk):''}</span><span style="color:#8aa0bd">F12</span></div>`
          +`<div class="s4m" data-a="no" style="padding:7px 12px;cursor:${canX?'pointer':'not-allowed'};color:${canX?'#c0392b':'#c0c8d2'};border-top:1px solid #eee;display:flex;justify-content:space-between;gap:14px"><span>⏪ 취 소(출하취소) ${qNo?nf(qNo):''}</span><span style="color:#8aa0bd">F11</span></div>`;
        document.body.appendChild(mn);
        const rc=mn.getBoundingClientRect();
        if(rc.right>innerWidth)mn.style.left=(innerWidth-rc.width-6)+'px';
        if(rc.bottom>innerHeight)mn.style.top=(innerHeight-rc.height-6)+'px';
        mn.querySelectorAll('.s4m').forEach(el=>{
          el.onmouseenter=()=>{if(!el.style.cursor.includes('not'))el.style.background='#eaf2ff';};
          el.onmouseleave=()=>el.style.background='';
          el.onclick=()=>{const ac=el.dataset.a;
            if((ac==='ok'&&!canC)||(ac==='no'&&!canX))return;
            mn.remove(); if(ac==='ok')doConfirm(); else doCancel();};});
        setTimeout(()=>document.addEventListener('click',()=>{
          const x=document.getElementById('s4-ctxmenu');if(x)x.remove();},{once:true}),0);
      };
    }

    // 선택셀 → 처리대상
    const picked=()=>{const out=[];
      rows.forEach(r=>dates.forEach(d=>{
        if(!st.sel.has(ckey(r,d)))return;
        const pl=(r.days&&r.days[d])||0,sd=(r.sday&&r.sday[d])||0;
        const rem=Math.max(0,pl-sd);
        if(rem>0)out.push({wo:r.wo,swo:r.swo,item:r.item,line_no:r.line_no,ymd:d,qty:rem});}));
      return out;};
    const msg=(t,ok)=>{const e=g('#s4-msg');if(e)e.innerHTML=`<span style="color:${ok?'#1c7c3a':'#c0392b'}">${esc2(t)}</span>`;};
    // 부분갱신 — 서버 done[] 을 st.rows 에 반영하고 표만 다시 그린다(재조회 X, 스크롤 유지)
    const applyLocal=(done,sgn)=>{const left={};
      (done||[]).forEach(x=>{const y=x.cell_ymd||x.ymd, q=(+x.qty||0)*sgn;
        st.rows.forEach(r=>{if(r.item!==x.item)return;
          if(x.wo&&r.wo!==x.wo)return;
          if(x.swo!==undefined&&x.swo!==null&&(r.swo||'')!==(x.swo||''))return;
          r.sale_qty=Math.max(0,(+r.sale_qty||0)+q);
          if(y){r.sday=r.sday||{};r.sday[y]=Math.max(0,(+r.sday[y]||0)+q);}});
        if(x.left!==undefined&&x.left!==null)left[x.item]=+x.left;});
      st.rows.forEach(r=>{if(r.item in left)r.stock_qty=left[r.item];});
      st.sel.clear();
      const w0=c.querySelector('.grid-wrap');const sy=w0?w0.scrollTop:0,sx=w0?w0.scrollLeft:0;
      draw();
      const w1=c.querySelector('.grid-wrap');if(w1){w1.scrollTop=sy;w1.scrollLeft=sx;}};

    const doConfirm=async()=>{
      if(st.src==='live'){msg('레거시 대사 모드에서는 출하처리를 할 수 없습니다(읽기전용). 소스를 우리(nx)로 바꾸세요.',false);return;}
      const cells=picked();
      if(!cells.length){msg('출하처리할 셀을 선택하세요(계획 남은 칸).',false);return;}
      // ★ASSY재고 부족 사전점검 — 서버는 "재고만큼만" 출하하므로, 선택량을 다 못 잡는 경우
      //   무엇이 얼마나 모자란지 먼저 알리고 진행여부를 묻는다.
      //   같은 도번을 여러 셀이 함께 쓰면 재고를 나눠 쓰므로 도번 단위로 합산해 판정.
      {
        const stkOf={}; rows.forEach(r=>{if(!(r.item in stkOf))stkOf[r.item]=+r.stock_qty||0;});
        const need={}; cells.forEach(x=>{need[x.item]=(need[x.item]||0)+(+x.qty||0);});
        const short=Object.keys(need).filter(it=>(stkOf[it]||0)<need[it])
          .map(it=>({item:it,need:need[it],have:Math.max(0,stkOf[it]||0)}));
        if(short.length){
          const totN=Object.values(need).reduce((a,b)=>a+b,0);
          const totG=Object.keys(need).reduce((a,it)=>a+Math.min(need[it],Math.max(0,stkOf[it]||0)),0);
          const list=short.slice(0,10).map(s=>
            `　· ${s.item} : 계획 ${nf(s.need)} / 재고 ${nf(s.have)} → ${nf(s.have)}개만 처리`).join('\n');
          const more=short.length>10?`\n　… 외 ${short.length-10}건`:'';
          if(!confirm(`ASSY(완제품)재고가 부족합니다.\n\n${list}${more}\n\n`
            +`선택 ${nf(totN)}개 중 ${nf(totG)}개만 출하실적이 잡히고,\n`
            +`나머지 ${nf(totN-totG)}개는 계획으로 남습니다.\n\n그래도 진행할까요?`))return;
        }
      }
      // 우클릭 확인 = 즉시 처리(재확인 없음)
      g('#s4-ok').disabled=true;
      try{
        const d=await(await fetch(`${API}/api/sale040/confirm`,{method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({cells:cells,user:'웹',ymd:st.from})})).json();
        if(d.ok){applyLocal(d.done||[],+1);msg('✔ '+d.msg,true);} else msg(d.msg||'출하처리 실패',false);
      }catch(e){msg('출하처리 실패',false);}
      finally{const b=c.querySelector('#s4-ok');if(b)b.disabled=false;}};

    const doCancel=async()=>{
      if(st.src==='live'){msg('레거시 대사 모드에서는 취소할 수 없습니다(읽기전용).',false);return;}
      const out=[];
      rows.forEach(r=>dates.forEach(d=>{
        if(!st.sel.has(ckey(r,d)))return;
        const sd=(r.sday&&r.sday[d])||0;
        if(sd>0)out.push({wo:r.wo,swo:r.swo,item:r.item,ymd:d});}));
      if(!out.length){msg('취소할 출하실적이 있는 셀을 선택하세요.',false);return;}
      if(!confirm(`[출하취소]\n\n선택 ${out.length}칸의 출하실적을 취소합니다.\n완제품 재고가 복원됩니다. 진행할까요?`))return;
      g('#s4-cancel').disabled=true;
      try{
        const d=await(await fetch(`${API}/api/sale040/cancel`,{method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({cells:out,user:'웹'})})).json();
        if(d.ok){applyLocal(d.done||[],-1);msg('✔ '+d.msg,true);} else msg(d.msg||'취소 실패',false);
      }catch(e){msg('취소 실패',false);}
      finally{const b=c.querySelector('#s4-cancel');if(b)b.disabled=false;}};

    g('#s4-ok').onclick=doConfirm;
    g('#s4-cancel').onclick=doCancel;
    selInfo();
  };
  (async()=>{await loadLines();load();})();
};

SCREEN.prodstockadj=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const d8=s=>{s=(''+(s||'')).trim();return s.length>=6?`20${s.slice(0,2)}-${s.slice(2,4)}-${s.slice(4,6)}`:s;};
  const dt=s=>String(s||"").slice(0,19).replace("T"," ");
  const now=new Date();
  const won=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:4});
  let st={rows:[],tags:{},tag:'%',item:'',fr:iso(new Date(now.getFullYear(),now.getMonth(),1)),to:iso(now),
          sel:{},edit:null,itemnm:'',loading:false,totqty:0,totamt:0};
  const load=async()=>{st.loading=true;st.sel={};draw();
    try{const r=await fetch(`${API}/api/prodstockadj/list?fr=${yy(st.fr)}&to=${yy(st.to)}&tag=${encodeURIComponent(st.tag)}&item=${encodeURIComponent(st.item)}`);
      const j=await r.json();st.rows=j.rows||[];st.tags=j.tags||{};st.totqty=j.totqty||0;st.totamt=j.totamt||0;}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const lookItem=async()=>{const e=st.edit;if(!e||!e.item_code){st.itemnm='';draw();return;}
    try{const r=await fetch(`${API}/api/wr/itemsearch?q=${encodeURIComponent(e.item_code)}`);const j=await r.json();
      const hit=(j.rows||[]).find(x=>x.item===e.item_code);st.itemnm=hit?hit.nm:'';}catch(x){st.itemnm='';}draw();};
  const save=async()=>{const e=st.edit;if(!e.item_code)return alert("도번을 입력하세요.");
    if(e.maint_qty===""||isNaN(+e.maint_qty))return alert("수정수량(숫자)을 입력하세요.");
    try{const r=await fetch(`${API}/api/prodstockadj/save`,{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({...e,maint_ymd:yy(e.maint_ymd_iso)||e.maint_ymd})});
      const j=await r.json();if(!r.ok)throw new Error(j.detail||r.status);st.edit=null;st.itemnm='';await load();}catch(x){alert("저장 실패: "+x.message);}};
  const delSel=async()=>{const ids=Object.keys(st.sel).filter(k=>st.sel[k]).map(Number);
    if(!ids.length)return alert("삭제할 행을 선택해 주세요.");
    if(!window.confirm(`${ids.length}건 삭제할까요?`))return;
    try{const r=await fetch(`${API}/api/prodstockadj/delete`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ids})});
      if(!r.ok)throw new Error((await r.json()).detail||r.status);await load();}catch(x){alert("삭제 실패: "+x.message);}};
  const openEdit=(r)=>{st.edit=r?{id:r.id,maint_ymd_iso:d8(r.maint_ymd),maint_tag:r.maint_tag||'2',item_code:r.item_code,
      cust_code:r.cust_code||'',maint_qty:r.maint_qty,maint_cost:r.maint_cost,work_order:r.work_order||'',split_work_order:r.split_work_order||'',remarks:r.remarks||''}
      :{maint_ymd_iso:st.to,maint_tag:'2',item_code:'',cust_code:'',maint_qty:'',maint_cost:0,work_order:'',split_work_order:'',remarks:''};
    st.itemnm=r?r.itemnm:'';draw();if(r)lookItem();};
  const draw=()=>{
    const selcnt=Object.values(st.sel).filter(Boolean).length;const e=st.edit;
    const tagOpts=Object.entries(st.tags).map(([k,v])=>`${k}:${v}`);
    c.innerHTML=`<div style="display:flex;flex-direction:column;height:100%">
     <div class="page-title" style="flex:0 0 auto">📦 제품재고조정</div>
     <div class="page-sub" style="flex:0 0 auto">제품수불원장 <code>SA_T_STOCK_MAINT</code> 조회 + 수동 재고조정 · 🔵 nx(미러 이력=읽기전용 ∪ 웹조정=편집) · 레거시 <code>w_sa_stock_010</code></div>
     <div class="toolbar" style="flex:0 0 auto">
       <label class="tl">수정기간</label><input class="inp" type="date" id="a-fr" value="${esc(st.fr)}" style="width:135px"> ~ <input class="inp" type="date" id="a-to" value="${esc(st.to)}" style="width:135px">
       <label class="tl" style="margin-left:8px">구분</label>
       <select class="inp" id="a-tag"><option value="%" ${st.tag==='%'?'selected':''}>전체</option>${Object.entries(st.tags).map(([k,v])=>`<option value="${esc(k)}" ${st.tag===k?'selected':''}>${esc(k)}:${esc(v)}</option>`).join('')}</select>
       <label class="tl" style="margin-left:8px">도번</label><input class="inp" id="a-item" value="${esc(st.item)}" placeholder="도번" style="width:130px">
       <button class="btn" id="a-go">🔍 조회</button>
       <div class="spacer"></div>
       <button class="btn" id="a-add" style="background:#2e86de;color:#fff">➕ 추가</button>
       <button class="btn" id="a-del">🗑 삭제${selcnt?`(${selcnt})`:""}</button>
       <button class="btn xls" id="a-xls">📥 엑셀</button>
     </div>
     ${e?`<div class="panel" style="border:2px solid #2e86de;flex:0 0 auto"><div class="panel-h">${e.id?"수정":"신규"} 재고조정</div><div class="panel-b">
       <div class="toolbar" style="flex-wrap:wrap;gap:8px">
         <label class="tl">수정일자<span style="color:red">*</span></label><input class="inp" type="date" id="e-ymd" value="${esc(e.maint_ymd_iso||'')}" style="width:135px">
         <label class="tl">구분</label><select class="inp" id="e-tag">${Object.entries(st.tags).map(([k,v])=>`<option value="${esc(k)}" ${(e.maint_tag||'2')===k?"selected":""}>${esc(k)}:${esc(v)}</option>`).join("")}</select>
         <label class="tl">도번<span style="color:red">*</span></label><input class="inp" id="e-item" value="${esc(e.item_code||"")}" placeholder="도번" style="width:150px" list="e-itemdl">
         <span style="font-size:12px;color:var(--muted);max-width:180px;overflow:hidden;text-overflow:ellipsis" title="${esc(st.itemnm||'')}">${esc(st.itemnm||'')}</span>
         <label class="tl">수정수량<span style="color:red">*</span></label><input class="inp" id="e-qty" value="${esc(e.maint_qty??"")}" style="width:90px;text-align:right" placeholder="±수량">
         <label class="tl">수정단가</label><input class="inp" id="e-cost" value="${esc(e.maint_cost??0)}" style="width:90px;text-align:right">
         <label class="tl">Work Order</label><input class="inp" id="e-wo" value="${esc(e.work_order||"")}" style="width:100px">
         <label class="tl">비고</label><input class="inp" id="e-rmk" value="${esc(e.remarks||"")}" style="width:160px">
         <button class="btn" id="e-save" style="background:#27ae60;color:#fff">💾 저장</button><button class="btn" id="e-cancel">취소</button>
       </div>
       <div style="font-size:12px;color:var(--muted);margin-top:6px">수정금액(예상) = 수량 × 단가 = <b>${won(Math.trunc((+e.maint_qty||0)*(+e.maint_cost||0)))}</b> · 재고조정(수량)이 기본, 단가 미입력시 0</div></div></div>`:""}
     <div class="grid-wrap psa-grid" style="flex:1;min-height:0;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
       <th class="center" style="width:28px"><input type="checkbox" id="a-all"></th>
       <th>수정일자</th><th class="num">수정SEQ</th><th class="center">수정구분</th><th>도번</th><th>품명</th>
       <th class="num">수정수량</th><th class="num">수정단가</th><th class="num">수정금액</th>
       <th>비고</th><th>작업자</th><th>작업일시</th><th>Work Order</th><th>Split WO</th><th class="center">관리</th></tr></thead>
     <tbody>${st.loading?`<tr><td colspan="15" class="empty">조회 중…</td></tr>`:(st.rows.length?st.rows.map(r=>`<tr${r.editable?"":' style="background:#fafbfc"'}>
       <td class="center">${r.editable?`<input type="checkbox" class="a-ck" data-id="${r.id}" ${st.sel[r.id]?"checked":""}>`:""}</td>
       <td>${d8(r.maint_ymd)}</td><td class="num">${r.maint_seq??""}</td>
       <td class="center">${esc(r.maint_tag||"")}:${esc(r.tagnm||"")}</td>
       <td><b>${esc(r.item_code)}</b></td><td class="cap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.itemnm||"")}">${esc(r.itemnm||"")}</td>
       <td class="num" style="${(+r.maint_qty<0)?'color:#c0392b':''}">${won(r.maint_qty)}</td><td class="num">${won(r.maint_cost)}</td><td class="num">${won(r.maint_amt)}</td>
       <td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.remarks||"")}">${esc(r.remarks||"")}</td>
       <td>${esc(r.reg_user||"")}</td><td style="font-size:11px">${dt(r.work_dt)}</td>
       <td>${esc(r.work_order||"")}</td><td>${esc(r.split_work_order||"")}</td>
       <td class="center">${r.editable?`<button class="btn xs a-ed" data-id="${r.id}">수정</button>`:'<span style="color:#9aa6b2;font-size:11px" title="기존이력(nx미러)·읽기전용">📁이력</span>'}</td></tr>`).join("")
       :`<tr><td colspan="15" class="empty">결과 없음 — [추가]로 재고조정 등록</td></tr>`)}
     <tr class="grandtot"><td colspan="6" class="right">합계 ${won(st.rows.length)}건</td><td class="num">${won(st.totqty)}</td><td></td><td class="num">${won(st.totamt)}</td><td colspan="6"></td></tr>
     </tbody></table></div>
     <datalist id="e-itemdl"></datalist>
     <div class="rowcount" style="flex:0 0 auto">${won(st.rows.length)}건 · ${esc(yy(st.fr))}~${esc(yy(st.to))}</div>
     <style>.psa-grid thead th{position:sticky;top:0;z-index:3;background:#f4f7fc}.psa-grid tr.grandtot td{position:sticky;bottom:0;background:#eaf1fb;font-weight:700;z-index:2;border-top:2px solid #cdd9ef}</style></div>`;
    const g=id=>c.querySelector(id);
    g("#a-fr").onchange=x=>st.fr=x.target.value;g("#a-to").onchange=x=>st.to=x.target.value;
    g("#a-tag").onchange=x=>{st.tag=x.target.value;load();};
    g("#a-item").oninput=x=>st.item=x.target.value;g("#a-item").onkeyup=x=>{if(x.key==='Enter')load();};
    g("#a-go").onclick=load;g("#a-add").onclick=()=>openEdit(null);g("#a-del").onclick=delSel;
    g("#a-xls").onclick=()=>{const hd=['수정일자','수정SEQ','수정구분','도번','품명','수정수량','수정단가','수정금액','비고','작업자','작업일시','WorkOrder','SplitWO'];
      downloadCSV('제품재고조정_'+yy(st.fr)+'_'+yy(st.to)+'.csv',hd,st.rows.map(r=>[d8(r.maint_ymd),r.maint_seq,r.maint_tag+':'+(r.tagnm||''),r.item_code,r.itemnm,r.maint_qty,r.maint_cost,r.maint_amt,r.remarks,r.reg_user,dt(r.work_dt),r.work_order,r.split_work_order]));};
    const all=g("#a-all");if(all)all.onclick=x=>{st.rows.forEach(r=>{if(r.editable)st.sel[r.id]=x.target.checked;});draw();};
    c.querySelectorAll(".a-ck").forEach(x=>x.onchange=()=>{st.sel[x.dataset.id]=x.checked;draw();});
    c.querySelectorAll(".a-ed").forEach(x=>x.onclick=()=>{const r=st.rows.find(v=>v.id==x.dataset.id);openEdit(r);});
    if(e){g("#e-ymd").onchange=x=>e.maint_ymd_iso=x.target.value;
      g("#e-tag").onchange=x=>e.maint_tag=x.target.value;
      g("#e-item").oninput=x=>e.item_code=x.target.value.trim();g("#e-item").onblur=lookItem;
      g("#e-qty").oninput=x=>e.maint_qty=x.target.value;g("#e-qty").onblur=draw;
      g("#e-cost").oninput=x=>e.maint_cost=x.target.value;g("#e-cost").onblur=draw;
      g("#e-wo").oninput=x=>e.work_order=x.target.value.trim();g("#e-rmk").oninput=x=>e.remarks=x.target.value;
      g("#e-save").onclick=save;g("#e-cancel").onclick=()=>{st.edit=null;st.itemnm='';draw();};}
    if(typeof attachResizers!=='undefined')attachResizers(c);
  };
  load();
};
