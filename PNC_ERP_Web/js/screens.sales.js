/* ===== PNC ERP screens.sales.js — 영업 SCREEN (app.js 분할, 순수이동) ===== */

/* 제품입출고현황 (영업, dw_pr_stock_110) — 좌:제품(P/N)재고(수불장) 우:선택품목 입출고이력. item기준(파트없음), 전월이월 2502기준 */
SCREEN.prodinvout=(c)=>{
  const API=API_BASE;
  let rows=[], mv={}, curYm='', loading=false, msg='';   // rows=[item,desc,workNm,stock,bf]
  const fmtYmd=y=>{y=(''+(y||'')).trim();return (y.length>=6&&y!=='000000')?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:'00/00/00';};
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-','');
  let sel=null, curL=[], source='live';   // ★Phase5 데이터원(기본 라이브 무변경)
  const load=async(ym)=>{loading=true;msg='';sel=null;
    const st=c.querySelector('#lbody');if(st)st.innerHTML=spinRow(4);
    if(source==='nx'){loading=false;return nxDerivedView(c,`${API}/api/live/prodinvout?ym=${encodeURIComponent(ym||'')}&source=nx`,{title:'제품입출고현황',onBack:()=>{source='live';load(ym);}});}
    try{const r=await fetch(`${API}/api/live/prodinvout?ym=${encodeURIComponent(ym||'')}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();curYm=j.ym||ym||'';rows=j.stock||[];mv=j.moves||{};}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];mv={};}
    loading=false;
    const ymi=c.querySelector('#ym');if(ymi)ymi.value=ymToInput(curYm);
    const ws=[...new Set(rows.map(r=>r[2]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ko'));
    const wsel=c.querySelector('#work');if(wsel){const v=wsel.value;wsel.innerHTML='<option value="">전체</option>'+ws.map(w=>`<option value="${esc(w)}">${esc(w)}</option>`).join('');wsel.value=v;}
    const sub=c.querySelector('#piv-sub');if(sub)sub.innerHTML=`제품(P/N)별 재고 + 선택품목 입출고이력(누적재고) · 원본 <code>SA_T_STOCK_MAINT</code> 외 · 🔴 라이브 ${esc(ymToInput(curYm)||'-')}(이월기준 2502) · 0재고 숨김`;
    renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 품목을 클릭하세요</div>';};
  c.innerHTML=`
   <div class="page-title">🔁 제품입출고현황</div>
   <div class="page-sub" id="piv-sub">제품(P/N)별 재고 + 선택품목 입출고이력(누적재고) · 원본 <code>SA_T_STOCK_MAINT</code> 외 · 🔴 라이브(이월기준 2502) · 0재고 숨김</div>
   <div class="toolbar">
     <label class="tl">조회월</label><input type="month" class="inp" id="ym" style="min-width:120px">
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
  c.querySelector('#go').onclick=renderLeft;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')renderLeft();};
  c.querySelector('#nxsrc').onclick=()=>{source='nx';load(curYm);};   // ★Phase5 nx 파생 보기
  c.querySelector('#gubun').onchange=renderLeft;c.querySelector('#work').onchange=renderLeft;
  c.querySelector('#ym').onchange=e=>load(inYm(e.target.value));
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#gubun').value='all';c.querySelector('#work').value='';sel=null;renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 품목을 클릭하세요</div>';};
  c.querySelector('#xls').onclick=()=>downloadCSV('제품입출고현황.csv',['P/N','품명','재고','작업처'],curL.map(r=>[r[0],r[1],r[3],r[2]]));
  load('');
};

/* 영업예상매출현황 (영업, dw_pr_plan_190) — 도번×일별 수량 피벗 + 하단 일별 금액줄. ★차감=LG리시빙(20일 백로그), 21일+ 라이브일치. 차감전/차감후 토글 */
SCREEN.salesforecast=(c)=>{
  const API=API_BASE;
  let F={days:[],rows:[],base:''}, loading=true, mode='net', cur=[], metric='sales', reqSeq=0, sortKey='', sortDir=1;   // mode:net(차감후)|gross(차감전=라이브) · metric:sales(영업예상매출)|sagub(예상 LG사급금액) · sortKey/Dir:헤더더블클릭 정렬
  const WD=['일','월','화','수','목','금','토'];
  const dlabel=y=>{y=''+y;const D=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));return `${y.slice(2,4)}/${y.slice(4,6)}<span class="wd">${WD[D.getDay()]}</span>`;};
  const load=async(base,to)=>{loading=true;const mySeq=++reqSeq, myMetric=metric;draw();   // ★race가드: 토글 왕복 시 늦게 온 이전 응답이 최신 데이터 덮어쓰기 방지(최신 mySeq만 반영)
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
        ?'🟢 <b>라이브</b> LG 생산계획 기준 <b>예상 LG사급금액</b>(LG사급 2종 중 <b>사급부품</b>·원소재 동 별도) · 계획수량 × 개당 사급금액(BOM 사급부품[소분류 LG사급] 소요 × <b>COSP 사급가</b>=품목단가관리 사급가업로드) · 원화(KRW)'
        :'🟢 <b>라이브</b> LG 생산계획 기준 일별 예상매출 · 원본 <code>sa_t_plan_item_dtl</code>+<code>pr_t_plan_input</code>×단가(<code>pr_m_item_cost</code> S/E=LG판매가) · 레거시 190 재현(차감전=완전일치 검증) · <b>차감후=첫계획일 pr_t_plan_input 과대분 제거</b> · 원화(KRW)'} · 기간 ${esc(F.base||'')}~${esc(F.to||'')}${metric==='sagub'&&F.asof?' · 사급가 기준일 '+esc(F.asof):''}${loading?' · <span style="color:#b8860b">불러오는 중…</span>':''}${F._err?' · <span style="color:#c0392b">'+esc(F._err)+'</span>':''}</div>
     <div class="toolbar">
       <label class="tl">종류</label>
       <div class="toggle-group"><button data-metric="sales" class="${metric==='sales'?'on':''}">영업 예상매출</button><button data-metric="sagub" class="${metric==='sagub'?'on':''}">예상 LG사급금액</button></div>
       <label class="tl">기간</label><input type="text" inputmode="numeric" class="inp sf-date" id="sf-base" value="${F.base?('20'+F.base.slice(0,2)+'-'+F.base.slice(2,4)+'-'+F.base.slice(4,6)):''}" placeholder="YYYY-MM-DD" maxlength="10" title="시작일 — 숫자 직접입력(예 20260901 또는 260901)" style="width:118px"><span style="color:var(--muted);margin:0 3px">~</span><input type="text" inputmode="numeric" class="inp sf-date" id="sf-to" value="${F.to?('20'+F.to.slice(0,2)+'-'+F.to.slice(2,4)+'-'+F.to.slice(4,6)):''}" placeholder="YYYY-MM-DD" maxlength="10" title="종료일(비우면 전체) — 숫자 직접입력" style="width:118px">
       <label class="tl">구분</label>
       <div class="toggle-group"><button data-mode="net" class="${mode==='net'?'on':''}">차감후(순예상)</button><button data-mode="gross" class="${mode==='gross'?'on':''}">차감전(원계획=라이브)</button></div>
       <select class="sel" id="work"><option value="">전체작업처</option>${works.map(w=>`<option value="${esc(w)}">${esc(w)}</option>`).join('')}</select>
       <input class="inp" id="q" list="sf-ql" placeholder="도번/품명 입력" autocomplete="off"><datalist id="sf-ql">${sfOpts}</datalist>
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    c.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;draw();});
    // ★날짜 텍스트 직접입력: 6자리(YYMMDD)/8자리(YYYYMMDD) 모두 처리. 자동 대시 서식. Enter/blur 시 재조회. (type=date 네이티브 타이핑 불안정 회피)
    const toY=el=>{const d=(el.value||'').replace(/\D/g,''); return d.length>=8?d.slice(2,8):(d.length===6?d:'');};
    const fmtD=v=>{const d=(''+v).replace(/\D/g,'').slice(0,8); let s=d.slice(0,4); if(d.length>4)s+='-'+d.slice(4,6); if(d.length>6)s+='-'+d.slice(6,8); return s;};
    c.querySelectorAll('[data-metric]').forEach(b=>b.onclick=()=>{if(metric===b.dataset.metric)return;metric=b.dataset.metric;load(toY(c.querySelector('#sf-base')),toY(c.querySelector('#sf-to')));});
    const sfReload=()=>load(toY(c.querySelector('#sf-base')),toY(c.querySelector('#sf-to')));   // 기간(from~to) 재조회
    c.querySelectorAll('.sf-date').forEach(el=>{
      el.oninput=()=>{const p=el.value.length; el.value=fmtD(el.value);};   // 타이핑 즉시 YYYY-MM-DD 서식
      el.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();sfReload();}};
      el.onchange=sfReload;   // 포커스 벗어날 때 재조회
    });
    const dayQ=(r,d)=>(mode==='net'?r.ndays:r.gdays)[d]||0;
    const rowQ=r=>mode==='net'?r.nq:r.gq, rowA=r=>mode==='net'?r.namt:r.gamt;
    // ★헤더 더블클릭 정렬: 컬럼별 정렬값(도번/품명/작업처=문자, 합계=금액, 일자=그 날 수량)
    const sortVal=(r,k)=>{ if(k==='item'||k==='nm'||k==='wc')return r[k]||''; if(k==='amt')return rowA(r); if(k&&k[0]==='d')return dayQ(r,k.slice(2)); return ''; };
    const arrow=k=>sortKey===k?(sortDir===1?' ▲':' ▼'):'';
    const render=()=>{
      const q=c.querySelector('#q').value.trim().toLowerCase(), wf=c.querySelector('#work').value;
      cur=rows.filter(r=>(!wf||r.wc===wf)&&(!q||(''+r.item).toLowerCase().includes(q)||(''+r.nm).toLowerCase().includes(q))&&rowQ(r)>0);
      if(sortKey){ cur.sort((a,b)=>{const x=sortVal(a,sortKey),y=sortVal(b,sortKey),nx=+x,ny=+y;
          return (typeof x==='number'||(x!==''&&y!==''&&!isNaN(nx)&&!isNaN(ny)))?(nx-ny)*sortDir:String(x).localeCompare(String(y),'ko')*sortDir;}); }
      else cur.sort((a,b)=>(''+a.item).localeCompare(''+b.item,'ko'));
      const dHdr=days.map(d=>`<th class="num" data-sk="d:${d}" title="더블클릭 정렬">${dlabel(d)}${arrow('d:'+d)}</th>`).join('');
      // ★단가 숨김, 합계·일별 모두 수량(위)/금액(아래) 스택 · th data-sk=더블클릭 정렬키
      c.querySelector('#th').innerHTML=`<tr><th data-sk="item" title="더블클릭 정렬">도번${arrow('item')}</th><th class="cap" data-sk="nm" title="더블클릭 정렬">품명${arrow('nm')}</th><th data-sk="wc" title="더블클릭 정렬">작업처${arrow('wc')}</th><th class="num gstock" data-sk="amt" title="더블클릭 정렬(금액)">합계${arrow('amt')}<br><span class="wd">수량/금액</span></th>${dHdr}</tr>`;
      const stack=(q,a)=>`<b class="qty">${won(q)}</b><br><span class="famt">${wonI(a)}</span>`;
      let tb=cur.map(r=>`<tr><td><b>${esc(r.item)}</b></td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td class="cap" title="${esc(r.wc)}">${esc(r.wc)}</td><td class="num gstock">${stack(rowQ(r),rowA(r))}</td>${days.map(d=>{const v=dayQ(r,d);return `<td class="num">${v?stack(v,Math.round(v*r.cost)):''}</td>`;}).join('')}</tr>`).join('');
      const gQ=cur.reduce((a,b)=>a+rowQ(b),0), gA=cur.reduce((a,b)=>a+rowA(b),0);
      const gdQ=days.map(d=>cur.reduce((a,b)=>a+dayQ(b,d),0));
      const gdA=days.map(d=>cur.reduce((a,b)=>a+dayQ(b,d)*b.cost,0));
      if(cur.length){
        // 하단 총계(sticky): 각 칸에 수량/금액 스택
        tb+=`<tr class="grandtot"><td colspan="3" class="right">총계 (${won(cur.length)} 도번)</td><td class="num gstock">${stack(gQ,gA)}</td>${gdQ.map((v,i)=>`<td class="num">${v?stack(v,Math.round(gdA[i])):''}</td>`).join('')}</tr>`;
      }
      c.querySelector('#body').innerHTML=cur.length?tb:`<tr><td colspan="${4+days.length}" class="empty">결과 없음</td></tr>`;
      const sumG=cur.reduce((a,b)=>a+b.gamt,0), sumN=cur.reduce((a,b)=>a+b.namt,0);
      const mlab=metric==='sagub'?'예상 LG사급금액':'예상매출';
      c.querySelector('#sum').innerHTML=`<div class="s-item">도번 <b>${won(cur.length)}</b></div>
        <div class="s-item">차감전(=라이브) <b>${wonI(sumG)} 원</b></div>
        <div class="s-item neg">첫계획일 과대분 제거 <b>-${wonI(sumG-sumN)} 원</b></div>
        <div class="s-item">차감후 ${mlab} <b>${wonI(sumN)} 원</b></div>`;
      c.querySelector('#cnt').textContent=`${cur.length}도번 · ${metric==='sagub'?'예상 LG사급금액 · ':''}${mode==='net'?'차감후':'차감전(라이브)'} · 셀=수량, 하단=금액${metric==='sagub'?'(수량×개당LG사급비)':''} · 헤더 더블클릭=정렬`;
      attachResizers(c);
      // ★헤더 더블클릭 정렬 바인딩(리사이저는 자체 dblclick으로 stopPropagation → 충돌없음)
      c.querySelectorAll('#th th[data-sk]').forEach(th=>{th.style.cursor='pointer';th.ondblclick=()=>{const k=th.dataset.sk;sortDir=sortKey===k?-sortDir:1;sortKey=k;render();};});
    };
    c.querySelector('#go').onclick=render;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')render();};
    c.querySelector('#work').onchange=render;
    c.querySelector('#reset').onclick=()=>{mode='net';sortKey='';sortDir=1;draw();};
    c.querySelector('#xls').onclick=()=>{
      const amtcol=metric==='sagub'?'예상LG사급금액':'예상매출금액', unitcol=metric==='sagub'?'개당LG사급비':'단가';
      const hd=['도번','품명','작업처',unitcol,'합계수량',amtcol].concat(days.map(d=>(''+d).slice(2)+'수량')).concat(days.map(d=>(''+d).slice(2)+'금액'));
      downloadCSV((metric==='sagub'?'예상LG사급금액_':'영업예상매출현황_')+mode+'.csv',hd,cur.map(r=>[r.item,r.nm,r.wc,r.cost,rowQ(r),rowA(r)].concat(days.map(d=>dayQ(r,d))).concat(days.map(d=>Math.round(dayQ(r,d)*r.cost)))));};
    render();
  };
  load();
};

/* LG리시빙관리 (영업, dw_sa_sale_110) — 도번 × 일자(1~n) 피벗. 수량/금액 토글, 내수/수출(mkt) */
SCREEN.lgrecv=(c)=>{
  const API=API_BASE;
  let cells=[], IM={}, curYm='', loading=false, msg='';
  const WD=['일','월','화','수','목','금','토'];
  const MKT={'1':'수출','2':'내수'};  // mkt1=수출, mkt2=내수
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-','');
  let metric='amt', mkt='', cur=[];
  const load=async(ym)=>{loading=true;msg='';
    const bd=c.querySelector('#body');if(bd)bd.innerHTML=spinRow(20);
    try{const r=await fetch(`${API}/api/live/lgrecv?ym=${encodeURIComponent(ym||'')}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();cells=j.cells||[];IM={};(j.items||[]).forEach(x=>IM[x.item]=x);curYm=j.ym||ym||'';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';cells=[];IM={};}
    loading=false;draw();};
  const draw=()=>{
    const maxDay=cells.reduce((m,r)=>Math.max(m,+r.d||0),0)||31;
    const days=[]; for(let d=1;d<=maxDay;d++)days.push(d);
    const yy=2000+(+curYm.slice(0,2)||26), mm=(+curYm.slice(2,4)||7);
    const wdOff=(new Date(yy,mm-1,1)).getDay();  // 그 달 1일의 요일 인덱스
    c.innerHTML=`
     <div class="page-title">🏢 LG리시빙관리</div>
     <div class="page-sub">LG 리시빙 도번×일자 집계 · 원본 <code>SA_T_LG_RECEIVING_DTL</code> · 🔴 라이브 ${esc(ymToInput(curYm)||'-')}</div>
     <div class="toolbar">
       <label class="tl">조회월</label>
       <input type="month" class="inp" id="ym" value="${esc(ymToInput(curYm))}" style="min-width:120px">
       <label class="tl">수량/금액</label>
       <div class="toggle-group"><button data-me="qty" class="${metric==='qty'?'on':''}">수량</button><button data-me="amt" class="${metric==='amt'?'on':''}">금액</button></div>
       <label class="tl">내수/수출</label>
       <select class="sel" id="mkt"><option value="" ${mkt===''?'selected':''}>전체</option><option value="2" ${mkt==='2'?'selected':''}>내수</option><option value="1" ${mkt==='1'?'selected':''}>수출</option></select>
       <input class="inp" id="iq" placeholder="도번/작업처">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:510px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    c.querySelectorAll('[data-me]').forEach(b=>b.onclick=()=>{metric=b.dataset.me;render();});
    c.querySelector('#mkt').onchange=e=>{mkt=e.target.value;render();};
    const render=()=>{
      const iq=c.querySelector('#iq').value.trim().toLowerCase();
      const map=new Map();
      cells.forEach(r=>{ if(mkt&&(''+r.mkt).trim()!==mkt)return;
        let o=map.get(r.item); if(!o){o={item:r.item,tot:0,dd:{}};map.set(r.item,o);}
        const v=metric==='qty'?(+r.q||0):(+r.amt||0); o.tot+=v; o.dd[r.d]=(o.dd[r.d]||0)+v; });
      cur=[...map.values()].map(o=>{const im=IM[o.item]||{};o.wcc=im.wcc||'';o.wc=im.wc||'';o.wt=im.wt||0;return o;})
        .filter(o=>!iq||(''+o.item).toLowerCase().includes(iq)||(''+o.wc).toLowerCase().includes(iq))
        .sort((a,b)=>(''+a.item).localeCompare(''+b.item,'ko'));
      const dHdr=days.map(d=>`<th class="num">${String(d).padStart(2,'0')}${WD[(wdOff+d-1)%7]}</th>`).join('');
      c.querySelector('#th').innerHTML=`<tr><th>도번</th><th>작업장명</th><th class="num">합계</th>${dHdr}</tr>`;
      let tbody=cur.map(o=>`<tr><td><b>${esc(o.item)}</b></td><td class="cap" title="${esc(o.wc)}">${esc(o.wc)}</td><td class="num gstock"><b>${won(o.tot)}</b></td>${days.map(d=>`<td class="num">${o.dd[d]?won(o.dd[d]):''}</td>`).join('')}</tr>`).join('');
      const gt=cur.reduce((a,b)=>a+(+b.tot||0),0);
      const gd=days.map(d=>cur.reduce((a,b)=>a+(+b.dd[d]||0),0));
      if(cur.length)tbody+=`<tr class="grandtot"><td colspan="2" class="right">총계 (${won(cur.length)} 도번)</td><td class="num">${won(gt)}</td>${gd.map(v=>`<td class="num">${v?won(v):''}</td>`).join('')}</tr>`;
      c.querySelector('#body').innerHTML=loading?spinRow(3+days.length):(msg?`<tr><td colspan="${3+days.length}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`:(cur.length?tbody:`<tr><td colspan="${3+days.length}" class="empty">결과 없음</td></tr>`));
      c.querySelector('#sum').innerHTML=`<div class="s-item">도번 <b>${won(cur.length)}</b></div><div class="s-item">${metric==='qty'?'수량':'금액'} 합계 <b>${wonI(gt)} ${metric==='qty'?'':'원'}</b></div>`;
      c.querySelector('#cnt').textContent=`${cur.length}도번 · ${metric==='qty'?'수량':'금액'} 기준`;
      attachResizers(c);
    };
    c.querySelector('#ym').onchange=e=>load(inYm(e.target.value));
    c.querySelector('#go').onclick=render;c.querySelector('#iq').onkeyup=e=>{if(e.key==='Enter')render();};
    c.querySelector('#reset').onclick=()=>{metric='amt';mkt='';c.querySelector('#iq').value='';render();};
    c.querySelector('#xls').onclick=()=>{
      const hd=['도번','작업장명','합계'].concat(days.map(d=>String(d).padStart(2,'0')+WD[(2+d)%7]));
      downloadCSV('LG리시빙관리_'+metric+(mkt?('_'+MKT[mkt]):'')+'.csv',hd,cur.map(o=>[o.item,o.wc,o.tot].concat(days.map(d=>o.dd[d]||0))));};
    render();
  };
  load('');
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
     <div class="page-sub">출하(매출) 실적 라인 · 원본 <code>SA_T_SALE_DTL</code> · 🔴 라이브 ${esc(dToInput(curFrom)||'-')}~${esc(dToInput(curTo)||'-')}</div>
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
  let pool=[], loading=false, msg='', curFrom='', curTo='', cur=[], source='live';   // ★Phase5 데이터원(기본 라이브 무변경)
  const dToInput=d=>{d=(''+(d||'')).trim();return d.length>=6?`20${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4,6)}`:'';};
  const inD=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const load=async()=>{loading=true;msg='';
    const bd=c.querySelector('#body');if(bd)bd.innerHTML=spinRow(10);
    if(source==='nx'){loading=false;return nxDerivedView(c,`${API}/api/live/salesstock?dfrom=${curFrom}&dto=${curTo}&source=nx`,{title:'제품재고조회',onBack:()=>{source='live';load();}});}
    try{const r=await fetch(`${API}/api/live/salesstock?dfrom=${curFrom}&dto=${curTo}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();pool=j.rows||[];curFrom=j.dfrom||curFrom;curTo=j.dto||curTo;}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';pool=[];}
    loading=false;
    const df=c.querySelector('#dfrom'),dt=c.querySelector('#dto');if(df)df.value=dToInput(curFrom);if(dt)dt.value=dToInput(curTo);
    const sub=c.querySelector('#ss-sub');if(sub)sub.innerHTML=`제품 수불(기초+입고−출고−기타출고) · 판매단가(S/E) 기준 · 원본 <code>SA_T_STOCK_MAINT</code> · 🔴 라이브 ${esc(dToInput(curFrom)||'-')}~${esc(dToInput(curTo)||'-')}`;
    const ws=[...new Set(pool.map(r=>r.wc).filter(Boolean))].sort();
    const wsel=c.querySelector('#wc');if(wsel){const v=wsel.value;wsel.innerHTML='<option value="">전체작업장</option>'+ws.map(w=>`<option value="${esc(w)}">${esc(w)}</option>`).join('');wsel.value=v;}
    apply();};
  c.innerHTML=`
   <div class="page-title">📦 제품재고조회</div>
   <div class="page-sub" id="ss-sub">제품 수불(기초+입고−출고−기타출고) · 판매단가(S/E) 기준 · 원본 <code>SA_T_STOCK_MAINT</code> · 🔴 라이브</div>
   <div class="toolbar">
     <label style="font-size:12px;color:var(--muted);font-weight:600">수불기간</label>
     <input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom))}" style="min-width:135px">
     <span style="color:var(--muted)">~</span>
     <input type="date" class="inp" id="dto" value="${esc(dToInput(curTo))}" style="min-width:135px">
     <input class="inp" id="q" placeholder="품목코드/품명/규격">
     <select class="sel" id="wc"><option value="">전체작업장</option></select>
     <select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
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
       <tbody>${st.rows.map(r=>`<tr>
         <td class="center"><input type="checkbox" class="o-ck" data-id="${r.id}" ${st.sel[r.id]?"checked":""}></td>
         <td>${d8(r.out_ymd)}</td><td class="center">${r.gubun?esc(r.gubun)+":"+esc(r.gubunnm):""}</td><td>${esc(r.out_cust||"")}</td>
         <td class="cap" style="max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.custnm||"")}">${esc(r.custnm||"")}</td>
         <td>${esc(r.sheet_no||"")}</td><td class="num">${r.out_seq??""}</td>
         <td><b>${esc(r.item_code)}</b></td><td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.itemnm||"")}">${esc(r.itemnm||"")}</td><td class="num qty">${won(r.out_qty)}</td>
         <td class="num">${won(r.cost)}</td><td class="num" style="color:#c0392b">${won(r.amt)}</td><td class="num">${won(r.vat)}</td>
         <td class="cap" style="max-width:130px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.remarks||"")}">${esc(r.remarks||"")}</td>
         <td>${esc(r.reg_user||"")}</td><td>${esc(r.upd_user||"")}</td><td style="font-size:11px">${dt(r.work_dt)}</td>
         <td>${esc(r.work_order||"")}</td><td>${esc(r.split_work_order||"")}</td><td class="center">${d8(r.sale_ymd)}</td><td class="center">${esc(r.sale_hms||"")}</td>
         <td class="center"><button class="btn xs o-ed" data-id="${r.id}">수정</button> <button class="btn xs o-cp" data-id="${r.id}">복사</button></td></tr>`).join("")||'<tr><td colspan="22" style="padding:16px;color:var(--muted)">판매출고 없음 — [추가]로 등록</td></tr>'}
       <tr class="grandtot"><td colspan="9" class="center">합계 ${st.rows.length}건 · 출고증 ${st.sheetcnt}건</td><td class="num">${won(st.totqty)}</td><td></td><td class="num">${won(st.totamt)}</td><td class="num">${won(st.totvat)}</td><td colspan="9"></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    g("#o-fr").onchange=x=>st.fr=x.target.value;g("#o-to").onchange=x=>st.to=x.target.value;
    g("#o-sheet").oninput=x=>st.sheet=x.target.value;g("#o-cust").onchange=x=>st.cust=x.target.value;
    g("#o-item").oninput=x=>st.item=x.target.value;g("#o-gb").onchange=x=>st.gubun=x.target.value;
    g("#o-go").onclick=load;g("#o-del").onclick=delSel;g("#o-cv").onclick=carryover;g("#o-carry").onchange=x=>st.carry=x.target.value;
    g("#o-add").onclick=()=>{st.edit={gubun:"5",out_cust:st.cust||"",sheet_no:"",item_code:"",out_qty:"",work_order:"",remarks:""};draw();};
    const all=g("#o-all");if(all)all.onclick=x=>{st.rows.forEach(r=>st.sel[r.id]=x.target.checked);draw();};
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

/* 영업 > 출하실적등록/LG송장 (레거시 w_pr_input_040 복원) — 출하실적 CRUD + LG송장 발행/취소. nx.sale_dtl+nx.lg_songjang_dtl. */
SCREEN.lgsale=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const now=new Date();
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  let st={rows:[],wo:"",item:"",fin:"",fr:iso(new Date(now.getFullYear(),now.getMonth(),1)),to:iso(now),
          sel:{},edit:null,sortKey:"",sortDir:1,loading:false,busy:false};
  const load=async()=>{st.loading=true;st.sel={};draw();
    try{const r=await fetch(`${API}/api/lgsale/list?fr=${yy(st.fr)}&to=${yy(st.to)}&wo=${encodeURIComponent(st.wo)}&item=${encodeURIComponent(st.item)}&fin=${st.fin}`);
      const j=await r.json();st.rows=j.rows||[];}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const save=async()=>{const e=st.edit;if(!e.work_order||!e.item_code)return alert("제번·품번을 입력하세요.");
    if(e.sale_qty===""||isNaN(+e.sale_qty))return alert("출하수량(숫자)을 입력하세요.");
    try{const r=await fetch(`${API}/api/lgsale/save`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(e)});
      if(!r.ok)throw new Error((await r.json()).detail||r.status);st.edit=null;await load();}catch(x){alert("저장 실패: "+x.message);}};
  const del=async(id)=>{if(!window.confirm("이 출하실적을 삭제할까요?"))return;
    try{const r=await fetch(`${API}/api/lgsale/delete`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});if(!r.ok)throw new Error((await r.json()).detail||r.status);await load();}catch(x){alert("삭제 실패: "+x.message);}};
  const issue=async()=>{if(st.busy)return;const ids=Object.keys(st.sel).filter(k=>st.sel[k]).map(Number);
    if(!ids.length)return alert("발행할 출하실적을 체크하세요(미발행 건만).");
    if(!window.confirm(`${ids.length}건 LG송장 발행 → 동일 송장번호로 묶임. 진행?`))return;st.busy=true;draw();
    try{const r=await fetch(`${API}/api/lgsale/issue`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ids})});
      const j=await r.json();if(!r.ok)throw new Error(j.detail||r.status);alert(`LG송장 발행완료 — ${j.issued}건, 송장번호 ${j.sheet_no}`);await load();}catch(x){alert("발행 실패: "+x.message);}st.busy=false;draw();};
  const cancel=async(sheet)=>{if(!window.confirm(`송장번호 ${sheet} 전체 취소 → 발행정보 제거 + LG송장 원장 삭제. 진행?`))return;
    try{const r=await fetch(`${API}/api/lgsale/cancel`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sheet_no:sheet})});if(!r.ok)throw new Error((await r.json()).detail||r.status);await load();}catch(x){alert("취소 실패: "+x.message);}};
  const draw=()=>{
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;st.rows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const totq=st.rows.reduce((a,r)=>a+(+r.sale_qty||0),0);const selcnt=Object.values(st.sel).filter(Boolean).length;
    const e=st.edit;
    c.innerHTML=`
     <div class="page-title">🚚 출하실적등록 / LG송장</div>
     <div class="page-sub">제번단위 <b>출하실적 등록 → LG송장 발행/취소</b>(<b style="color:#c0392b">LG 완제품 출하=매출</b>) · nx.sale_dtl+nx.lg_songjang_dtl · <span style="color:var(--muted)">⚠완제품 재고차감은 완제품원장 확정후</span> · 레거시 <code>w_pr_input_040</code>(복원)</div>
     <div class="toolbar">
       <label class="tl">출하기간</label><input class="inp" type="date" id="l-fr" value="${esc(st.fr)}"> ~ <input class="inp" type="date" id="l-to" value="${esc(st.to)}">
       <label class="tl" style="margin-left:8px">제번</label><input class="inp" id="l-wo" value="${esc(st.wo)}" placeholder="제번" style="width:120px">
       <label class="tl" style="margin-left:8px">품번</label><input class="inp" id="l-item" value="${esc(st.item)}" placeholder="품번" style="width:120px">
       <label class="tl" style="margin-left:8px">송장</label><select class="inp" id="l-fin"><option value="">전체</option><option value="0" ${st.fin==="0"?"selected":""}>미발행</option><option value="1" ${st.fin==="1"?"selected":""}>발행완료</option></select>
       <button class="btn" id="l-go">🔍 조회</button>
       <button class="btn" id="l-add" style="background:#2e86de;color:#fff">➕ 실적추가</button>
       <button class="btn" id="l-issue" style="background:#8e44ad;color:#fff" ${st.busy?"disabled":""}>🧾 LG송장 발행${selcnt?`(${selcnt})`:""}</button>
     </div>
     ${e?`<div class="panel" style="border:2px solid #2e86de"><div class="panel-h">${e.id?"수정":"신규"} 출하실적</div><div class="panel-b">
       <div class="toolbar" style="flex-wrap:wrap;gap:8px">
         <label class="tl">제번<span style="color:red">*</span></label><input class="inp" id="e-wo" value="${esc(e.work_order||"")}" placeholder="work_order" style="width:120px">
         <label class="tl">split</label><input class="inp" id="e-sp" value="${esc(e.split_work_order||"")}" style="width:60px">
         <label class="tl">품번<span style="color:red">*</span></label><input class="inp" id="e-item" value="${esc(e.item_code||"")}" placeholder="품번" style="width:150px">
         <label class="tl">출하수량<span style="color:red">*</span></label><input class="inp" id="e-qty" value="${esc(e.sale_qty??"")}" style="width:90px;text-align:right">
         <label class="tl">비고</label><input class="inp" id="e-rmk" value="${esc(e.remarks||"")}" style="width:180px">
         <button class="btn" id="e-save" style="background:#27ae60;color:#fff">💾 저장</button><button class="btn" id="e-cancel">취소</button>
       </div></div></div>`:""}
     <div class="panel"><div class="panel-h">출하실적 목록 ${st.loading?"(조회중…)":`(${st.rows.length}건)`}</div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th class="center" style="width:30px"><input type="checkbox" id="l-all"></th>
         <th data-key="work_order">제번</th><th class="center" data-key="split_work_order">split</th><th data-key="item_code">품번</th><th data-key="itemnm">품명</th>
         <th data-key="sale_ymd">출하일자</th><th class="num" data-key="sale_qty">출하수량</th>
         <th class="center" data-key="print_flag">송장상태</th><th data-key="sheet_no">송장번호</th><th data-key="remarks">비고</th><th class="center">관리</th></tr></thead>
       <tbody>${st.rows.map(r=>{const done=r.print_flag==='1';return `<tr>
         <td class="center">${done?'':`<input type="checkbox" class="l-ck" data-id="${r.id}" ${st.sel[r.id]?"checked":""}>`}</td>
         <td><b>${esc(r.work_order)}</b></td><td class="center">${esc(r.split_work_order||"")}</td><td>${esc(r.item_code)}</td>
         <td class="cap" style="max-width:170px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.itemnm||"")}">${esc(r.itemnm||"")}</td>
         <td>${esc(r.sale_ymd)}</td><td class="num qty">${won(r.sale_qty)}</td>
         <td class="center">${done?'<span style="color:#1f7a3d;font-weight:700">발행완료</span>':'<span style="color:#c67d00">미발행</span>'}</td>
         <td>${esc(r.sheet_no||"")}</td>
         <td class="cap" style="max-width:130px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.remarks||"")}">${esc(r.remarks||"")}</td>
         <td class="center">${done?`<button class="btn xs l-cancel" data-sheet="${esc(r.sheet_no)}">송장취소</button>`:`<button class="btn xs l-ed" data-id="${r.id}">수정</button> <button class="btn xs l-del" data-id="${r.id}">삭제</button>`}</td></tr>`;}).join("")||'<tr><td colspan="11" style="padding:16px;color:var(--muted)">출하실적 없음 — [실적추가]로 등록</td></tr>'}
       <tr class="grandtot"><td colspan="6" class="center">합계 ${st.rows.length}건</td><td class="num">${won(totq)}</td><td colspan="4"></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    g("#l-fr").onchange=x=>st.fr=x.target.value;g("#l-to").onchange=x=>st.to=x.target.value;
    g("#l-wo").oninput=x=>st.wo=x.target.value;g("#l-item").oninput=x=>st.item=x.target.value;g("#l-fin").onchange=x=>st.fin=x.target.value;
    g("#l-go").onclick=load;g("#l-issue").onclick=issue;
    g("#l-add").onclick=()=>{st.edit={work_order:"",split_work_order:"",item_code:"",sale_qty:"",remarks:""};draw();};
    const all=g("#l-all");if(all)all.onclick=x=>{st.rows.forEach(r=>{if(r.print_flag!=='1')st.sel[r.id]=x.target.checked;});draw();};
    c.querySelectorAll(".l-ck").forEach(x=>x.onchange=()=>{st.sel[x.dataset.id]=x.checked;draw();});
    if(e){g("#e-wo").oninput=x=>e.work_order=x.target.value.trim();g("#e-sp").oninput=x=>e.split_work_order=x.target.value.trim();
      g("#e-item").oninput=x=>e.item_code=x.target.value.trim();g("#e-qty").oninput=x=>e.sale_qty=x.target.value;g("#e-rmk").oninput=x=>e.remarks=x.target.value;
      g("#e-save").onclick=save;g("#e-cancel").onclick=()=>{st.edit=null;draw();};}
    c.querySelectorAll(".l-ed").forEach(x=>x.onclick=()=>{const r=st.rows.find(v=>v.id==x.dataset.id);st.edit={id:r.id,work_order:r.work_order,split_work_order:r.split_work_order||"",item_code:r.item_code,sale_qty:r.sale_qty,remarks:r.remarks||""};draw();});
    c.querySelectorAll(".l-del").forEach(x=>x.onclick=()=>del(+x.dataset.id));
    c.querySelectorAll(".l-cancel").forEach(x=>x.onclick=()=>cancel(x.dataset.sheet));
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(k){th.style.cursor="pointer";th.title="더블클릭 정렬·경계드래그 너비조절";th.ondblclick=()=>{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};}});
  };
  load();
};
