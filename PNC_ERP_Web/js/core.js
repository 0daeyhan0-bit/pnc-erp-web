/* ===== PNC ERP core.js — 전역 상수/헬퍼/RBAC/UI (app.js 분할 1/9, 순수이동) ===== */
/* ===== PNC ERP 프론트엔드 (조회 전용 프로토타입) ===== */
// ★API 서버 주소: 페이지를 서빙한 서버(location.origin)로 자동 지정 → 내부망 어느 PC에서 열어도 동작.
//   file:// 로 직접 열거나 host가 없으면 로컬 백엔드(개발용)로 폴백.
const API_BASE=(typeof location!=='undefined' && location.protocol!=='file:' && location.host)?location.origin:'http://127.0.0.1:8010';
/* ===== ★인증 토큰 (협력사 포털 1단계, 2026-08-29) =====
   왜 여기인가 — fetch 호출이 524곳이다. 전부 고치면 하나는 반드시 빠진다.
   window.fetch 를 **한 곳에서** 감싸면 지금 있는 것도, 앞으로 만들 것도 자동으로 토큰이 붙는다.
   ★서버가 401 을 주면 토큰을 버리고 로그인 화면으로 되돌린다(만료를 조용히 무시하지 않는다). */
const AUTH={
  get token(){try{return localStorage.getItem('auth_token')||'';}catch(e){return '';}},
  set token(v){try{v?localStorage.setItem('auth_token',v):localStorage.removeItem('auth_token');}catch(e){}},
  get user(){try{return JSON.parse(localStorage.getItem('auth_user')||'null');}catch(e){return null;}},
  set user(u){try{u?localStorage.setItem('auth_user',JSON.stringify(u)):localStorage.removeItem('auth_user');}catch(e){}},
  async login(id,pw){
    const r=await fetch(API_BASE+'/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id,pw})});
    let j={}; try{j=await r.json();}catch(e){}
    if(!r.ok) throw new Error((j&&j.detail)||'로그인에 실패했습니다.');
    this.token=j.token; this.user=j.user; return j.user;
  },
  async me(){ if(!this.token)return null;
    try{const r=await fetch(API_BASE+'/api/auth/me');
      if(!r.ok)return null; const j=await r.json(); this.user=j.user; return j.user;}catch(e){return null;} },
  async logout(){ try{await fetch(API_BASE+'/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});}catch(e){}
    this.clear(); },
  clear(){ this.token=null; this.user=null; try{sessionStorage.removeItem('perm_authed');}catch(e){} },
};
(function(){
  const _f=window.fetch.bind(window);
  window.fetch=function(input,init){
    init=init||{};
    try{
      const url=(typeof input==='string')?input:(input&&input.url)||'';
      // 우리 API 요청에만 붙인다(외부 주소에 토큰을 흘리지 않는다)
      if(AUTH.token && (url.startsWith('/api/')||url.indexOf(API_BASE+'/api/')===0)){
        const h=new Headers(init.headers||(typeof input!=='string'&&input.headers)||{});
        if(!h.has('Authorization'))h.set('Authorization','Bearer '+AUTH.token);
        init=Object.assign({},init,{headers:h});
      }
    }catch(e){}
    return _f(input,init).then(r=>{
      // ★만료·폐기 → 조용히 넘기지 않고 로그인 화면으로 되돌린다
      if(r&&r.status===401&&AUTH.token){ AUTH.clear();
        try{if(!window.__authRedirecting){window.__authRedirecting=1;
          alert('로그인이 만료되었습니다. 다시 로그인해 주세요.'); location.reload();}}catch(e){} }
      return r;
    });
  };
})();
const won = n => (n==null||n==='')?'-':Number(n).toLocaleString('ko-KR',{maximumFractionDigits:2});
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// ★전역 날짜 기본값(모든 화면 통일): 일자=당일 · 월=당월 · 기간=당월1일~당일
const nowCD = () => {const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};   // 당일 YYYY-MM-DD
const nowCM = () => nowCD().slice(0,7);   // 당월 YYYY-MM
const nowMS = () => nowCM()+'-01';        // 당월1일 YYYY-MM-01
/* ★계획 기준일 = **마지막 업로드 파일의 일자축 첫날**(2026-08-28 신설, 사용자 확정).
   왜 당일(nowCD)이 아닌가 —
     27일 기준으로 보던 계획을 28일 업로드 후 다시 보면, 27일 미출하분이 28일로 재편성되면서
     재고가 그쪽에 충당된다. 즉 27일 화면은 이미 '그때의 재고반영'이 아니게 되어 재고가
     실제보다 많이 채워져 보인다. 28일(업로드 일자)로 조회하면 그 재편성분에 재고가 채워져
     정합이 맞는다. (출하가 다 끝난 날은 무관하지만 미출하가 남으면 반드시 어긋난다)
   쓰는 화면: 파트별계획 · 자재소요 · 영업계획 · 가공계획 · 가공이동계획 · 협력사계획.
   ※백엔드 GET /api/plan/basedate 가 정본. 첫 호출만 네트워크, 이후 캐시.
     계획일자칸이 있는 화면은 초기값을 이 값으로 잡고, 사용자가 바꾸면 그 값을 쓴다. */
let _PLAN_BASE=null, _PLAN_BASE_P=null;
const planBase = async () => {
  if(_PLAN_BASE) return _PLAN_BASE;
  if(!_PLAN_BASE_P) _PLAN_BASE_P = (async()=>{
    try{ const j=await (await fetch(`${API_BASE}/api/plan/basedate`)).json();
         if(j&&j.base_iso) _PLAN_BASE={iso:j.base_iso, ymd:j.base_ymd, src:j.src, up:j.upload_dt};
    }catch(e){}
    if(!_PLAN_BASE) _PLAN_BASE={iso:nowCD(), ymd:nowCD().slice(2).replace(/-/g,''), src:'today', up:null};
    return _PLAN_BASE;})();
  return _PLAN_BASE_P;
};
const planBaseIso = () => (_PLAN_BASE ? _PLAN_BASE.iso : nowCD());   // 동기 접근(미로드 시 당일 폴백)
// ★날짜 input(type=date)은 브라우저 네이티브 키보드 편집에 맡김: 세그먼트(연/월/일) 클릭 후 숫자 입력·연속 타이핑·화살표·달력 모두 네이티브 지원.
//   (과거 전역 커스텀 핸들러가 모든 숫자키 preventDefault→ 월/일 세그먼트만 고치기 불가·YYMMDD 오인 문제. 2026-08-14 제거. 커스텀 자동채움 재도입 시 세그먼트 편집을 막지 말 것.)
// ★날짜칸 change 는 **디바운스해서** 받는다 — bindDate(el, fn)
//   Chrome 은 값이 유효해지는 순간마다 change 를 쏜다. 일 세그먼트에 '2' 를 치면 그 순간
//   260802 로 유효 → change → 조회·재렌더 → **입력칸이 다시 그려져 캐럿이 날아간다**.
//   그래서 두 자리를 치면 첫 자리만 먹었다(2026-08-30 실측: d_to 가 260801→260805→260802→
//   260808→260828 로 매 타건마다 무거운 조회. 브라우저가 계속 도는 것도 이 증상).
//   ⟹ 마지막 입력 후 조용해지면 실행한다. 키를 막지 않으므로 네이티브 세그먼트 편집은 그대로다.
//   날짜/월 입력이 조회·재렌더를 유발한다면 **예외 없이 이걸 쓴다**(직접 onchange 금지).
//   ★fn 에는 change 이벤트와 같은 모양({target:el})을 넘긴다 — 기존 `e=>...e.target.value`
//     핸들러를 그대로 옮겨 붙일 수 있게(호출부를 안 고쳐도 된다).
const bindDate=(el,fn,ms=800)=>{ if(!el)return el; let t=null;
  const run=()=>{t=null;fn({target:el});};
  el.onchange=()=>{ clearTimeout(t); t=setTimeout(run,ms); };
  // 포커스를 벗어나면 기다리지 않고 바로(달력 선택·탭 이동 뒤 지연 체감 제거)
  el.onblur=()=>{ if(t){clearTimeout(t);run();} };
  return el; };
const bindDates=(els,fn,ms=800)=>{ (els||[]).forEach(e=>bindDate(e,fn,ms)); };

  window.bindDate=bindDate; window.bindDates=bindDates;   // ★날짜칸 공용 바인더(§3)
const TYPE_NM={RAW:'원자재',SUB:'부자재',CON:'소모품',S_ASSY:'반제품',PROD:'완제품'};
// 용접봉 판정(품명 '용접봉' 포함). 신 원칙: 용접봉=재료비지만 BOM 아닌 용접공정 종속 → 화면에서 기본 숨김(데이터는 보존). [[newerp-weld-cost-split]]
const isWeld=nm=>/용접봉/.test(nm||'');
const tbadge = t => `<span class="bdg ${t}">${TYPE_NM[t]||t}</span>`;
const supCount = cd => (DB.itemDetail[cd]?.suppliers?.length)||0;
/* 라인 코드 → 표시명 매핑 */
const LINE_NM = (typeof DB!=='undefined' && DB.lineNames) ? DB.lineNames : {};
const lineName = l => { if(!l) return ''; const k=(''+l).trim(); return LINE_NM[k] || LINE_NM[l] || l; };
const wonI = n => (n==null||n==='')?'-':Math.round(Number(n)).toLocaleString('ko-KR');  /* 정수 금액 */
/* ===== ★Phase5: nx.stock_ledger 파생 조회 공통 뷰 (조회 8종 source=live|nx 토글) =====
   각 SCREEN load()에서 source==='nx'면 이 함수로 위임(라이브 render 대체). 라이브 기본 동작은 완전 무변경.
   nxUrl = 해당 라이브 엔드포인트 + '&source=nx'. opts={title, onBack}. 잔량=기초+ΣMAINT 균일 그리드+사유표시. */
async function nxDerivedView(c, nxUrl, opts){
  opts=opts||{};
  c.innerHTML=`<div class="page-title">${esc(opts.title||'nx 원장 파생')} <span style="font-size:12px;color:var(--muted);font-weight:400">nx원장 파생(대조용)</span></div>
   <div class="page-sub">✏️ 단일원장 <code>nx.stock_ledger</code> 파생(잔량=기초+ΣMAINT) · 병행운영 대조 · <b>기본값은 라이브</b></div>
   <div class="toolbar"><button class="btn" id="nxback">← 라이브로</button><span id="nxinfo" style="font-size:12px;color:var(--muted)"></span>
     <div class="spacer"></div><button class="btn xls" id="nxxls">📥 엑셀</button></div>
   <div class="summary-bar" id="nxsum"></div>
   <div class="grid-wrap" style="max-height:500px;overflow:auto"><table class="tbl fit"><thead id="nxth"></thead><tbody id="nxbody"><tr><td class="empty"><span class="lspin"></span> nx 원장 파생 조회 중…</td></tr></tbody></table></div>
   <div class="rowcount" id="nxcnt"></div>`;
  if(opts.onBack) c.querySelector('#nxback').onclick=opts.onBack;
  try{
    const r=await fetch(nxUrl); if(!r.ok) throw new Error('HTTP '+r.status);
    const j=await r.json(); const rows=j.rows||[], t=j.totals||{};
    c.querySelector('#nxinfo').innerHTML=j.nx_note?`ⓘ ${esc(j.nx_note)}`:`point=${esc(j.point||'')} · ${esc(j.from_ymd||'')}~${esc(j.to_ymd||'')}`;
    c.querySelector('#nxsum').innerHTML=`<div class="s-item">건수 <b>${won(rows.length)}</b></div><div class="s-item">기초 <b>${won(t.base||0)}</b></div><div class="s-item">입고 <b>${won(t.inq||0)}</b></div><div class="s-item">출고 <b>${won(t.outq||0)}</b></div><div class="s-item">기말 <b>${won(t.endq||0)}</b></div>`;
    c.querySelector('#nxth').innerHTML=`<tr><th>품목/자도번</th><th class="cap">품명</th><th>파트</th><th>거래처</th><th class="num">기초</th><th class="num">입고</th><th class="num">출고</th><th class="num">기말</th></tr>`;
    // ★#4 파트(gpc)·거래처(cust) 코드→이름(품목처럼) · 합계=grandtot 하단고정([[feedback-ui-rules]])
    const gt=rows.length?`<tr class="grandtot"><td colspan="4" class="right">총계 (${won(rows.length)}건)</td><td class="num">${won(t.base||0)}</td><td class="num">${won(t.inq||0)}</td><td class="num">${won(t.outq||0)}</td><td class="num"><b>${won(t.endq||0)}</b></td></tr>`:'';
    c.querySelector('#nxbody').innerHTML=rows.length?rows.map(x=>`<tr><td><b>${esc(x.cd)}</b></td><td class="cap" title="${esc(x.nm||'')}">${esc(x.nm||'')}</td><td title="${esc(x.gpc||'')}">${esc(x.gpc_nm||x.gpc||'')}</td><td title="${esc(x.cust||'')}">${esc(x.cust_nm||x.cust||'')}</td><td class="num">${won(x.base)}</td><td class="num">${won(x.inq)}</td><td class="num">${won(x.outq)}</td><td class="num"><b>${won(x.endq)}</b></td></tr>`).join('')+gt:`<tr><td colspan="8" class="empty">nx 원장 파생 데이터 없음${j.nx_note?' — '+esc(j.nx_note):''}</td></tr>`;
    c.querySelector('#nxcnt').textContent=`${rows.length}건 (nx 원장 파생)`;
    c.querySelector('#nxxls').onclick=()=>downloadCSV((opts.title||'nx파생')+'.csv',['품목/자도번','품명','파트','파트명','거래처','거래처명','기초','입고','출고','기말'],rows.map(x=>[x.cd,x.nm,x.gpc,x.gpc_nm,x.cust,x.cust_nm,x.base,x.inq,x.outq,x.endq]));
  }catch(e){ const b=c.querySelector('#nxbody'); if(b) b.innerHTML=`<tr><td colspan="8" class="empty" style="color:#c0392b">⚠ nx 파생 조회 실패</td></tr>`; }
}
/* ===== 전역 로딩 스피너 (모든 라이브 화면 공용) ===== */
const SPIN='<span class="lspin"></span>';
const spinRow=(cols,txt)=>`<tr><td colspan="${cols}" class="empty"><span class="lspin"></span> ${esc(txt||'라이브 조회 중…')}</td></tr>`;
(function(){const s=document.createElement('style');s.textContent=`
.lspin{display:inline-block;width:15px;height:15px;border:2px solid var(--line-2,#cbd5e1);border-top-color:var(--accent,#2f6db3);border-radius:50%;vertical-align:-3px;animation:lspin .7s linear infinite;margin-right:6px}
@keyframes lspin{to{transform:rotate(360deg)}}
.lspin-lg{width:26px;height:26px;border-width:3px}
.empty .lspin{vertical-align:-2px}
.botsum{background:linear-gradient(0deg,#eef4ff,#f8faff);border:1px solid #cfe0ff;border-radius:8px;box-shadow:0 -2px 8px rgba(30,45,70,.06);padding:8px 14px}`;document.head.appendChild(s);})();
/* 컬럼 헤더 더블클릭 정렬 (keys: 컬럼순서별 데이터키, null=정렬제외) */
/* 컬럼 너비 조절 핸들 — 우측 경계 드래그로 조절, 핸들 더블클릭으로 초기화. 모든 .tbl th에 부여 */
function addResizer(th){
  if(!th.dataset.base) th.dataset.base=th.textContent.trim();
  if(th.querySelector('.col-resizer'))return;
  const rz=document.createElement('div'); rz.className='col-resizer';
  rz.addEventListener('mousedown',e=>{e.preventDefault();e.stopPropagation();
    const sx=e.pageX, sw=th.offsetWidth;
    const mv=ev=>{const w=Math.max(0,sw+ev.pageX-sx);th.style.width=th.style.minWidth=th.style.maxWidth=w+'px';};
    const up=()=>{document.removeEventListener('mousemove',mv);document.removeEventListener('mouseup',up);};
    document.addEventListener('mousemove',mv);document.addEventListener('mouseup',up);});
  rz.addEventListener('dblclick',e=>{e.stopPropagation();th.style.width=th.style.minWidth=th.style.maxWidth='';});
  th.appendChild(rz);
}
function attachResizers(c){ c.querySelectorAll('table.tbl thead th').forEach(addResizer); }

function enableSort(c, keys, getRows, render){
  const ths=c.querySelectorAll('thead th');
  ths.forEach((th,i)=>{
    addResizer(th);
    const key=keys&&keys[i]; if(!key)return;   // keys 미전달(단일인자 호출=리사이저만)시 정렬 스킵·크래시 방지
    th.style.cursor='pointer'; th.title='더블클릭하여 정렬 · 우측 경계 드래그로 너비조절';
    th.ondblclick=()=>{
      th._d = th._d===1?-1:1; const d=th._d;
      getRows().sort((a,b)=>{let x=a[key],y=b[key];
        const nx=parseFloat(x),ny=parseFloat(y);
        if(x!=null&&y!=null&&x!==''&&y!==''&&!isNaN(nx)&&!isNaN(ny)) return (nx-ny)*d;
        return String(x==null?'':x).localeCompare(String(y==null?'':y),'ko')*d;});
      render(getRows());
      // 화살표는 첫 텍스트 노드만 교체 → 리사이저 보존
      ths.forEach(o=>{const t=o.childNodes[0]; if(t&&t.nodeType===3) t.nodeValue=o.dataset.base;});
      const t=th.childNodes[0]; if(t&&t.nodeType===3) t.nodeValue=th.dataset.base+(d===1?' ▲':' ▼');
    };
  });
}

/* ---- 모듈(상단) → 하위메뉴(좌측) 구성 ---- */
const MODULES=[
 {id:'base',nm:'기준정보 관리',ic:'📦',subs:[
   {id:'items',ic:'📦',nm:'품목 조회'},
   {id:'bomview',ic:'🔀',nm:'품목 BOM 조회'},
   {id:'lgbomview',ic:'🔀',nm:'LG BOM 관리'},
   {id:'docmgr',ic:'📐',nm:'도면/문서 조회'},
   {id:'basemaster',ic:'🗂️',nm:'기준 마스터 관리'},
   {id:'prodinfo',ic:'⚙️',nm:'생산정보등록'},
   // ★검토용(2026-08-26) — ① 신규모델 검색·생성 결과 확인 + 제외조건 등록(레거시 w_pr_master_050/070).
   //   삭제=일회성(다음 편성에 재생성) / 제외조건=영구차단. 편성 STEP M 의 3중 NOT EXISTS 중 하나.
   {id:'modelbomhist',ic:'🧪',nm:'모델BOM 이력·제외',tag:'검토'},
 ]},
 {id:'pur',nm:'구매/자재',ic:'🧾',subs:[
   {id:'mat',ic:'📦',nm:'자재목록조회'},
   {id:'matledger',ic:'📒',nm:'자재수불장'},
   {id:'dispatchdetail',ic:'📋',nm:'자재불출명세서'},
   {id:'dispatch',ic:'📤',nm:'자재불출집계표'},
   {id:'receiptdetail',ic:'🧾',nm:'자재입고명세서'},
   {id:'receipt',ic:'📥',nm:'자재입고집계표'},
   {id:'matkanban',ic:'📊',nm:'자재입고현황',hide:true},
   {sep:true},
   {id:'dopippur',ic:'🚢',nm:'도입-수입입력'},
   {id:'dopipsale',ic:'✈️',nm:'도입-수출입력'},
   {sep:true},
   {id:'stockreceipt',ic:'📥',nm:'자재입고관리'},
   {id:'matinput',ic:'📈',nm:'자재입고진행현황'},
   {id:'matreceive',ic:'📦',nm:'자재입고(발주분)'},
   {id:'stockissue',ic:'📤',nm:'자재출고관리'},
   {id:'stockadjust',ic:'🛠️',nm:'자재재고조정'},
   {id:'saguboutput',ic:'📤',nm:'사급출고관리'},
   {id:'matinout',ic:'🔁',nm:'자재 입출고현황'},
   {id:'manorder',ic:'🛒',nm:'수동발주'},
   {id:'matprice',ic:'💲',nm:'원소재/용접봉 시세',hide:true},
   {sep:true},
   // ★자재세트 4종(레거시 자재관리 메뉴 순서) — 2026-08-29 신설
   {id:'setstock',ic:'📦',nm:'자재세트입고관리'},
   {id:'setinstat',ic:'📋',nm:'자재세트입고현황'},
   // 자재세트재고현황은 입출고현황과 내용이 같아 제외(2026-08-29 사용자 확정)
   {id:'setstockio',ic:'🔁',nm:'자재세트재고입출고현황'},
   {id:'setstockadj',ic:'🛠️',nm:'자재세트재고조정'},
   {sep:true},
   {id:'lgsagub',ic:'📊',nm:'LG사급현황'},
   {id:'matexpect',ic:'📦',nm:'자재예상매입'},
   {id:'sourceprofile',ic:'🧭',nm:'조달 프로파일'},
   {id:'salemagam',ic:'🧾',nm:'자재매출마감'},
   {id:'purmagam',ic:'📥',nm:'자재매입마감'},
   {id:'coopquote2',ic:'💱',nm:'협력사견적관리'},
 ]},
 {id:'partner',nm:'협력사',ic:'🤝',subs:[
   {id:'partnerplan',ic:'📋',nm:'협력사 계획현황'},
   {id:'coopporder',ic:'📦',nm:'협력사 발주현황(일반)'},
   {id:'deliv420',ic:'🧾',nm:'거래명세서 발행'},
   {id:'delivedit',ic:'📝',nm:'거래명세표 수정'},
   // {id:'setinreq',ic:'🏷️',nm:'거래명세서 발행(바코드)'},   // ★2026-08-28 메뉴 숨김(요청). SCREEN.setinreq 는 유지 — 되살릴 땐 이 줄만 해제
   // 자재세트입고관리는 구매/자재 메뉴로 이동(레거시 배치와 동일) — 2026-08-29
   {id:'sagubadjust',ic:'🛠️',nm:'협력사사급재고관리'},
   {id:'sagubledger',ic:'📊',nm:'사급 수불장'},
 ]},
 {id:'prod',nm:'생산',ic:'🏭',subs:[
   {id:'prodstock',ic:'🏭',nm:'생산재고조회'},
   {id:'prodinout',ic:'🔁',nm:'생산입출고현황'},
   {sep:true},
   {id:'orderupload',ic:'📥',nm:'주문업로드'},
   // {id:'planupload',ic:'📅',nm:'생산계획업로드'},   // ★2026-08-28 메뉴 숨김(요청) — 검토본으로 일원화. SCREEN.planupload 는 유지
   // ★검토용(2026-08-26) — 레거시식 단계별 실행. 편성로직은 사본(동일), 실행방식만 다름. 기존분과 병행.
   //   tag:'검토' = 사이드바에 주황 배지 + 글자색으로 구분(검토중 메뉴임을 한눈에).
   {id:'planuploadrev',ic:'🧪',nm:'생산계획업로드',tag:'검토'},
   {id:'planinput',ic:'➕',nm:'생산계획추가입력'},
   {id:'prodsheet',ic:'🖨️',nm:'생산전표출력관리'},
   {id:'partplan',ic:'🧩',nm:'파트별 생산계획'},
   {id:'kitting',ic:'🧰',nm:'준비실적처리(키팅)'},
   // ★2026-08-30 메뉴에서만 숨김(사용자 요청) — 파트별 생산계획의 드래그 실적처리로
   //   같은 일을 하게 되어 당분간 감춘다. 화면(SCREEN.procresult)·API 는 그대로 두므로
   //   되살리려면 이 줄의 주석만 풀면 됨.
   // {id:'procresult',ic:'✅',nm:'공정별 생산실적등록'},
   {id:'procbarcode',ic:'🔫',nm:'공정별 바코드생산실적'},
   {id:'partresult',ic:'📈',nm:'파트별 생산실적현황'},
   // ★2026-08-26 메뉴에서만 숨김(사용자 요청) — 나중에 쓸 수 있어 화면(SCREEN.prodresult,
   //   screens.prod.js)과 API 는 그대로 둔다. 되살리려면 이 줄의 주석만 풀면 됨.
   // {id:'prodresult',ic:'📊',nm:'생산실적현황'},
   {id:'gongsu',ic:'⏱️',nm:'공수등록(근무/지원)'},
   {sep:true},
   {id:'partstockadj',ic:'🛠️',nm:'생산파트재고조정'},
   {id:'partissue',ic:'📤',nm:'생산자재출고관리'},
 ]},
 {id:'sales',nm:'영업',ic:'📈',subs:[
   {id:'salesstock',ic:'📦',nm:'제품재고조회'},
   {id:'prodinvout',ic:'🔁',nm:'제품입출고현황'},
   {id:'prodstockadj',ic:'📦',nm:'제품재고조정'},
   {id:'saleout',ic:'📤',nm:'판매및출고등록'},
   {id:'lgsale',ic:'🚚',nm:'출하실적등록/LG송장'},
   {id:'shipment',ic:'🚚',nm:'출하실적현황'},
   {id:'salesforecast',ic:'📅',nm:'영업예상매출현황'},
   {id:'salesplan',ic:'🗓️',nm:'영업계획현황'},
   {id:'muldong',ic:'📊',nm:'LG 물동량'},
   {id:'lgrecv',ic:'🏢',nm:'LG리시빙관리'},
 ]},
 {id:'gagong',nm:'가공',ic:'⚙️',subs:[
   {id:'gagongprog420',ic:'🏭',nm:'가공생산진척관리(전표발행)'},
   {id:'gagongplan4w',ic:'📋',nm:'4주간 가공계획현황'},
   {id:'gagongjeohist',ic:'🧾',nm:'가공전표이력현황'},
   {id:'gagongmove580',ic:'🚚',nm:'가공창고 이동계획'},
   {id:'gagongset280',ic:'📦',nm:'가공세트재고관리'},
 ]},
 {id:'qc',nm:'품질',ic:'🔎',subs:[
   {id:'qcerror',ic:'🚫',nm:'품질불량관리'},
   {id:'scrapraw',ic:'🗑',nm:'가공스크랩관리'},
   {id:'qcspec',ic:'📐',nm:'시방변경관리'},
   {id:'qciqc',ic:'🔬',nm:'수입검사(IQC)조회'},
   {id:'meeting',ic:'📝',nm:'품질 반성회의록'},
 ]},
 {id:'dev',nm:'개발',ic:'🧪',subs:[
   {id:'devmaster',ic:'🛠️',nm:'원가/BOM 기준정보'},
   {id:'itemmaster',ic:'📇',nm:'품목마스터 관리'},
   {id:'rawmat',ic:'🧱',nm:'원소재 마스터'},
   {id:'itembom',ic:'📋',nm:'품목별 공정관리'},
   {id:'unifybom',ic:'🔀',nm:'품목 BOM관리'},
   {id:'modelbom',ic:'🧬',nm:'모델BOM 관리'},
   {id:'delivery',ic:'📦',nm:'납품 포장/적재'},
   {id:'subvariant',ic:'🧩',nm:'조달경로 통합검토'},
   {id:'costanalysis',ic:'💹',nm:'품목별 원가분석'},
   {id:'costverify',ic:'🔬',nm:'원가엔진 검증(라이브)'},
   {id:'price',ic:'💰',nm:'품목단가 조회'},
   {id:'pricemgmt',ic:'🛠️',nm:'품목단가 관리'},
   {id:'dtradeprice',ic:'🔁',nm:'직거래 LME 판가연동'},
 ]},
 {id:'mgmt',nm:'경영',ic:'📊',subs:[
   {id:'dailypurissue',ic:'📋',nm:'일일 영업/매입 현황'},
 ]},
 {id:'sys',nm:'시스템관리',ic:'⚙️',subs:[
   {id:'close',ic:'🔒',nm:'마감관리'},
   {id:'users',ic:'👤',nm:'사용자관리'},
   {id:'perm',ic:'🔑',nm:'권한관리'},
 ]},
];
const allSubs=()=>MODULES.flatMap(m=>m.subs);

/* ---- 좌측 메뉴 사용자 순서(드래그 재배치) 저장/적용 ---- */
const MENU_ORDER_KEY='pnc_menu_order_v1';
function loadMenuOrder(){try{return JSON.parse(localStorage.getItem(MENU_ORDER_KEY)||'{}')||{};}catch(e){return {};}}
function saveMenuOrder(o){try{localStorage.setItem(MENU_ORDER_KEY,JSON.stringify(o));}catch(e){}}
function applyMenuOrder(){
  const ord=loadMenuOrder();
  MODULES.forEach(m=>{
    const saved=ord[m.id]; if(!saved||!saved.length)return;
    const byId={}; m.subs.forEach(it=>{if(!it.sep)byId[it.id]=it;});
    const used=new Set(), out=[];
    saved.forEach(tok=>{ if(tok==='__sep__')out.push({sep:true});
      else if(byId[tok]&&!used.has(tok)){out.push(byId[tok]);used.add(tok);} });
    // ★신규(미저장) 항목은 '정의상 바로 앞 항목' 뒤에 끼운다(2026-08-26 수정).
    //   예전엔 무조건 맨 뒤로 밀어서, 메뉴를 한 번이라도 드래그한 사용자는 새 메뉴가
    //   엉뚱한 위치(맨 아래)에 나타났다. 이제 개발자가 의도한 자리에 들어간다.
    m.subs.forEach((it,i)=>{
      if(it.sep||used.has(it.id))return;
      let at=out.length;                                  // 기본=맨 뒤(앞 항목이 전부 신규면)
      for(let k=i-1;k>=0;k--){                            // 정의상 바로 앞의 '이미 배치된' 항목을 찾아
        const p=m.subs[k]; if(p.sep||!used.has(p.id))continue;
        const pos=out.findIndex(o=>!o.sep&&o.id===p.id);
        if(pos>=0){at=pos+1;break;}
      }
      out.splice(at,0,it); used.add(it.id);
    });
    if(out.some(it=>!it.sep))m.subs=out;
  });
}
function serializeFolder(folderEl){
  const fid=folderEl.dataset.folder;
  const toks=[...folderEl.querySelectorAll('.tree-children > *')]
    .map(k=>k.classList.contains('tree-sep')?'__sep__':k.dataset.id).filter(Boolean);
  const ord=loadMenuOrder(); ord[fid]=toks; saveMenuOrder(ord); applyMenuOrder();
}
function resetMenuOrder(){ localStorage.removeItem(MENU_ORDER_KEY); location.reload(); }

/* ---- 좌측 트리 메뉴 (열고/닫기 + 드래그 재배치) ---- */
function buildTree(){
  applyMenuOrder();
  if(!document.getElementById('menuDragCss')){const st=document.createElement('style');st.id='menuDragCss';
    st.textContent='.tree-leaf[draggable=true]{cursor:grab}.tree-leaf.dragging{opacity:.45}.tree-leaf.drop-before{box-shadow:inset 0 2px 0 #1c47a0}.tree-leaf.drop-after{box-shadow:inset 0 -2px 0 #1c47a0}.menu-reset{font-size:11px;color:#8aa0bd;cursor:pointer;padding:6px 12px}.menu-reset:hover{color:#1c47a0;text-decoration:underline}'
      /* ★검토중 메뉴 강조(2026-08-26) — 운영메뉴와 시각적으로 확실히 구분.
         메뉴명이 길어도 배지가 줄바꿈되지 않게 flex + nowrap. 배지는 우측 정렬. */
      +'.tree-leaf-tag{color:#b45309!important;font-weight:600;background:linear-gradient(90deg,#fff7ec,transparent);border-left:3px solid #e08a1c;'
      +'display:flex;align-items:center;gap:6px;white-space:nowrap}'
      +'.tree-leaf-tag:hover{background:linear-gradient(90deg,#ffeed4,transparent)}'
      +'.tag-chip{flex:0 0 auto;margin-left:auto;padding:0 6px;border-radius:8px;background:#e08a1c;color:#fff;'
      +'font-size:10px;font-weight:700;line-height:16px;letter-spacing:-.3px}';
    document.head.appendChild(st);}
  const sb=document.getElementById('sidebar');
  let h=`<div class="tree"><div class="tree-leaf" data-id="dash">대시보드</div>`;
  MODULES.forEach(m=>{
    const subs=m.subs.filter(it=>it.sep||(!it.hide&&PERM.canView(it.id)));   // 조회권한 없는/숨김 메뉴 제외(구분선 유지)
    if(!subs.some(it=>!it.sep))return;                            // 실제 메뉴 없는 폴더는 폴더째 숨김
    h+=`<div class="tree-folder collapsed" data-folder="${m.id}">
      <div class="tree-fhead"><span class="arw">▾</span>${m.nm}</div>
      <div class="tree-children">`;
    subs.forEach(it=>{
       if(it.sep){h+=`<div class="tree-sep" data-sep="1" style="height:1px;background:#d5dde8;margin:6px 12px"></div>`;return;}
       // ★tag 붙은 메뉴(검토중 등)는 색상·배지로 구분 — 운영메뉴와 헷갈리지 않게(2026-08-26)
       h+=`<div class="tree-leaf${it.tag?' tree-leaf-tag':''}" draggable="true" data-id="${it.id}"${it.tag?` title="${it.tag}중인 메뉴 — 운영메뉴와 병행"`:''}>${it.nm}
       ${it.tag?`<span class="tag-chip">${it.tag}</span>`:''}${it.cnt!=null?`<span class="badge">${won(it.cnt)}</span>`:''}${it.soon?'<span class="badge">준비</span>':''}</div>`;});
    h+=`</div></div>`;
  });
  h+=`<div class="menu-reset" title="드래그로 바꾼 메뉴 순서를 기본값으로 되돌립니다">↺ 메뉴 순서 초기화</div>`;
  h+=`</div>`;
  sb.innerHTML=h;
  const rs=sb.querySelector('.menu-reset');if(rs)rs.onclick=()=>{if(confirm('메뉴 순서를 기본값으로 되돌릴까요?'))resetMenuOrder();};
  sb.querySelectorAll('.tree-fhead').forEach(fh=>fh.onclick=()=>fh.parentElement.classList.toggle('collapsed'));
  // 드래그 재배치(폴더 내 leaf 순서 변경 → localStorage 저장)
  let dragEl=null;
  sb.querySelectorAll('.tree-leaf[draggable=true]').forEach(lf=>{
    lf.addEventListener('dragstart',e=>{dragEl=lf;lf.classList.add('dragging');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',lf.dataset.id);});
    lf.addEventListener('dragend',()=>{dragEl=null;sb.querySelectorAll('.tree-leaf').forEach(x=>x.classList.remove('dragging','drop-before','drop-after'));});
    lf.addEventListener('dragover',e=>{
      if(!dragEl||dragEl===lf||dragEl.parentElement!==lf.parentElement)return;   // 같은 폴더 내에서만
      e.preventDefault();e.dataTransfer.dropEffect='move';
      const r=lf.getBoundingClientRect(),after=(e.clientY-r.top)>r.height/2;
      lf.classList.toggle('drop-after',after);lf.classList.toggle('drop-before',!after);});
    lf.addEventListener('dragleave',()=>lf.classList.remove('drop-before','drop-after'));
    lf.addEventListener('drop',e=>{
      if(!dragEl||dragEl===lf||dragEl.parentElement!==lf.parentElement)return;
      e.preventDefault();
      const r=lf.getBoundingClientRect(),after=(e.clientY-r.top)>r.height/2;
      lf.parentElement.insertBefore(dragEl,after?lf.nextSibling:lf);
      lf.classList.remove('drop-before','drop-after');
      serializeFolder(lf.closest('.tree-folder'));});
  });
  sb.querySelectorAll('.tree-leaf').forEach(lf=>lf.onclick=()=>{
    const id=lf.dataset.id;
    if(id==='dash'){openTab('dash','대시보드');return;}
    const it=allSubs().find(x=>x.id===id);
    if(it.soon){alert('해당 메뉴는 준비 중입니다. (조회 기능을 하나씩 추가 중)');return;}
    openTab(it.id,it.nm);
  });
  highlightActive();
}
function highlightActive(){
  document.querySelectorAll('.tree-leaf').forEach(e=>e.classList.toggle('active',e.dataset.id===active));
}

/* ---- 탭 관리 ---- */
const tabs={}; let active=null;
const $content=document.getElementById('content'), $tabbar=document.getElementById('tabbar');
function openTab(id,nm){
  if(!tabs[id]){
    tabs[id]={nm};
    const t=document.createElement('div');t.className='tab';t.dataset.id=id;
    t.innerHTML=`<span>${nm}</span>`+(id!=='dash'?`<span class="x">✖</span>`:'');
    t.onclick=(ev)=>{if(ev.target.classList.contains('x')){closeTab(id);ev.stopPropagation();}else activate(id);};
    $tabbar.appendChild(t);tabs[id].el=t;
    // ★height:100% 를 쓰는 화면(대부분의 조회화면)이 정상 작동하려면 이 컨테이너부터
    //   확정된 높이를 가져야 한다. display:block 인 채로는 자식의 height:100% 가
    //   전달되지 않아, 내용이 짧은 화면은 표가 화면 아래까지 안 늘어나는 문제가 생긴다.
    //   ※c52de04(2026-08-21) 로 확정된 구조 — 바꾸지 말 것. flex 로 대체 시도했다가 되돌림(2026-08-27).
    const c=document.createElement('div');c.id='pg-'+id;c.style.cssText='display:none;height:100%';
    $content.appendChild(c);tabs[id].pg=c;
    (SCREEN[id]||SCREEN._na)(c,id);
    attachResizers(c);
  }
  activate(id);
}
function activate(id){
  active=id;
  Object.entries(tabs).forEach(([k,v])=>{v.el.classList.toggle('active',k===id);v.pg.style.display=k===id?'block':'none';});
  highlightActive();
}
function closeTab(id){
  tabs[id].el.remove();tabs[id].pg.remove();delete tabs[id];
  const rest=Object.keys(tabs);activate(rest[rest.length-1]||'dash');
}

/* ===== ★전역 검색칸 autocomplete (UI규칙17) — 모든 화면 공통 자동적용 =====
   검색성 <input.inp>에 datalist를 자동 부착하고, 같은 화면 표(table.tbl)의 앞 컬럼(이름·코드) distinct로 초이스 채움.
   화면이 draw()로 innerHTML 갈아끼워도 MutationObserver가 재부착(자가치유). 이미 list= 있는 화면은 그대로 유지. */
(function(){
  const KW=/품번|품명|도번|자도번|코드|거래처|자재|검색|이름|모델|작업처|납품|P\/N|불출처|매입처|업체|파트|사용자|부서|작업자/;
  const sig=new WeakMap();
  function build(inp){
    const dl=document.getElementById(inp.getAttribute('list')); if(!dl)return;
    const pg=inp.closest('[id^="pg-"]')||document;
    const tbl=pg.querySelector('table.tbl')||pg.querySelector('table'); if(!tbl)return;
    const tb=tbl.querySelector('tbody'); if(!tb)return;
    const s=tb.children.length+':'+(tb.children[0]?tb.children[0].textContent.length:0);
    if(sig.get(inp)===s)return; sig.set(inp,s);   // 표 미변경이면 재빌드 안함(루프방지)
    // ★검색칸 placeholder에 맞는 헤더 컬럼에서만 후보 추출(거래처 오염 방지)
    const P=inp.getAttribute('placeholder')||'';
    let colRe=null;
    if(/품번|품명|P\/N|PART/i.test(P)) colRe=/품명|품번|품목|PART|P\/N/i;
    else if(/자도번|도번/i.test(P)) colRe=/자도번|도번|PART|MAT|자재/i;
    else if(/거래처|매입처|업체|공급처|불출처|작업처|납품/i.test(P)) colRe=/거래처|매입처|업체|공급처|불출처|작업처|납품/i;
    else if(/제번/i.test(P)) colRe=/제번|WORK/i;
    else if(/모델/i.test(P)) colRe=/모델|MODEL/i;
    else if(/라인/i.test(P)) colRe=/라인|LINE/i;
    else if(/자재/i.test(P)) colRe=/자재|MAT|품명|도번/i;
    else if(/부서|사용자|작업자|담당/i.test(P)) colRe=/부서|사용자|작업자|담당|이름|성명/i;
    let cols=[];
    if(colRe){[...tbl.querySelectorAll('thead th')].forEach((th,i)=>{ if(colRe.test((th.textContent||'').trim())) cols.push(i); });}
    if(!cols.length) cols=[0,1,2,3];   // 헤더 매칭 실패시 앞4컬럼(기존 동작)
    const set=new Set();
    for(const tr of tb.children){const tds=tr.children;
      for(const ci of cols){ if(ci<tds.length){const t=(tds[ci].textContent||'').trim();
        if(t&&t.length<40&&!/^[\d,.\-\s]+$/.test(t)&&t!=='·')set.add(t);}}
      if(set.size>1200)break;}
    dl.innerHTML=[...set].slice(0,1200).map(v=>'<option value="'+v.replace(/"/g,'&quot;').replace(/</g,'&lt;')+'"></option>').join('');
  }
  function enhance(root){
    root.querySelectorAll('input.inp:not([data-ac])').forEach(inp=>{
      const ty=(inp.getAttribute('type')||'text').toLowerCase();
      if(['date','number','month','checkbox','file','radio'].includes(ty)){inp.setAttribute('data-ac','skip');return;}
      if(inp.getAttribute('list')){inp.setAttribute('data-ac','pre');return;}   // 화면 자체 datalist 유지
      if(!KW.test(inp.getAttribute('placeholder')||'')){inp.setAttribute('data-ac','skip');return;}
      const id='ac_'+Math.random().toString(36).slice(2,9);
      const dl=document.createElement('datalist');dl.id=id;
      inp.setAttribute('list',id);inp.setAttribute('autocomplete','off');inp.setAttribute('data-ac','1');
      inp.parentNode.insertBefore(dl,inp.nextSibling);
      build(inp);
    });
    root.querySelectorAll('input.inp[data-ac="1"]').forEach(build);   // 로드된 데이터 반영 재빌드
  }
  let t=null;
  const obs=new MutationObserver(()=>{clearTimeout(t);t=setTimeout(()=>{try{enhance($content);}catch(e){}},250);});
  function start(){ if(!$content)return; obs.observe($content,{childList:true,subtree:true}); enhance($content); }
  if(document.readyState!=='loading')start(); else document.addEventListener('DOMContentLoaded',start);
})();

/* ================= 권한(RBAC) ================= */
const ROLES=['시스템관리자','원가개발','영업','구매/자재','생산','품질','조회전용','협력사'];
// ★슈퍼 계정(전권) + 개발용 자동 로그인 계정. DEV_AUTOLOGIN을 ''로 비우면 일반 로그인으로 전환.
/* ★비밀번호 없음 — 대조는 서버(nx.app_user)에서만 한다 */
const SUPER_USER={id:'super',nm:'슈퍼관리자',type:'내부',dept:'전산',pos:'대표',roles:['시스템관리자'],partner:'',email:'pncind@pncind.co.kr',tel:'',status:'사용'};
const DEV_AUTOLOGIN='';   // ''=일반 로그인(다중사용자 병행). 개발 단독확인시만 'super'
const SEED_USERS=[
  SUPER_USER,
  {id:'admin',nm:'관리자',type:'내부',dept:'전산',pos:'관리자',roles:['시스템관리자'],partner:'',email:'admin@pncind.co.kr',tel:'',status:'사용'},
  {id:'kdev',nm:'김개발',type:'내부',dept:'원가개발',pos:'대리',roles:['원가개발','조회전용'],partner:'',email:'',tel:'',status:'사용'},
  {id:'ysales',nm:'이영업',type:'내부',dept:'영업',pos:'과장',roles:['영업'],partner:'',email:'',tel:'',status:'사용'},
  {id:'ysales2',nm:'최영업',type:'내부',dept:'영업',pos:'사원',roles:['조회전용'],partner:'',email:'',tel:'',status:'사용'},
  {id:'jbuy',nm:'박구매',type:'내부',dept:'구매/자재',pos:'사원',roles:['구매/자재'],partner:'',email:'',tel:'',status:'사용'},
  {id:'TEST1',nm:'테스트1(전권)',type:'내부',dept:'전산',pos:'',roles:['시스템관리자'],partner:'',email:'',tel:'',status:'사용'},
  {id:'TEST2',nm:'테스트2(자재·협력사)',type:'내부',dept:'구매/자재',pos:'',roles:['구매/자재'],partner:'',email:'',tel:'',status:'사용'},
  {id:'TEST3',nm:'테스트3(생산)',type:'내부',dept:'생산',pos:'',roles:['생산'],partner:'',email:'',tel:'',status:'사용'},
  {id:'TEST4',nm:'테스트4(개발)',type:'내부',dept:'원가개발',pos:'',roles:['원가개발'],partner:'',email:'',tel:'',status:'사용'},
];
// 역할 → 편집권 부여 모듈(그룹). 시스템관리자=전권(별도). 미설정 모듈=조회만.
const ROLE_MOD={'구매/자재':['pur','partner'],'생산':['prod','gagong'],'원가개발':['dev'],'영업':['sales'],'품질':['qc'],'경영':['mgmt']};
const COMMON_VIEW=['base'];   // 전부서 공통 '조회' 모듈(기준정보=품목·BOM·도면 조회). 수정은 역할/관리자만(직원 읽기전용).
const _sid2mod=(sid)=>{for(const m of MODULES){for(const s of (m.subs||[])){if(s.id===sid)return m.id;}}return '';};
const getUsers=()=>{try{const s=localStorage.getItem('perm_users');if(s)return JSON.parse(s);}catch(e){}return JSON.parse(JSON.stringify(SEED_USERS));};
const PERM={
  userId: localStorage.getItem('perm_userId')||'admin',
  perms: (()=>{try{return JSON.parse(localStorage.getItem('perm_userperm'))||{};}catch(e){return {};}})(),  // 사용자×프로그램×{view,edit}
  savePerms(){localStorage.setItem('perm_userperm',JSON.stringify(this.perms));
    try{return fetch(API_BASE+'/api/perm/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({perms:this.perms,by:this.userId})});}catch(e){return Promise.resolve();}},
  async loadFromServer(){try{const r=await fetch(API_BASE+'/api/perm/all');if(!r.ok)return false;const j=await r.json();if(j&&j.perms){this.perms=j.perms;localStorage.setItem('perm_userperm',JSON.stringify(this.perms));return true;}}catch(e){}return false;},
  // ★계정목록 서버 로드(전 PC 공통) — 로그인 전 호출. 서버값=정본, 시드계정은 항상 병합 보장.
  async loadUsersFromServer(){try{const r=await fetch(API_BASE+'/api/perm/users');if(!r.ok)return false;const j=await r.json();
    if(j&&Array.isArray(j.users)&&j.users.length){const merged=j.users.slice();
      SEED_USERS.forEach(su=>{if(!merged.some(u=>u.id===su.id))merged.push(JSON.parse(JSON.stringify(su)));});
      localStorage.setItem('perm_users',JSON.stringify(merged));return true;}}catch(e){}return false;},
  saveUsersToServer(users){try{return fetch(API_BASE+'/api/perm/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({users,by:this.userId})});}catch(e){return Promise.resolve();}},
  setUser(id){this.userId=id;localStorage.setItem('perm_userId',id);},
  // ★서버가 준 사용자를 우선한다 — partner_code(거래처코드)가 여기 실려 온다.
  //   로컬 시드는 서버 응답이 없을 때의 역할 표시용일 뿐, 권한 판정의 근거가 아니다(판정은 서버).
  currentUser(){const a=(typeof AUTH!=='undefined')&&AUTH.user;
    if(a&&a.id===this.userId)return a;
    return getUsers().find(u=>u.id===this.userId)||{id:'-',nm:'미지정',roles:['시스템관리자']};},
  isAdmin(){return (this.currentUser().roles||[]).includes('시스템관리자');},
  can(sid,act){ if(this.isAdmin())return true;   // TEST1(시스템관리자)=전권
    const pm=(this.perms[this.userId]||{})[sid];
    if(pm){ if(act==='view')return pm.view!==false; return !!pm.edit; }   // ★TEST1이 개별 부여한 권한 우선(override)
    const roles=this.currentUser().roles||[], mod=_sid2mod(sid);
    if(act==='view' && COMMON_VIEW.includes(mod)) return true;   // 기준정보=전부서 공통 조회
    return roles.some(r=>(ROLE_MOD[r]||[]).includes(mod)); },   // 기본=본인 부서 모듈만 조회·수정(자재는 자재것만). 나머지 부서=숨김
  canView(sid){return this.can(sid,'view');},
  canEdit(sid){return this.can(sid,'edit');},
  label(){const u=this.currentUser();return `${u.nm}${this.isAdmin()?'·전권':''}`;},
};
// ===== UI규칙: 컬럼 크기 사용자 조정 (전역 .tbl 표 헤더 우측 드래그) =====
(function(){
  const EDGE=7;
  document.addEventListener('mousemove',function(e){
    if(document.body.classList.contains('col-rsz'))return;
    const th=e.target.closest&&e.target.closest('table.tbl thead th');
    if(!th){return;}
    const r=th.getBoundingClientRect();
    th.style.cursor=(r.right-e.clientX<=EDGE)?'col-resize':'';
  });
  document.addEventListener('mousedown',function(e){
    const th=e.target.closest&&e.target.closest('table.tbl thead th');
    if(!th)return;
    const r=th.getBoundingClientRect();
    if(r.right-e.clientX>EDGE)return;   // 우측 가장자리에서만
    e.preventDefault(); e.stopPropagation();
    const sx=e.pageX, sw=th.offsetWidth;
    document.body.classList.add('col-rsz'); document.body.style.cursor='col-resize';
    const mv=ev=>{const w=Math.max(24,sw+ev.pageX-sx); th.style.width=w+'px'; th.style.minWidth=w+'px'; th.style.maxWidth=w+'px';};
    const up=()=>{document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up);
      document.body.classList.remove('col-rsz'); document.body.style.cursor='';};
    document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
  });
})();

// 전 프로그램(화면) 목록 = MODULES flatten
function allPrograms(){const out=[];MODULES.forEach(m=>(m.subs||[]).forEach(s=>out.push({id:s.id,nm:s.nm,mod:m.nm,modId:m.id})));return out;}

/* 공용: CSV(엑셀) 다운로드 — 대부분 화면 공용. header=배열, rows=배열의 배열 */
function dlCSV(name, header, rows){
  const q=v=>{v=(v==null?'':''+v); return /[",\n\r]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;};
  const csv='﻿'+[header,...rows].map(r=>r.map(q).join(',')).join('\r\n');
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  a.download=name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}

/* ================= 화면들 ================= */
const SCREEN={};
SCREEN._na=(c,id)=>{c.innerHTML=`<div class="empty">「${id}」 화면은 준비 중입니다.</div>`;};

/* ===== 시방변경 상태 마커(구시방 경보) — 거래/조회 화면 공용 =====
   사용법: 품번 셀에 data-si="품번" 부여 → 렌더 후 specDecorate(container) 호출.
   red(적용지남=구시방,금지) 🔴✕ / orange(적용예정) 🟠✕ · 클릭 시 시방내용 팝업 */
const SPEC={cache:{},allLoaded:false,_p:null};
function specLoadAll(){   // 시방변경 전체맵 1회 로드(캐시)
  if(SPEC.allLoaded)return Promise.resolve();
  if(!SPEC._p)SPEC._p=fetch(API_BASE+'/api/spec/all').then(r=>r.json())
    .then(j=>{Object.assign(SPEC.cache,j.map||{});SPEC.allLoaded=true;}).catch(()=>{});
  return SPEC._p;
}
function specMark(item){
  const s=SPEC.cache[item]; if(!s)return '';
  const col=s.sev==='red'?'#c0392b':'#e08e0b';
  return `<span class="spec-x" data-si="${esc(item)}" title="시방변경 ${s.applied?'적용됨(구시방)':'예정'} · 적용 ${esc(s.apply_ymd)} · ${esc(s.rev_desc)}" style="cursor:pointer;color:${col};font-weight:900;margin-right:3px">✕</span>`;
}
function specBindPopup(container){
  container.querySelectorAll('.spec-x').forEach(el=>el.onclick=(e)=>{e.stopPropagation();const it=el.dataset.si,s=SPEC.cache[it];if(!s)return;
    alert(`[시방변경 ${s.applied?'적용됨 · 구시방':'적용 예정'}]\n\n품번: ${it}\n적용일: ${s.apply_ymd}\nECO: ${s.eco_no}\n접수일: ${s.rev_ymd}\n내용: ${s.rev_desc}\n\n${s.applied?'⛔ 적용일 경과 — 이 품번(구시방)은 발주·입고·키팅·생산·출하 금지. 재고는 폐기대상.':'⚠ 적용 예정 — 사전 확인 후 진행하세요.'}`);});
}
async function specDecorate(container){
  await specLoadAll();
  const cells=[...container.querySelectorAll('[data-si]')].filter(c=>!c.classList.contains('spec-x')&&!c.dataset.done);
  cells.forEach(c=>{const m=specMark(c.dataset.si);if(m)c.insertAdjacentHTML('afterbegin',m);c.dataset.done='1';});
  specBindPopup(container);
}

/* 공용: 품목 검색그리드 렌더러 (품목 조회 / 자재 목록 공용) */
function itemGrid(c,{title,sub,types,showSupCnt}){
  const typeOpts = Object.entries(TYPE_NM).filter(([k])=>!types||types.includes(k));
  c.innerHTML=`
   <div class="page-title">${title}</div><div class="page-sub">${sub}</div>
   <div class="toolbar">
     <label>검색</label><input class="inp" id="q" placeholder="품목코드 / 품명">
     <label>유형</label><select class="sel" id="type"><option value="">전체</option>
       ${typeOpts.map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
   </div>
   <div class="split">
     <div><div class="grid-wrap"><table class="tbl"><thead><tr>
        <th>품목코드</th><th>품명</th><th>유형</th><th>분류</th><th>단위</th>
        <th class="num">표준원가</th>${showSupCnt?'<th class="center">매입처</th>':''}<th class="center">사용</th>
       </tr></thead><tbody id="body"></tbody></table></div><div class="rowcount" id="cnt"></div></div>
     <div class="panel" id="i-detail"><div class="panel-h">상세 정보</div><div class="panel-b empty">좌측에서 품목을 선택하세요.</div></div>
   </div>`;
  const pool = DB.items.filter(r=>!types||types.includes(r.type));
  const body=c.querySelector('#body');
  const render=rows=>{
    body.innerHTML=rows.length?rows.map(r=>`<tr data-cd="${esc(r.cd)}">
      <td data-si="${esc(r.cd)}"><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td>
      <td>${esc(r.cat)}</td><td class="center">${esc(r.uom)}</td>
      <td class="num">${won(r.price)}</td>${showSupCnt?`<td class="center">${supCount(r.cd)||'-'}</td>`:''}
      <td class="center"><span class="bdg ${r.useyn==='Y'?'ok':'off'}">${r.useyn==='Y'?'사용':'중지'}</span></td></tr>`).join('')
      :`<tr><td colspan="8" class="empty">결과 없음</td></tr>`;
    c.querySelector('#cnt').textContent=`${rows.length}건 표시 / 대상 ${pool.length}건`;
    body.querySelectorAll('tr[data-cd]').forEach(tr=>tr.onclick=()=>{
      body.querySelectorAll('tr').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');
      itemDetail(c,tr.dataset.cd);});
    specDecorate(body);   // 구시방 품번 X 마커
  };
  const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),t=c.querySelector('#type').value;
    render(pool.filter(r=>(!t||r.type===t)&&(!q||r.cd.toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
  c.querySelector('#go').onclick=apply;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
  c.querySelector('#type').onchange=apply;
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#type').value='';apply();};
  render(pool); c._apply=apply;
}
function itemDetail(c,cd){
  const it=DB.items.find(x=>x.cd===cd), dt=DB.itemDetail[cd]||{suppliers:[],prices:[]};
  const sup=dt.suppliers.length?`<table class="tbl"><thead><tr><th>거래처코드</th><th>거래처명</th><th>조달구분</th><th class="center">우선</th></tr></thead>
     <tbody>${dt.suppliers.map(s=>`<tr><td>${esc(s.pcd)}</td><td>${esc(s.pnm)}</td>
       <td>${({BUY:'매입',OUTSOURCE:'가공외주',DIRECT:'직납'}[s.stype]||s.stype)}</td><td class="center">${s.pri}</td></tr>`).join('')}</tbody></table>`
     :`<div class="empty">등록된 매입처 없음</div>`;
  const px=dt.prices.length?`<table class="tbl"><thead><tr><th>유형</th><th>통화</th><th>적용일</th><th class="num">단가</th></tr></thead>
     <tbody>${dt.prices.map(p=>`<tr><td>${({STD_COST:'표준원가',SALE:'판가',BUY:'매입가',SAGUB:'사급단가'}[p.ptype]||p.ptype)}</td>
       <td class="center">${esc(p.cur)}</td><td>${esc(p.ymd)}</td><td class="num">${won(p.up)}</td></tr>`).join('')}</tbody></table>`
     :`<div class="empty">단가 이력 없음</div>`;
  c.querySelector('#i-detail').innerHTML=`<div class="panel-h">상세 정보 ${tbadge(it.type)}</div><div class="panel-b">
     <div class="detail-title">${esc(it.nm)}</div><div class="detail-code">${esc(it.cd)}</div>
     <dl class="kv" style="margin-top:12px">
       <dt>유형</dt><dd>${TYPE_NM[it.type]||it.type}</dd><dt>분류</dt><dd>${esc(it.cat)||'-'}</dd>
       <dt>기준단위</dt><dd>${esc(it.uom)}</dd><dt>표준원가</dt><dd>${won(it.price)}</dd>
       <dt>사용여부</dt><dd>${it.useyn==='Y'?'사용':'중지'}</dd></dl>
     <div class="section-t">매입처 (N:M)</div>${sup}
     <div class="section-t">단가 이력 (시계열)</div>${px}</div>`;
}

/* 품목 조회 (전체) */
/* 품목/자재 조회 — 라이브 PR_M_ITEM 전 컬럼(코드→이름), 레거시 w_pr_master_010 · mat=true→자재만+표준원가 */
function itemLiveView(c, mat){
  const API=API_BASE;
  const st={rows:[],cnt:0,q:'',lg:'',sg:'',nat:'',use:'1',lgroups:[],sgroups:[],natures:[],loading:false};   // use=사용여부(1사용중/0사용중지/''전체) 기본 사용중
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/item/list?q=${encodeURIComponent(st.q)}&lgroup=${encodeURIComponent(st.lg)}&sgroup=${encodeURIComponent(st.sg)}&nature=${encodeURIComponent(st.nat)}&use=${encodeURIComponent(st.use)}&mat=${mat?'1':''}`);
      const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;if(j.lgroups)st.lgroups=j.lgroups;if(j.sgroups)st.sgroups=j.sgroups;if(j.natures)st.natures=j.natures;}
    catch(e){st.rows=[];}
    st.loading=false;draw();};
  // [key, label, align('n'=우측숫자), width(px)] — table-layout:fixed+colgroup 폭. 헤더 우측경계 드래그로 조절.
  const COLS=[['item_code','품번','',95],['nm','품명','',150],['nature','성격','',68],['spec','규격','',75],['lgroup','대분류','',55],['sgroup','소분류','',60],['pipe_kind','품목형태','',62],['unit','단위','',44],
    ['in_cust','매입처','',92]].concat(mat?[['item_cost','표준원가','n',72]]:[]).concat([
    ['diam','외경','n',48],['thick','두께','n',48],['length','길이','n',48],['weight','단위중량','n',62],['metal','재질','',46],['work','작업처','',60],
    ['make_type','제작유형','',66],['status','상태','',46],['safe_min','안전min','n',54],['safe_max','안전max','n',54],['kitting_min','키팅최소','n',58],
    ['weld_in','용접IN','n',52],['weld_out','용접OUT','n',56],['tariff','관세율','n',54],['remarks','비고','',110]]);
  // tbody만 렌더(정렬 시 헤더 유지·화살표 보존용) — draw와 재사용
  const rowsHTML=()=> st.loading?spinRow(COLS.length):(st.rows.length?st.rows.map(r=>`<tr>${COLS.map((x,i)=>{const v=r[x[0]];
        if(x[0]==='nature')return `<td style="overflow:hidden;text-overflow:ellipsis"><span style="font-size:10px;color:#33507d">${esc(String(v||'').replace(/^\d+\./,''))}</span>${r.active===0?' <span title="정리대상 후보" style="color:#c0392b;font-weight:700">▲</span>':''}</td>`;
        if(x[0]==='status')return `<td style="overflow:hidden;text-overflow:ellipsis">${v==='사용'?'':esc(v)}</td>`;
        return `<td class="${x[2]==='n'?'num':''}" title="${esc(v)}" style="overflow:hidden;text-overflow:ellipsis">${i===0?`<b>${esc(v)}</b>`:(x[2]==='n'?won(v):esc(v))}</td>`;}).join('')}</tr>`).join(''):`<tr><td colspan="${COLS.length}" class="empty">조회 결과 없음</td></tr>`);
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">${mat?'자재 목록 조회':'품목 조회'} <span style="font-size:12px;color:var(--muted);font-weight:400">라이브 · ${mat?'구매 대상 자재':'레거시 w_pr_master_010'}</span></div>
     ${mat?`<div class="page-sub">구매 자재(원자재·부자재·소모품·사급) + <b>표준원가·매입처</b>(코드→이름: 대/소분류·품목형태·단위·재질·매입처·작업처·제작유형). 원본 <code>PR_M_ITEM</code> · 빈컬럼(밸브/형상 등) 미표시</div>`:''}
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <input class="inp" id="it-q" value="${esc(st.q)}" placeholder="품번/품명 검색" style="width:170px">
       <label class="tl">대분류</label><select class="inp" id="it-lg" style="width:auto"><option value="">전체</option>${st.lgroups.map(o=>`<option value="${esc(o.code)}" ${st.lg===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
       <label class="tl">소분류</label><select class="inp" id="it-sg" style="width:auto"><option value="">전체</option>${st.sgroups.map(o=>`<option value="${esc(o.code)}" ${st.sg===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
       <label class="tl">성격</label><select class="inp" id="it-nat" style="width:auto"><option value="">전체</option>${st.natures.map(o=>`<option value="${esc(o.code)}" ${st.nat===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
       <label class="tl" title="LG 리시빙 2501~ 실사용 + 매입/매출/불출 거래품목=사용중">사용여부</label><select class="inp" id="it-use" style="width:auto"><option value="1" ${st.use==='1'?'selected':''}>사용중</option><option value="0" ${st.use==='0'?'selected':''}>사용중지</option><option value="" ${st.use===''?'selected':''}>전체</option></select>
       <button class="btn" id="it-go">조회</button>
       <button class="btn xls" id="it-xls">⬇ 엑셀</button>
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건${st.cnt>=3000?'(상한)':''}</span>
     </div>
     <div class="grid-wrap" style="max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px;table-layout:fixed;width:100%"><thead><tr>${COLS.map(x=>`<th class="${x[2]==='n'?'num':''}" style="width:${x[3]}px">${x[1]}</th>`).join('')}</tr></thead>
      <tbody>${rowsHTML()}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#it-go').onclick=()=>{st.q=g('#it-q').value;st.lg=g('#it-lg').value;st.sg=g('#it-sg').value;st.nat=g('#it-nat').value;st.use=g('#it-use').value;load();};
    g('#it-q').onkeyup=e=>{if(e.key==='Enter')g('#it-go').click();};
    g('#it-xls').onclick=async()=>{   // 화면(500)이 아닌 조회조건 전량을 재조회해 다운로드
      const b=g('#it-xls'), t0=b.textContent; b.textContent='내보내는 중…'; b.disabled=true;
      try{
        const r=await fetch(`${API}/api/item/list?q=${encodeURIComponent(st.q)}&lgroup=${encodeURIComponent(st.lg)}&sgroup=${encodeURIComponent(st.sg)}&nature=${encodeURIComponent(st.nat)}&use=${encodeURIComponent(st.use)}&mat=${mat?'1':''}&limit=30000`);
        const j=await r.json(); const rows=j.rows||[];
        const hd=COLS.map(x=>x[1]);
        const out=rows.map(r2=>COLS.map(x=>x[0]==='status'?(r2[x[0]]==='사용'?'':(r2[x[0]]||'')):(r2[x[0]]==null?'':r2[x[0]])));
        downloadCSV((mat?'자재목록':'품목목록')+'.csv',hd,out);
      }catch(e){alert('엑셀 내보내기 실패: '+e);}
      finally{b.textContent=t0; b.disabled=false;}
    };
    // ★UI규칙: 헤더 더블클릭=정렬(enableSort) + 컬럼폭 드래그(addResizer 내장). tbody만 갱신해 헤더/화살표 보존
    enableSort(c, COLS.map(x=>x[0]), ()=>st.rows, ()=>{const tb=c.querySelector('tbody'); if(tb)tb.innerHTML=rowsHTML();});
  };
  load();
}

/* 자재 목록 조회 = itemLiveView(c,true) — 위 SCREEN.mat 정의(라이브) 사용 */

/* 품목단가 조회 (품목별 그룹 → 구매/판매 단가 히스토리) */
const MKT_NM={EXPORT:'수출',DOMESTIC:'내수'};
/* 전사 단가변동내역 — 라이브 PR_M_ITEM_COST 피드(직전단가 대비 Δ) */
function priceHistView(host){
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),item:'',tag:'',lgroup:'',sgroup:'',cust:'',changed:true};
  let vT=null;
  let data={rows:[],cnt:0,changed:0}, loading=false, msg='';
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,item:F.item,tag:F.tag,lgroup:F.lgroup,sgroup:F.sgroup,cust:F.cust,changed:F.changed?'1':''});
    try{const r=await fetch(`${API}/api/price/history?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';data={rows:[],cnt:0,changed:0};}
    loading=false;draw();};
  const dcell=d=>{if(d==null)return '<span style="color:#8aa0bd">신규</span>';
    const col=d<0?'#c0392b':(d>0?'#1c7c3a':'#888');const sg=d>0?'▲':(d<0?'▼':'–');
    return `<b style="color:${col}">${sg} ${won(Math.abs(d))}</b>`;};
  const draw=()=>{
    host.innerHTML=`
     <div class="page-sub" style="margin:2px 0 6px">전사 단가변경 이력을 <b>적용일 내림차순</b>으로. 직전단가 대비 증감(Δ) 표시. 원본 <code>PR_M_ITEM_COST</code>(라이브·읽기전용) · 구분 1=매입·E=수출판매·S=내수판매</div>
     <div class="toolbar">
       <label class="tl">적용기간</label><input class="inp" type="date" id="ph-from" value="${F.from}"> ~ <input class="inp" type="date" id="ph-to" value="${F.to}">
       <label class="tl">품번</label><input class="inp" id="ph-item" value="${esc(F.item)}" style="width:110px">
       <label class="tl">대분류</label><select class="inp" id="ph-lg" style="max-width:130px"><option value="">전체</option>${(data.lgroups||[]).map(o=>`<option value="${esc(o.code)}"${F.lgroup===o.code?' selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">소분류</label><select class="inp" id="ph-sg" style="max-width:130px"><option value="">전체</option>${(data.sgroups||[]).map(o=>`<option value="${esc(o.code)}"${F.sgroup===o.code?' selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">거래처</label><input class="inp" id="ph-cust" list="ph-custdl" autocomplete="off" value="${esc(F.cust)}" placeholder="거래처명/코드" style="width:120px"><datalist id="ph-custdl"></datalist>
       <label class="tl">구분</label><select class="inp" id="ph-tag"><option value="">전체</option><option value="1"${F.tag==='1'?' selected':''}>매입</option><option value="E"${F.tag==='E'?' selected':''}>판매(수출)</option><option value="S"${F.tag==='S'?' selected':''}>판매(내수)</option></select>
       <label class="tl" style="cursor:pointer"><input type="checkbox" id="ph-chg" ${F.changed?'checked':''}> 변동분만</label>
       <button class="btn" id="ph-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${won(data.cnt)}건${F.changed?'':` · 변동 ${won(data.changed)}`}</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>
        <th>적용일</th><th>구분</th><th>품번</th><th>품명</th><th>거래처</th><th class="center">시장</th><th class="center">통화</th>
        <th class="num">단가</th><th class="num">직전단가</th><th class="num">증감</th><th class="num">재료비</th><th class="num">가공비</th><th>담당</th><th>등록일시</th></tr></thead>
      <tbody>${loading?spinRow(14):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${dcol(r.apply_ymd)}</td><td class="center">${esc(r.tag_nm)}</td>
        <td><b>${esc(r.item)}</b></td><td class="bcap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="bcap" title="${esc(r.cust_nm||r.cust)}" style="max-width:110px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_nm||r.cust)}</td>
        <td class="center">${esc(r.mkt)}</td><td class="center">${esc(r.curr)}</td>
        <td class="num"><b>${won(r.cost)}</b></td><td class="num" style="color:#888">${r.prev==null?'-':won(r.prev)}</td>
        <td class="num">${dcell(r.delta)}</td><td class="num">${won(r.mat)}</td><td class="num">${won(r.procc)}</td>
        <td>${esc(r.usr)}</td><td class="center" style="color:#8aa0bd">${esc(r.idt)}</td></tr>`).join(''):`<tr><td colspan="14" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#ph-search').onclick=()=>{F.from=g('#ph-from').value;F.to=g('#ph-to').value;F.item=g('#ph-item').value;F.tag=g('#ph-tag').value;F.lgroup=g('#ph-lg').value;F.sgroup=g('#ph-sg').value;F.cust=g('#ph-cust').value.trim();F.changed=g('#ph-chg').checked;load();};
    g('#ph-item').onkeyup=e=>{if(e.key==='Enter')g('#ph-search').click();};
    g('#ph-cust').onkeyup=e=>{if(e.key==='Enter')g('#ph-search').click();};
    // 거래처 오토컴플리트(디바운스 서버검색 → datalist)
    g('#ph-cust').oninput=e=>{const q=e.target.value.trim();clearTimeout(vT);if(q.length<1)return;
      vT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(q)}`);const vs=(await r.json()).rows||[];
        const dl=g('#ph-custdl');if(dl)dl.innerHTML=vs.map(x=>`<option value="${esc(x.code)}">${esc(x.name)}</option>`).join('');}catch(err){}},250);};
  };
  load();
}
/* 단가이력 매입/판매 분리 섹션(각 적용월 내림차순) — tag 1/매입=매입, E/S=판매 */
function priceHistSections(rows){
  const dcol=s=>{s=''+(s||'');return s.length===6?`${s.slice(0,2)}/${s.slice(2,4)}`:s;};
  const tagColor=t=>t==='1'?'#1c47a0':(t==='E'?'#b12a2a':'#7a5c1c');
  const isBuy=t=>{t=(''+(t||'')).trim();return t==='1'||t==='매입';};
  const buy=rows.filter(r=>isBuy(r.tag)).slice().sort((a,b)=>(''+(b.apply_ymd||'')).localeCompare(''+(a.apply_ymd||'')));
  const sale=rows.filter(r=>!isBuy(r.tag)).slice().sort((a,b)=>(''+(b.apply_ymd||'')).localeCompare(''+(a.apply_ymd||'')));
  const tbl=(list)=>`<table class="tbl fit" style="font-size:11px"><thead><tr><th>단가구분</th><th>거래처</th><th class="center">적용월</th><th class="center">대표</th><th class="center">통화</th><th class="num">단가</th><th class="num">재료비</th><th class="num">가공비</th><th class="num">기타</th><th>비고</th></tr></thead>
     <tbody>${list.map(r=>`<tr>
       <td class="center"><span style="color:#fff;background:${tagColor((''+(r.tag||'')).trim())};padding:1px 6px;border-radius:8px;font-size:10px">${esc(r.tag_nm)}</span></td>
       <td class="cap" title="${esc(r.cust_nm||r.cust)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_nm||r.cust)||'-'}</td>
       <td class="center">${dcol(r.apply_ymd)}</td><td class="center">${r.main?'<b style="color:#e0a020">★</b>':''}</td><td class="center">${esc(r.curr_nm)}</td>
       <td class="num"><b>${won(r.item_cost)}</b></td><td class="num">${won(r.mat_cost)}</td><td class="num">${won(r.proc_cost)}</td><td class="num">${won(r.other_cost)}</td>
       <td class="cap" title="${esc(r.remarks)}" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${esc(r.remarks)}</td></tr>`).join('')}</tbody></table>`;
  const sec=(title,color,list)=>`<div class="section-t" style="margin:6px 0 3px;font-weight:700;color:${color}">${title} <span class="muted" style="font-weight:400">(${list.length}건)</span></div>${list.length?tbl(list):'<div class="empty" style="padding:6px">없음</div>'}`;
  return sec('🛒 매입단가','#1c47a0',buy)+sec('💹 판매단가 (수출/내수)','#b12a2a',sale);
}
/* 품목별 단가조회(기존) */
/* 품목별 단가조회 — 라이브 PR_M_ITEM_COST (거래처별·적용월 시계열, 레거시 w_pr_master_150) */
function priceItemView(c){
  const API=API_BASE;
  const st={rows:[],cnt:0,q:'',lg:'',sg:'',cust:'',lgroups:[],sgroups:[],sel:'',det:null,plan:null,planEdit:null,loading:false};
  let custT=null;
  const dcol=s=>{s=''+(s||'');return s.length===6?`${s.slice(0,2)}/${s.slice(2,4)}`:s;};
  const tagColor=t=>t==='1'?'#1c47a0':(t==='E'?'#b12a2a':'#7a5c1c');
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/price/search?q=${encodeURIComponent(st.q)}&lgroup=${encodeURIComponent(st.lg)}&sgroup=${encodeURIComponent(st.sg)}&cust=${encodeURIComponent(st.cust)}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;if(j.lgroups)st.lgroups=j.lgroups;if(j.sgroups)st.sgroups=j.sgroups;}
    catch(e){st.rows=[];}
    st.loading=false;draw();};
  const loadDet=async(item)=>{st.sel=item;st.det=null;st.plan=null;draw();
    try{st.det=await (await fetch(`${API}/api/price/item?item=`+encodeURIComponent(item))).json();}catch(e){}
    // 조달후보 계획단가(후보/계획 단가 — 정산 아님, sourcing 레이어). ★여기서도 편집 가능(조달 프로파일과 동일 nx 테이블)
    st.planEdit=null;
    try{st.plan=await (await fetch(`${API}/api/sourcing/plan_price?item=`+encodeURIComponent(item))).json();}catch(e){st.plan=null;}
    draw();};
  // ★계획단가 편집(품목단가 관리에서도 입력) — 조달 프로파일과 동일 엔드포인트 재사용 → 자동 동기화. 공통(기본)+업체별 예외(override).
  const ovk=(vc,k)=>`${vc}||${k}`;
  const peOpen=async(route_id)=>{
    const rt=((st.plan&&st.plan.routes)||[]).find(r=>r.route_id===route_id)||{};
    const vends=(rt.vendors||[]).filter(v=>v.vendor_code).map(v=>({vendor_code:v.vendor_code,vendor_name:v.vendor_name||v.vendor_code}));
    st.planEdit={route_id,vends,subs:[],children:[],direct:[],assyOv:{},sagubOv:{},loading:true,saving:false,msg:''};draw();
    try{const sr=await (await fetch(`${API}/api/sourcing/sub_price?route_id=${route_id}`)).json();
      st.planEdit.subs=(sr.subs||[]).map(s=>{const pr=(sr.prices||[]).find(p=>p.sub_item===s.sub_item)||{};
        (pr.overrides||[]).forEach(o=>{st.planEdit.assyOv[ovk(o.vendor_code,s.sub_item)]=(o.assy_price!=null?o.assy_price:null);});  // ★ASSY=업체별만
        return {sub_item:s.sub_item,sub_name:s.sub_name||'',gubun:s.gubun||''};});
      st.planEdit.direct=sr.direct_items||[];
    }catch(e){}
    try{const gr=await (await fetch(`${API}/api/sourcing/sagub_price?route_id=${route_id}`)).json();
      st.planEdit.children=(gr.rows||[]).map(x=>{(x.overrides||[]).forEach(o=>{st.planEdit.sagubOv[ovk(o.vendor_code,x.item_code)]=(o.sagub_price!=null?o.sagub_price:null);});
        return {item_code:x.item_code,item_name:x.item_name||'',sub_item:x.sub_item||'',gubun:x.gubun||'',is_purchase:!!x.is_purchase,sagub:(x.is_purchase&&x.sagub_price!=null?x.sagub_price:null)};});
    }catch(e){}
    st.planEdit.loading=false;draw();};
  const peClose=()=>{st.planEdit=null;draw();};
  const peSave=async()=>{const pe=st.planEdit;if(!pe)return;pe.saving=true;pe.msg='';draw();
    const pf=v=>(v!==''&&v!=null)?parseFloat(v):null;
    const arows=[];pe.subs.forEach(s=>{   // ★ASSY=업체별만(공통행 없음)
      pe.vends.forEach(v=>{const k=ovk(v.vendor_code,s.sub_item);if(k in pe.assyOv)arows.push({vendor_code:v.vendor_code,sub_item:s.sub_item,assy_price:pf(pe.assyOv[k])});});});
    const grows=[];pe.children.filter(x=>x.is_purchase).forEach(x=>{grows.push({vendor_code:'',item_code:x.item_code,sagub_price:pf(x.sagub)});
      pe.vends.forEach(v=>{const k=ovk(v.vendor_code,x.item_code);if(k in pe.sagubOv)grows.push({vendor_code:v.vendor_code,item_code:x.item_code,sagub_price:pf(pe.sagubOv[k])});});});
    try{
      if(arows.length){await fetch(`${API}/api/sourcing/sub_price/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:pe.route_id,rows:arows})});}
      if(grows.length){await fetch(`${API}/api/sourcing/sagub_price/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:pe.route_id,rows:grows})});}
      st.planEdit=null;
      try{st.plan=await (await fetch(`${API}/api/sourcing/plan_price?item=`+encodeURIComponent(st.sel))).json();}catch(e){}
      draw();
    }catch(e){pe.saving=false;pe.msg='❌ 저장 실패: '+e;draw();}};
  // 후보/계획 단가 섹션 — 정산 매입/판매 단가(마스터, 마감때만 수정)와 명확히 구분. 계획단가(공통+업체예외)는 여기서 편집 가능
  const planPriceSection=(pl)=>{
    const hdr=`<div class="section-t" style="color:#8a6d1c">🧭 조달후보 계획단가 <span class="muted" style="font-weight:400">(후보/계획 단가 — <b>정산 아님</b>, 여기서 편집 가능)</span></div>
      <div style="font-size:11px;color:#8a6d1c;background:#fdf7e6;border:1px solid #f0e6c8;border-radius:6px;padding:5px 8px;margin-bottom:6px"><b>ASSY 매입단가=업체별</b>(외주 SUB×업체) · <b>사급 부품가=공통+업체예외</b>(매입 부품, 예외 비우면 공통 COALESCE). 단품 매입품은 매입 마스터 자동. 업체는 배분%만. <b>계획단가(nx.item_price)</b>는 여기서 입력·저장(조달 프로파일과 자동 동기화). 위 <b>정산 매입/판매 단가</b>(마스터·마감때만 수정)와는 별개입니다.</div>`;
    if(!pl||!pl.routes||!pl.routes.length)return hdr+`<div class="empty" style="font-size:12px">조달후보(승인 route) 없음 — [개발 › 조달경로 통합검토]에서 후보 생성·승인 후 여기/조달 프로파일에서 계획단가 입력</div>`;
    const pe=st.planEdit;
    const ovtxt=(arr,pk)=>(arr&&arr.length)?' <span style="color:#b8860b;font-size:10px">['+arr.map(o=>`${esc(o.vendor_name||o.vendor_code)}:${o[pk]==null?'-':won(o[pk])}`).join(', ')+']</span>':'';
    const blocks=pl.routes.map(rt=>{
      const rlabel=`R${String(rt.route_no).padStart(2,'0')}${rt.current_flag?'·현행':''}`;
      const editable=rt.approve_flag&&rt.route_id>0;
      const editing=pe&&pe.route_id===rt.route_id;
      const badge=`<span style="background:${rt.current_flag?'#1c7c3a':'#1c47a0'};color:#fff;border-radius:8px;padding:1px 7px;font-size:11px;font-weight:700">${esc(rlabel)}</span> <span style="font-size:12px;color:#556;font-weight:600">${esc(rt.route_name||'')}</span>`;
      const vs=(rt.vendors||[]).filter(v=>v.vendor_code);
      const vendHtml=vs.length?`<div style="font-size:11px;color:#556;margin:2px 0 4px">업체 배분: ${vs.map(v=>`${esc(v.vendor_name||v.vendor_code)} <b>${v.alloc_ratio==null?'-':won(v.alloc_ratio)+'%'}</b>${v.is_active?'':' <span style="color:#aab">(비활성)</span>'}`).join(' · ')}</div>`:'<div style="font-size:11px;color:#aab;margin:2px 0 4px">지정 업체 없음</div>';
      let body;
      if(editing){
        if(pe.loading)body='<div class="empty" style="font-size:12px">불러오는 중…</div>';
        else{
          const asy=pe.subs.length?`<table class="tbl" style="font-size:12px;margin:2px 0"><thead><tr><th>외주 SUB(ASSY 매입단가=업체별)</th>${pe.vends.length?pe.vends.map(v=>`<th class="num" title="${esc(v.vendor_code)}">${esc(v.vendor_name)}</th>`).join(''):'<th class="num">업체별</th>'}</tr></thead><tbody>${pe.subs.map(s=>`<tr><td><b>🧩 ${esc(s.sub_item)}</b> <span class="cap" style="color:#8aa0bd">${esc(s.sub_name)}</span></td>${pe.vends.length?pe.vends.map(v=>{const av=pe.assyOv[ovk(v.vendor_code,s.sub_item)];return `<td class="num"><input class="inp pe-assyov num" data-vc="${esc(v.vendor_code)}" data-si="${esc(s.sub_item)}" type="number" step="1" value="${av==null?'':av}" placeholder="업체별" style="width:96px"></td>`;}).join(''):'<td class="num"><span style="font-size:10px;color:#aab">업체 지정 후</span></td>'}</tr>`).join('')}</tbody></table>`:'';
          const purch=pe.children.filter(x=>x.is_purchase);
          const madeCnt=pe.children.length-purch.length;
          const sag=purch.length?`<table class="tbl" style="font-size:12px;margin:2px 0"><thead><tr><th>사급 부품(매입)</th><th class="num">공통</th>${pe.vends.map(v=>`<th class="num">${esc(v.vendor_name)} 예외</th>`).join('')}</tr></thead><tbody>${purch.map(x=>`<tr><td><b>${esc(x.item_code)}</b> <span class="cap" style="color:#8aa0bd" title="${esc(x.item_name)}">${esc(x.item_name)}</span></td><td class="num"><input class="inp pe-sag num" data-ic="${esc(x.item_code)}" type="number" step="1" value="${x.sagub==null?'':x.sagub}" placeholder="공통" style="width:96px"></td>${pe.vends.map(v=>{const sv=pe.sagubOv[ovk(v.vendor_code,x.item_code)];return `<td class="num"><input class="inp pe-sagov num" data-vc="${esc(v.vendor_code)}" data-ic="${esc(x.item_code)}" type="number" step="1" value="${sv==null?'':sv}" placeholder="공통(${x.sagub==null?'-':won(x.sagub)})" style="width:96px"></td>`;}).join('')}</tr>`).join('')}</tbody></table>`:'';
          body=`${(pe.subs.length||purch.length)?'':'<div class="empty" style="font-size:12px">이 후보는 외주 SUB/매입 사급 부품이 없습니다(단품·제작만 — 매입 마스터/원가 자동).</div>'}
            ${asy}${sag}${madeCnt>0?`<div style="font-size:11px;color:#8aa0bd">※ 제작(가공품) ${madeCnt}건은 원가 자동(입력 대상 아님). 예외 비우면 공통 사용.</div>`:'<div style="font-size:11px;color:#8aa0bd">※ 예외 비우면 공통 사용(COALESCE).</div>'}
            ${pe.msg?`<div style="font-size:12px;color:#c0392b;font-weight:600">${esc(pe.msg)}</div>`:''}
            <div style="margin-top:4px;display:flex;gap:6px"><button class="btn pp-save" data-ri="${rt.route_id}" style="background:#8a6d1c;color:#fff" ${pe.saving?'disabled':''}>💾 계획단가 저장</button><button class="btn ghost pp-cancel">취소</button></div>`;
        }
      }else{
        const asyR=(rt.assy_subs&&rt.assy_subs.length)?rt.assy_subs.map(a=>`<span style="font-size:11px;white-space:nowrap;margin-right:10px">🧩 ${esc(a.sub_name||a.sub_item)} ${(a.overrides&&a.overrides.length)?a.overrides.map(o=>`<b>${esc(o.vendor_name||o.vendor_code)}:${o.assy_price==null?'-':won(o.assy_price)}</b>`).join(' '):'<span style="color:#c9d1dc">미입력</span>'}</span>`).join(''):'';
        const sagR=(rt.sagub_items&&rt.sagub_items.length)?rt.sagub_items.map(si=>`<span style="font-size:11px;white-space:nowrap;margin-right:10px">${esc(si.item_name||si.item_code)} <b>${si.sagub_price==null?'-':won(si.sagub_price)}</b>${ovtxt(si.overrides,'sagub_price')}</span>`).join(''):'';
        body=`<div style="font-size:11px;margin:1px 0"><span style="color:#8a6d1c;font-weight:600">ASSY 매입단가:</span> ${asyR||'<span style="color:#c9d1dc">미입력</span>'}</div>
          <div style="font-size:11px;margin:1px 0"><span style="color:#8a6d1c;font-weight:600">사급 부품가:</span> ${sagR||'<span style="color:#c9d1dc">미입력</span>'}</div>`;
      }
      return `<div style="border:1px solid #ece3c4;border-radius:8px;padding:6px 9px;margin-bottom:6px">
        <div style="display:flex;align-items:center;gap:8px">${badge}<span style="flex:1"></span>
          ${editable?(editing?'':`<button class="btn ghost pp-edit" data-ri="${rt.route_id}" style="font-size:11px;padding:1px 8px;color:#8a6d1c;border-color:#e6d29a">✏ 계획단가 편집</button>`):`<span style="font-size:10px;color:#aab">${rt.route_id>0?'미승인(편집 불가)':'현행 baseline(합성·편집 불가)'}</span>`}</div>
        ${vendHtml}${body}</div>`;
    }).join('');
    return hdr+blocks;
  };
  const draw=()=>{
    const _sc=(()=>{const g=c.querySelector('#pi-list');return g?g.scrollTop:0;})();   // 좌측 스크롤 보존
    const d=st.det;
    c.innerHTML=`
     <div class="page-sub">품번 선택 → <b>거래처별·적용월 단가 이력</b>(시계열, 소급조회의 원장). 원본 <code>PR_M_ITEM_COST</code>(라이브) · 구분 매입/LG판매/판매 · 코드→이름</div>
     <div class="split" style="grid-template-columns:1fr 1.5fr">
       <div>
         <div class="toolbar" style="flex-wrap:wrap;gap:4px"><input class="inp" id="pi-q" value="${esc(st.q)}" placeholder="품번/품명" style="width:130px">
           <select class="inp" id="pi-lg" style="width:auto"><option value="">대분류</option>${st.lgroups.map(o=>`<option value="${esc(o.code)}" ${st.lg===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
           <select class="inp" id="pi-sg" style="width:auto"><option value="">소분류</option>${st.sgroups.map(o=>`<option value="${esc(o.code)}" ${st.sg===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
           <input class="inp" id="pi-cust" list="pi-custdl" autocomplete="off" value="${esc(st.cust)}" placeholder="거래처명/코드" style="width:120px"><datalist id="pi-custdl"></datalist>
           ${st.cust?`<button class="btn ghost" id="pi-custx" title="거래처 필터 해제" style="padding:2px 6px">✖거래처</button>`:''}
           <button class="btn" id="pi-go">🔍</button><span class="rowcount">${won(st.cnt)}건${st.cnt>=1000?' (상한·검색/분류로 좁히세요)':''}</span></div>
         <div class="grid-wrap" id="pi-list" style="max-height:calc(100vh - 300px);overflow:auto"><table class="tbl fit"><thead><tr><th>품번</th><th>품명</th><th>소분류</th><th class="num">단가건</th></tr></thead>
          <tbody>${st.loading?spinRow(4):(st.rows.length?st.rows.map(r=>`<tr class="pi-row ${st.sel===r.ITEM_CODE?'sel':''}" data-cd="${esc(r.ITEM_CODE)}" style="cursor:pointer"><td><b>${esc(r.ITEM_CODE)}</b></td><td class="cap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td><td class="cap" title="${esc(r.spec)}" style="max-width:100px;overflow:hidden;text-overflow:ellipsis">${esc(r.sg_nm||'')}</td><td class="num">${won(r.cnt)}</td></tr>`).join(''):`<tr><td colspan="4" class="empty">품번/품명으로 검색</td></tr>`)}</tbody></table></div>
       </div>
       <div class="panel"><div class="panel-h">단가 이력 ${d?`— ${esc(d.item)} ${esc(d.nm)}`:''}</div>
        <div class="panel-b" style="max-height:calc(100vh - 260px);overflow:auto">${!d?'<div class="empty">좌측에서 품번을 선택하세요.</div>':((d.rows&&d.rows.length?priceHistSections(d.rows):'<div class="empty">단가 이력 없음</div>')+planPriceSection(st.plan))}</div></div>
     </div>`;
    const g=id=>c.querySelector(id);
    g('#pi-go').onclick=()=>{st.q=g('#pi-q').value;st.lg=g('#pi-lg').value;st.sg=g('#pi-sg').value;st.cust=g('#pi-cust').value.trim();load();};
    g('#pi-q').onkeyup=e=>{if(e.key==='Enter')g('#pi-go').click();};
    g('#pi-cust').onkeyup=e=>{if(e.key==='Enter'){st.cust=g('#pi-cust').value.trim();g('#pi-go').click();}};
    g('#pi-lg').onchange=()=>{st.lg=g('#pi-lg').value;load();};
    g('#pi-sg').onchange=()=>{st.sg=g('#pi-sg').value;load();};
    // 거래처 오토컴플리트(디바운스 서버검색 → datalist) + 필터해제
    g('#pi-cust').oninput=e=>{const q=e.target.value.trim();clearTimeout(custT);if(q.length<1)return;
      custT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(q)}`);const vs=(await r.json()).rows||[];
        // ★거래처명 기준 표시(코드는 보조): option value=이름, 라벨에 코드
        const dl=g('#pi-custdl');if(dl)dl.innerHTML=vs.map(x=>`<option value="${esc(x.name)}">${esc(x.name)} (${esc(x.code)})</option>`).join('');}catch(err){}},250);};
    {const cx=g('#pi-custx');if(cx)cx.onclick=()=>{st.cust='';load();};}
    c.querySelectorAll('.pi-row').forEach(tr=>tr.onclick=()=>loadDet(tr.dataset.cd));
    // 계획단가 편집 wiring(정산 이력은 읽기전용 유지, 계획단가=nx만 편집)
    c.querySelectorAll('.pp-edit').forEach(el=>el.onclick=()=>peOpen(+el.dataset.ri));
    {const pc=c.querySelector('.pp-cancel');if(pc)pc.onclick=peClose;
     const ps=c.querySelector('.pp-save');if(ps)ps.onclick=peSave;}
    c.querySelectorAll('.pe-assy').forEach(el=>el.onchange=()=>{if(st.planEdit){const s=st.planEdit.subs.find(x=>x.sub_item===el.dataset.si);if(s)s.assy=(el.value===''?null:el.value);}});
    c.querySelectorAll('.pe-sag').forEach(el=>el.onchange=()=>{if(st.planEdit){const x=st.planEdit.children.find(y=>y.item_code===el.dataset.ic);if(x)x.sagub=(el.value===''?null:el.value);}});
    c.querySelectorAll('.pe-assyov').forEach(el=>el.onchange=()=>{if(st.planEdit)st.planEdit.assyOv[ovk(el.dataset.vc,el.dataset.si)]=(el.value===''?null:el.value);});
    c.querySelectorAll('.pe-sagov').forEach(el=>el.onchange=()=>{if(st.planEdit)st.planEdit.sagubOv[ovk(el.dataset.vc,el.dataset.ic)]=(el.value===''?null:el.value);});
    attachResizers(c);
    const _g=c.querySelector('#pi-list'); if(_g&&_sc) _g.scrollTop=_sc;   // 스크롤 복원
  };
  load();
};
function priceDetail(c,cd){
  const it=DB.priceItems.find(x=>x.cd===cd);
  const buy=DB.priceBuyHist[cd]||[], sale=DB.priceSaleHist[cd]||[];
  const cur=m=>m==='Y'?'<span class="bdg ok">현행</span>':'';
  const buyTbl=buy.length?`<table class="tbl"><thead><tr><th>거래처코드</th><th>거래처명</th><th class="center">통화</th>
     <th class="num">재료비</th><th class="num">가공비</th><th class="num">기타</th><th class="num">매입단가</th><th>적용일</th><th class="center">현행</th></tr></thead>
     <tbody>${buy.map(r=>`<tr class="${r.main==='Y'?'sel':''}"><td>${esc(r.pcd)||'-'}</td><td>${esc(r.pnm)}</td><td class="center">${esc(r.cur)}</td>
       <td class="num">${won(r.mat)}</td><td class="num">${won(r.pcost)}</td><td class="num">${won(r.oth)}</td>
       <td class="num"><b>${won(r.up)}</b></td><td>${esc(r.ymd)}</td><td class="center">${cur(r.main)}</td></tr>`).join('')}</tbody></table>`
     :`<div class="empty">구매단가 없음</div>`;
  const saleTbl=sale.length?`<table class="tbl"><thead><tr><th class="center">구분</th><th>거래처코드</th><th>거래처명</th><th class="center">통화</th>
     <th class="num">판매단가</th><th>적용일</th><th class="center">현행</th></tr></thead>
     <tbody>${sale.map(r=>`<tr class="${r.main==='Y'?'sel':''}"><td class="center">${MKT_NM[r.mkt]||r.mkt||'-'}</td>
       <td>${esc(r.pcd)||'-'}</td><td>${esc(r.pnm)}</td><td class="center">${esc(r.cur)}</td>
       <td class="num"><b>${won(r.up)}</b></td><td>${esc(r.ymd)}</td><td class="center">${cur(r.main)}</td></tr>`).join('')}</tbody></table>`
     :`<div class="empty">판매단가 없음</div>`;
  c.querySelector('#pr-detail').innerHTML=`<div class="panel-h">단가 히스토리 ${tbadge(it.type)}</div><div class="panel-b">
     <div class="detail-title">${esc(it.nm)}</div><div class="detail-code">${esc(it.cd)} · ${esc(it.cat)||'-'} · ${esc(it.uom)}</div>
     <div class="section-t">🛒 구매처별 구매단가 <span class="muted">(${buy.length}건)</span></div>${buyTbl}
     <div class="section-t">💹 매출처별 판매단가 (수출/내수) <span class="muted">(${sale.length}건)</span></div>${saleTbl}</div>`;
}

/* ===== 재고 공용 (엑셀다운로드 / 단계별 그리드) ===== */
function downloadCSV(fname, headers, rows){
  const q=v=>{v=(v==null?'':String(v)); return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;};
  const csv='﻿'+[headers.join(',')].concat(rows.map(r=>r.map(q).join(','))).join('\r\n');
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));
  a.download=fname; document.body.appendChild(a); a.click(); a.remove();
}
function stockGrid(c, opt){
  const pool=DB.stock.filter(r=>r.stage===opt.stage);
  const lines= opt.showLine? [...new Set(pool.map(r=>r.loc).filter(Boolean))].sort():[];
  c.innerHTML=`
   <div class="page-title">${opt.title}</div><div class="page-sub">${opt.sub}</div>
   <div class="toolbar">
     <input class="inp" id="q" placeholder="품목코드 / 품명">
     <select class="sel" id="type"><option value="">전체유형</option>${Object.entries(TYPE_NM).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>
     ${opt.showLine?`<select class="sel" id="line"><option value="">전체라인</option>${lines.map(l=>`<option value="${esc(l)}">${esc(lineName(l))}</option>`).join('')}</select>`:''}
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
     <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
   </div>
   <div class="summary-bar" id="sum"></div>
   <div class="grid-wrap" style="max-height:540px"><table class="tbl"><thead><tr>
     <th>품목코드</th><th>품명</th><th>유형</th>${opt.showLine?'<th class="center">라인</th>':''}
     <th class="num">재고수량</th><th class="center">단위</th><th class="num">단가</th><th class="num">재고금액</th><th>최종입고일</th>
   </tr></thead><tbody id="body"></tbody></table></div><div class="rowcount" id="cnt"></div>`;
  let cur=[];
  const render=rows=>{cur=rows;
    c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr>
      <td><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td>
      ${opt.showLine?`<td class="center">${esc(lineName(r.loc))||'-'}</td>`:''}
      <td class="num qty">${won(r.qty)}</td><td class="center">${esc(r.uom)}</td>
      <td class="num">${won(r.cost)}</td><td class="num"><b>${won(r.amt)}</b></td><td>${esc(r.lastin)||'-'}</td></tr>`).join('')
      :`<tr><td colspan="9" class="empty">결과 없음</td></tr>`;
    const qty=rows.reduce((a,b)=>a+(+b.qty||0),0), amt=rows.reduce((a,b)=>a+(+b.amt||0),0);
    c.querySelector('#sum').innerHTML=`<div class="s-item">품목수 <b>${won(rows.length)}</b></div>
      <div class="s-item">재고수량 합계 <b>${won(qty)}</b></div>
      <div class="s-item ${amt<0?'neg':''}">재고금액 합계 <b>${won(amt)} 원</b></div>`;
    c.querySelector('#cnt').textContent=`${rows.length}건 표시 / 대상 ${pool.length}건`;};
  const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),t=c.querySelector('#type').value,
      ln=opt.showLine?c.querySelector('#line').value:'';
    render(pool.filter(r=>(!t||r.type===t)&&(!ln||r.loc===ln)&&(!q||r.cd.toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
  c.querySelector('#go').onclick=apply;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
  c.querySelector('#type').onchange=apply; if(opt.showLine)c.querySelector('#line').onchange=apply;
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#type').value='';if(opt.showLine)c.querySelector('#line').value='';apply();};
  c.querySelector('#xls').onclick=()=>downloadCSV(opt.title.replace(/[\s()]/g,'')+'.csv',
     ['품목코드','품명','유형',...(opt.showLine?['라인']:[]),'재고수량','단위','단가','재고금액','최종입고일'],
     cur.map(r=>[r.cd,r.nm,TYPE_NM[r.type]||r.type,...(opt.showLine?[lineName(r.loc)]:[]),r.qty,r.uom,r.cost,r.amt,r.lastin]));
  render(pool);
  enableSort(c,['cd','nm','type',...(opt.showLine?['loc']:[]),'qty','uom','cost','amt','lastin'],()=>cur,render);
}
const _DEMO_unifybom_UNUSED=(c)=>{
  const M={
    part:{code:'AJR75563402',name:'Tube Assembly, Manifold',cust:'LG전자',unit:'EA'},
    subParts:[
      {code:'MJU64794201',name:'Tube Connector',spec:'Ø6.35×0.70×176 CU',sagub:0,qty:1,cost:457,routes:['내부용','명진','미래','태국']},
      {code:'MJU64794202',name:'Tube Connector',spec:'Ø6.35×0.70×178 CU',sagub:0,qty:1,cost:421,routes:['내부용','명진','미래','태국']},
      {code:'MJU64794302',name:'Tube Connector',spec:'Ø9.52×0.70×167 CU',sagub:0,qty:1,cost:637,routes:['내부용','명진','미래','태국']},
      {code:'5210A22409B',name:'Tube,Connector',spec:'Ø9.52×0.70×27 CU',sagub:1,qty:1,cost:121,routes:['내부용','명진','미래','태국']},
      {code:'3H02717A',name:'COUPLING',spec:'Ø15.88×1.00×42 CU',sagub:1,qty:1,cost:458,routes:['내부용','명진','미래','태국']},
      {code:'3A00375E',name:'SOCKET(Ø12.7)',spec:'Ø12.7',sagub:0,qty:1,cost:1059,routes:['태국'],opt:'태국 경로만'},
      {code:'RAC30599327',name:'3% 용접봉',spec:'BCup-3S 2.4*700',sagub:0,qty:0.0015,cost:96600,unit:'KG',routes:['내부용','태국'],opt:'자체·태국'},
      {code:'RAC30599301-1',name:'1% 용접봉',spec:'1.8*3.8*700',sagub:0,qty:0.0048,cost:60000,unit:'KG',routes:['내부용','명진','미래','태국']},
    ],
    kit:[
      {code:'5410A30279K',name:'Insulator',qty:1,cost:97,tag:'키팅'},
      {code:'4930A20053B',name:'Holder,Sensor',qty:1,cost:35,tag:'키팅'},
      {code:'RAC30599301-1',name:'1% 용접봉 (각봉)',qty:0.0048,cost:60000,unit:'KG',tag:'부자재'},
    ],
    profiles:[
      {id:'내부용',name:'내부용',type:'자체생산',vendor:'PNC',vcode:'',partner:'없음',pnc:'절삭·은납·체결·포장',lme:false,pur:null,legacy:'-은납',cls:'self',
       split:[{who:'PNC',pct:100,lab:'절삭·은납·체결·포장'}], scope:['절삭','은납','체결포장']},
      {id:'태국',name:'태국 F&T',type:'매입(수입)',vendor:'FONE THAI',vcode:'2337',partner:'커넥터~은납',pnc:'체결·포장',lme:false,pur:4559,legacy:'-F&T',cls:'buy',active:true,
       split:[{who:'협력사',pct:72,lab:'커넥터~은납'},{who:'PNC',pct:28,lab:'체결·포장'}], scope:['체결포장']},
    ],
    proc:{ // PNC 조립공정 실측(공수) — 그룹별
      은납:[{p:'ACS 너트체결기',st:6},{p:'CAP삽입',st:4}],
      체결포장:[{p:'교정-황동',st:25},{p:'클립',st:4},{p:'원형폼피',st:3.32},{p:'포장1-일반BOX',st:3.34},{p:'품번 라벨부착',st:3}],
      절삭:[{p:'컷팅·면취·딤플·후레아·은납 (커넥터 제작)',st:null}],
    },
    labor:20776,
  };
  const f=n=>(n===''||n==null)?'':Number(n).toLocaleString('ko-KR');
  const clsChip={self:'background:#e8f0f9;color:#2f6db3;border:1px solid #2f6db3',sagub:'background:#f7edd7;color:#b6791b;border:1px solid #b6791b',buy:'background:#e0f1ee;color:#1f8a7a;border:1px solid #1f8a7a'};
  const partsOf=pid=>M.subParts.filter(p=>p.routes.includes(pid));
  const subMatOf=pid=>Math.round(partsOf(pid).reduce((s,p)=>s+p.qty*p.cost,0));
  const subCostOf=P=>P.pur!=null?P.pur:subMatOf(P.id);      // 서브 조달원가: 매입=pur, 자체=재료전개
  const kitMat=Math.round(M.kit.reduce((s,t)=>s+t.qty*t.cost,0));
  const pncST=P=>P.scope.reduce((s,g)=>s+(M.proc[g]||[]).reduce((a,x)=>a+(x.st||0),0),0);
  let pid='태국', pno='AJR75563402', pnm='', bdate='2026-07-19';
  const draw=()=>{
    const P=M.profiles.find(x=>x.id===pid);
    const parts=partsOf(pid);
    const subCost=subCostOf(P);
    const purchased=P.pur!=null;
    const total=subCost+kitMat;                              // (가공비·간접·LME는 별도 표기)
    // BOM 전개
    const rows=[{lv:0,code:M.part.code,name:M.part.name,spec:'완제품',sagub:0,qty:'',dg:'',price:'',amt:total,head:1}];
    rows.push({lv:1,code:'◆ 서브조립',name:'Tube Connector 서브조립',spec:P.vendor,sagub:0,qty:1,
      dg:purchased?(P.type+' · 매입'):'자체 · 공정전개',price:purchased?P.pur:'',amt:subCost,sub:1});
    parts.forEach(p=>rows.push({lv:2,code:p.code,name:p.name,spec:p.spec,sagub:p.sagub,qty:p.qty,
      dg:purchased?(p.sagub?'사급(원소재)':'→ 매입에 포함'):(p.sagub?'사급':(p.unit==='KG'?'부자재':'소재/구매')),
      price:p.cost,amt:Math.round(p.qty*p.cost),muted:purchased&&!p.sagub}));
    M.kit.forEach(t=>rows.push({lv:1,code:t.code,name:t.name,spec:'',sagub:0,qty:t.qty,dg:t.tag,price:t.cost,amt:Math.round(t.qty*t.cost)}));

    c.innerHTML=`
     <div class="page-title">🔀 통합 BOM (${esc(M.part.code)})</div>
     <div class="page-sub"><b>품번 1개</b> + 원가구분(내부용 / 실원가=태국 F&T)으로 전환 · 현재 BOM에 물린 서브(태국 F&T active)와 내부용 대조용 · PARTNER_ERP 실측 단가</div>
     <div class="toolbar">
       <label class="tl">PART-NO</label><input class="inp" id="q_pno" value="${esc(pno)}" style="width:150px">
       <label class="tl">품명</label><input class="inp" id="q_pnm" value="${esc(pnm)}" placeholder="품명 검색" style="width:150px">
       <label class="tl">단가기준일</label><input class="inp" type="date" id="q_bd" value="${esc(bdate)}" style="width:150px">
       <button class="btn" id="q_go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">단가 기준일 <b>${esc(bdate)}</b> 적용</span></div>
     <div class="summary-bar">
       <div class="s-item"><span>품번</span><b>${esc(M.part.code)}</b></div>
       <div class="s-item"><span>품명</span><b>${esc(M.part.name)}</b></div>
       <div class="s-item"><span>고객</span><b>${esc(M.part.cust)}</b></div>
       <div class="s-item"><span>프로파일</span><b>${M.profiles.length}</b></div>
       <div class="s-item"><span>서브 조달원가</span><b>${f(subCost)} 원</b></div>
     </div>
     <div class="toolbar"><span class="rowcount">선택 <b style="color:var(--brand,#2a6df4)">${esc(P.name)}</b> · 구(舊) <b style="color:var(--danger)">${esc(P.legacy)}</b>${P.active?' · <b style="color:#1f8a7a">현재 BOM active</b>':''} <span style="color:var(--muted)">— 오른쪽 「원가구분·조달처」 표에서 클릭하여 전환</span></span></div>
     <div class="page-sub" style="margin:2px 0 12px;padding:9px 13px;background:#f7f9ff;border:1px solid #dbe4ff;border-radius:7px;display:flex;gap:14px;flex-wrap:wrap;align-items:center">
       <span class="badge" style="${clsChip[P.cls]}">${esc(P.type)}</span>
       <span><b>공급원</b> ${esc(P.vendor)}${P.vcode?` (${esc(P.vcode)})`:''}</span>
       <span><b>협력사 공정</b> ${esc(P.partner)}</span>
       <span><b>PNC 공정</b> ${esc(P.pnc)}</span>
       ${P.sagub?`<span><b>사급</b> ${esc(P.sagub)}</span>`:''}
       <span><b>LME</b> ${P.lme?'<span class="badge" style="background:#f6ede2;color:#b06a2c;border:1px solid #b06a2c">대상</span>':'무관'}</span>
       ${P.pur!=null?`<span><b>매입</b> ${f(P.pur)}원</span>`:'<span><b>자체</b> 공정전개</span>'}</div>

     <div style="display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap">
       <div style="flex:1 1 540px;min-width:0">
         <div style="font-weight:700;margin-bottom:6px">BOM 전개 <span style="color:var(--muted);font-weight:400;font-size:12px">(${esc(P.name)})</span></div>
         <div class="grid-wrap"><table class="tbl fit"><thead><tr><th>레벨</th><th>품번</th><th>품명</th><th>규격</th><th class="center">사급</th><th class="right">소요량</th><th>조달구분</th><th class="right">단가</th><th class="right">금액</th></tr></thead><tbody>
           ${rows.map(r=>`<tr style="${r.head?'background:#eef4ff;font-weight:700':r.sub?'background:#fafbff;font-weight:600':r.muted?'color:#aaa':''}">
             <td class="center">${r.head?'0':r.lv}</td>
             <td style="padding-left:${8+r.lv*16}px;${r.sub?'color:#b06a2c':''}">${esc(r.code)}</td>
             <td>${esc(r.name)}</td><td style="color:var(--muted);font-size:12px">${esc(r.spec)}</td>
             <td class="center">${r.sagub?'<span class="badge" style="background:#f7edd7;color:#b6791b;border:1px solid #b6791b">사급</span>':''}</td>
             <td class="right">${r.qty===''?'':r.qty}</td>
             <td style="font-size:12px;color:${r.muted?'#bbb':'var(--muted)'}">${esc(r.dg)}</td>
             <td class="right">${f(r.price)}</td><td class="right">${f(r.amt)}</td></tr>`).join('')}
         </tbody></table></div>
         <div style="font-weight:700;margin:14px 0 6px">공정 분담 <span style="color:var(--muted);font-weight:400;font-size:12px">(협력사 / PNC)</span></div>
         <div style="display:flex;height:30px;border-radius:6px;overflow:hidden;border:1px solid var(--line)">
           ${P.split.map(s=>`<div style="flex:${s.pct};display:flex;align-items:center;justify-content:center;font-size:11.5px;font-weight:600;color:#fff;background:${s.who==='PNC'?'#b06a2c':'#5b6672'};white-space:nowrap;padding:0 6px">${esc(s.who)} : ${esc(s.lab)}</div>`).join('')}
         </div>
         <div style="font-weight:700;margin:14px 0 6px">PNC 수행공정 <span style="color:var(--muted);font-weight:400;font-size:12px">(조립 공수 실측 · 임율 ${f(M.labor)})</span></div>
         <div class="grid-wrap"><table class="tbl fit"><thead><tr><th>구분</th><th>공정</th><th class="right">공수(ST)</th></tr></thead><tbody>
           ${P.scope.map(g=>(M.proc[g]||[]).map((x,i)=>`<tr><td>${i===0?`<b>${esc(g)}</b>`:''}</td><td>${esc(x.p)}</td><td class="right">${x.st==null?'UPH별도':x.st}</td></tr>`).join('')).join('')}
           <tr style="background:#fafbff;font-weight:700"><td colspan="2">PNC 조립 공수 합</td><td class="right">${pncST(P).toFixed(2)}</td></tr>
         </tbody></table></div>
       </div>

       <div style="flex:0 0 400px;width:400px">
         <div style="font-weight:700;margin-bottom:6px">원가 구성 <span style="color:var(--muted);font-weight:400;font-size:12px">(${esc(P.name)})</span></div>
         <div class="grid-wrap"><table class="tbl fit"><tbody>
           <tr><td>서브 조달원가</td><td class="right">${f(subCost)}${P.pur==null?' <span style="color:#bbb;font-size:11px">재료전개</span>':' <span style="color:#bbb;font-size:11px">매입</span>'}</td></tr>
           <tr><td>키팅·부자재</td><td class="right">${f(kitMat)}</td></tr>
           <tr><td>PNC 가공비</td><td class="right">공수 ${pncST(P).toFixed(2)} × 임율</td></tr>
           <tr><td>LME 차액</td><td class="right">${P.lme?'대상 (LG인증가−협력사가)':'무관'}</td></tr>
           <tr style="background:#eef4ff;font-weight:700"><td>실원가</td><td class="right">재료+가공비+간접+이윤${P.lme?'±LME':''}</td></tr>
         </tbody></table></div>
         <div class="page-sub" style="margin-top:6px">실원가 = 재료비 + 가공비(PNC 담당공정) + 일반관리 + 이윤 ${P.lme?'± LME차액':''} · 손익 = LG단가 − 실원가</div>

         <div style="font-weight:700;margin:14px 0 6px">프로파일 비교</div>
         <div class="grid-wrap"><table class="tbl fit"><thead><tr><th>프로파일</th><th>공급구분</th><th class="center">부품</th><th class="right">서브조달</th><th>LME</th></tr></thead><tbody>
           ${M.profiles.map(p=>{const sc=subCostOf(p);return `<tr style="${pid===p.id?'background:#eef4ff;font-weight:600':''};cursor:pointer" data-cmp="${esc(p.id)}">
             <td>${esc(p.name)} <span style="color:#ccc;font-size:11px">${esc(p.legacy)}</span></td>
             <td><span class="badge" style="${clsChip[p.cls]};font-size:10.5px">${esc(p.type)}</span></td>
             <td class="center">${partsOf(p.id).length}</td>
             <td class="right"><b>${f(sc)}</b>${p.pur==null?'<span style="color:#bbb;font-size:10px"> 전개</span>':''}</td>
             <td>${p.lme?'대상':'무관'}</td></tr>`;}).join('')}
         </tbody></table></div>
         <div class="page-sub" style="margin-top:8px;padding:9px 12px;background:#fff8ec;border:1px solid #f2e2bf;border-radius:6px">
           <b>은납</b>은 형제 경로가 아니라 <b>완제품 최종조립(PNC 자체)</b> — 협력사는 inner 서브(커넥터~은납)를 대고, <b>PNC가 체결·포장</b>. 태국은 은납까지 협력사, 나머지 PNC.</div>
       </div>
     </div>`;
    c.querySelectorAll('[data-cmp]').forEach(tr=>tr.onclick=()=>{pid=tr.dataset.cmp;draw();});
    const go=()=>{const v=(c.querySelector('#q_pno').value||'').trim().toUpperCase();
      pnm=c.querySelector('#q_pnm').value||''; bdate=c.querySelector('#q_bd').value||bdate;
      if(v&&v!=='AJR75563402'){alert('시연 데이터는 AJR75563402만 준비돼 있습니다.\n(다른 품목은 대표 BOM 이관 방식으로 확장 예정)');}
      pno='AJR75563402'; draw();};
    c.querySelector('#q_go').onclick=go;
    c.querySelector('#q_pno').onkeyup=e=>{if(e.key==='Enter')go();};
    c.querySelector('#q_pnm').onkeyup=e=>{if(e.key==='Enter')go();};
  };
  draw();
};
const _C39={"0":"nnnwwnwnn","1":"wnnwnnnnw","2":"nnwwnnnnw","3":"wnwwnnnnn","4":"nnnwwnnnw","5":"wnnwwnnnn","6":"nnwwwnnnn","7":"nnnwnnwnw","8":"wnnwnnwnn","9":"nnwwnnwnn","A":"wnnnnwnnw","B":"nnwnnwnnw","C":"wnwnnwnnn","D":"nnnnwwnnw","E":"wnnnwwnnn","F":"nnwnwwnnn","G":"nnnnnwwnw","H":"wnnnnwwnn","I":"nnwnnwwnn","J":"nnnnwwwnn","K":"wnnnnnnww","L":"nnwnnnnww","M":"wnwnnnnwn","N":"nnnnwnnww","O":"wnnnwnnwn","P":"nnwnwnnwn","Q":"nnnnnnwww","R":"wnnnnnwwn","S":"nnwnnnwwn","T":"nnnnwnwwn","U":"wwnnnnnnw","V":"nwwnnnnnw","W":"wwwnnnnnn","X":"nwnnwnnnw","Y":"wwnnwnnnn","Z":"nwwnwnnnn","-":"nwnnnnwnw",".":"wwnnnnwnn"," ":"nwwnnnwnn","*":"nwnnwnwnn"};
function _barcodeDataURL(text){
  text=String(text||"").toUpperCase().replace(/[^0-9A-Z\-. ]/g,"");
  const data="*"+text+"*",nw=2,wide=5,h=54,gap=nw;
  let total=8;for(const ch of data){const p=_C39[ch]||_C39["*"];for(const e of p)total+=(e==="w"?wide:nw);total+=gap;}
  const cv=document.createElement("canvas");cv.width=Math.ceil(total);cv.height=h+4;
  const x0=cv.getContext("2d");x0.fillStyle="#fff";x0.fillRect(0,0,cv.width,cv.height);x0.fillStyle="#000";
  let x=4;for(const ch of data){const p=_C39[ch]||_C39["*"];for(let i=0;i<9;i++){const w=(p[i]==="w"?wide:nw);if(i%2===0)x0.fillRect(x,2,w,h);x+=w;}x+=gap;}
  return cv.toDataURL();
}

/* ==== 자재 재고 3화면(조정·입고·출고) = 동일 원장(nx.stock_ledger), 백엔드 가드(마감월·FK·재고부족) ==== */
const STOCK_API=API_BASE;
const STOCK_CFG={
  stockadjust:{key:'adjust',ic:'🛠️',nm:'자재개별재고조정',signed:true,
    tags:[['1','불량(−)'],['2','장부수정(±)'],['3','기초재고'],['A','개발불출(−)']],
    sub:'장부수정·불량·기초재고·개발불출 등 개별 재고 증감을 등록합니다. <b>수량은 부호 입력</b>(증가 +, 감소 −). 가드: 마감월 잠금·미등록품목·음수재고 차단.'},
  stockreceipt:{key:'receipt',ic:'📥',nm:'자재입고관리',retn:true,rettags:[['RT','반품(−)']],
    tags:[['9','개별입고'],['S','세트입고'],['C','가공입고'],['G','축관입고'],['H','5팀입고']],
    sub:'가공·세트·축관 등 자재 입고를 등록합니다(＋). 가드: 마감월 잠금·미등록품목 차단.',
    retsub:'입고된 부품을 반품합니다(−). 가드: 반품수량 ≤ 현재고(다음공정 이동분은 이미 재고감소 → 반품 불가, 마이너스 재고 방지).'},
  stockissue:{key:'issue',ic:'📤',nm:'자재출고관리',neg:true,
    tags:[['4','생산사용']],
    sub:'생산사용 등 자재 출고를 등록합니다(−, 수량은 양수 입력). 가드: 마감월 잠금·재고부족 차단.'},
};
const _nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
const _toYMD=v=>v?v.slice(2).replace(/-/g,''):'';        // 2026-07-21 → 260721
const _fmtY=y=>{y=''+(y||'');return y.length>=6?`${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:y;};
// ★등록자/갱신자 = 로그인 사용자 **이름**(레거시가 실명을 남김). 못 얻으면 'web' 폴백.
const _curUserNm=()=>{try{return (PERM.currentUser().nm||'').trim()||'web';}catch(e){return 'web';}};
// 등록시각 표시(2026-08-28 09:08 → 08-28 09:08)
const _fmtDT=v=>{v=String(v||'').replace('T',' ');return v?v.slice(5,16):'';};

/* ══ 자재개별일괄입고 팝업 (레거시 w_pu_stock_057) ══════════════════════════
   ★수동입고 전용. 발주 연동 없음(개별자재 발주기능 미사용 — 2026-08-28 사용자 확정).
   레거시 동작을 그대로:
     · 행추가 = 100행씩 증가, **입력된 행만 저장**(빈행은 무시)
     · 자도번 입력 → 품명·규격·단위·현재고 자동 추적(배치 API /api/stock/matinfo)
     · 엑셀 붙여넣기 지원 — 자도번칸에 Ctrl+V 하면 여러 행/열을 그대로 채운다
   ★모달은 document.body 에 렌더(CLAUDE.md §3 — .content 안에 넣으면 잘림).      */
/* ══ 자재개별입고 수정 팝업 (레거시 w_pu_stock_055) ═══════════════════════
   ★한 건씩 단일 폼. 목록에서 행을 고르면 그 행만 열어 수정/삭제한다.
   레거시 실물 필드(2026-08-28 사용자 제공):
     수정일자 · 수정SEQ(+그룹SEQ) / 거래처 / 자도번 · 직납구분 / 입고창고 · 검사구분
     입고구분 · 검사처리일 / 수량 · 단가(MASTER단가) / 금액 · 부가세 / 비고
     납품서순번 · 품목구분 / 납품서바코드 · 발주수량 / 세트입고구분 · 입고수량
     세트입고순번 · 취소수량 / 갱신내역(수정자·시각)
   ·◀이전 ▶다음 = 같은 조회목록 안에서 행 이동(레거시 동일)
   ·단가는 읽기전용(CLAUDE.md §1-2 — 마감 화면 외 단가 편집 금지). MASTER단가만 표시.   */
function openMatEditPopup(opt){
  const API=API_BASE, list=opt.rows||[], onSaved=opt.onSaved||(()=>{});
  // ★mode: 'edit'=수정 / 'del'=삭제. 레거시는 **같은 창**을 제목·버튼만 바꿔 쓴다
  //   (수정: 저장·삭제 / 삭제: 삭제만, 입력칸 잠금).
  const MODE=(opt.mode==='del')?'del':'edit', DEL=(MODE==='del');
  // ★단가 수정 권한(2026-08-28) — 사용자 요청으로 **현재는 전원 개방**.
  //   나중에 별도 권한을 만들면 여기 한 곳만 바꾸면 된다:
  //     예) PERM.canEditCost && PERM.canEditCost('stockreceipt')
  //   CLAUDE.md §1-2(단가는 마감 때만) 의 예외 지점이므로 이 플래그로 명시적으로 관리한다.
  const CAN_COST=(typeof PERM!=='undefined'&&PERM.canEditCost)?PERM.canEditCost('stockreceipt'):true;
  let idx=Math.max(0,opt.index|0), busy=false, master=null;
  const pad=n=>String(n).padStart(2,'0');
  const y2d=y=>{y=''+(y||'');return y.length>=6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';};
  const TAGN={'9':'개별입고','S':'세트입고','C':'가공입고','G':'축관입고','H':'5팀입고',
              'RT':'반품','2':'장부수정','4':'생산사용','5':'협력사 매출출고'};
  let f={};                                            // 편집중 값
  const cur=()=>list[idx]||{};
  const load=()=>{const r=cur();
    f={qty:Math.abs(Number(r.qty||0)), rmk:r.REMARKS||'', cust:(r.CUST_CODE||'').trim(),
       custnm:r.cust_name||'', wh:(r.GAGONG_PROC_CODE||'').trim(),
       cost:Number(r.MAINT_COST||0)};
    master=null;};
  load();

  const ov=document.createElement('div');
  ov.style.cssText='position:fixed;inset:0;z-index:1310;background:rgba(20,30,48,.45);display:flex;align-items:center;justify-content:center';
  document.body.appendChild(ov);
  const close=()=>ov.remove();
  ov.onclick=e=>{if(e.target===ov&&!busy)close();};

  const row=(l1,v1,l2,v2)=>`<tr><th>${l1}</th><td>${v1}</td>${l2!==undefined?`<th>${l2}</th><td>${v2}</td>`:'<th></th><td></td>'}</tr>`;
  const ro=v=>`<span class="mev-ro">${esc(v==null||v===''?'':v)}</span>`;

  const draw=()=>{
    const r=cur(), amt=Number(f.qty||0)*Number(f.cost||0);
    const dis=DEL?'disabled':'';                       // 삭제모드=입력 잠금
    const upd=(r.UPDATE_USER_ID||r.INSERT_USER_ID||'')+'　'+
              String(r.UPDATE_DATETIME||r.INSERT_DATETIME||'').replace('T',' ').slice(0,19);
    ov.innerHTML=`
     <div class="mev ${DEL?'mev-del':''}">
       <div class="mev-h"><span>${DEL?'🗑 자재개별입고수정 — 삭 제':'✎ 자재개별입고수정 — 수 정'}</span><span class="mev-x" id="me-x">✕</span></div>
       <div class="mev-b">
        <table class="mev-t">
         ${row('수정일자', ro(y2d(r.MAINT_YMD)), '수정SEQ', ro(r.MAINT_SEQ)+' <span class="mut">'+esc(r.MAINT_GROUP_SEQ||'')+'</span>')}
         ${row('거래처', `<input class="inp" id="me-cust" list="me-cdl" value="${esc(f.custnm||f.cust)}" placeholder="거래처명" autocomplete="off" style="width:230px" ${dis}><datalist id="me-cdl"></datalist>`, '', '')}
         ${row('자도번', ro(r.MAT_CODE)+' <span class="mut">'+esc(r.item_name||'')+'</span>', '직납구분', ro(r.DIRECT_ITEM_FLAG||'0'))}
         ${row('입고창고', `<select class="inp" id="me-wh" style="width:180px" ${dis}>${(opt.whs||[]).length?(opt.whs||[]).map(w=>`<option value="${esc(w.wh)}" ${w.wh===f.wh?'selected':''}>${esc(w.wh)} ${esc(w.nm||'')}</option>`).join(''):`<option value="${esc(f.wh)}">${esc(f.wh||'(없음)')}</option>`}</select>`,
                '검사구분', ro(({'F':'유검사','S':'체크검사'})[(r.INSP_FLAG||'').trim()]||'무검사'))}
         ${row('입고구분', ro(TAGN[(r.MAINT_TAG||'').trim()]||r.MAINT_TAG), '검사처리일', ro(y2d(r.INSP_PROC_YMD)||'/  /'))}
         ${row('수량', `<input class="inp" id="me-qty" type="number" step="any" min="0" value="${esc(f.qty)}" style="width:140px;text-align:right" ${dis}>`,
                '단가', `<input class="inp" id="me-cost" type="number" step="any" min="0" value="${esc(f.cost)}" style="width:110px;text-align:right" ${CAN_COST?dis:'disabled'}>`
                       +` <button class="btn ghost mev-mst" id="me-mst" title="품목 마스터 단가를 불러옵니다" ${CAN_COST?dis:'disabled'}>MASTER단가</button>`)}
         ${row('금액', `<span class="mev-ro" id="me-amt">${_nf(amt)}</span>`, '부가세', `<span class="mev-ro" id="me-vat">${_nf(Math.round(amt*0.1))}</span>`)}
         <tr><th>비 고</th><td colspan="3"><input class="inp" id="me-rmk" value="${esc(f.rmk)}" style="width:100%" ${dis}></td></tr>
         ${row('납품서순번', ro(r.SHEET_NO||''), '품목구분', ro(r.ITEM_GUBUN||''))}
         ${row('납품서바코드', ro(''), '발주수량', ro(''))}
         ${row('세트입고구분', ro(r.SET_MAINT_YMD?'세트':''), '입고수량', ro(_nf(Math.abs(Number(r.qty||0)))))}
         ${row('세트입고순번', ro(r.SET_MAINT_SEQ||''), '취소수량', ro(''))}
         <tr><th>갱신내역</th><td colspan="3">${ro(upd)}</td></tr>
        </table>
       </div>
       <div class="mev-f">
         <button class="btn ghost" id="me-prev" ${idx<=0?'disabled':''}>◀ 이전</button>
         <span class="mut" style="font-size:12px">${idx+1} / ${list.length}</span>
         <button class="btn ghost" id="me-next" ${idx>=list.length-1?'disabled':''}>다음 ▶</button>
         <div class="spacer"></div>
         ${DEL
           ?`<button class="btn" id="me-del" style="background:#c0392b;color:#fff" ${busy?'disabled':''}>🗑 삭제</button>`
           :`<button class="btn ghost" id="me-del" style="color:#c0392b;border-color:#e2b6b0">🗑 삭제</button>
             <button class="btn" id="me-save" style="background:#1c7c3a;color:#fff" ${busy?'disabled':''}>✔ 저장</button>`}
         <button class="btn ghost" id="me-close">✖ 닫기</button>
       </div>
     </div>
     <style>
      .mev{background:#fff;border-radius:10px;box-shadow:0 12px 40px rgba(20,30,48,.35);width:min(700px,96vw);display:flex;flex-direction:column;overflow:hidden}
      .mev-h{display:flex;align-items:center;justify-content:space-between;padding:9px 14px;background:#1c47a0;color:#fff;font-weight:700;font-size:14px}
      .mev-x{cursor:pointer;opacity:.85}.mev-x:hover{opacity:1}
      .mev-b{padding:14px 16px}
      .mev-t{width:100%;border-collapse:collapse;font-size:12.5px}
      .mev-t th{width:88px;text-align:center;background:#eef3fb;color:#24406e;font-weight:700;
                border:1px solid #c9d3e0;padding:5px 6px;white-space:nowrap}
      .mev-t td{border:1px solid #c9d3e0;padding:4px 8px}
      .mev-ro{display:inline-block;color:#1a2b45;font-weight:600}
      .mev-tag{display:inline-block;margin-left:6px;padding:1px 6px;border-radius:4px;background:#eef4ff;color:#2f5aa8;font-size:10.5px;font-weight:600}
      .mev-mst{margin-left:4px;padding:2px 7px;font-size:10.5px;min-width:0}
      .mev-f{display:flex;align-items:center;gap:6px;padding:10px 14px;border-top:1px solid #c9d3e0;background:#f7f9fd}
     </style>`;
    const g=id=>ov.querySelector(id);
    g('#me-x').onclick=g('#me-close').onclick=close;
    g('#me-prev').onclick=()=>{if(idx>0){idx--;load();draw();}};
    g('#me-next').onclick=()=>{if(idx<list.length-1){idx++;load();draw();}};
    // 금액·부가세는 전체 재렌더 없이 갱신(입력 포커스 유지)
    const calc=()=>{const a=Number(f.qty||0)*Number(f.cost||0);
      const ea=g('#me-amt'), ev=g('#me-vat');
      if(ea)ea.textContent=_nf(a);
      if(ev)ev.textContent=_nf(Math.round(a*0.1));};
    g('#me-qty').oninput=e=>{f.qty=e.target.value;calc();};
    const ec=g('#me-cost');if(ec)ec.oninput=e=>{f.cost=e.target.value;calc();};
    // MASTER단가 = 품목 마스터의 매입단가를 끌어온다
    const em=g('#me-mst');
    if(em)em.onclick=async()=>{
      const mat=(cur().MAT_CODE||'').trim();
      if(!mat)return;
      em.disabled=true;const t0=em.textContent;em.textContent='조회중…';
      try{const j=await (await fetch(`${API}/api/stock/mastercost?mat=${encodeURIComponent(mat)}`)).json();
        if(j.cost==null){alert('마스터 단가가 없습니다.');}
        else{f.cost=j.cost;const el=g('#me-cost');if(el)el.value=j.cost;calc();}
      }catch(e){alert('마스터단가 조회 실패: '+e.message);}
      em.textContent=t0;em.disabled=false;};
    g('#me-rmk').oninput=e=>{f.rmk=e.target.value;};
    g('#me-wh').onchange=e=>{f.wh=e.target.value;};
    let ct=null, cmap={};
    const ci=g('#me-cust');
    ci.oninput=()=>{f.custnm=ci.value;f.cust=cmap[ci.value.toLowerCase()]||f.cust;
      clearTimeout(ct);const v=ci.value.trim();if(!v)return;
      ct=setTimeout(async()=>{try{const rr=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(v)}`);
        const dl=g('#me-cdl');
        if(dl)dl.innerHTML=((await rr.json()).rows||[]).map(x=>{cmap[(x.name||'').toLowerCase()]=x.code;
          return `<option value="${esc(x.name||'')}">${esc(x.code||'')}</option>`;}).join('');}catch(e){}},220);};
    // ★삭제모드에는 #me-save 가 렌더되지 않는다(1275~1278). 종전엔 무조건 참조해
    //   null.onclick 에서 TypeError 가 나고 **그 다음 줄(#me-del 바인딩)이 실행되지 않아**
    //   삭제 버튼이 먹지 않았다(2026-08-31 실사용 버그).
    const _sv=g('#me-save');if(_sv)_sv.onclick=save;
    const _dl=g('#me-del');if(_dl)_dl.onclick=del;
  };

  async function save(){
    if(busy)return;
    const r=cur(), q=Number(f.qty||0);
    if(!(q>0)){alert('수량은 0보다 커야 합니다.');return;}
    busy=true;draw();
    try{
      const body={screen:'receipt', user:_curUserNm(),
        MAINT_YMD:r.MAINT_YMD, MAINT_SEQ:r.MAINT_SEQ,
        MAINT_TAG:(r.MAINT_TAG||'').trim(), qty:q,
        CUST_CODE:f.cust||null, GAGONG_PROC_CODE:f.wh||null,
        REMARKS:(f.rmk||'').trim()||null};
      // 단가는 권한 있을 때만 전송(미전송 시 백엔드가 기존값 유지)
      if(CAN_COST)body.MAINT_COST=Number(f.cost||0);
      const rr=await fetch(`${API}/api/stock/update`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await rr.json();
      if(!j.ok){alert('수정 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));busy=false;draw();return;}
      alert('✅ 수정 완료 (재고 반영)');close();onSaved();
    }catch(e){alert('수정 실패: '+e.message);busy=false;draw();}
  }
  async function del(){
    if(busy)return;
    const r=cur();
    if(!confirm(`이 입고를 삭제할까요?\n${r.MAT_CODE} · ${_fmtY(r.MAINT_YMD)} · 수량 ${_nf(r.qty)}\n\n재고가 되돌려집니다.`))return;
    busy=true;draw();
    try{
      const rr=await fetch(`${API}/api/stock/delete`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({screen:'receipt',MAINT_YMD:r.MAINT_YMD,MAINT_SEQ:r.MAINT_SEQ})});
      const j=await rr.json();
      if(!j.ok){alert('삭제 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));busy=false;draw();return;}
      alert('🗑 삭제 완료 (재고 반영)');close();onSaved();
    }catch(e){alert('삭제 실패: '+e.message);busy=false;draw();}
  }
  draw();
}

/* ══ 가공이동전표 바코드입고처리 (레거시 w_pu_stock_057_2) ═══════════════════
   가공이동계획(580)에서 발행한 이동전표 바코드를 읽어 **자재창고로 입고**한다.
   상단: 입고일자 ◀▶ · 입고창고 · 바코드 · 처리바코드
   그리드: SEQ · 자도번 · 품명 · 규격 · 단위 · 입고수량 · 비고 · 상위코드
   ·바코드칸에 전표(MV+MAINT_GROUP_SEQ)를 찍으면 그 전표의 미입고분이 행으로 붙는다.
   ·같은 전표를 두 번 찍으면 무시(처리바코드에 누적 표시).
   ·저장 = /api/matrecv/gagong_receive → nx.stock_ledger MAINT_TAG='C'(가공입고).      */
function openGagongMovePopup(opt){
  const API=API_BASE, onSaved=opt.onSaved||(()=>{});
  const pad=n=>String(n).padStart(2,'0');
  const isoT=(d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`)(new Date());
  const nf=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const yy=s=>s?s.slice(2).replace(/-/g,''):'';
  let ymd=opt.ymd||isoT, inWh='IS0001';
  let rows=[], done=[], busy=false, whs=[];
  let pend='', scanBc='', confirmBc='';   // pend=1회차로 올라온 전표키 · 두 칸은 레거시 barcode/confirm_barcode

  const ov=document.createElement('div');
  ov.style.cssText='position:fixed;inset:0;z-index:1300;background:rgba(20,30,48,.45);display:flex;align-items:center;justify-content:center';
  document.body.appendChild(ov);
  const close=()=>ov.remove();
  ov.onclick=e=>{if(e.target===ov&&!busy&&!rows.length)close();};

  const bodyHtml=()=>rows.length?rows.map((r,i)=>`<tr data-i="${i}">
      <td class="center mut">${i+1}</td>
      <td><b>${esc(r.MAT_CODE||'')}</b></td>
      <td class="cap" title="${esc(r.nm||'')}">${esc(r.nm||'')}</td>
      <td class="cap mut" title="${esc(r.spec||'')}">${esc(r.spec||'')}</td>
      <td class="center mut">${esc(r.unit||'')}</td>
      <td class="num"><b>${nf(r.remain)}</b></td>
      <td class="cap mut">${esc(r.GAGONG_PROC_CODE||'')} → ${esc(r.TO_GAGONG_PROC_CODE||'')}</td>
      <td class="mut">${esc(r.upper_code||'')}</td>
      <td class="center"><span class="gm-del" data-i="${i}" title="행 제거">✖</span></td>
    </tr>`).join('')
    :`<tr><td colspan="9" class="center mut" style="padding:26px">바코드칸에 <b>이동전표 바코드</b>를 찍으세요.</td></tr>`;

  const draw=()=>{
    ov.innerHTML=`
     <div class="mip">
       <div class="mip-h"><span>🔖 가공이동전표 바코드입고처리 — 등 록</span><span class="mip-x" id="gm-x">✕</span></div>
       <div class="mip-tb">
         <label class="tl">입고일자</label>
         <button class="btn ghost mip-nav" id="gm-prev" title="전일">◀</button>
         <input type="date" class="inp mip-w" id="gm-ymd" value="${ymd}" style="width:140px">
         <button class="btn ghost mip-nav" id="gm-next" title="익일">▶</button>
         <label class="tl">입고창고</label>
         <select class="inp mip-w" id="gm-wh" style="width:160px">
           ${(whs.length?whs:[{code:'IS0001',nm:'자재창고'}]).map(w=>`<option value="${esc(w.code)}" ${w.code===inWh?'selected':''}>${esc(w.code)} ${esc(w.nm||'')}</option>`).join('')}
         </select>
         <label class="tl">바코드</label>
         <input class="inp mip-w mip-ci" id="gm-bc" value="${esc(scanBc)}" placeholder="전표 바코드 스캔" autocomplete="off" style="width:190px">
         <label class="tl">처리바코드</label>
         <input class="inp mip-w" id="gm-bcd" value="${esc(confirmBc)}" readonly style="width:190px;background:#eef1f6">
       </div>
       <div class="mip-tb">
         <span class="mip-hint">💡 바코드를 <b>한 번</b> 찍으면 내역이 뜨고, <b>같은 바코드를 다시</b> 찍으면 입고확정됩니다(레거시 동일).</span>
         <div class="spacer"></div>
         <span class="rowcount" id="gm-foot">${pend?`전표 <b>${esc(scanBc||pend)}</b> · `:''}대기 <b>${rows.length}</b>행 · 수량 <b>${nf(rows.reduce((s,r)=>s+Number(r.remain||0),0))}</b>${done.length?` <span class="mut">/ 처리완료 ${done.length}건</span>`:''}</span>
       </div>
       <div class="mip-grid"><table class="tbl mip-tbl"><thead><tr>
         <th style="width:44px">SEQ</th><th style="width:170px">자도번</th><th style="width:230px">품명</th>
         <th style="width:150px">규격</th><th style="width:50px">단위</th>
         <th style="width:90px">입고수량</th><th style="width:170px">비고(이동)</th>
         <th style="width:150px">상위코드</th><th style="width:32px"></th></tr></thead>
         <tbody id="gm-tb">${bodyHtml()}</tbody></table></div>
       <div class="mip-f">
         <button class="btn ghost" id="gm-clr">✖ 목록비우기</button>
         <div class="spacer"></div>
         <span class="mut" style="font-size:12px">가드: 마감월 잠금 · 중복입고 차단</span>
         <button class="btn" id="gm-save" style="background:#0f7b6c;color:#fff" ${(busy||!rows.length)?'disabled':''}>✔ 입고확정</button>
         <button class="btn ghost" id="gm-close">✖ 닫기</button>
       </div>
     </div>
     <style>
      /* ★.mip 스타일은 openMatIssuePopup 내부에만 있어 이 팝업엔 적용되지 않았다
         → 배경이 없어 뒤 화면이 비쳐 보였다(2026-08-28 수정). 여기서 자체 정의한다. */
      .mip{background:#fff;border-radius:10px;box-shadow:0 12px 40px rgba(20,30,48,.35);
           width:min(1180px,96vw);height:min(84vh,820px);display:flex;flex-direction:column;overflow:hidden}
      .mip-h{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;
             padding:9px 14px;background:#0f7b6c;color:#fff;font-weight:700;font-size:14px}
      .mip-x{cursor:pointer;opacity:.85}.mip-x:hover{opacity:1}
      .mip-tb{flex:0 0 auto;display:flex;align-items:center;gap:6px;padding:7px 12px;flex-wrap:wrap;background:#fff}
      .mip-tb:first-of-type{border-bottom:1px solid #e6ecf5}
      .mip-tb:nth-of-type(2){border-bottom:1px solid #c9d3e0;background:#f7f9fd}
      .mip-w{min-width:0}
      .mip-nav{padding:2px 7px;min-width:0}
      .mip-ci{background:#fff8dc;border-color:#e0c97a}
      .mip-ci:focus{background:#fffdf2;border-color:#c9a227;outline:none}
      .mip-hint{color:#0f5f54;background:#e7f5f2;border-radius:6px;padding:3px 9px;font-size:11.5px}
      .mip-grid{flex:1 1 auto;min-height:0;overflow:auto;margin:0 12px;border:1px solid #c9d3e0;border-radius:6px;background:#fff}
      .mip-tbl{font-size:12px;table-layout:fixed;width:100%;background:#fff}
      .mip-tbl th,.mip-tbl td{padding:3px 5px;white-space:nowrap;border-bottom:1px solid #eef1f6}
      .mip-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2;text-align:center;border-bottom:1px solid #c9d3e0}
      .mip-tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
      .mip-tbl td.center{text-align:center}
      .mip-tbl td.mut{color:var(--muted)}.mip-tbl td.cap{overflow:hidden;text-overflow:ellipsis}
      .mip-f{flex:0 0 auto;display:flex;align-items:center;gap:6px;padding:9px 12px;border-top:1px solid #c9d3e0;background:#f7f9fd}
      .gm-del{cursor:pointer;color:#c0392b;opacity:.55}.gm-del:hover{opacity:1}
     </style>`;
    wire();
    const bi=ov.querySelector('#gm-bc'); if(bi&&!busy){bi.focus();}
  };

  // ★레거시 w_pu_stock_057_2 원문 구조(2026-08-28 PBL 실측):
  //     [바코드]     1회 스캔 → 전표 내역을 dw_data 에 올림(확인용)
  //     [처리바코드] 2회 스캔 → 이 칸에 채워지고 ue_save 실행 = 입고확정
  //   확정 시 전표번호: ll_barcode_no = long(mid(confirm_barcode, 3))  ← 앞 2자('MV') 제거
  //   저장 후 ue_save 가 두 칸을 비우고 바코드칸에 포커스 복귀(연속 스캔).
  //   'MV001313' / '001313' 둘 다 같은 전표 — 숫자만 뽑아 비교한다.
  const bcKey=v=>{const d=(''+(v||'')).replace(/\D/g,'');return d.replace(/^0+/,'')||d;};
  async function scan(v){
    v=(v||'').trim(); if(!v)return;
    const key=bcKey(v);
    if(!key){alert(`바코드를 인식할 수 없습니다: ${v}`);return;}
    if(done.includes(key)){alert(`이미 입고처리한 전표입니다: ${v}`);return;}
    // ── 2회차(=처리바코드) : 같은 전표를 다시 찍으면 입고확정 ──
    if(pend===key){
      if(!rows.length){pend='';draw();return;}
      confirmBc=v;                                    // 처리바코드칸 표시(레거시 confirm_barcode)
      await save();
      return;
    }
    // ── 1회차(=바코드) : 전표 조회해서 그리드에 올림 ──
    try{
      const r=await fetch(`${API}/api/matrecv/gagong_pending?sheet=${encodeURIComponent(key)}`);
      const j=await r.json(); const rs=j.rows||[];
      if(!rs.length){alert(`미입고 내역이 없습니다: ${v}\n(이미 입고됐거나 발행되지 않은 전표)`);return;}
      rows=rs; pend=key; scanBc=v; confirmBc='';      // 전표 단위 — 새 전표를 찍으면 교체
      draw();
    }catch(e){alert('조회 실패: '+e.message);}
  }

  function wire(){
    const g=id=>ov.querySelector(id);
    g('#gm-x').onclick=g('#gm-close').onclick=()=>{
      if(rows.length&&!confirm(`입고하지 않은 ${rows.length}행이 있습니다. 닫을까요?`))return;close();};
    g('#gm-ymd').onchange=e=>{ymd=e.target.value;};
    const shift=d=>{const t=new Date(ymd);t.setDate(t.getDate()+d);
      ymd=`${t.getFullYear()}-${pad(t.getMonth()+1)}-${pad(t.getDate())}`;draw();};
    g('#gm-prev').onclick=()=>shift(-1); g('#gm-next').onclick=()=>shift(1);
    g('#gm-wh').onchange=e=>{inWh=e.target.value;};
    const bi=g('#gm-bc');
    bi.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();const v=bi.value;bi.value='';scan(v);}};
    g('#gm-clr').onclick=()=>{if(rows.length&&!confirm('목록을 비울까요?'))return;
      rows=[];pend='';scanBc='';confirmBc='';draw();};   // ★처리이력(done)은 유지
    g('#gm-save').onclick=save;
    ov.querySelectorAll('.gm-del').forEach(el=>el.onclick=()=>{rows.splice(+el.dataset.i,1);draw();});
  }

  async function save(){
    if(busy||!rows.length)return;
    busy=true;draw();
    try{
      const body={ymd:yy(ymd), in_wh:inWh, user:_curUserNm(),
        rows:rows.map(r=>({MAINT_GROUP_SEQ:r.MAINT_GROUP_SEQ, MAT_CODE:r.MAT_CODE,
          ITEM_CODE:r.upper_code||null, qty:Number(r.remain),
          GAGONG_PROC_CODE:r.GAGONG_PROC_CODE||null,
          TO_GAGONG_PROC_CODE:inWh||r.TO_GAGONG_PROC_CODE||null}))};
      const rr=await fetch(`${API}/api/matrecv/gagong_receive`,{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await rr.json();
      if(!j.ok){
        alert('입고 거부 (백엔드 가드):\n'+((j.errors||[]).join('\n')||j.detail||'오류'));
        busy=false;confirmBc='';draw();return;}
      const n=j.count||rows.length;
      // ★레거시 ue_save 후처리: 두 칸 비우고 목록 리셋 → 바코드칸 포커스(연속 스캔)
      done.push(pend); rows=[]; pend=''; scanBc=''; confirmBc='';
      busy=false; draw();
      const ft=ov.querySelector('#gm-foot');
      if(ft)ft.innerHTML=`✅ <b>${esc(done[done.length-1])}</b> 입고완료 ${n}건 · 다음 바코드를 찍으세요`;
      onSaved();
    }catch(e){alert('입고 실패: '+e.message);busy=false;confirmBc='';draw();}
  }

  // 창고 목록 로드 후 렌더
  (async()=>{try{const j=await (await fetch(`${API}/api/stock/warehouses`)).json();
      whs=(j.rows||[]).map(x=>({code:x.wh,nm:x.nm}));}catch(e){}
    draw();})();
}

function openMatRecvPopup(opt){
  const API=API_BASE, CFG=opt.cfg||{}, onSaved=opt.onSaved||(()=>{});
  const ROWSTEP=100;                                   // 레거시: 행추가 100건씩
  const pad=n=>String(n).padStart(2,'0');
  const isoT=(d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`)(new Date());
  // ★수동 등록은 **개별입고(9) 만** 가능(2026-08-28 사용자 확정).
  //   C:가공입고 = 가공이동전표 바코드로만 생성 · S:세트입고 = 세트납품으로만 생성
  //   → 여기서 만들면 근거 없는 입고가 되므로 구분 선택 자체를 막는다(수정/삭제는 전 구분 가능).
  const TAG_NEW='9', TAG_NEW_NM='개별입고';
  // ★그룹(=입고일자) 단위 등록/수정. 레거시 057 은 「입고일자 그 하루」를 한 화면에서
  //   신규입력 + 기존행 수정·삭제까지 처리한다(2026-08-28 사용자 요청).
  let ymd=opt.ymd||isoT, wh=opt.wh||'IS0001', tag=TAG_NEW, custNm='', custCode='';
  let whs=[], rows=[], busy=false, info={}, loading=false;
  //   rows[] = 기존행(id 있음) + 신규행(id 없음) 혼재.
  const blank=()=>({mat:'',nm:'',spec:'',unit:'',stock:'',qty:'',cost:'',rmk:'',bad:0});
  const addRows=n=>{for(let i=0;i<n;i++)rows.push(blank());};
  addRows(ROWSTEP);
  const filled=()=>rows.filter(r=>(r.mat||'').trim()&&Number(r.qty)>0);

  const ov=document.createElement('div');
  ov.style.cssText='position:fixed;inset:0;z-index:1300;background:rgba(20,30,48,.45);display:flex;align-items:center;justify-content:center';
  document.body.appendChild(ov);
  const close=()=>{ov.remove();};
  ov.onclick=e=>{if(e.target===ov&&!busy&&!filled().length)close();};

  const draw=()=>{
    const nF=filled().length, sumQ=filled().reduce((s,r)=>s+Number(r.qty||0),0);
    ov.innerHTML=`
     <div class="mrp">
       <div class="mrp-h"><span>📥 자재개별일괄입고 — 등 록</span>
         <span class="mrp-x" id="mp-x" title="닫기">✕</span></div>
       <div class="mrp-tb">
         <label class="tl">입고일자</label>
         <button class="btn ghost mrp-nav" id="mp-prev" title="전일">◀</button>
         <input type="date" class="inp" id="mp-ymd" value="${ymd}" style="width:140px">
         <button class="btn ghost mrp-nav" id="mp-next" title="익일">▶</button>
         <label class="tl">자도번거래처 <span class="mrp-req">*</span></label>
         <input class="inp mrp-cust ${custCode?'ok':''}" id="mp-cust" list="mp-cdl" value="${esc(custNm)}" placeholder="거래처명(필수)" autocomplete="off" style="width:160px">
         <span class="mrp-ccd" id="mp-ccd">${custCode?esc(custCode):''}</span>
         <datalist id="mp-cdl"></datalist>
         <label class="tl">입고창고</label>
         <select class="inp" id="mp-wh" style="width:180px" title="창고는 가공공정 마스터의 IS* 코드로 등록돼 있다(IS0001=자재창고)">
           ${whs.length?whs.map(w=>`<option value="${esc(w.wh)}" ${w.wh===wh?'selected':''}>${esc(w.wh)} ${esc(w.nm||'')}</option>`).join('')
                       :`<option value="${esc(wh)}" selected>${esc(wh)} 자재창고</option>`}
         </select>
         <label class="tl">입고구분</label>
         <span class="mrp-fix" title="수동 등록은 개별입고만 가능합니다. 가공입고(C)는 가공이동전표 바코드로, 세트입고(S)는 세트납품으로 자동 생성됩니다.">${esc(TAG_NEW_NM)}</span>
       </div>
       <div class="mrp-tb2">
         <span class="mrp-hint">💡 <b>자도번</b>칸에 엑셀에서 복사한 셀을 <b>Ctrl+V</b> 하면 여러 행이 한 번에 채워집니다(자도번↹수량↹비고 순).</span>
         <div class="spacer"></div>
         <span class="rowcount">입력 <b>${nF}</b>건 · 수량합 <b>${_nf(sumQ)}</b> <span class="mut">/ ${rows.length}행</span></span>
       </div>
       <div class="mrp-grid">
         <table class="tbl mrp-tbl"><thead><tr>
           <!-- ★레거시 w_pu_stock_057 컬럼 순서(2026-08-31): 자도번·품명·규격·단위·
                (발주잔량)·입고수량·입고단가·**입고금액·입고부가세**·비고.
                금액/부가세 두 칸을 넣느라 품명·규격·비고를 줄여 **가로스크롤 없이** 한 줄에 담았다. -->
           <th style="width:38px">SEQ</th><th style="width:132px">자도번</th><th style="width:150px">품명</th>
           <th style="width:96px">규격</th><th style="width:38px">단위</th><th style="width:66px">현재고</th>
           <th style="width:76px">입고수량</th><th style="width:74px">입고단가</th>
           <th style="width:84px">입고금액</th><th style="width:78px">입고부가세</th><th>비고</th>
           <th style="width:28px"></th></tr></thead>
         <tbody id="mp-tb">${bodyHtml()}</tbody></table>
       </div>
       <div class="mrp-f">
         <button class="btn" id="mp-add">☰＋ 행추가 (${ROWSTEP})</button>
         <button class="btn ghost" id="mp-clr">☰− 빈행정리</button>
         <!-- ★MASTER단가(2026-08-31) — 레거시 w_pu_stock_055 동일. 직접 고친 단가를
              마스터값(nx.price_item 매입가, 거래처·입고일 기준)으로 되돌린다. -->
         <button class="btn ghost" id="mp-mcost" title="입고단가를 MASTER단가로 다시 채웁니다(직접 입력분 포함)">💲 MASTER단가</button>
         <div class="spacer"></div>
         <span class="mut" style="font-size:12px">가드: 마감월 잠금 · 미등록품목 차단</span>
         <button class="btn" id="mp-save" style="background:#1c7c3a;color:#fff" ${busy?'disabled':''}>✔ 저장</button>
         <button class="btn ghost" id="mp-close">✖ 닫기</button>
       </div>
     </div>
     <style>
      .mrp{background:#fff;border-radius:10px;box-shadow:0 12px 40px rgba(20,30,48,.35);
           width:min(1180px,96vw);height:min(88vh,900px);display:flex;flex-direction:column;overflow:hidden}
      .mrp-h{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;
             padding:9px 14px;background:#1c47a0;color:#fff;font-weight:700;font-size:14px}
      .mrp-x{cursor:pointer;font-size:16px;opacity:.85}.mrp-x:hover{opacity:1}
      .mrp-tb,.mrp-tb2{flex:0 0 auto;display:flex;align-items:center;gap:6px;padding:8px 12px;flex-wrap:wrap}
      .mrp-tb{border-bottom:1px solid var(--line-2,#c9d3e0);background:#f7f9fd}
      .mrp-tb2{padding:5px 12px;font-size:12px}
      .mrp-hint{color:#2f5aa8;background:#eef4ff;border-radius:6px;padding:3px 9px;font-size:11.5px}
      .mrp-fix{display:inline-block;padding:3px 10px;border:1px solid #c9d3e0;border-radius:4px;
               background:#eef4ff;color:#24406e;font-weight:700;font-size:12px}
      .mrp-req{color:#c0392b;font-weight:700}
      /* ★입고단가 출처 표시(2026-08-31) — 타사단가 대체는 노랑, 직접수정은 파랑 */
      .mp-cost.alt{background:#fffbe6;border-color:#e8c96a}
      .mp-cost.ed{background:#eef4ff;border-color:#9dc0e8;font-weight:600}
      .mp-cb{position:absolute;right:3px;top:50%;transform:translateY(-50%);pointer-events:none;
             font-size:9.5px;padding:0 3px;border-radius:3px;line-height:1.5}
      .mp-cb.alt{background:#f6d365;color:#5c4405}
      .mp-cb.ed{background:#dbeafe;color:#1c47a0}
      .mrp-cust{background:#fff8dc;border-color:#e0c97a;min-width:0}   /* min-width 해제(app.css 200px) */
      .mrp-cust.ok{background:#f2fbf4;border-color:#7ec48f}
      .mrp-tb .inp{min-width:0}                                        /* 팝업 조건칸 폭 지정이 먹게 */
      .mrp-ccd{display:inline-block;min-width:38px;font-size:11.5px;color:#1c7c3a;font-weight:700}
      .mrp-nav{padding:2px 7px;min-width:0}
      .mrp-grid{flex:1 1 auto;min-height:0;overflow:auto;margin:0 12px;border:1px solid var(--line-2,#c9d3e0);border-radius:6px}
      .mrp-tbl{font-size:12px;table-layout:fixed;width:100%}
      .mrp-tbl th,.mrp-tbl td{padding:2px 5px;white-space:nowrap;border-bottom:1px solid #eef1f6}
      .mrp-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2;border-bottom:1px solid #c9d3e0;
                        text-align:center}   /* ★그리드 헤더는 항상 가운데 정렬(전 화면 공통 규칙) */
      .mrp-tbl td.mut{color:var(--muted)}.mrp-tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
      .mrp-tbl input{border:1px solid transparent;border-radius:3px;padding:2px 4px;font-size:12px;width:100%;background:transparent}
      .mrp-tbl input:focus{border-color:#2f6db3;background:#fff;outline:none}
      .mrp-tbl tr.on{background:#f4fbf6}.mrp-tbl tr.bad input.mp-mat{background:#ffecec;border-color:#c0392b;color:#c0392b}
      .mrp-tbl td.cap{overflow:hidden;text-overflow:ellipsis}
      .mrp-f{flex:0 0 auto;display:flex;align-items:center;gap:6px;padding:9px 12px;border-top:1px solid var(--line-2,#c9d3e0);background:#f7f9fd}
      .mrp-del{cursor:pointer;color:#c0392b;opacity:.55}.mrp-del:hover{opacity:1}
     </style>`;
    wire();
  };

  // ★입고금액 = 수량 × 단가(반올림). 둘 중 하나라도 비면 공란(레거시도 0 대신 빈칸).
  const _amtOf=r=>{const q=Number(r.qty), c=Number(r.cost);
    if(!(q>0)||!isFinite(c)||r.cost===''||r.cost==null)return '';
    return Math.round(q*c);};
  function bodyHtml(){
    return rows.map((r,i)=>`<tr data-i="${i}" class="${(r.mat||'').trim()?'on':''} ${r.bad?'bad':''}">
      <td class="center mut">${i+1}</td>
      <td><input class="mp-mat" data-i="${i}" value="${esc(r.mat)}" autocomplete="off" list="mp-mdl"></td>
      <td class="cap mp-nm" title="${esc(r.nm)}">${esc(r.nm)}</td>
      <td class="cap mp-sp" title="${esc(r.spec)}">${esc(r.spec)}</td>
      <td class="center mut mp-un">${esc(r.unit)}</td>
      <td class="num mut mp-st">${r.stock===''?'':_nf(r.stock)}</td>
      <td><input class="mp-qty" data-i="${i}" type="number" step="any" min="0" value="${esc(r.qty)}" style="text-align:right"></td>
      <!-- ★단가 출처 표시(2026-08-31) — 그 거래처 단가가 없어 다른 업체 단가를 가져오면
           칸을 노랗게 + [타사] 배지. 직접 고치면 [수정]. 값 자체는 언제든 수정 가능. -->
      <td style="position:relative">
        <input class="mp-cost${r.costEdited?' ed':(r.costSrc==='other'?' alt':'')}" data-i="${i}"
               type="number" step="any" min="0" value="${esc(r.cost)}" style="text-align:right"
               title="${r.costEdited?'직접 입력한 단가':(r.costVendor?`MASTER단가 · 거래처 ${esc(r.costVendor)}${r.costYmd?' · 적용 '+esc(_fmtY(r.costYmd)):''}`:'')}">
        ${r.costEdited?'<span class="mp-cb ed">수정</span>'
          :(r.costSrc==='other'?`<span class="mp-cb alt" title="이 거래처 단가가 없어 ${esc(r.costVendor||'')} 단가를 가져왔습니다">타사</span>`:'')}
      </td>
      <!-- ★입고금액·입고부가세(2026-08-31 레거시 w_pu_stock_057 대조 — 웹에 없던 두 칸).
           금액 = 수량 × 단가(반올림) · 부가세 = 금액 × 10%(반올림). 자동계산 = 읽기전용.
           단가·수량이 바뀌면 redrawBody 로 함께 갱신된다. -->
      <td class="num mut mp-amt" title="${_amtOf(r)===''?'':_nf(_amtOf(r))}">${_amtOf(r)===''?'':_nf(_amtOf(r))}</td>
      <td class="num mut mp-vat" title="${_amtOf(r)===''?'':_nf(Math.round(_amtOf(r)*0.1))}">${_amtOf(r)===''?'':_nf(Math.round(_amtOf(r)*0.1))}</td>
      <td><input class="mp-rmk" data-i="${i}" value="${esc(r.rmk)}"></td>
      <td class="center"><span class="mrp-del" data-i="${i}" title="행 비우기">✖</span></td>
    </tr>`).join('')+`<datalist id="mp-mdl"></datalist>`;
  }
  // ★재렌더 시 포커스·커서 보존 — 안 하면 입력 중 커서가 튀고 IME 조합이 깨진다.
  const redrawBody=()=>{
    const ae=document.activeElement;
    const keep=(ae&&ov.contains(ae)&&ae.dataset&&ae.dataset.i!==undefined)
      ? {cls:[...ae.classList].find(x=>x.startsWith('mp-')), i:ae.dataset.i,
         s:ae.selectionStart, e:ae.selectionEnd} : null;
    const tb=ov.querySelector('#mp-tb');if(tb){tb.innerHTML=bodyHtml();wireRows();}
    const rc=ov.querySelector('.rowcount');
    if(rc)rc.innerHTML=`입력 <b>${filled().length}</b>건 · 수량합 <b>${_nf(filled().reduce((s,r)=>s+Number(r.qty||0),0))}</b> <span class="mut">/ ${rows.length}행</span>`;
    if(keep&&keep.cls){
      const el=ov.querySelector(`.${keep.cls}[data-i="${keep.i}"]`);
      if(el){el.focus();try{el.setSelectionRange(keep.s,keep.e);}catch(e){}}
    }};

  // 자도번 → 품명·규격·단위·현재고 + ★MASTER단가 배치추적
  //   단가는 거래처·입고일자에 따라 달라지므로 함께 넘긴다(같은 자재도 업체별 단가가 다르다).
  const trace=async(codes)=>{
    codes=[...new Set(codes.map(c=>(c||'').trim().toUpperCase()).filter(Boolean))].filter(c=>info[c]===undefined);
    if(!codes.length)return;
    try{const r=await fetch(`${API}/api/stock/matinfo`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({codes, cust:(custCode||'').trim(), ymd:_toYMD(ymd)})});
      ((await r.json()).rows||[]).forEach(x=>{info[(x.mat||'').toUpperCase()]=x;});
    }catch(e){}
  };
  const applyInfo=()=>{rows.forEach(r=>{const k=(r.mat||'').trim().toUpperCase();if(!k)return;
    const v=info[k];if(!v)return;
    r.nm=v.nm||'';r.spec=v.spec||'';r.unit=v.unit||'';r.stock=v.stock;r.bad=v.unknown?1:0;
    // ★MASTER단가 자동채움(2026-08-31) — 사용자가 이미 고쳤으면 덮지 않는다.
    //   r.costEdited 는 입고단가칸을 직접 만졌을 때만 선다(아래 .mp-cost oninput).
    if(!r.costEdited && (r.cost===''||r.cost===undefined||r.cost===null||Number(r.cost)===0)){
      if(v.cost!==undefined && v.cost!==null)r.cost=v.cost;
    }
    r.costSrc=v.cost_src||'';        // own=그 거래처 / other=타사 대체 / any=거래처 미지정
    r.costVendor=v.cost_vendor||'';
    r.costYmd=v.cost_ymd||'';});};

  function wireRows(){
    const g=s=>ov.querySelectorAll(s);
    g('.mp-mat').forEach(el=>{
      el.onchange=async()=>{const i=+el.dataset.i;rows[i].mat=el.value.trim().toUpperCase();
        await trace([rows[i].mat]);applyInfo();redrawBody();};
      // ★엑셀 붙여넣기 — 자도번↹수량↹비고, 여러 행
      el.onpaste=async ev=>{
        const t=(ev.clipboardData||window.clipboardData).getData('text');
        if(!t||!/[\t\r\n]/.test(t))return;                 // 단일 셀이면 기본동작
        ev.preventDefault();
        const start=+el.dataset.i;
        const lines=t.replace(/\r/g,'').split('\n').filter(x=>x.trim()!=='');
        while(rows.length<start+lines.length)addRows(ROWSTEP);
        lines.forEach((ln,k)=>{const cel=ln.split('\t');const r=rows[start+k];
          r.mat=(cel[0]||'').trim().toUpperCase();
          if(cel.length>1){const q=parseFloat(String(cel[1]).replace(/,/g,''));if(!isNaN(q))r.qty=q;}
          if(cel.length>2)r.rmk=(cel[2]||'').trim();});
        await trace(lines.map(l=>l.split('\t')[0]));applyInfo();redrawBody();
        const nx=ov.querySelector(`.mp-mat[data-i="${Math.min(start+lines.length,rows.length-1)}"]`);if(nx)nx.focus();
      };
      let t=null;
      el.oninput=()=>{const v=el.value.trim();clearTimeout(t);if(v.length<2)return;
        t=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(v)}&all_active=1`);
          const dl=ov.querySelector('#mp-mdl');
          if(dl)dl.innerHTML=((await r.json()).rows||[]).map(x=>`<option value="${esc(x.item)}">${esc(x.name||'')}</option>`).join('');
        }catch(e){}},220);};
    });
    // ★금액·부가세 갱신은 **그 행만** 고친다 — redrawBody 로 전체를 다시 그리면
    //   입력 중 커서가 튀고 IME 조합이 깨진다(기존 주석과 같은 이유).
    const syncAmt=i=>{const tr=ov.querySelector(`#mp-tb tr[data-i="${i}"]`); if(!tr)return;
      const a=_amtOf(rows[i]);
      const ea=tr.querySelector('.mp-amt'), ev=tr.querySelector('.mp-vat');
      const sa=(a===''?'':_nf(a)), sv=(a===''?'':_nf(Math.round(a*0.1)));
      if(ea){ea.textContent=sa; ea.title=sa;}          // 자릿수가 넘쳐도 툴팁으로 전액 확인
      if(ev){ev.textContent=sv; ev.title=sv;}};
    g('.mp-qty').forEach(el=>el.oninput=()=>{const i=+el.dataset.i; rows[i].qty=el.value; syncAmt(i);
      const rc=ov.querySelector('.rowcount');
      if(rc)rc.innerHTML=`입력 <b>${filled().length}</b>건 · 수량합 <b>${_nf(filled().reduce((s,r)=>s+Number(r.qty||0),0))}</b> <span class="mut">/ ${rows.length}행</span>`;});
    // ★단가 직접수정(2026-08-31) — costEdited 를 세워 MASTER단가 자동채움이 덮지 않게 한다.
    //   레거시 w_pu_stock_055 도 단가칸을 직접 고칠 수 있다(MASTER단가 버튼 옆 입력칸).
    g('.mp-cost').forEach(el=>el.oninput=()=>{
      const i=+el.dataset.i, r=rows[i]; r.cost=el.value; r.costEdited=1; syncAmt(i);});
    g('.mp-rmk').forEach(el=>el.oninput=()=>{rows[+el.dataset.i].rmk=el.value;});
    g('.mrp-del').forEach(el=>el.onclick=()=>{rows[+el.dataset.i]=blank();redrawBody();});
  }

  function wire(){
    const g=id=>ov.querySelector(id);
    g('#mp-x').onclick=g('#mp-close').onclick=()=>{
      if(filled().length&&!confirm(`입력한 ${filled().length}건이 저장되지 않았습니다. 닫을까요?`))return;close();};
    g('#mp-ymd').onchange=e=>{ymd=e.target.value;};
    const shift=d=>{const t=new Date(ymd);t.setDate(t.getDate()+d);ymd=`${t.getFullYear()}-${pad(t.getMonth()+1)}-${pad(t.getDate())}`;draw();};
    g('#mp-prev').onclick=()=>shift(-1);g('#mp-next').onclick=()=>shift(1);
    g('#mp-wh').onchange=e=>{wh=e.target.value;};
    g('#mp-add').onclick=()=>{addRows(ROWSTEP);redrawBody();};
    g('#mp-clr').onclick=()=>{rows=rows.filter(r=>(r.mat||'').trim());if(rows.length<ROWSTEP)addRows(ROWSTEP-rows.length);redrawBody();};
    // ★MASTER단가 — 입고일자·거래처 기준 최신 매입가로 전 행 재조회(직접 입력분도 덮는다)
    const mc=g('#mp-mcost');
    if(mc)mc.onclick=async()=>{
      const cds=[...new Set(rows.map(r=>(r.mat||'').trim().toUpperCase()).filter(Boolean))];
      if(!cds.length)return alert('자도번을 먼저 입력하세요.');
      mc.disabled=true; const _t=mc.textContent; mc.textContent='조회중…';
      info={};                                   // 캐시 비우고 현재 일자·거래처로 다시 받는다
      rows.forEach(r=>{r.costEdited=0;});        // 수동수정 해제 → 마스터값으로 덮어쓴다
      await trace(cds); applyInfo(); redrawBody();
      mc.disabled=false; mc.textContent=_t;
      const n=rows.filter(r=>(r.mat||'').trim()&&Number(r.cost)>0).length;
      const miss=rows.filter(r=>(r.mat||'').trim()&&!(Number(r.cost)>0)).length;
      alert(`MASTER단가 적용 — ${_fmtY(_toYMD(ymd))} 기준\n\n단가 있음 ${n}건`
           +(miss?`\n단가 없음 ${miss}건 (직접 입력하세요)`:''));
    };
    // 거래처 오토컴플리트(값=이름, 저장 시 코드매핑)
    let ct=null, cmap={}, composing=false;
    const ci=g('#mp-cust');
    // 코드 확정 상태를 칸 색·옆 코드표시로 즉시 보여준다(미확정이면 저장이 막히므로)
    const showCC=()=>{const b=g('#mp-ccd');if(b)b.textContent=custCode||'';
      ci.classList.toggle('ok',!!custCode);};
    const resolveNm=async(v)=>{
      if(composing)return;                    // ★IME 조합 중 value 덮어쓰기 금지(글자 중복 버그)
      v=(v||'').trim();
      if(!v){custCode='';showCC();return;}
      const hit=cmap[v.toLowerCase()];
      if(hit){custCode=hit;showCC();return;}
      try{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(v)}`);
        const rr=(await r.json()).rows||[];
        rr.forEach(x=>{cmap[(x.name||'').toLowerCase()]=x.code;});
        const dl=g('#mp-cdl');
        if(dl)dl.innerHTML=rr.map(x=>`<option value="${esc(x.name||'')}">${esc(x.code||'')}</option>`).join('');
        const lv=v.toLowerCase();
        const h=rr.find(x=>String(x.name||'').trim().toLowerCase()===lv)
             || rr.find(x=>String(x.code||'').trim().toLowerCase()===lv)
             || (rr.length===1?rr[0]:null);
        if(h){custCode=String(h.code||'').trim();custNm=String(h.name||'').trim();ci.value=custNm;}
        else custCode='';
      }catch(e){custCode='';}
      showCC();};
    ci.addEventListener('compositionstart',()=>{composing=true;});
    ci.addEventListener('compositionend',()=>{composing=false;custNm=ci.value;resolveNm(ci.value);});
    ci.oninput=()=>{custNm=ci.value;custCode=cmap[custNm.trim().toLowerCase()]||'';showCC();
      clearTimeout(ct);const v=ci.value.trim();if(composing||!v)return;
      ct=setTimeout(()=>resolveNm(v),240);};
    ci.onchange=()=>{custNm=ci.value;if(!composing)resolveNm(ci.value);};
    showCC();
    g('#mp-save').onclick=save;
    wireRows();
  }

  async function save(){
    if(busy)return;
    const sel=filled();                                  // ★입력된 행만 저장(레거시 동일)
    if(!sel.length){alert('입력된 행이 없습니다. 자도번과 입고수량을 입력하세요.');return;}
    const bad=sel.filter(r=>r.bad);
    if(bad.length){alert(`미등록 품목 ${bad.length}건이 있습니다:\n`+bad.slice(0,10).map(r=>r.mat).join(', '));return;}
    // ★거래처(자도번거래처) 필수 — 미지정이면 매입처 없는 입고가 되어 매입마감·수불에서 누락된다.
    //   이름만 치고 목록에서 안 고르면 코드가 안 잡히므로 **코드 확정**까지 요구한다(2026-08-28).
    if(!custCode){
      const t=(custNm||'').trim();
      alert(t?`거래처 「${t}」를 목록에서 선택해 주세요. (코드가 확정되지 않았습니다)`
             :'자도번거래처를 입력하세요. 거래처 없이는 입고 등록이 안 됩니다.');
      const el=ov.querySelector('#mp-cust');if(el){el.focus();el.select();}
      return;
    }
    if(!confirm(`${sel.length}건 · 수량합 ${_nf(sel.reduce((s,r)=>s+Number(r.qty||0),0))}\n입고일 ${ymd} · 창고 ${wh}\n\n저장할까요? (재고 증가)`))return;
    busy=true;draw();
    try{
      // ★금액·부가세도 함께 전송(2026-08-31) — 화면에 보이는 값과 DB 가 어긋나지 않게.
      //   (백엔드도 같은 식으로 계산하지만, 화면 표시값을 정본으로 보낸다)
      const body={screen:'receipt', user:_curUserNm(), rows:sel.map(r=>{
        const a=_amtOf(r);
        return {MAINT_YMD:_toYMD(ymd), MAT_CODE:r.mat, MAINT_TAG:tag, qty:Number(r.qty),
          CUST_CODE:custCode||null, GAGONG_PROC_CODE:wh||null,
          MAINT_COST:Number(r.cost||0),
          MAINT_AMT:(a===''?0:a), MAINT_VAT:(a===''?0:Math.round(a*0.1)),
          REMARKS:(r.rmk||'').trim()||null};})};
      const rr=await fetch(`${API}/api/stock/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await rr.json();
      if(!j.ok){alert('저장 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));busy=false;draw();return;}
      alert(`✅ 저장 완료 — ${j.count}건 등록 (재고 반영)`);
      close();onSaved();
    }catch(e){alert('저장 실패: '+e.message);busy=false;draw();}
  }

  draw();
  // ★창고목록은 비동기 도착 — 여기서 draw()(전체 재렌더)를 하면 사용자가 입력 중인
  //   한글 IME 조합이 깨져 「케이비」가 「케케이비」처럼 중복된다(2026-08-28 실사용 버그).
  //   → 셀렉트 옵션만 교체한다.
  (async()=>{try{const r=await fetch(`${API}/api/stock/warehouses`);whs=(await r.json()).rows||[];
    if(whs.length&&!whs.some(w=>w.wh===wh))wh=whs[0].wh;
    const sel=ov.querySelector('#mp-wh');
    if(sel&&whs.length){
      sel.innerHTML=whs.map(w=>`<option value="${esc(w.wh)}" ${w.wh===wh?'selected':''}>${esc(w.wh)} ${esc(w.nm||'')}</option>`).join('');
      sel.value=wh;
    }
  }catch(e){}})();
  setTimeout(()=>{const f=ov.querySelector('.mp-mat');if(f)f.focus();},60);
}
function stockScreen(sid){
  const CFG=STOCK_CFG[sid], KEY=CFG.key;
  const dl=`${sid}-matdl`, cdl=`${sid}-custdl`;
  return (c)=>{
    let q='', rows=[], news=[], editMode=false, loading=false, msg='', itemNames={}, custNames={}, editRowKey=null, retMode=false;
    // ★자재입고관리는 레거시처럼 팝업 방식(등록=057 / 수정·삭제=055). 나머지 화면은 종전 인라인.
    const POPUP=(sid==='stockreceipt');
    let selKey=null, whList=[];                 // 선택행(단건 수정/삭제 대상) · 입고창고 목록
    // ★매입처 조회조건(2026-08-23) — 코드/거래처명 아무거나 입력.
    //   custQ=입력값, custQCode=이름이 정확히 매칭돼 확정된 거래처코드(있으면 이 코드로만 조회),
    //   custQName=옆에 따라오는 표시. 코드확정 없이 부분입력이면 이름 LIKE 검색(그린산업→김해공장도 포함).
    let custQ='', custQName='', custQCode='';
    const curKey=()=>retMode?'return':KEY;                       // 반품모드=return screen(음수·≤현재고 가드)
    const curTags=()=>retMode?CFG.rettags:CFG.tags;
    const rowKey=r=>`${r.MAINT_YMD}|${r.MAINT_SEQ}`;
    // 기본 조회기간: 당월 1일 ~ 오늘 (2026-08-23 변경, 이전=최근 120일)
    const now=new Date(), pad=n=>String(n).padStart(2,'0');
    const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
    let fromV=iso(new Date(now.getFullYear(),now.getMonth(),1)), toV=iso(now);
    const list=async()=>{loading=true;msg='';draw();
      // ★업체코드 칸이 코드/업체명 겸용이라, 코드로 확정된 값일 때만 cust_code(정확일치)로 보낸다.
      //   확정 안 된 문자열(예: 업체명 일부)은 cust 로 넘겨 이름 LIKE 검색되게.
      const _ccOk=/^[A-Za-z0-9_-]+$/.test((custQCode||'').trim());
      const _cq=(custQ||'').trim() || (_ccOk?'':(custQCode||'').trim());
      try{const u=`${STOCK_API}/api/stock/list?screen=${curKey()}&ymd_from=${_toYMD(fromV)}&ymd_to=${_toYMD(toV)}&q=${encodeURIComponent(q)}&cust=${encodeURIComponent(_cq)}${(_ccOk&&custQCode)?`&cust_code=${encodeURIComponent(custQCode.trim())}`:''}`;
        const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);rows=(await r.json()).rows||[];}
      catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];}
      loading=false;draw();};
    const addRow=()=>{news.push({MAINT_YMD:toV,MAT_CODE:'',item_name:'',MAINT_TAG:curTags()[0][0],qty:'',CUST_CODE:'',cust_name:'',GAGONG_PROC_CODE:'',REMARKS:''});draw();};
    const save=async()=>{
      if(!news.length){alert('등록할 신규 행이 없습니다. ＋행추가로 입력하세요.');return;}
      const errs=[];news.forEach((n,i)=>{const y=(n.MAINT_YMD||'').trim(),m=(n.MAT_CODE||'').trim(),qn=Number(n.qty||0);
        if(!y)errs.push(`${i+1}행: 일자 필요`);if(!m)errs.push(`${i+1}행: 자도번 필요`);
        if(CFG.signed){if(qn===0)errs.push(`${i+1}행: 조정수량은 0일 수 없습니다(증가 +, 감소 −)`);}
        else if(!(qn>0))errs.push(`${i+1}행: 수량은 0보다 커야 함`);});
      if(errs.length){alert('저장 불가:\n'+errs.join('\n'));return;}
      const body={screen:curKey(),rows:news.map(n=>({MAINT_YMD:_toYMD(n.MAINT_YMD),MAT_CODE:(n.MAT_CODE||'').trim().toUpperCase(),
        MAINT_TAG:n.MAINT_TAG,qty:Number(n.qty),CUST_CODE:(n.CUST_CODE||'').trim()||null,GAGONG_PROC_CODE:(n.GAGONG_PROC_CODE||'').trim()||null,REMARKS:(n.REMARKS||'').trim()||null}))};
      try{const r=await fetch(`${STOCK_API}/api/stock/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const j=await r.json();if(!j.ok){alert('저장 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));return;}
        alert(`저장 완료 — ${j.count}건 등록`);news=[];editMode=false;list();}
      catch(e){alert('저장 실패: '+e.message);}};
    const updateRow=async(r,vals)=>{
      const body={screen:curKey(),MAINT_YMD:r.MAINT_YMD,MAINT_SEQ:r.MAINT_SEQ,...vals};
      try{const rr=await fetch(`${STOCK_API}/api/stock/update`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const j=await rr.json();if(!j.ok){alert('수정 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));return;}
        editRowKey=null;list();}catch(e){alert('수정 실패: '+e.message);}};
    const deleteRow=async r=>{if(!confirm(`이 행을 삭제할까요?\n${r.MAT_CODE} · ${_fmtY(r.MAINT_YMD)} · 수량 ${_nf(r.qty)}`))return;
      try{const rr=await fetch(`${STOCK_API}/api/stock/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({screen:curKey(),MAINT_YMD:r.MAINT_YMD,MAINT_SEQ:r.MAINT_SEQ})});
        const j=await rr.json();if(!j.ok){alert('삭제 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));return;}
        list();}catch(e){alert('삭제 실패: '+e.message);}};
    const draw=()=>{
      const totQ=rows.reduce((s,r)=>s+Number(r.qty||0),0);
      const newTbl=editMode?`
        <div class="stk-new">
          <div class="stk-new-h">신규 등록 <span style="font-weight:400;color:var(--muted);font-size:12px">— 저장 시 일자별 채번, 마감월·FK·재고 가드 검증</span></div>
          <table class="tbl stk-tbl"><thead><tr><th>#</th><th>일자</th><th>구분</th><th>자도번</th><th>품명</th><th>수량${CFG.neg?'(출고)':''}</th><th>${retMode?'매입처':'거래처'}</th><th>비고</th><th>삭제</th></tr></thead>
          <tbody>${news.map((n,i)=>`<tr>
            <td class="center mut">${i+1}</td>
            <td><input class="ce sn-date" type="date" data-i="${i}" value="${esc(n.MAINT_YMD)}" style="width:130px"></td>
            <td><select class="ce sn-tag" data-i="${i}">${curTags().map(t=>`<option value="${t[0]}" ${t[0]===n.MAINT_TAG?'selected':''}>${esc(t[1])}</option>`).join('')}</select></td>
            <td><input class="ce sn-mat" list="${dl}" data-i="${i}" value="${esc(n.MAT_CODE)}" placeholder="자도번 검색·선택" autocomplete="off" style="width:130px"></td>
            <td class="bcap sn-nm" style="max-width:170px">${esc(n.item_name||'')}</td>
            <td><input class="ce sn-qty" type="number" step="any" ${CFG.signed?'':'min="0"'} data-i="${i}" value="${n.qty}" placeholder="${CFG.signed?'± 부호':''}" style="width:80px;text-align:right"></td>
            <td><input class="ce sn-cust" list="${cdl}" data-i="${i}" value="${esc(n.cust_name||n.CUST_CODE||'')}" placeholder="거래처명 검색(선택)" autocomplete="off" style="width:120px"></td>
            <td><input class="ce sn-rmk" data-i="${i}" value="${esc(n.REMARKS)}" style="width:120px"></td>
            <td class="center"><span class="stk-del" data-i="${i}" title="행삭제" style="cursor:pointer;color:#c0392b">✖</span></td>
          </tr>`).join('')||`<tr><td colspan="9" class="empty">＋행추가로 신규 등록 행을 추가하세요</td></tr>`}</tbody></table>
        </div>`:'';
      c.innerHTML=`
       <div class="page-title">${retMode?'↩️':CFG.ic} ${esc(CFG.nm)}${retMode?' <span style="color:#c0392b">— 반품 모드</span>':''} <span style="font-size:12px;color:var(--muted);font-weight:400">nx · 백엔드 등록·가드</span></div>
       <div class="page-sub"${retMode?' style="color:#c0392b"':''}>${esc(retMode?CFG.retsub:CFG.sub)}</div>
       <div class="toolbar">
         <label class="tl">기간</label><input class="inp" id="stk-from" type="date" value="${fromV}" style="width:150px">
         <span class="mut">~</span><input class="inp" id="stk-to" type="date" value="${toV}" style="width:150px">
         <!-- ★매입처 = [코드][🔍][거래처명] 3칸 연동(2026-08-28 사용자 요청·410 화면과 동일 형식).
                코드를 치면 이름이, 이름을 고르면 코드가 서로 채워진다. -->
         <label class="tl">업체코드</label>
         <input class="inp stk-ci" id="stk-custcode" list="${cdl}c" value="${esc(custQCode)}" placeholder="코드" autocomplete="off" style="width:88px" title="업체코드(5자리) 또는 업체명 입력 — 서로 자동으로 채워집니다">
         <datalist id="${cdl}c"></datalist>
         <button class="btn ghost stk-cbtn" id="stk-cfind" title="거래처명 칸으로 이동">🔍</button>
         <input class="inp stk-ci" id="stk-cust" list="${cdl}" value="${esc(custQ)}" placeholder="거래처명" autocomplete="off" style="width:140px">
         <button class="btn" id="stk-go">🔍 조회</button>
         <div class="spacer"></div><span class="rowcount">${rows.length}건 · 수량합 <b>${_nf(totQ)}</b></span>
       </div>
       <div class="toolbar">
         <label class="tl">자도번</label><input class="inp" id="stk-q" value="${esc(q)}" placeholder="코드 일부" style="width:150px">
         ${CFG.retn&&!editMode?`<button class="btn ${retMode?'':'ghost'}" id="stk-ret" style="${retMode?'background:#c0392b;color:#fff;border-color:#c0392b':''}">↩ ${retMode?'입고로 전환':'반품'}</button>`:''}
         ${POPUP
           ?/* ★자재입고관리 = 레거시와 동일하게 **팝업 방식**(2026-08-28 사용자 요청).
                등록 = w_pu_stock_057(일괄) · 수정/삭제 = w_pu_stock_055(단건, 행 더블클릭) */
            (PERM.canEdit(sid)
              ?`<button class="btn" id="stk-bulk" style="background:#1c47a0;color:#fff" title="레거시 w_pu_stock_057 — 여러 건 한 번에 수동입고">➕ 등록(일괄입고)</button>
                <button class="btn" id="stk-bc" style="background:#0f7b6c;color:#fff;border-color:#0f7b6c" title="가공이동계획(580)에서 발행된 이동전표 바코드를 읽어 자재창고로 입고">🔖 가공이동바코드</button>
                <button class="btn" id="stk-mod" title="선택행 수정 — 행을 더블클릭해도 열립니다">✎ 수정</button>
                <button class="btn ghost" id="stk-rm" style="color:#c0392b;border-color:#e2b6b0" title="선택행 삭제">🗑 삭제</button>`
              :`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`)
           :(editMode
             ?`<button class="btn" id="stk-add">＋ ${retMode?'반품행':'행추가'}</button><button class="btn" id="stk-save">💾 저장</button><button class="btn ghost" id="stk-cancel">✖ 취소</button>`
             :`${PERM.canEdit(sid)?`<button class="btn" id="stk-edit">✎ ${retMode?'반품등록/수정':'등록/수정'}</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`}`)}
         <button class="btn" id="stk-xls">⬇ 엑셀</button>
       </div>
       <datalist id="${dl}"></datalist><datalist id="${cdl}"></datalist>
       ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
       ${newTbl}
       ${loading?`<div class="empty">조회 중…</div>`:`
       <div class="grid-wrap stk-wrap"><table class="tbl stk-tbl"><thead><tr>
         <th>일자</th><th>구분</th><th>자도번</th><th>품명</th><th>규격</th><th>수량</th><th>매입처</th><th>투입공정</th><th>비고</th><th>등록자</th><th>등록시간</th>${editMode?'<th>관리</th>':''}</tr></thead>
       <tbody>${rows.map(r=>{const k=rowKey(r);
         if(editMode&&editRowKey===k)return `<tr class="stk-editing" data-key="${esc(k)}">
           <td class="center">${esc(_fmtY(r.MAINT_YMD))}</td>
           <td><select class="ce re-tag">${curTags().map(t=>`<option value="${t[0]}" ${t[0]===r.MAINT_TAG?'selected':''}>${esc(t[1])}</option>`).join('')}</select></td>
           <td><b>${esc(r.MAT_CODE||'')}</b></td>
           <td class="bcap" title="${esc(r.item_name||'')}">${esc(r.item_name||'')}</td>
           <td class="bcap" title="${esc(r.item_spec||'')}">${esc(r.item_spec||'')}</td>
           <td><input class="ce re-qty" type="number" step="any" ${CFG.signed?'':'min="0"'} value="${CFG.signed?(Number(r.qty)||0):Math.abs(Number(r.qty||0))}" style="width:80px;text-align:right"></td>
           <td><input class="ce re-cust" list="${cdl}" value="${esc(r.cust_name||r.CUST_CODE||'')}" placeholder="거래처명(선택)" autocomplete="off" style="width:120px"></td>
           <td><input class="ce re-proc" value="${esc(r.GAGONG_PROC_CODE||'')}" placeholder="(선택)" style="width:70px"></td>
           <td><input class="ce re-rmk" value="${esc(r.REMARKS||'')}" style="width:120px"></td>
           <td class="center mut">${esc(r.INSERT_USER_ID||'')}</td>
           <td class="center mut">${esc(_fmtDT(r.INSERT_DATETIME))}</td>
           <td class="center" style="white-space:nowrap"><span class="re-save" title="저장" style="cursor:pointer;color:#2f6db3;font-weight:700">💾</span> <span class="re-cancel" title="취소" style="cursor:pointer;color:#888">✖</span></td></tr>`;
         return `<tr data-key="${esc(k)}" class="${POPUP?'stk-row':''}${selKey===k?' sel':''}">
         <td class="center">${esc(_fmtY(r.MAINT_YMD))}</td>
         <td class="center"><span class="stk-tag">${esc(r.tag_name||r.MAINT_TAG||'')}</span></td>
         <td><b>${esc(r.MAT_CODE||'')}</b></td>
         <td class="bcap" title="${esc(r.item_name||'')}">${esc(r.item_name||'')}</td>
         <td class="bcap" title="${esc(r.item_spec||'')}">${esc(r.item_spec||'')}</td>
         <td class="num ${Number(r.qty)<0?'neg':''}">${_nf(r.qty)}</td>
         <td class="bcap" title="${esc(r.cust_name||r.CUST_CODE||'')}">${esc(r.cust_name||r.CUST_CODE||'')}</td>
         <td class="center mut">${esc(r.GAGONG_PROC_CODE||'')}</td>
         <td class="bcap" title="${esc(r.REMARKS||'')}">${esc(r.REMARKS||'')}</td>
         <td class="center mut">${esc(r.INSERT_USER_ID||'')}</td>
         <td class="center mut" title="${esc(String(r.INSERT_DATETIME||'').replace('T',' ').slice(0,19))}">${esc(_fmtDT(r.INSERT_DATETIME))}</td>${editMode?`<td class="center" style="white-space:nowrap"><span class="rowedit" data-key="${esc(k)}" title="수정" style="cursor:pointer;color:#2f6db3">✎</span> <span class="rowdel" data-key="${esc(k)}" title="삭제" style="cursor:pointer;color:#c0392b">🗑</span></td>`:''}</tr>`;
         }).join('')||`<tr><td colspan="${editMode?12:11}" class="empty">조회 결과 없음 — 기간/조건을 확인하세요</td></tr>`}</tbody></table></div>`}
       <style>
         .stk-wrap{max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;box-shadow:0 3px 12px rgba(30,45,70,.08)}
         .stk-tbl{font-size:12px}.stk-tbl th,.stk-tbl td{padding:3px 7px;white-space:nowrap}
         .stk-tbl thead th{text-align:center}      /* ★헤더 가운데 정렬(2026-08-28 사용자 요청) */
         /* ★매입처 [코드][🔍][거래처명] — 입력칸은 연노랑 배경으로 구분(레거시 조회조건 스타일).
            ⚠app.css 의 .inp{min-width:200px} 가 인라인 width 를 눌러버려서 폭이 안 줄었다.
              → min-width 를 함께 풀어야 실제로 좁아진다(2026-08-28). */
         .stk-ci{background:#fff8dc;border-color:#e0c97a;min-width:0}
         .stk-ci:focus{background:#fffdf2;border-color:#c9a227;outline:none}
         /* 조회 툴바 입력칸도 지정 폭이 먹게(기간·자도번 등) */
         .toolbar .inp{min-width:0}
         .stk-cbtn{padding:3px 7px;min-width:0;background:#2f6db3;color:#fff;border-color:#2f6db3}
         .stk-cbtn:hover{background:#255a96}
         .stk-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2}
         .stk-tbl td.bcap{max-width:160px;overflow:hidden;text-overflow:ellipsis}
         .stk-tbl td.mut,.stk-tbl .mut{color:var(--muted)}.stk-tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
         .stk-tbl td.neg{color:#c0392b}
         .stk-tag{display:inline-block;padding:1px 7px;border-radius:10px;background:#eef4ff;color:#2f5aa8;font-size:11px;font-weight:600}
         .stk-row{cursor:pointer}.stk-row:hover{background:#f4f8ff}
         .stk-tbl tr.sel{background:#e6f0ff !important;box-shadow:inset 3px 0 0 #1c47a0}
         .stk-new{margin:10px 0;padding:12px 14px;background:#f4fbf6;border:2px solid #1c7c3a;border-radius:10px;box-shadow:0 2px 10px rgba(28,124,58,.15)}
         .stk-new-h{font-weight:800;color:#1c7c3a;font-size:14px;margin-bottom:8px}
         .ce{border:1px solid var(--line);border-radius:4px;padding:2px 5px;font-size:12px}
       </style>`;
      // 핸들러
      const gv=id=>c.querySelector(id);
      // 거래처(매입처) 오토컴플리트: 값=거래처명, 저장시 코드매핑(규칙#21). 미해석시 입력값 그대로.
      let custT=null;
      const custSearch=v=>{clearTimeout(custT);v=(v||'').trim();if(v.length<1)return;
        custT=setTimeout(async()=>{try{const r=await fetch(`${STOCK_API}/api/item/vendorsearch?q=${encodeURIComponent(v)}`);const rr=(await r.json()).rows||[];
          const d=c.querySelector('#'+cdl);if(d)d.innerHTML=rr.map(x=>{custNames[(x.name||'').toLowerCase()]=x.code;return `<option value="${esc(x.name||'')}">${esc(x.code||'')}</option>`;}).join('');}catch(e){}},220);};
      const resolveCust=v=>{v=(v||'').trim();if(!v)return null;const code=custNames[v.toLowerCase()];return code||v;};
      gv('#stk-from').onchange=e=>fromV=e.target.value;
      gv('#stk-to').onchange=e=>toV=e.target.value;
      const qi=gv('#stk-q');qi.oninput=e=>q=e.target.value;qi.onkeyup=e=>{if(e.key==='Enter')list();};
      // ★매입처 [코드][🔍][거래처명] 3칸 연동 — 어느 쪽에 넣어도 나머지가 따라온다.
      //   코드칸 입력 → 이름 조회해 채움 · 이름칸 선택 → 코드 확정.
      //   조회 시 custQCode 가 있으면 그 거래처만(정확일치), 없으면 이름 LIKE.
      const ci=gv('#stk-cust'), cc=gv('#stk-custcode'), cf=gv('#stk-cfind');
      const nameOfCode=async code=>{code=(code||'').trim();if(!code)return '';
        try{const r=await fetch(`${STOCK_API}/api/item/vendorsearch?q=${encodeURIComponent(code)}`);
          const rr=(await r.json()).rows||[];
          const hit=rr.find(x=>String(x.code).trim().toLowerCase()===code.toLowerCase());
          if(hit){custNames[(hit.name||'').toLowerCase()]=hit.code;return hit.name||'';}
        }catch(e){}
        return '';};
      // ★업체코드 칸은 **코드/업체명 둘 다** 받는다(2026-08-28 사용자 요청).
      //   코드를 넣으면 → 옆 거래처명 채움
      //   업체명을 넣으면 → 그 칸을 코드로 바꾸고 옆에 이름 채움(레거시 코드검색 동작)
      if(cc){
        let ct2=null, composing=false;
        const resolveCC=async(v)=>{
          if(composing)return;                    // 조합 중이면 보류(끝난 뒤 다시 호출됨)
          v=(v||'').trim();
          if(!v){custQCode='';custQ='';if(ci)ci.value='';return;}
          try{
            const r=await fetch(`${STOCK_API}/api/item/vendorsearch?q=${encodeURIComponent(v)}`);
            const rr=(await r.json()).rows||[];
            rr.forEach(x=>{custNames[(x.name||'').toLowerCase()]=x.code;});
            // datalist: 코드칸에는 「코드 — 업체명」을 보여준다
            const dlc=c.querySelector('#'+cdl+'c');
            if(dlc)dlc.innerHTML=rr.map(x=>`<option value="${esc(x.code||'')}">${esc(x.name||'')}</option>`).join('');
            const lv=v.toLowerCase();
            let hit=rr.find(x=>String(x.code||'').trim().toLowerCase()===lv)      // 코드 정확일치
                 || rr.find(x=>String(x.name||'').trim().toLowerCase()===lv)      // 업체명 정확일치
                 || (rr.length===1?rr[0]:null);                                   // 후보 1개면 확정
            if(hit){
              custQCode=String(hit.code||'').trim();
              custQ=String(hit.name||'').trim();
              cc.value=custQCode;                 // ★업체명을 쳤어도 코드로 바꿔 표시
              if(ci)ci.value=custQ;
            }else{
              custQCode=v;                        // 미확정이면 입력값 그대로(부분검색)
            }
          }catch(e){}
        };
        // ★한글 IME 조합 중에는 value 를 덮어쓰지 않는다 — 「케이비」가 「케케이비」로 중복되던 버그.
        cc.addEventListener('compositionstart',()=>{composing=true;});
        cc.addEventListener('compositionend',()=>{composing=false;resolveCC(cc.value);});
        cc.oninput=e=>{const v=e.target.value;custQCode=v.trim();
          clearTimeout(ct2);if(composing||v.trim().length<1)return;
          ct2=setTimeout(()=>resolveCC(v),280);};
        cc.onchange=e=>{if(!composing)resolveCC(e.target.value);};
        cc.onkeyup=e=>{if(e.key==='Enter'&&!composing){resolveCC(cc.value).then(list);}};
      }
      if(cf)cf.onclick=()=>{if(ci){ci.focus();ci.select();}};
      if(ci){
        ci.oninput=e=>{custQ=e.target.value;custSearch(e.target.value);
          // 이름이 정확히 매칭되면 코드칸 자동채움
          setTimeout(()=>{const code=custNames[(custQ||'').trim().toLowerCase()];
            if(code){custQCode=code;if(cc)cc.value=code;}},260);};
        ci.onchange=e=>{custQ=e.target.value;
          const code=custNames[(custQ||'').trim().toLowerCase()];
          if(code){custQCode=code;if(cc)cc.value=code;}
          else if(!custQ.trim()){custQCode='';if(cc)cc.value='';}};
        ci.onkeyup=e=>{if(e.key==='Enter')list();};
      }
      gv('#stk-go').onclick=list;
      const rb=gv('#stk-ret');if(rb)rb.onclick=()=>{retMode=!retMode;news=[];editMode=false;editRowKey=null;list();};
      const ed=gv('#stk-edit');if(ed)ed.onclick=()=>{editMode=true;if(!news.length)addRow();draw();};
      const cx=gv('#stk-cancel');if(cx)cx.onclick=()=>{editMode=false;news=[];editRowKey=null;draw();};
      const ad=gv('#stk-add');if(ad)ad.onclick=addRow;
      const sv=gv('#stk-save');if(sv)sv.onclick=save;
      // ★팝업 방식(자재입고관리) — 등록=057 일괄 / 수정·삭제=055 단건
      const bk=gv('#stk-bulk');
      if(bk)bk.onclick=()=>openMatRecvPopup({cfg:CFG, ymd:toV, onSaved:list});
      // ★가공이동바코드(2026-08-28) — 가공이동계획(580)에서 발행한 이동전표를 읽어 자재창고 입고.
      //   전표=MV+MAINT_GROUP_SEQ. 백엔드 /api/matrecv/gagong_pending → /gagong_receive (tag='C').
      const bc=gv('#stk-bc');
      if(bc)bc.onclick=()=>openGagongMovePopup({ymd:toV, onSaved:list});
      if(POPUP){
        const openOne=(mode)=>{
          const i=rows.findIndex(r=>rowKey(r)===selKey);
          if(i<0){alert('행을 먼저 선택하세요. (행을 클릭하거나 더블클릭)');return;}
          openMatEditPopup({rows, index:i, mode, whs:whList, onSaved:list});
        };
        const md=gv('#stk-mod');if(md)md.onclick=()=>openOne('edit');
        const rm=gv('#stk-rm'); if(rm)rm.onclick=()=>openOne('del');
        c.querySelectorAll('tr.stk-row').forEach(tr=>{
          tr.onclick=()=>{                                  // 선택 하이라이트만(재렌더 X — 스크롤 유지)
            selKey=tr.dataset.key;
            c.querySelectorAll('tr.stk-row.sel').forEach(x=>x.classList.remove('sel'));
            tr.classList.add('sel');};
          tr.ondblclick=()=>{selKey=tr.dataset.key;openOne('edit');};
        });
        if(!whList.length){(async()=>{try{
          whList=((await (await fetch(`${STOCK_API}/api/stock/warehouses`)).json()).rows)||[];}catch(e){}})();}
      }
      gv('#stk-xls').onclick=()=>dlCSV(`${CFG.nm}_${_toYMD(fromV)}_${_toYMD(toV)}.csv`,
        ['일자','구분','자도번','품명','규격','수량','매입처','투입공정','비고','등록자','등록시간'],
        rows.map(r=>[_fmtY(r.MAINT_YMD),r.tag_name||r.MAINT_TAG,r.MAT_CODE,r.item_name,r.item_spec,r.qty,r.cust_name||r.CUST_CODE,r.GAGONG_PROC_CODE,r.REMARKS,r.INSERT_USER_ID,
          String(r.INSERT_DATETIME||'').replace('T',' ').slice(0,19)]));
      c.querySelectorAll('.stk-del').forEach(el=>el.onclick=()=>{news.splice(+el.dataset.i,1);draw();});
      c.querySelectorAll('.sn-date').forEach(el=>el.onchange=()=>{news[+el.dataset.i].MAINT_YMD=el.value;});
      c.querySelectorAll('.sn-tag').forEach(el=>el.onchange=()=>{news[+el.dataset.i].MAINT_TAG=el.value;});
      c.querySelectorAll('.sn-qty').forEach(el=>el.oninput=()=>{news[+el.dataset.i].qty=el.value;});
      c.querySelectorAll('.sn-cust').forEach(el=>{
        el.oninput=()=>{const i=+el.dataset.i;news[i].cust_name=el.value;news[i].CUST_CODE=resolveCust(el.value);custSearch(el.value);};
        el.onchange=()=>{const i=+el.dataset.i;news[i].cust_name=el.value;news[i].CUST_CODE=resolveCust(el.value);};});
      c.querySelectorAll('.sn-rmk').forEach(el=>el.oninput=()=>{news[+el.dataset.i].REMARKS=el.value;});
      let matT=null;
      c.querySelectorAll('.sn-mat').forEach(el=>{
        el.oninput=()=>{const i=+el.dataset.i,v=el.value.trim();news[i].MAT_CODE=v.toUpperCase();
          if(itemNames[v.toUpperCase()]!==undefined){news[i].item_name=itemNames[v.toUpperCase()];const tr=el.closest('tr');if(tr&&tr.querySelector('.sn-nm'))tr.querySelector('.sn-nm').textContent=itemNames[v.toUpperCase()];}
          clearTimeout(matT);if(v.length<2)return;
          matT=setTimeout(async()=>{try{const r=await fetch(`${STOCK_API}/api/bom/search?q=${encodeURIComponent(v)}&all_active=1`);const rr=(await r.json()).rows||[];
            const d=c.querySelector('#'+dl);if(d)d.innerHTML=rr.map(x=>{itemNames[x.item]=x.name||'';return `<option value="${esc(x.item)}">${esc(x.name||'')}</option>`;}).join('');}catch(e){}},250);};
        el.onchange=()=>{const i=+el.dataset.i,code=el.value.trim().toUpperCase();news[i].MAT_CODE=code;
          if(itemNames[code]!==undefined){news[i].item_name=itemNames[code];const tr=el.closest('tr');if(tr&&tr.querySelector('.sn-nm'))tr.querySelector('.sn-nm').textContent=itemNames[code];}};
      });
      // 기존행 인라인 수정·삭제
      c.querySelectorAll('.rowedit').forEach(el=>el.onclick=()=>{editRowKey=el.dataset.key;draw();});
      c.querySelectorAll('.rowdel').forEach(el=>el.onclick=()=>{const r=rows.find(x=>rowKey(x)===el.dataset.key);if(r)deleteRow(r);});
      const rec=c.querySelector('.re-cust');if(rec)rec.oninput=()=>custSearch(rec.value);
      const rc=c.querySelector('.re-cancel');if(rc)rc.onclick=()=>{editRowKey=null;draw();};
      const rs=c.querySelector('.re-save');if(rs)rs.onclick=()=>{const r=rows.find(x=>rowKey(x)===editRowKey);if(!r)return;
        const g=s=>c.querySelector('.stk-editing '+s);
        const qv=Number(g('.re-qty').value);
        if(CFG.signed){if(qv===0){alert('조정수량은 0일 수 없습니다(증가 +, 감소 −).');return;}}
        else if(!(qv>0)){alert('수량은 0보다 커야 합니다.');return;}
        updateRow(r,{MAINT_TAG:g('.re-tag').value,qty:qv,CUST_CODE:resolveCust(g('.re-cust').value),
          GAGONG_PROC_CODE:g('.re-proc').value.trim()||null,REMARKS:g('.re-rmk').value.trim()||null});};
    };
    list();
  };
}
Object.keys(STOCK_CFG).forEach(id=>SCREEN[id]=stockScreen(id));

/* ==== 자재출고관리 (구매/자재, 레거시 w_pu_stock_150 동일 조회) — PU_T_STOCK_MAINT TAG='B' 라이브 ==== */
/* 레거시 13컬럼(출고일자/SEQ/FROM파트창고/P·N/TO창고구분/TO파트창고/자도번/출고수량/출고단가/출고금액/비고/작업자/작업일시).
   서버 집계(건수·수량합)로 500 cap 부분합 문제 제거. 라이브 PARTNER_ERP 읽기전용(사용자 대조용). */

/* ==== 매출마감처리 (w_pu_sale_020 재설계) — 협력사 매출 업체별 마감·조정·사유 ==== */
const _mkMagam=(CFG)=>(c)=>{
  const API=API_BASE;
  const CT=DB.custTypeNames||{};
  const ctN=t=>CT[(''+t).trim()]||(''+t).trim()||'';
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-','');
  // ★월 입력 견고화(2026-09-01): 네이티브 <input type="month">는 한국어 로케일에서 연도 세그먼트가 먼저라
  //   "08" 타이핑이 연도로 들어가 월이 안 바뀌는 오동작이 있음. (a)연도 가드로 비정상 연도(20xx 밖) 거부,
  //   (b)◀▶ 버튼으로 월 이동을 확실하게. YYMM 기준 delta 이동(연 넘김 처리).
  const ymValid=raw=>{const m=/^(\d{4})-(\d{2})$/.exec((''+(raw||'')).trim());return m&&+m[1]>=2015&&+m[1]<=2099&&+m[2]>=1&&+m[2]<=12;};
  const shiftYm=(y,delta)=>{y=(''+(y||'')).trim();if(y.length<4)return y;const tot=(+y.slice(0,2))*12+(+y.slice(2,4)-1)+delta;const ny=Math.floor(tot/12),nm=(tot%12)+1;return String(ny).padStart(2,'0')+String(nm).padStart(2,'0');};
  const canW=(typeof PERM!=='undefined')?PERM.canEdit(CFG.base):true;   // 수정권한 게이트(규칙#16)
  let ym='', rows=[], loading=false, msg='', reasons=[], q='', wmap={}, realRaw=25000, sagubRaw=20000;
  let sortKey='', sortDir=1, ctf='';   // 정렬키·방향(1오름/-1내림)·분류필터
  // ★2026-08-23 P/No 펼침(레거시 w_pu_sale_010) — 집계를 자도번 단위로 풀어서 본다.
  //   view='sum'(기존 거래처집계, 마감/계산서) | 'line'(P/No 상세)
  //   basis='magam'(거래처별 마감일 창) | 'input'(입고기간 fr~to, 기본 당월1일~오늘)
  let view='sum', basis='magam', lrows=[], ldays=[], lLoading=false, lcnt=0, ltotq=0, ltota=0, lq='';
  let lsel=new Set();          // ★단가재계산 체크(레거시 select_flag) — 키 = cc|mat
  const _pad=n=>String(n).padStart(2,'0');
  const _isoToday=()=>{const d=new Date();return `${d.getFullYear()}-${_pad(d.getMonth()+1)}-${_pad(d.getDate())}`;};
  const _isoM1=()=>{const d=new Date();return `${d.getFullYear()}-${_pad(d.getMonth()+1)}-01`;};
  let lfr=_isoM1(), lto=_isoToday();
  const _y6=v=>(''+(v||'')).slice(2).replace(/-/g,'');     // 2026-08-01 → 260801
  const _d2=s=>{s=''+(s||'');return s.length===6?`${s.slice(2,4)}/${s.slice(4,6)}`:s;};   // 260801 → 08/01
  // 모달 상태
  let mc=null, detail=null, mLoading=false, mClosed=false, pEdit={}, dEdit={}, amtAdjs=[], expanded=new Set();
  // ★상단 품목별/일자별 통합 — 2026-09-01. detail.items[].byday[].carry(1=이월,매출금액0).
  //   view2='item'(품목별)|'day'(일자별 평면). 체크박스 선택 → 이월 버튼 1개로 이월/이월해제.
  let carryNextYm='', carryBusy=false, view2='item', selRows=new Set(), fromDt='', toDt='';
  const dkey=(mat,d)=>mat+'|'+d;
  const ymd6=d=>(''+ym).slice(0,4)+String(d).padStart(2,'0');
  const num=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const won0=n=>Math.round(Number(n||0)).toLocaleString('ko-KR');

  const load=async(y)=>{loading=true;msg='';draw();
    try{const r=await fetch(`${API}/api/${CFG.base}/list?ym=${encodeURIComponent(y||'')}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();rows=j.rows||[];ym=j.ym||y||'';
      if(CFG.weight){try{const rw=await fetch(`${API}/api/${CFG.base}/weight_quote?ym=${encodeURIComponent(ym)}`);const jw=await rw.json();wmap={};(jw.rows||[]).forEach(w=>{wmap[w.cc]={raw_out:w.raw_out,raw_in:w.raw_in,raw_diff:w.raw_diff,raw_amt:w.settle_amt,weld_out:w.weld_out,weld_in:w.weld_in,weld_diff:w.weld_diff,weld_amt:w.weld_amt,specs:w.specs,unmapped_out:w.unmapped_out};});}catch(e){wmap={};}}}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];}
    loading=false;draw();};
  const ensureReasons=async()=>{if(reasons.length)return;try{const r=await fetch(`${API}/api/salemagam/reasons`);reasons=(await r.json()).rows||[];}catch(e){}};

  // ★P/No 펼침 조회 — 집계와 동일 원천·동일 마감창, GROUP BY만 자도번 단위
  const loadLines=async()=>{lLoading=true;msg='';lsel.clear();draw();
    try{let u=`${API}/api/${CFG.base}/lines?ym=${encodeURIComponent(ym||'')}&basis=${basis}`;
      if(basis==='input')u+=`&fr=${_y6(lfr)}&to=${_y6(lto)}`;
      if(lq.trim())u+=`&q=${encodeURIComponent(lq.trim())}`;
      if(q.trim())u+=`&cust=${encodeURIComponent(q.trim())}`;
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();lrows=j.rows||[];ldays=j.days||[];lcnt=j.cnt||0;ltotq=j.totqty||0;ltota=j.totamt||0;
      lrows.forEach((x,i)=>{x._ix=i;});    // ★행 고유키(체크박스용) — 같은 cc/mat 이 단가·모도번별로 여러행
      if(j.ym)ym=j.ym;}
    catch(e){msg='조회 실패 — '+e.message;lrows=[];ldays=[];lcnt=0;ltotq=0;ltota=0;}
    lLoading=false;draw();};

  const filt=()=>{const k=q.trim().toLowerCase();return rows.filter(r=>(!k||(''+r.cc).toLowerCase().includes(k)||(''+r.nm).toLowerCase().includes(k)||(''+r.chg).toLowerCase().includes(k))&&(!ctf||ctN(r.ct)===ctf));};
  const finw0=(r)=>(+r.final_amt||0)+((wmap[r.cc]||{}).raw_amt||0)+((wmap[r.cc]||{}).weld_amt||0);
  const SVAL=(r,key)=>{const w=wmap[r.cc]||{};switch(key){   // 정렬값 접근자(문자=코드/명/담당/분류, 그외 숫자)
    case 'cc':return (''+r.cc); case 'nm':return (''+r.nm); case 'chg':return (''+r.chg); case 'ct':return ctN(r.ct);
    case 'qty':return +r.qty||0; case 'amt':return +r.amt||0;
    case 'raw_out':return +w.raw_out||0; case 'raw_in':return +w.raw_in||0; case 'raw_diff':return +w.raw_diff||0;
    case 'weld_out':return +w.weld_out||0; case 'weld_in':return +w.weld_in||0; case 'weld_diff':return +w.weld_diff||0;
    case 'adj_amt':return +r.adj_amt||0; case 'raw_amt':return +w.raw_amt||0; case 'weld_amt':return +w.weld_amt||0;
    case 'finw':return CFG.weight?finw0(r):(+r.final_amt||0); case 'close_flag':return +r.close_flag||0; default:return 0;}};
  const sortList=(list)=>{if(!sortKey)return list;const cp=list.slice();
    cp.sort((a,b)=>{const va=SVAL(a,sortKey),vb=SVAL(b,sortKey);
      if(typeof va==='string'||typeof vb==='string')return sortDir*(''+va).localeCompare(''+vb,'ko');
      return sortDir*((va||0)-(vb||0));});return cp;};
  const sa=k=>sortKey===k?`<span class="sm-ar">${sortDir>0?'▲':'▼'}</span>`:'';   // 정렬 화살표(헤더 구조 불변, span만 추가)

  // ★P/No 펼침 그리드(레거시 w_pu_sale_010 배치) — 거래처 첫행에만 코드·거래처명, 거래처 끝에 (업체계)
  /* ★엑셀 다운로드 — 현재 보고 있는 그리드 그대로(집계/상세 각각, 일자컬럼 포함).
     2026-08-28 사용자요청. 화면 = 파일 원칙(보이는 컬럼만·보이는 순서대로). */
  const exportXls=()=>{
    const tag=(CFG.base==='purmagam'?'매입마감':'매출마감');
    if(view==='line'){
      if(!lrows.length){alert('내보낼 자료가 없습니다.');return;}
      const hasModa=CFG.base==='purmagam';
      const H=['구분','거래처코드','거래처명'].concat(hasModa?['모도번']:[])
              .concat(['자도번','PART DESC','PART SPEC','단위','단가','합계수량','합계금액'])
              .concat(ldays.map(d=>_d2(d)));
      const gubun=hasModa?'구매(국내)':'매출';
      const rows=lrows.map(r=>[gubun,r.cc,r.cnm||''].concat(hasModa?[r.moda||'']:[])
        .concat([r.mat||'',r.nm||'',r.spec||'',r.unit||'',r.cost||0,r.qty||0,r.amt||0])
        .concat(ldays.map(d=>(r.byday&&r.byday[d])||0)));
      rows.push(['총계','','' ].concat(hasModa?['']:[]).concat(['','','','','',ltotq,ltota])
        .concat(ldays.map(d=>lrows.reduce((a,b)=>a+((b.byday&&b.byday[d])||0),0))));
      const per=(basis==='input'?`입고 ${lfr}~${lto}`:`마감 ${ymToInput(ym)}`);
      downloadCSV(`${tag}_PNo상세_${per.replace(/[^0-9]/g,'')}.csv`,H,rows);
    }else{
      // cur/tAmt 는 draw() 지역이라 여기서 같은 방식으로 다시 만든다(정렬·필터 반영).
      const cur=sortList(filt());
      if(!cur.length){alert('내보낼 자료가 없습니다.');return;}
      const tAmt=cur.reduce((a,b)=>a+(+b.amt||0),0),
            tFin=cur.reduce((a,b)=>a+(+b.final_amt||0),0),
            tAdj=cur.reduce((a,b)=>a+(+b.adj_amt||0),0);
      // 중량정산 6컬럼은 wmap(별도 API)에서. finw 는 draw() 지역함수라 여기서 직접 합산.
      const wH=CFG.weight?['원소재출고','원소재소요','원소재차액','용접봉출고','용접봉소요','용접봉차액','원소재정산','용접봉정산']:[];
      const H=['코드','거래처명','담당자','분류','수량',(CFG.amtlbl||'금액')]
              .concat(wH).concat(['조정','최종금액','상태']);
      const _fw=r=>{const w=wmap[r.cc]||{};return (+r.final_amt||0)+(+w.raw_amt||0)+(+w.weld_amt||0);};
      const rows=cur.map(r=>{const w=wmap[r.cc]||{};
        return [r.cc,r.nm,r.chg||'',ctN(r.ct),r.qty||0,r.amt||0]
        .concat(CFG.weight?[w.raw_out||0,w.raw_in||0,w.raw_diff||0,w.weld_out||0,w.weld_in||0,w.weld_diff||0,w.raw_amt||0,w.weld_amt||0]:[])
        .concat([r.adj_amt||0,(CFG.weight?_fw(r):r.final_amt)||0,r.close_flag?'마감':'미마감']);});
      rows.push(['총계','','','',cur.reduce((a,b)=>a+(+b.qty||0),0),tAmt]
        .concat(CFG.weight?['','','','','','','','']:[])
        .concat([tAdj,(CFG.weight?cur.reduce((a,r)=>a+_fw(r),0):tFin),'']));
      downloadCSV(`${tag}_거래처집계_${(ym||'')}.csv`,H,rows);
    }
  };

  /* ★단가 재계산 — 레거시 w_pu_sale_010(매입)/020(매출) 'cost_calc' 이식.
     체크(select_flag)한 행마다 (거래처 + 자도번 + 조회기간) 으로
     원장의 단가·금액·부가세를 단가마스터 최신값으로 다시 쓴다.
       매입 = 확정입고(9/S) × 매입단가 · 매출 = 협력사판매(5) × 매출단가(TAGS/TAGE)
     마스터단가 0원인 행은 레거시와 동일하게 건드리지 않는다. */
  const recalcCost=async()=>{
    if(!canW){alert('권한이 없습니다.');return;}
    if(!lsel.size){alert('재계산할 행을 체크하세요.');return;}
    // 기간 = 현재 조회조건(레거시 c_as_from_ymd/c_as_to_ymd 와 같은 의미)
    let fr,to;
    if(basis==='input'){fr=_y6(lfr);to=_y6(lto);}
    else{const y=(ym||'');fr=y+'01';to=y+'31';}   // 마감년월 = 그 달 전체
    if(!(fr.length===6&&to.length===6)){alert('조회기간을 확인하세요.');return;}
    // 체크행 → 재계산 단위(거래처+자도번). 단가만 다른 행들은 같은 단위로 합쳐진다.
    const seen=new Set(), items=[];
    [...lsel].forEach(k=>{const r=lrows[+k];if(!r)return;
      const u=`${r.cc}|${r.mat||''}`;
      if(!seen.has(u)){seen.add(u);items.push({cc:r.cc,mat:r.mat||''});}});
    if(!items.length){alert('재계산할 행을 체크하세요.');return;}
    const per=(basis==='input'?`입고 ${lfr} ~ ${lto}`:`마감 ${ymToInput(ym)} (${fr}~${to})`);
    const dup=(lsel.size>items.length)?`\n(체크 ${lsel.size}행 중 거래처·자도번이 겹치는 행은 ${items.length}건으로 합산)`:'';
    const tgt=(CFG.base==='purmagam')?'확정입고(9=개별, S=세트)':'협력사판매(5)';
    if(!confirm(`체크한 ${lsel.size}행 / ${items.length}건에 대해 ${CFG.verb}단가 재계산 작업을 하시겠습니까?${dup}\n\n기간: ${per}\n대상: ${tgt}\n\n※ 원장의 단가·금액·부가세가 갱신됩니다.`))return;
    const btn=c.querySelector('#sm-recalc');if(btn){btn.disabled=true;btn.textContent='🧮 재계산중…';}
    try{
      const r=await fetch(`${API}/api/${CFG.base}/recalc_cost`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({fr,to,items})});
      if(r.status===404||r.status===501){alert('단가재계산 기능이 서버에 아직 없습니다.');return;}
      const j=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(j.detail||('HTTP '+r.status));
      const ch=j.changed||[];
      let m=`${CFG.verb}단가 재계산 작업이 완료되었습니다.\n\n선택 ${num(j.pairs||0)}건 · 대상원장 ${num(j.scanned||0)}행 · 단가변경 ${num(ch.length)}행`;
      if(ch.length)m+='\n\n[변경내역]\n'+ch.slice(0,15).map(x=>
        `${x.mat} (${x.cc}) ${_d2(x.ymd)}  ${won0(x.old)} → ${won0(x.new)}`).join('\n')
        +(ch.length>15?`\n… 외 ${ch.length-15}건`:'');
      else m+='\n\n※ 마스터 단가와 이미 같아 변경된 행이 없습니다.';
      alert(m);
      lsel.clear(); loadLines();
    }catch(e){alert(`${CFG.verb}단가 재계산 작업시 오류가 발생하였습니다.\n\n`+e.message);}
    finally{const b2=c.querySelector('#sm-recalc');if(b2){b2.disabled=false;b2.textContent=`🧮 ${CFG.verb}단가 재계산`;}}
  };

  const drawLines=()=>{
    const dcols=ldays;                               // 일자 컬럼(YYMMDD)
    const gubun=CFG.base==='purmagam'?'구매(국내)':'매출';
    // ★매출(tag5)은 단품기준 — 원천에 상위품번(ITEM_CODE)이 없어 모도번 컬럼 자체를 뺀다.
    //   매입은 모도번별로 행이 갈린다(같은 자도번이라도 상위품번 다르면 별개 행 = 레거시 동일).
    const hasModa=CFG.base==='purmagam';
    const CK=(CFG.recalc&&canW)?1:0;                 // ★재계산 체크박스 컬럼(레거시 select_flag)
    const FIX=(hasModa?11:10)+CK;                    // 고정컬럼 수(일자 제외)
    // 거래처 블록 단위로 행 생성(소계 포함)
    const body=[];let i=0;
    while(i<lrows.length){
      const cc=lrows[i].cc;const blk=[];
      while(i<lrows.length&&lrows[i].cc===cc){blk.push(lrows[i]);i++;}
      blk.forEach((r,k)=>{
        const first=k===0;
        // ★행키 = lrows 인덱스(모도번·단가가 달라도 별개 행이라 cc|mat 로는 겹친다)
        const rk=String(r._ix);
        body.push(`<tr class="ml-row${first?' ml-first':''}">
          ${CK?`<td class="center"><input type="checkbox" class="ml-ck" data-k="${rk}" ${lsel.has(rk)?'checked':''}></td>`:''}
          <td class="center">${first?esc(gubun):''}</td>
          <td class="center">${first?`<b>${esc(r.cc)}</b>`:''}</td>
          <td class="bcap" title="${esc(r.cnm||'')}">${first?esc(r.cnm||''):''}</td>
          ${hasModa?`<td>${esc(r.moda||'')}</td>`:''}
          <td><b>${esc(r.mat||'')}</b></td>
          <td class="bcap" title="${esc(r.nm||'')}">${esc(r.nm||'')}</td>
          <td class="bcap" title="${esc(r.spec||'')}">${esc(r.spec||'')}</td>
          <td class="center">${esc(r.unit||'')}</td>
          <td class="num">${num(r.cost)}</td>
          <td class="num">${num(r.qty)}</td>
          <td class="num">${won0(r.amt)}</td>
          ${dcols.map(d=>`<td class="num mld">${r.byday&&r.byday[d]?num(r.byday[d]):'0'}</td>`).join('')}
        </tr>`);});
      const sq=blk.reduce((a,b)=>a+(+b.qty||0),0), sa2=blk.reduce((a,b)=>a+(+b.amt||0),0);
      body.push(`<tr class="ml-sub">
        <td colspan="${FIX-3}" class="right">(업체계)</td><td></td>
        <td class="num"><b>${num(sq)}</b></td><td class="num"><b>${won0(sa2)}</b></td>
        ${dcols.map(d=>`<td class="num">${num(blk.reduce((a,b)=>a+((b.byday&&b.byday[d])||0),0))}</td>`).join('')}
      </tr>`);
    }
    return `
     <div class="grid-wrap sm-wrap"><table class="tbl sm-tbl ml-tbl"><thead><tr>
       ${CK?'<th class="center" title="전체선택"><input type="checkbox" id="ml-ckall"></th>':''}
       <th>구분</th><th>거래처코드</th><th>거래처명</th>${hasModa?'<th>모도번</th>':''}<th>자도번</th>
       <th>PART DESC</th><th>PART SPEC</th><th>단위</th><th class="num">단가</th>
       <th class="num">합계수량</th><th class="num">합계금액</th>
       ${dcols.map(d=>`<th class="num mld">${esc(_d2(d))}</th>`).join('')}
     </tr></thead>
     <tbody>${lLoading?spinRow(FIX+dcols.length):(body.length?body.join(''):`<tr><td colspan="${FIX+dcols.length}" class="empty">조회 결과 없음</td></tr>`)}</tbody>
     ${body.length?`<tfoot><tr class="grandtot">
       <td colspan="${FIX-2}" class="right">총계 (${lcnt}건)</td>
       <td class="num"><b>${num(ltotq)}</b></td><td class="num"><b>${won0(ltota)}</b></td>
       ${dcols.map(d=>`<td class="num">${num(lrows.reduce((a,b)=>a+((b.byday&&b.byday[d])||0),0))}</td>`).join('')}
     </tr></tfoot>`:''}
     </table></div>`;
  };

  const draw=()=>{
    const cur=sortList(filt());
    const cts=[...new Set(rows.map(r=>ctN(r.ct)).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ko'));   // 분류 드롭다운 옵션
    const tAmt=cur.reduce((a,b)=>a+(+b.amt||0),0), tFin=cur.reduce((a,b)=>a+(+b.final_amt||0),0), tAdj=cur.reduce((a,b)=>a+(+b.adj_amt||0),0);
    const nClosed=cur.filter(r=>r.close_flag).length;
    const wTot=cur.reduce((a,b)=>{const w=wmap[b.cc]||{};a.out+=+w.raw_out||0;a.in+=+w.raw_in||0;a.diff+=+w.raw_diff||0;a.amt+=+w.raw_amt||0;a.wo+=+w.weld_out||0;a.wi+=+w.weld_in||0;a.wd+=+w.weld_diff||0;a.wa+=+w.weld_amt||0;return a;},{out:0,in:0,diff:0,amt:0,wo:0,wi:0,wd:0,wa:0});
    const _n=v=>(v!=null?num(v):''),_w=v=>(v!=null?won0(v):'');
    // 중량 6컬럼: 원소재(출고·소요·차액) + 용접봉(출고·소요·차액, 빈칸)
    const wc=(cc)=>{const w=wmap[cc]||{};
      return '<td class="num wcol">'+_n(w.raw_out)+'</td><td class="num wcol">'+_n(w.raw_in)+'</td><td class="num wcol '+(w.raw_diff<0?'neg':'')+'">'+_n(w.raw_diff)+'</td>'+
        '<td class="num wcol2">'+_n(w.weld_out)+'</td><td class="num wcol2">'+_n(w.weld_in)+'</td><td class="num wcol2 '+((w.weld_diff||0)<0?'neg':'')+'">'+_n(w.weld_diff)+'</td>';};
    // 조정 3컬럼: 단가조정 · 원소재정산 · 용접봉정산
    const spTip=(w)=>((w.specs||[]).slice(0,12).map(s=>`${s.mat} Φ${s.od}: 재고 ${num(s.diff)}kg ×(${won0((s.spot||0)-(s.sagub||0))}) = ${won0(s.amt)}`).join('&#10;'))||'';
    const ac=(r)=>{const w=wmap[r.cc]||{};
      return '<td class="num acol '+(r.adj_amt<0?'neg':'')+'">'+(r.adj_amt?won0(r.adj_amt):'')+'</td>'+
        '<td class="num acol '+((w.raw_amt||0)<0?'neg':'')+'" title="'+spTip(w)+'">'+_w(w.raw_amt)+'</td>'+
        '<td class="num acol '+((w.weld_amt||0)<0?'neg':'')+'">'+(w.weld_amt?won0(w.weld_amt):'')+'</td>';};
    const finw=(r)=>(+r.final_amt||0)+((wmap[r.cc]||{}).raw_amt||0)+((wmap[r.cc]||{}).weld_amt||0);
    const NC=CFG.weight?18:10, amtl=CFG.amtlbl;
    const THEAD=CFG.weight?`<thead>
       <tr>
         <th rowspan="2" data-sk="cc">코드${sa('cc')}</th><th rowspan="2" data-sk="nm">거래처명${sa('nm')}</th><th rowspan="2" data-sk="chg">담당자${sa('chg')}</th><th rowspan="2" data-sk="ct">분류${sa('ct')}</th>
         <th rowspan="2" class="num" data-sk="qty">수량${sa('qty')}</th><th rowspan="2" class="num" data-sk="amt">${amtl}${sa('amt')}</th>
         <th colspan="3" class="center wcol">원소재 <small>kg</small></th>
         <th colspan="3" class="center wcol2">용접봉 <small>kg</small></th>
         <th colspan="3" class="center acol">조정 <small>원</small></th>
         <th rowspan="2" class="num" data-sk="finw">최종금액${sa('finw')}</th>
         <th rowspan="2" class="center" data-sk="close_flag">상태${sa('close_flag')}</th><th rowspan="2" class="center">처리</th>
       </tr>
       <tr>
         <th class="num wcol" data-sk="raw_out">출고${sa('raw_out')}</th><th class="num wcol" data-sk="raw_in">소요${sa('raw_in')}</th><th class="num wcol" data-sk="raw_diff">차액${sa('raw_diff')}</th>
         <th class="num wcol2" data-sk="weld_out">출고${sa('weld_out')}</th><th class="num wcol2" data-sk="weld_in">소요${sa('weld_in')}</th><th class="num wcol2" data-sk="weld_diff">차액${sa('weld_diff')}</th>
         <th class="num acol" data-sk="adj_amt">단가조정${sa('adj_amt')}</th><th class="num acol" data-sk="raw_amt">원소재정산${sa('raw_amt')}</th><th class="num acol" data-sk="weld_amt">용접봉정산${sa('weld_amt')}</th>
       </tr></thead>`:`<thead><tr>
         <th data-sk="cc">코드${sa('cc')}</th><th data-sk="nm">거래처명${sa('nm')}</th><th data-sk="chg">담당자${sa('chg')}</th><th data-sk="ct">분류${sa('ct')}</th><th class="num" data-sk="qty">수량${sa('qty')}</th><th class="num" data-sk="amt">${amtl}${sa('amt')}</th><th class="num" data-sk="adj_amt">조정${sa('adj_amt')}</th><th class="num" data-sk="finw">최종금액${sa('finw')}</th><th class="center" data-sk="close_flag">상태${sa('close_flag')}</th><th class="center">처리</th>
       </tr></thead>`;
    const rowMid=(r)=>CFG.weight?`${wc(r.cc)}${ac(r)}<td class="num"><b>${won0(finw(r))}</b></td>`:`<td class="num ${r.adj_amt<0?'neg':''}">${r.adj_amt?won0(r.adj_amt):''}</td><td class="num"><b>${won0(r.final_amt)}</b></td>`;
    const gtMid=CFG.weight?`<td class="num">${num(wTot.out)}</td><td class="num">${num(wTot.in)}</td><td class="num ${wTot.diff<0?'neg':''}">${num(wTot.diff)}</td><td class="num wcol2">${num(wTot.wo)}</td><td class="num wcol2">${num(wTot.wi)}</td><td class="num wcol2 ${wTot.wd<0?'neg':''}">${num(wTot.wd)}</td><td class="num">${won0(tAdj)}</td><td class="num ${wTot.amt<0?'neg':''}"><b>${won0(wTot.amt)}</b></td><td class="num acol ${wTot.wa<0?'neg':''}">${wTot.wa?won0(wTot.wa):''}</td><td class="num"><b>${won0(tFin+wTot.amt+wTot.wa)}</b></td>`:`<td class="num">${won0(tAdj)}</td><td class="num"><b>${won0(tFin)}</b></td>`;
    c.innerHTML=`
     <div class="sm-root" style="display:flex;flex-direction:column;height:100%;min-height:0">
     <div class="page-title">${CFG.title} <span style="font-size:12px;color:var(--muted);font-weight:400">${CFG.sub} · 거래처별 마감 · nx 저장</span></div>
     <div class="page-sub">거래처별 ${CFG.verb} 집계 → [마감]에서 품목×일자·단가변경·총액조정·사유 입력 후 확정. 원본 <code>${CFG.src}</code> · 🔴 라이브 마감기준 ${esc(ymToInput(ym)||'-')}</div>
     ${CFG.weight?`<div class="page-sub" style="color:#3a6ea5">⚖️ LME 중량정산(견적기준): [출고(tag5) − 견적소요] × (현물가 − 사급가). <b>원소재</b>=규격(재질·외경)별 nx.price_metal · <b>용접봉</b>=1% 단일단가(현물 62,700 / 사급 21,100). 협력사(수테크=소요만). 원소재정산 셀 툴팁=규격내역.</div>`:''}
     <div class="toolbar">
       <label class="tl">보기</label>
       <select class="inp" id="sm-view" style="width:auto"><option value="sum" ${view==='sum'?'selected':''}>거래처 집계</option><option value="line" ${view==='line'?'selected':''}>P/No 상세</option></select>
       ${view==='line'?`
         <label class="tl" style="margin-left:8px">조회기준</label>
         <select class="inp" id="sm-basis" style="width:auto"><option value="magam" ${basis==='magam'?'selected':''}>마감기준</option><option value="input" ${basis==='input'?'selected':''}>입고기준</option></select>
         ${basis==='input'
           ?`<label class="tl">입고기간</label><input type="date" class="inp" id="sm-fr" value="${esc(lfr)}" style="width:150px"><span class="mut">~</span><input type="date" class="inp" id="sm-to" value="${esc(lto)}" style="width:150px">`
           :`<label class="tl">마감년월</label><button class="btn" id="sm-ymp" title="이전 월" style="padding:2px 7px">◀</button><input type="month" class="inp" id="sm-ym" value="${esc(ymToInput(ym))}" style="min-width:120px"><button class="btn" id="sm-ymn" title="다음 월" style="padding:2px 7px">▶</button>`}
         <label class="tl">자도번</label><input class="inp" id="sm-lq" value="${esc(lq)}" placeholder="자도번/품명" style="width:130px">
       `:`
         <label class="tl" style="margin-left:8px">마감년월</label><button class="btn" id="sm-ymp" title="이전 월" style="padding:2px 7px">◀</button><input type="month" class="inp" id="sm-ym" value="${esc(ymToInput(ym))}" style="min-width:120px"><button class="btn" id="sm-ymn" title="다음 월" style="padding:2px 7px">▶</button>
       `}
       <label class="tl">거래처</label><input class="inp" id="sm-q" value="${esc(q)}" placeholder="코드/거래처명${view==='line'?'':'/담당자'}" style="width:180px">
       ${view==='sum'?`<label class="tl">분류</label><select class="inp" id="sm-ct" style="width:auto"><option value="">전체</option>${cts.map(t=>`<option value="${esc(t)}" ${ctf===t?'selected':''}>${esc(t)}</option>`).join('')}</select>`:''}
       <button class="btn" id="sm-go">🔍 조회</button>
       <button class="btn xls" id="sm-xls">📥 엑셀</button>
       <!-- ★단가 재계산(레거시 w_pu_sale_010/020 'cost_calc' 이식) — 체크한 행만 처리.
            P/No 상세에서만 노출. 매입=확정입고(9/S)·매출=협력사판매(5). 2026-08-28 -->
       ${(view==='line'&&CFG.recalc&&canW)
         ?`<button class="btn" id="sm-recalc" style="background:#7a5c1e;color:#fff;border-color:#7a5c1e"
                   title="체크한 행의 ${CFG.verb}단가를 단가마스터 기준으로 재계산합니다(레거시 동일)">🧮 ${CFG.verb}단가 재계산</button>`:''}
       <div class="spacer"></div>
       ${view==='line'
         ?`<span class="rowcount">${lcnt}건 · 수량 <b>${num(ltotq)}</b> · 금액 <b>${won0(ltota)}</b></span>`
         :`<span class="rowcount">${cur.length}업체 · 마감 ${nClosed}/${cur.length} · 금액 <b>${won0(tAmt)}</b> → 최종 <b>${won0(tFin)}</b>${tAdj?` (조정 ${won0(tAdj)})`:''}</span>`}
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     ${view==='line'?drawLines():`
     <div class="grid-wrap sm-wrap"><table class="tbl sm-tbl">${THEAD}
     <tbody>${loading?spinRow(NC):(cur.length?cur.map(r=>`<tr class="${r.close_flag?'sm-closed':''}">
       <td><b>${esc(r.cc)}</b></td><td class="bcap" title="${esc(r.nm)}">${esc(r.nm)}</td>
       <td class="center">${esc(r.chg)||'-'}</td><td>${esc(ctN(r.ct))}</td>
       <td class="num">${num(r.qty)}</td><td class="num">${won0(r.amt)}</td>
       ${rowMid(r)}
       <td class="center">${r.close_flag?'<span class="sm-badge on">🔒 마감</span>':'<span class="sm-badge">미마감</span>'}</td>
       <td class="center" style="white-space:nowrap">
         <button class="btn sm-mini sm-open" data-cc="${esc(r.cc)}" data-nm="${esc(r.nm)}">${(r.close_flag||!canW)?'상세':'✎ 마감'}</button>
         <button class="btn sm-mini ghost" title="계산서 발행(추후 구현)" disabled>🧾 계산서</button>
       </td></tr>`).join('')+`<tr class="grandtot"><td colspan="4" class="right">총계 (${cur.length}업체)</td><td class="num">${num(cur.reduce((a,b)=>a+(+b.qty||0),0))}</td><td class="num">${won0(tAmt)}</td>${gtMid}<td colspan="2"></td></tr>`:`<tr><td colspan="${NC}" class="empty">해당 마감월 ${CFG.verb} 없음</td></tr>`)}</tbody></table></div>`}
     </div>
     <div id="sm-modal"></div>
     <style>
       /* ★표 아래 공백 제거 — flex:1(남는높이 다먹음) 대신 0 1 auto+max-height:100%.
          행이 적으면 내용만큼만, 많으면 화면끝까지 늘고 내부스크롤. 2026-08-28 */
       .sm-wrap{flex:0 1 auto;min-height:0;max-height:100%;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;box-shadow:0 3px 12px rgba(30,45,70,.08)}
       /* ★P/No 펼침 그리드(레거시 w_pu_sale_010) */
       .ml-tbl{font-size:12px;white-space:nowrap}
       .ml-tbl th,.ml-tbl td{padding:2px 6px}
       .ml-tbl thead th{position:sticky;top:0;background:#dbe6f5;z-index:2;border-bottom:1px solid #9db4d4;text-align:center}
       .ml-tbl tbody tr.ml-first td{border-top:1px solid #b9cbe4}
       .ml-tbl tbody tr:hover td{background:#eaf2fd}
       .ml-tbl tr.ml-sub td{background:#cfe0f3;font-weight:700;border-top:1px solid #9db4d4;border-bottom:1px solid #9db4d4}
       .ml-tbl tfoot tr.grandtot td{position:sticky;bottom:0;background:#c7d8ef;font-weight:800;border-top:2px solid #7f9dc4;z-index:2}
       .ml-tbl td.mld,.ml-tbl th.mld{min-width:54px;color:#5a6b82}
       .ml-tbl td.bcap{max-width:190px;overflow:hidden;text-overflow:ellipsis}
       .sm-tbl{font-size:11.5px;width:100%;table-layout:auto}.sm-tbl th,.sm-tbl td{padding:3px 5px;white-space:nowrap}
       .sm-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2;cursor:pointer;user-select:none;text-align:center}.sm-tbl thead tr:nth-child(2) th{top:26px}.sm-tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
       .sm-tbl thead th[data-sk]:hover{background:#e4ecf8}.sm-ar{font-size:9px;color:#2f6db3;margin-left:2px}
       .sm-tbl td.bcap{max-width:150px;overflow:hidden;text-overflow:ellipsis}.sm-tbl td.neg{color:#c0392b}.sm-tbl .center{text-align:center}
       .sm-tbl tr.sm-closed{background:#f3f8f3}
       .sm-tbl .wcol{background:#f2f8ff}.sm-tbl th.wcol{background:#e6f1ff}.sm-tbl .wcol2{background:#f2f9f4;color:#2a6b45}.sm-tbl th.wcol2{background:#e0f0e6;color:#2a6b45}
       .sm-tbl .acol{background:#fff9ec}.sm-tbl th.acol{background:#fdf2d6}
       .sm-tbl small{font-weight:400;color:#8aa0bd;font-size:9.5px}.sm-tbl tr.grandtot td{font-weight:700;border-top-width:1px;padding:3px 5px}.sm-tbl tr.grandtot .wcol,.sm-tbl tr.grandtot .wcol2{background:#eaf1fb}.sm-tbl tr.grandtot .acol{background:#fbf3df}
       .sm-badge{font-size:11px;padding:1px 8px;border-radius:10px;background:#eee;color:#777}.sm-badge.on{background:#e5f3e8;color:#2e7d32;font-weight:700}
       .sm-mini{padding:2px 8px;font-size:11px}
       .sm-ov{position:fixed;inset:0;background:rgba(20,30,50,.45);z-index:9998;display:flex;align-items:center;justify-content:center}
       .sm-dlg{background:#fff;width:min(1180px,96vw);max-height:92vh;border-radius:12px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 12px 40px rgba(0,0,0,.3)}
       .sm-dlg-h{padding:12px 18px;background:linear-gradient(90deg,#1c47a0,#2f6db3);color:#fff;display:flex;align-items:center;gap:12px}
       .sm-dlg-h .x{margin-left:auto;cursor:pointer;font-size:20px;opacity:.9}
       .sm-dlg-b{padding:14px 18px;overflow:auto;flex:1}
       .sm-dlg-f{padding:11px 18px;border-top:1px solid var(--line);display:flex;align-items:center;gap:10px;background:#fafcff}
       .sm-it{font-size:12px;width:100%}.sm-it th,.sm-it td{padding:3px 7px;border-bottom:1px solid var(--line);white-space:nowrap}.sm-it th{background:#f4f7fc;text-align:right}.sm-it th:nth-child(-n+3){text-align:left}
       .sm-it td.num{text-align:right;font-variant-numeric:tabular-nums}.sm-it input{width:90px;text-align:right;border:1px solid var(--line);border-radius:4px;padding:2px 5px}
       .sm-it tr.chg input{border-color:#2f6db3;background:#eef4ff;font-weight:700}.sm-it td.dpos{color:#1f8a5a}.sm-it td.dneg{color:#c0392b}
       .sm-adj{margin-top:14px;border:1px solid #cfe0ff;border-radius:8px;padding:10px 12px;background:#fbfdff}
       .sm-adj-row{display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap}
       .sm-adj-row input[type=number]{width:120px;text-align:right}.sm-adj-row .rsel{min-width:150px}.sm-adj-row .rdet{flex:1;min-width:160px}
       .sm-sum{display:flex;gap:18px;font-size:13px;margin-left:auto}.sm-sum b{font-size:15px}
       .sm-warn{color:#c0392b;font-size:12px}
     </style>`;
    // ★보기 전환(거래처집계 ↔ P/No상세) + 조회기준(마감/입고)
    const vsel=c.querySelector('#sm-view');
    if(vsel)vsel.onchange=e=>{view=e.target.value;if(view==='line'&&!lrows.length)loadLines();else draw();};
    const bsel=c.querySelector('#sm-basis');
    if(bsel)bsel.onchange=e=>{basis=e.target.value;loadLines();};
    const fr_=c.querySelector('#sm-fr');if(fr_)fr_.onchange=e=>{lfr=e.target.value;};
    const to_=c.querySelector('#sm-to');if(to_)to_.onchange=e=>{lto=e.target.value;};
    const lqi=c.querySelector('#sm-lq');if(lqi){lqi.oninput=e=>{lq=e.target.value;};lqi.onkeyup=e=>{if(e.key==='Enter')loadLines();};}
    const ymi=c.querySelector('#sm-ym');
    if(ymi)ymi.onchange=e=>{
      // ★연도 가드: 네이티브 월 입력이 연도-먼저라 "08" 타이핑이 연도를 망가뜨리면(20xx 밖) 무시하고 현재 월 유지.
      if(!ymValid(e.target.value)){e.target.value=ymToInput(ym);return;}
      const v=inYm(e.target.value);if(view==='line'){ym=v;loadLines();}else load(v);};
    const goYm=v=>{if(view==='line'){ym=v;loadLines();}else load(v);};   // ◀▶ 월 이동
    const ymp=c.querySelector('#sm-ymp');if(ymp)ymp.onclick=()=>goYm(shiftYm(ym,-1));
    const ymn=c.querySelector('#sm-ymn');if(ymn)ymn.onclick=()=>goYm(shiftYm(ym,+1));
    const qi=c.querySelector('#sm-q');qi.oninput=e=>{q=e.target.value;};qi.onkeyup=e=>{if(e.key==='Enter'){view==='line'?loadLines():draw();}};
    c.querySelector('#sm-go').onclick=()=>{view==='line'?loadLines():draw();};
    const xb=c.querySelector('#sm-xls');if(xb)xb.onclick=()=>exportXls();
    const rb=c.querySelector('#sm-recalc');if(rb)rb.onclick=()=>recalcCost();
    // ★재계산 체크 — 재렌더 없이 Set 만 갱신(스크롤 유지). 버튼 라벨에 선택수 표시.
    const ckLbl=()=>{const b=c.querySelector('#sm-recalc');
      if(b&&!b.disabled)b.textContent=`🧮 ${CFG.verb}단가 재계산`+(lsel.size?` (${lsel.size})`:'');};
    c.querySelectorAll('.ml-ck').forEach(x=>x.onchange=()=>{
      if(x.checked)lsel.add(x.dataset.k);else lsel.delete(x.dataset.k);
      const all=c.querySelector('#ml-ckall');
      if(all){const n=c.querySelectorAll('.ml-ck').length;all.checked=(lsel.size>=n&&n>0);}
      ckLbl();});
    const ckall=c.querySelector('#ml-ckall');
    if(ckall)ckall.onchange=()=>{c.querySelectorAll('.ml-ck').forEach(x=>{
        x.checked=ckall.checked;
        if(ckall.checked)lsel.add(x.dataset.k);else lsel.delete(x.dataset.k);});
      ckLbl();};
    ckLbl();
    const cts_=c.querySelector('#sm-ct');if(cts_)cts_.onchange=e=>{ctf=e.target.value;draw();};   // 분류 필터
    c.querySelectorAll('.sm-tbl thead th[data-sk]').forEach(th=>{th.onclick=()=>{const k=th.dataset.sk;if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=1;}draw();};});   // 헤더 클릭 정렬(THEAD 재생성=구조동일, 스크롤만 상단복귀)
    c.querySelectorAll('.sm-open').forEach(b=>b.onclick=()=>openModal(b.dataset.cc,b.dataset.nm));
    if(mc)drawModal();
  };

  const openModal=async(cc,nm)=>{mc={cc,nm};detail=null;pEdit={};dEdit={};amtAdjs=[];expanded=new Set();
    carryNextYm='';carryBusy=false;view2='item';selRows=new Set();fromDt='';toDt='';
    mLoading=true;await ensureReasons();drawModal();
    try{const r=await fetch(`${API}/api/${CFG.base}/detail?ym=${encodeURIComponent(ym)}&cc=${encodeURIComponent(cc)}`);if(!r.ok)throw new Error('HTTP '+r.status);
      detail=await r.json();mClosed=!!detail.close_flag;carryNextYm=detail.next_ym||'';
      (detail.adjustments||[]).forEach(a=>{
        if(a.adj_type==='AMT_UP'||a.adj_type==='AMT_DN'||a.adj_type==='ITEM_ADJ'){amtAdjs.push({amt:a.delta_amt,rc:a.reason_code||'',rd:a.reason_detail||''});}
        else if(a.scope==='DATE'&&a.mat_code&&a.target_ymd){const d=+(''+a.target_ymd).slice(4,6);expanded.add(a.mat_code);
          dEdit[dkey(a.mat_code,d)]={nc:(a.new_cost!=null?a.new_cost:''),nq:(a.new_qty!=null?a.new_qty:''),rc:a.reason_code||'',rd:a.reason_detail||''};}
        else if(a.mat_code){pEdit[a.mat_code]={nc:(a.new_cost!=null?a.new_cost:''),rc:a.reason_code||'',rd:a.reason_detail||''};}});}
    catch(e){detail=null;}
    mLoading=false;drawModal();};
  const closeModal=()=>{mc=null;detail=null;const m=c.querySelector('#sm-modal');if(m)m.innerHTML='';};
  const reloadDetail=async(cc)=>{try{const r=await fetch(`${API}/api/${CFG.base}/detail?ym=${encodeURIComponent(ym)}&cc=${encodeURIComponent(cc)}`);const j=await r.json();detail=j;mClosed=!!j.close_flag;carryNextYm=j.next_ym||'';}catch(e){}};

  // 일자별 유효단가/수량(날짜조정>품목단가>원본). 이월(carry) 일자는 매출 0(마감 제외).
  const effDay=(it,bd)=>{if(bd.carry)return {ec:+bd.cost,eq:+bd.qty,base:0,delta:0,carry:1};
    const de=dEdit[dkey(it.mat,bd.d)];let ec=+bd.cost;
    if(de&&de.nc!=null&&de.nc!=='')ec=+de.nc;
    else{const pe=pEdit[it.mat];if(pe&&pe.nc!=null&&pe.nc!=='')ec=+pe.nc;}
    return {ec,eq:+bd.qty,base:+bd.amt,delta:ec*(+bd.qty)-(+bd.cost)*(+bd.qty),carry:0};};
  const calc=()=>{const items=(detail&&detail.items)||[];let base=0,pd=0;
    items.forEach(it=>(it.byday||[]).forEach(bd=>{const e=effDay(it,bd);base+=e.base;pd+=e.delta;}));
    const ad=amtAdjs.reduce((a,b)=>a+(+b.amt||0),0);
    return {base,pd,ad,adj:pd+ad,final:base+pd+ad};};

  // ── 일자 필터·이월 유틸 ──
  const _dlab=ymd=>{ymd=''+(ymd||'');return ymd.length>=6?`${ymd.slice(0,2)}/${ymd.slice(2,4)}/${ymd.slice(4,6)}`:ymd;};
  const _ynm=y=>{y=''+(y||'');return y.length>=4?`20${y.slice(0,2)}.${y.slice(2,4)}`:y;};
  const crClick=()=>canW&&!mClosed;   // 재배정 가능(권한 + 미마감)
  const _monPfx=()=>`20${(''+ym).slice(0,2)}-${(''+ym).slice(2,4)}`;
  const _dayOf=dt=>{const m=/^\d{4}-\d{2}-(\d{2})$/.exec(''+(dt||''));return m?+m[1]:0;};
  const inRange=d=>{const f=_dayOf(fromDt),t=_dayOf(toDt);return (!f||d>=f)&&(!t||d<=t);};
  const IBADGE=`<span style="background:#ffe0b2;color:#b5651d;border-radius:3px;padding:0 5px;font-size:11px;font-weight:700;margin-left:5px">이월</span>`;
  const fdays=it=>(it.byday||[]).filter(bd=>inRange(bd.d));    // 필터 적용된 일자
  // 선택키(I:mat / D:mat|d) 현재 이월상태
  const selKeyCarried=(k,byMat)=>{if(k.startsWith('I:')){const it=byMat[k.slice(2)];return it&&fdays(it).length&&fdays(it).every(bd=>bd.carry);}
    const p=k.slice(2).split('|');const it=byMat[p[0]];const bd=it&&(it.byday||[]).find(x=>x.d==+p[1]);return bd&&bd.carry;};
  const carryApply=async()=>{
    // 선택 각 행을 개별 토글: 이월 안된 것→이월(금액0) / 이월된 것→해제(금액복원)
    if(carryBusy||!selRows.size)return;
    const items=(detail&&detail.items)||[];const byMat={};items.forEach(it=>byMat[it.mat]=it);
    const toCarry=[],toUnc=[];
    const add=(mat,bds)=>bds.forEach(bd=>{(bd.carry?toUnc:toCarry).push({mat_code:mat,maint_ymd:bd.ymd});});
    selRows.forEach(k=>{if(k.startsWith('I:')){const it=byMat[k.slice(2)];if(it)add(it.mat,fdays(it));}
      else{const p=k.slice(2).split('|');const it=byMat[p[0]];const bd=it&&(it.byday||[]).find(x=>x.d==+p[1]);if(bd)add(it.mat,[bd]);}});
    if(!toCarry.length&&!toUnc.length)return;
    carryBusy=true;drawModal();
    try{const post=(carry,pairs)=>fetch(`${API}/api/${CFG.base}/carry_set`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ym,cust_code:mc.cc,carry,pairs})}).then(r=>r.json());
      if(toCarry.length){const j=await post(true,toCarry);if(!j.ok)throw new Error(j.detail||'이월');}
      if(toUnc.length){const j=await post(false,toUnc);if(!j.ok)throw new Error(j.detail||'해제');}
      selRows.clear();await reloadDetail(mc.cc);
    }catch(e){alert('이월 전환 실패: '+e.message);}
    carryBusy=false;drawModal();};

  // 상단 품목별/일자별 표(체크박스·이월·단가편집)
  const topSection=()=>{
    const items=(detail&&detail.items)||[];const rdis=mClosed?'disabled':'';const _ck=crClick();
    const byMat={};items.forEach(it=>byMat[it.mat]=it);
    let rows='';
    if(view2==='item'){
      items.forEach(it=>{const fd=fdays(it);if(!fd.length)return;
        const carried=fd.every(bd=>bd.carry),anyC=fd.some(bd=>bd.carry);
        const qty=fd.reduce((a,bd)=>a+(+bd.qty),0);
        const amt0=fd.filter(bd=>!bd.carry).reduce((a,bd)=>a+(+bd.amt),0);
        const delta=fd.reduce((a,bd)=>a+effDay(it,bd).delta,0);
        const pe=pEdit[it.mat]||{};const nc=(pe.nc!=null&&pe.nc!=='')?+pe.nc:'';const k='I:'+it.mat;
        rows+=`<tr class="${delta?'chg':''}" style="${anyC?'background:#fff6ec':''}">
          <td class="center">${_ck?`<input type="checkbox" class="tp-ck" data-k="${esc(k)}" ${selRows.has(k)?'checked':''}>`:''}</td>
          <td><b>${esc(it.mat)}</b>${carried?IBADGE:''}</td>
          <td class="bcap" title="${esc(it.nm||'')}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(it.nm||'')}</td>
          <td class="center">${esc(it.unit)||''}</td><td class="num">${num(qty)}</td><td class="num">${num(it.cost)}</td>
          <td class="num">${carried?'<span class="mut">-</span>':`<input class="tp-pc" data-mat="${esc(it.mat)}" type="number" step="any" value="${nc}" placeholder="${num(it.cost)}" ${rdis}>`}</td>
          <td class="num ${delta>0?'dpos':delta<0?'dneg':''}">${delta?won0(delta):''}</td>
          <td class="num">${carried?'<b style="color:#b5651d">0</b>':won0(amt0)}</td></tr>`;});
    }else{
      const flat=[];items.forEach(it=>(it.byday||[]).forEach(bd=>{if(inRange(bd.d))flat.push([it,bd]);}));
      flat.sort((a,b)=>a[1].d-b[1].d||Math.abs(b[1].amt)-Math.abs(a[1].amt));
      flat.forEach(([it,bd])=>{const de=dEdit[dkey(it.mat,bd.d)]||{};const e=effDay(it,bd);const k='D:'+it.mat+'|'+bd.d;
        rows+=`<tr class="${e.delta?'chg':''}" style="${bd.carry?'background:#fff6ec':''}">
          <td class="center">${_ck?`<input type="checkbox" class="tp-ck" data-k="${esc(k)}" ${selRows.has(k)?'checked':''}>`:''}</td>
          <td class="center">${_dlab(bd.ymd)}</td><td><b>${esc(it.mat)}</b>${bd.carry?IBADGE:''}</td>
          <td class="bcap" title="${esc(it.nm||'')}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(it.nm||'')}</td>
          <td class="num">${num(bd.qty)}</td><td class="num">${num(bd.cost)}</td>
          <td class="num">${bd.carry?'<span class="mut">-</span>':`<input class="tp-dc" data-mat="${esc(it.mat)}" data-d="${bd.d}" type="number" step="any" value="${(de.nc!=null&&de.nc!=='')?de.nc:''}" placeholder="${num(bd.cost)}" style="width:78px" ${rdis}>`}</td>
          <td class="num ${e.delta>0?'dpos':e.delta<0?'dneg':''}">${e.delta?won0(e.delta):''}</td>
          <td class="num">${bd.carry?'<b style="color:#b5651d">0</b>':won0(bd.amt)}</td></tr>`;});
    }
    const cols=view2==='item'
      ?`<th class="center" style="width:24px"></th><th>품번</th><th>품명</th><th class="center">단위</th><th>수량</th><th>현단가</th><th>변경단가</th><th>금액변동</th><th>매출금액</th>`
      :`<th class="center" style="width:24px"></th><th class="center">입고일</th><th>품번</th><th>품명</th><th>수량</th><th>현단가</th><th>변경단가</th><th>금액변동</th><th>매출금액</th>`;
    const selN=selRows.size;
    const btnLbl=selN?`선택 ${selN}건 이월/해제`:'이월';
    const carN=items.filter(it=>{const fd=fdays(it);return fd.length&&fd.every(bd=>bd.carry);}).length;
    const toolbar=`<div style="display:flex;align-items:center;gap:7px;flex-wrap:nowrap;margin-bottom:6px;overflow-x:auto">
      <b style="white-space:nowrap">품목별 매출</b>
      <select class="inp" id="tp-view" style="width:auto"><option value="item" ${view2==='item'?'selected':''}>품목별</option><option value="day" ${view2==='day'?'selected':''}>일자별</option></select>
      <label class="tl">기간</label><input type="date" class="inp" id="tp-from" value="${esc(fromDt||_monPfx()+'-01')}" style="width:138px"><span class="mut">~</span><input type="date" class="inp" id="tp-to" value="${esc(toDt||_monPfx()+'-31')}" style="width:138px">
      ${_ck?`<button class="btn" id="tp-carry" ${selN?'':'disabled'} style="${selN?'background:#b5651d;color:#fff;':''}white-space:nowrap">${btnLbl}</button>${carryBusy?'<span class="mut" style="font-size:11px">저장중…</span>':''}`:''}
      <span class="mut" style="font-size:11px;margin-left:auto;white-space:nowrap">이월 ${carN}품목 · 매출금액 0 · 차월(${_ynm(carryNextYm)}) 마감</span></div>`;
    return toolbar+`<div id="tp-scroll" style="max-height:42vh;overflow:auto;border:1px solid var(--line);border-radius:6px"><table class="sm-it"><thead><tr>${cols}</tr></thead><tbody>${rows||`<tr><td colspan="9" class="empty">해당 기간 품목 없음</td></tr>`}</tbody></table></div>`;
  };
  // 이월 버튼만 갱신(체크박스 클릭 시 전체 재렌더 금지 — 스크롤 리셋 방지 §3)
  const updCarryBtn=(m)=>{const cb=m.querySelector('#tp-carry');if(!cb)return;
    const items=(detail&&detail.items)||[];const byMat={};items.forEach(it=>byMat[it.mat]=it);
    const selN=selRows.size;cb.disabled=!selN;cb.style.background=selN?'#b5651d':'';cb.style.color=selN?'#fff':'';
    cb.textContent=selN?`선택 ${selN}건 이월/해제`:'이월';};
  const wireTop=(m)=>{
    const vs=m.querySelector('#tp-view');if(vs)vs.onchange=e=>{view2=e.target.value;selRows.clear();drawModal();};
    const ff=m.querySelector('#tp-from');if(ff)ff.onchange=e=>{fromDt=e.target.value;drawModal();};
    const ft=m.querySelector('#tp-to');if(ft)ft.onchange=e=>{toDt=e.target.value;drawModal();};
    m.querySelectorAll('.tp-ck').forEach(el=>el.onchange=()=>{if(el.checked)selRows.add(el.dataset.k);else selRows.delete(el.dataset.k);updCarryBtn(m);});
    const cb=m.querySelector('#tp-carry');if(cb)cb.onclick=carryApply;
    m.querySelectorAll('.tp-pc').forEach(el=>el.onchange=()=>{const mat=el.dataset.mat,v=el.value.trim();
      if(v===''){if(pEdit[mat]){delete pEdit[mat].nc;if(!pEdit[mat].nc)delete pEdit[mat];}}else{pEdit[mat]=Object.assign(pEdit[mat]||{rc:'',rd:''},{nc:+v});}drawModal();});
    m.querySelectorAll('.tp-dc').forEach(el=>el.onchange=()=>{const k=dkey(el.dataset.mat,+el.dataset.d),v=el.value.trim();dEdit[k]=dEdit[k]||{nc:'',nq:'',rc:'',rd:''};dEdit[k].nc=(v===''?'':+v);
      if((dEdit[k].nc===''||dEdit[k].nc==null)&&!dEdit[k].rc&&!(dEdit[k].rd||'').trim())delete dEdit[k];drawModal();});
  };

  const drawModal=()=>{
    const m=c.querySelector('#sm-modal');if(!m)return;
    if(!mc){m.innerHTML='';return;}
    const _sc=m.querySelector('#tp-scroll');const _scTop=_sc?_sc.scrollTop:0;   // 재렌더 후 스크롤 위치 복원(§3)
    const rsOpt=(sel)=>`<option value="">사유 선택</option>`+reasons.map(r=>`<option value="${esc(r.code)}" ${r.code===sel?'selected':''}>${esc(r.name)}</option>`).join('');
    if(mLoading||!detail){m.innerHTML=`<div class="sm-ov"><div class="sm-dlg"><div class="sm-dlg-h"><b>${esc(mc.nm)}</b> 마감상세 <span class="x" id="sm-x">✖</span></div><div class="sm-dlg-b"><div class="empty">${SPIN}불러오는 중…</div></div></div></div>`;
      const x=m.querySelector('#sm-x');if(x)x.onclick=closeModal;return;}
    const items=detail.items||[];
    const s=calc();
    const mmdd=d=>String(d).padStart(2,'0');
    const rdis=mClosed?'disabled':'';
    // 상단 표 = topSection()(품목별/일자별·기간필터·체크박스·이월·단가편집)
    let adjRows='';
    items.forEach(it=>{const pe=pEdit[it.mat];
      if(pe&&pe.nc!=null&&pe.nc!==''&&+pe.nc!==+it.cost){const dd=(it.byday||[]).reduce((a,bd)=>a+((dEdit[dkey(it.mat,bd.d)]||bd.carry)?0:(+pe.nc-+bd.cost)*(+bd.qty)),0);
        if(dd!==0)adjRows+=`<div class="sm-adj-row"><span style="min-width:180px"><b>품목단가</b> ${esc(it.mat)} ${num(it.cost)}→${num(pe.nc)} <span class="mut">(${won0(dd)})</span></span>
          <select class="sel rsel sm-prc" data-mat="${esc(it.mat)}" ${rdis}>${rsOpt(pe.rc)}</select>
          <input class="inp rdet sm-prd" data-mat="${esc(it.mat)}" value="${esc(pe.rd||'')}" placeholder="세부 사유(선택)" ${rdis}></div>`;}
      (it.byday||[]).forEach(bd=>{const de=dEdit[dkey(it.mat,bd.d)];if(!de)return;const ncC=de.nc!=null&&de.nc!==''&&+de.nc!==+bd.cost;if(!ncC)return;const e=effDay(it,bd);
        const lbl=`단가 ${num(bd.cost)}→${num(de.nc)}`;
        adjRows+=`<div class="sm-adj-row"><span style="min-width:180px"><b>${mmdd(bd.d)}일</b> ${esc(it.mat)} ${lbl} <span class="mut">(${won0(e.delta)})</span></span>
          <select class="sel rsel sm-drc" data-mat="${esc(it.mat)}" data-d="${bd.d}" ${rdis}>${rsOpt(de.rc)}</select>
          <input class="inp rdet sm-drd" data-mat="${esc(it.mat)}" data-d="${bd.d}" value="${esc(de.rd||'')}" placeholder="세부 사유(선택)" ${rdis}></div>`;});});
    const amtAdjRows=amtAdjs.map((a,i)=>`<div class="sm-adj-row"><input type="number" step="any" class="inp sm-aamt" data-i="${i}" value="${a.amt}" placeholder="증액(+)/차감(-)" ${rdis}>
        <select class="sel rsel sm-arc" data-i="${i}" ${rdis}>${rsOpt(a.rc)}</select>
        <input class="inp rdet sm-ard" data-i="${i}" value="${esc(a.rd||'')}" placeholder="세부 사유(선택)" ${rdis}>${mClosed?'':`<span class="sm-adel" data-i="${i}" style="cursor:pointer;color:#c0392b">✖</span>`}</div>`).join('');
    m.innerHTML=`<div class="sm-ov"><div class="sm-dlg">
      <div class="sm-dlg-h"><b>${esc(mc.nm)}</b> <span style="opacity:.85">(${esc(mc.cc)}) · 마감 ${esc(ymToInput(ym))}</span>${mClosed?'<span class="sm-badge on" style="background:#fff;color:#2e7d32">🔒 마감완료</span>':''}<span class="x" id="sm-x">✖</span></div>
      <div class="sm-dlg-b">
        ${topSection()}
        <div class="sm-adj">
          <div style="font-weight:700;margin-bottom:4px">조정내역 <span style="color:var(--muted);font-weight:400;font-size:12px">(품목단가/일자별 단가·수량/총액 증감 · 사유 필수)</span></div>
          ${adjRows||'<div class="mut" style="font-size:12px">단가·수량을 바꾸면 여기에 사유 입력란이 생깁니다.</div>'}
          ${amtAdjRows}
          ${(mClosed||!canW)?'':'<button class="btn sm-mini" id="sm-add-amt">＋ 총액 증감/차감(품목무관)</button>'}
        </div>
      </div>
      <div class="sm-dlg-f">
        <div class="sm-sum"><span>원매출 <b>${won0(s.base)}</b></span>
          <span>단가·수량 <b style="${s.pd<0?'color:#c0392b':''}">${s.pd?won0(s.pd):'0'}</b></span>
          <span>총액조정 <b style="${s.ad<0?'color:#c0392b':''}">${s.ad?won0(s.ad):'0'}</b></span>
          <span>최종금액 <b style="color:#1c47a0">${won0(s.final)}</b></span></div>
        <div class="spacer"></div>
        ${!canW?`<span style="color:#c0392b;font-size:12px;margin-right:auto">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span><button class="btn" id="sm-close2">닫기</button>`
          :mClosed?`<button class="btn ghost" id="sm-reopen">🔓 마감취소</button><button class="btn" id="sm-close2">닫기</button>`
          :`<button class="btn ghost" id="sm-save">💾 조정저장</button><button class="btn" id="sm-confirm" style="background:#1c7a37;color:#fff">🔒 마감확정</button><button class="btn ghost" id="sm-close2">닫기</button>`}
      </div>
    </div></div>`;
    m.querySelector('#sm-x').onclick=closeModal;
    const c2=m.querySelector('#sm-close2');if(c2)c2.onclick=closeModal;
    wireTop(m);   // 품목별/일자별 표: 뷰토글·기간필터·체크박스·이월버튼·단가편집
    m.querySelectorAll('.sm-prc').forEach(el=>el.onchange=()=>{const e=pEdit[el.dataset.mat];if(e)e.rc=el.value;});
    m.querySelectorAll('.sm-prd').forEach(el=>el.oninput=()=>{const e=pEdit[el.dataset.mat];if(e)e.rd=el.value;});
    m.querySelectorAll('.sm-drc').forEach(el=>el.onchange=()=>{const e=dEdit[dkey(el.dataset.mat,+el.dataset.d)];if(e)e.rc=el.value;});
    m.querySelectorAll('.sm-drd').forEach(el=>el.oninput=()=>{const e=dEdit[dkey(el.dataset.mat,+el.dataset.d)];if(e)e.rd=el.value;});
    m.querySelectorAll('.sm-aamt').forEach(el=>el.onchange=()=>{amtAdjs[+el.dataset.i].amt=el.value===''?0:+el.value;drawModal();});
    m.querySelectorAll('.sm-arc').forEach(el=>el.onchange=()=>{amtAdjs[+el.dataset.i].rc=el.value;});
    m.querySelectorAll('.sm-ard').forEach(el=>el.oninput=()=>{amtAdjs[+el.dataset.i].rd=el.value;});
    m.querySelectorAll('.sm-adel').forEach(el=>el.onclick=()=>{amtAdjs.splice(+el.dataset.i,1);drawModal();});
    const add=m.querySelector('#sm-add-amt');if(add)add.onclick=()=>{amtAdjs.push({amt:0,rc:'',rd:''});drawModal();};
    const sv=m.querySelector('#sm-save');if(sv)sv.onclick=()=>save(false);
    const cf=m.querySelector('#sm-confirm');if(cf)cf.onclick=()=>{if(confirm(`${mc.nm} ${CFG.verb}을 마감확정할까요?\n최종금액 ${won0(calc().final)}원`))save(true);};
    const ro=m.querySelector('#sm-reopen');if(ro)ro.onclick=reopen;
    const _sc2=m.querySelector('#tp-scroll');if(_sc2&&_scTop)_sc2.scrollTop=_scTop;   // 스크롤 위치 복원
  };

  const buildAdjustments=()=>{const items=(detail&&detail.items)||[];const out=[];const errs=[];
    items.forEach(it=>{
      (it.byday||[]).forEach(bd=>{if(bd.carry)return;const de=dEdit[dkey(it.mat,bd.d)];if(!de)return;const ncC=de.nc!=null&&de.nc!==''&&+de.nc!==+bd.cost;if(!ncC)return;
        const nc=+de.nc;const delta=nc*(+bd.qty)-(+bd.cost)*(+bd.qty);
        if(!(de.rc||(de.rd||'').trim()))errs.push(`${it.mat} ${bd.d}일: 사유 필요`);
        out.push({adj_type:'PRICE',scope:'DATE',mat_code:it.mat,target_ymd:bd.ymd||ymd6(bd.d),old_cost:+bd.cost,new_cost:nc,old_qty:+bd.qty,new_qty:+bd.qty,delta_amt:delta,reason_code:de.rc||null,reason_detail:de.rd||null});});
      const pe=pEdit[it.mat];
      if(pe&&pe.nc!=null&&pe.nc!==''&&+pe.nc!==+it.cost){let delta=0;(it.byday||[]).forEach(bd=>{if(bd.carry||dEdit[dkey(it.mat,bd.d)])return;delta+=(+pe.nc-+bd.cost)*(+bd.qty);});
        if(delta!==0){if(!(pe.rc||(pe.rd||'').trim()))errs.push(`${it.mat} 품목단가: 사유 필요`);
          out.push({adj_type:'PRICE',scope:'ITEM',mat_code:it.mat,target_ymd:null,old_cost:+it.cost,new_cost:+pe.nc,old_qty:null,new_qty:null,delta_amt:delta,reason_code:pe.rc||null,reason_detail:pe.rd||null});}}});
    amtAdjs.forEach((a,i)=>{if(+a.amt!==0){if(!(a.rc||(a.rd||'').trim()))errs.push(`총액조정 ${i+1}행: 사유 필요`);
      out.push({adj_type:(+a.amt>=0?'AMT_UP':'AMT_DN'),scope:null,mat_code:null,target_ymd:null,old_cost:null,new_cost:null,old_qty:null,new_qty:null,delta_amt:+a.amt,reason_code:a.rc||null,reason_detail:a.rd||null});}});
    return {out,errs};};

  const save=async(doClose)=>{const {out,errs}=buildAdjustments();
    if(errs.length){alert('저장 불가:\n'+errs.join('\n'));return;}
    const s=calc();
    try{const r=await fetch(`${API}/api/${CFG.base}/save`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ym,cust_code:mc.cc,base_amt:s.base,adjustments:out,close:doClose})});
      const j=await r.json();if(!j.ok){alert('저장 거부:\n'+(j.errors||[]).join('\n'));return;}
      alert(doClose?`마감확정 완료 — 최종금액 ${won0(j.final_amt)}원`:`조정저장 완료 — 최종금액 ${won0(j.final_amt)}원`);
      closeModal();load(ym);}catch(e){alert('저장 실패: '+e.message);}};
  const reopen=async()=>{if(!confirm(`${mc.nm} 마감을 취소할까요?`))return;
    try{const r=await fetch(`${API}/api/${CFG.base}/reopen`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ym,cust_code:mc.cc})});
      const j=await r.json();if(!j.ok)throw new Error('reopen');alert('마감 취소됨 — 수정 가능');closeModal();load(ym);}catch(e){alert('마감취소 실패: '+e.message);}};

  load('');
};
/* 공용 필터 렌더/바인딩 — 라벨+필드 나란히(nowrap), select 자동폭, 자동완성(이름표시/코드저장) */
function qfFields(filters,F,pfx){
  return (filters||[]).map(f=>{
    const val=F[f.k]||'', nm=F[f.k+'__nm']||'';
    let fld;
    if(f.type==='select') fld=`<select class="inp" id="${pfx}${f.k}" style="min-width:${f.width||54}px;width:auto;max-width:220px">${(f.opts||[]).map(o=>`<option value="${esc(o.v)}"${String(val)===String(o.v)?' selected':''}>${esc(o.t)}</option>`).join('')}</select>`;
    else if(f.type==='auto') fld=`<span style="position:relative;display:inline-block"><input class="inp qf-ac" id="${pfx}${f.k}" data-ac="${f.k}" data-kind="${f.optKind||''}" data-showcode="${f.showCode?1:''}" autocomplete="off" value="${esc(f.showCode?val:(nm||val))}" placeholder="입력하세요" style="width:${f.width||120}px"><div class="wr-acbox" id="${pfx}acb-${f.k}" style="display:none;position:absolute;left:0;top:100%;z-index:120;min-width:100%;max-height:220px;overflow:auto;background:#fff;border:1px solid #b9d3ef;border-radius:6px;box-shadow:0 6px 16px rgba(0,0,0,.16)"></div></span>`;
    else fld=`<input class="inp" id="${pfx}${f.k}" value="${esc(val)}" placeholder="입력하세요" style="width:${f.width||90}px">`;
    return `<span style="display:inline-flex;align-items:center;gap:4px;white-space:nowrap;margin-right:2px"><label class="tl" style="margin:0">${f.label}</label>${fld}</span>`;
  }).join('');
}
function qfBind(host,filters,F,pfx,doSearch){
  const API=API_BASE; const g=id=>host.querySelector(id);
  (filters||[]).forEach(f=>{const el=g('#'+pfx+f.k); if(!el)return;
    if(f.type==='auto'){const box=g('#'+pfx+'acb-'+f.k); let t=null;
      el.oninput=()=>{F[f.k+'__nm']=el.value; F[f.k]=''; clearTimeout(t); const q=el.value.trim();
        if(!q){box.style.display='none';return;}
        t=setTimeout(()=>fetch(`${API}/api/qc/opt?kind=${f.optKind}&q=`+encodeURIComponent(q)).then(r=>r.json()).then(j=>{
          const rows=j.rows||[]; box.innerHTML=rows.length?rows.map(x=>`<div class="qf-o" data-code="${esc(x.code)}" data-name="${esc(x.name)}" style="padding:5px 10px;cursor:pointer;font-size:12px;border-bottom:1px solid #f0f3f8">${esc(x.name)} <span style="color:#9aa8bd;font-size:11px">${esc(x.code)}</span></div>`).join(''):'<div style="padding:6px 10px;color:#999;font-size:12px">결과 없음</div>';
          box.style.display='block';
          box.querySelectorAll('.qf-o').forEach(o=>o.onmousedown=()=>{F[f.k]=o.dataset.code;F[f.k+'__nm']=o.dataset.name;el.value=o.dataset.name;box.style.display='none';});
        }),180);};
      el.onblur=()=>setTimeout(()=>{if(box)box.style.display='none';},180);
      el.onkeyup=e=>{if(e.key==='Enter')doSearch();};
    } else { el.onkeyup=e=>{if(e.key==='Enter'){F[f.k]=el.value;doSearch();}}; el.onchange=()=>{F[f.k]=el.value;}; }
  });
}
/* 검색 직전 비-auto 필터값 읽기 */
function qfRead(host,filters,F,pfx){(filters||[]).forEach(f=>{if(f.type==='auto')return;const el=host.querySelector('#'+pfx+f.k);if(el)F[f.k]=el.value;});}
function wrCrud(host, cfg){
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date(), back=cfg.days||20;
  const st={F:Object.assign({from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T)},cfg.filt0||{}),
            data:{rows:[],cnt:0}, loading:false, msg:'', form:null, sel:new Set()};
  const load=async()=>{st.loading=true;render();
    try{const r=await fetch(`${API}${cfg.listEp}?`+new URLSearchParams(cfg.buildQS(st.F)));st.data=await r.json();st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.data={rows:[],cnt:0};}
    st.loading=false;render();};
  const _req=f=>cfg.allReq?!f.optional:f.required;   // allReq=전항목 필수(예외만 optional)
  const save=async()=>{
    for(const f of cfg.form){if(_req(f)&&!String(st.form[f.k]??'').trim()){alert(f.label+' 은(는) 필수입니다');return;}}
    try{const r=await fetch(`${API}${cfg.saveEp}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg.toBody(st.form))});
      const j=await r.json();
      if(j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료':'✅ 수정완료')+' (id '+j.id+')';st.form=null;await load();}
      else alert('저장 실패: '+JSON.stringify(j.errors||j));}
    catch(e){alert('저장 오류: '+e);}};
  const del=async(ids)=>{if(!ids.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(ids.length+'건을 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}${cfg.delEp}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});
      const j=await r.json();st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();st.form=null;await load();}
    catch(e){alert('삭제 오류: '+e);}};
  const fld=(f)=>{
    const v=st.form[f.k]??'';
    // 드롭다운: 선택 글자에 맞춰 자동폭(width:auto)
    if(f.type==='select') return `<select class="inp" data-fk="${f.k}" style="min-width:${f.width||70}px;width:auto;max-width:280px">${(f.opts||[]).map(o=>`<option value="${esc(o.v)}" ${String(o.v)===String(v)?'selected':''}>${esc(o.t)}</option>`).join('')}</select>`;
    // 자동완성: 이름으로 보여주고 코드 저장, 한 글자 치면 후보 클릭
    if(f.type==='auto'){
      const nm=st.form[f.k+'__nm']??'', disp=f.showCode?v:(nm||v);
      return `<span style="position:relative;display:inline-block">
        <input class="inp wr-ac" data-ac="${f.k}" data-kind="${f.optKind||''}" data-showcode="${f.showCode?1:''}" data-ep="${f.searchEp||'/api/qc/opt'}" autocomplete="off" value="${esc(disp)}" placeholder="입력하세요" style="width:${f.width||140}px">
        <div class="wr-acbox" id="wr-ac-${f.k}" style="display:none;position:absolute;left:0;top:100%;z-index:120;min-width:100%;max-height:220px;overflow:auto;background:#fff;border:1px solid #b9d3ef;border-radius:6px;box-shadow:0 6px 16px rgba(0,0,0,.16)"></div></span>`;
    }
    const ph = f.ph ?? ((f.type==='date'||f.type==='num')?'':'입력하세요');
    const list=f.search?`list="wr-dl-${f.k}"`:'';
    const dl=f.search?`<datalist id="wr-dl-${f.k}"></datalist>`:'';
    return `<input class="inp" data-fk="${f.k}" ${list} type="${f.type==='date'?'date':'text'}" value="${esc(v)}" placeholder="${esc(ph)}" style="width:${f.width||110}px" ${f.type==='num'?'inputmode="decimal"':''}>${dl}`;
  };
  const render=()=>{
    const d=st.data, editing=st.form!==null;
    const ed=(typeof PERM!=='undefined')?PERM.canEdit(cfg.sid||''):true;   // 수정권한 게이트(규칙#16)
    host.innerHTML=`
     <div class="toolbar">
       <label class="tl">${cfg.dateLabel||'기간'}</label>
       <input class="inp" type="date" id="wr-from" value="${st.F.from}"> ~ <input class="inp" type="date" id="wr-to" value="${st.F.to}">
       ${qfFields(cfg.filters,st.F,'wr-f-')}
       <button class="btn" id="wr-search">🔍 조회</button>
       ${ed?`<button class="btn" id="wr-new" style="background:#1c7c3a;color:#fff">➕ 신규</button>
       <button class="btn" id="wr-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       <div class="spacer"></div><span class="rowcount">${nf(d.cnt||0)}건${cfg.sum?(' · '+cfg.sum(d)):''}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${(st.msg.includes('실패')||st.msg.includes('오류'))?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${(editing&&cfg.modal)?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:26px 10px">
        <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:${cfg.modalWidth||560}px;max-width:96vw">
          <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
            <b>${cfg.modalTitle||'등록'} ${st.form.id?'— 수정 (id '+st.form.id+')':'— 신규'}</b><span id="wr-x" style="cursor:pointer;font-size:17px">✕</span></div>
          <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
            ${(()=>{
              // ★modalCols(기본1) — 항목이 많으면 여러 열로 나눠 한 화면에 담는다(세로 스크롤 최소화).
              //   f.full:true 인 항목(불량내용 등 긴 입력)은 행 전체를 차지한다.
              const NC=Math.max(1,+(cfg.modalCols||1));
              if(NC===1)
                return `<table style="border-collapse:collapse;width:100%">${cfg.form.map(f=>`<tr>
                  <td style="padding:5px 10px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:104px;vertical-align:middle">${f.label}${_req(f)?'<span style="color:#c0392b">*</span>':''}</td>
                  <td style="padding:4px 0">${fld(f)}</td></tr>`).join('')}</table>`;
              const lb=f=>`<td style="padding:5px 8px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;vertical-align:middle">${f.label}${_req(f)?'<span style="color:#c0392b">*</span>':''}</td>`;
              let html='<table style="border-collapse:collapse;width:100%"><colgroup>'
                + Array.from({length:NC}).map(()=>'<col style="width:96px"><col>').join('') + '</colgroup>';
              let buf=[];
              const flush=()=>{ if(!buf.length)return;
                html+='<tr>'+buf.map(f=>lb(f)+`<td style="padding:4px 14px 4px 0">${fld(f)}</td>`).join('')
                     + (buf.length<NC?`<td colspan="${(NC-buf.length)*2}"></td>`:'') + '</tr>';
                buf=[]; };
              cfg.form.forEach(f=>{
                if(f.full){ flush();
                  html+=`<tr>${lb(f)}<td colspan="${NC*2-1}" style="padding:4px 0">${fld(f)}</td></tr>`;
                  return; }
                buf.push(f); if(buf.length===NC)flush();
              });
              flush();
              return html+'</table>';
            })()}
            ${/* ★확장영역 — 폼 필드로 표현 못하는 UI(파일첨부 등)를 화면쪽에서 끼워넣는다.
                  cfg.modalExtra(form) 이 HTML 을 돌려주면 폼 아래에 붙는다. 이벤트는
                  cfg.modalExtraBind(root, form, reload) 에서 건다(2026-08-26 품질불량 첨부). */
              (cfg.modalExtra? (cfg.modalExtra(st.form)||'') : '')}
          </div>
          <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center;gap:10px">
            <span style="color:#c0392b;font-size:11px;text-align:left">* 필수항목 제외품목들을 사용해보고 전산담당에게 알려주세요.</span>
            <span style="white-space:nowrap"><button class="btn" id="wr-save" style="background:#1b6ec2;color:#fff">💾 저장</button>
            <button class="btn" id="wr-cancel">닫기</button></span></div>
        </div></div>`:(editing?`<div style="background:#f2f8ff;border:1px solid #b9d3ef;border-radius:8px;padding:10px;margin:8px 0">
        <div style="font-weight:600;margin-bottom:6px">${st.form.id?'✏️ 수정 (id '+st.form.id+')':'➕ 신규 등록'}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center">
        ${cfg.form.map(f=>`<label class="tl">${f.label}${_req(f)?'<span style="color:#c0392b">*</span>':''}</label>${fld(f)}`).join('')}
        </div>
        <div style="margin-top:8px"><button class="btn" id="wr-save" style="background:#1b6ec2;color:#fff">💾 저장</button>
        <button class="btn" id="wr-cancel">취소</button></div>
      </div>`:'')}
     <div class="grid-wrap" style="max-height:calc(100vh - ${(editing&&!cfg.modal)?430:330}px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr><th style="width:26px"></th>${cfg.cols.map(col=>`<th class="${col.cls||''}">${col.h}</th>`).join('')}<th style="width:56px">작업</th></tr></thead>
      <tbody>${st.loading?spinRow(cfg.cols.length+2):((d.rows&&d.rows.length)?d.rows.map((r,i)=>`<tr>
        <td class="center">${ed&&r.ID?`<input type="checkbox" class="wr-chk" data-id="${r.ID}" ${st.sel.has(String(r.ID))?'checked':''}>`:''}</td>
        ${cfg.cols.map(col=>`<td class="${col.cls||''}" ${col.title?`title="${esc(r[col.title]||'')}"`:''} ${col.cap?'style="max-width:150px;overflow:hidden;text-overflow:ellipsis"':''}>${col.fmt?col.fmt(r):esc(r[col.k]??'')}</td>`).join('')}
        <td class="center">${ed&&(r.ID||cfg.editAll)?`<button class="btn wr-edit" data-idx="${i}" style="padding:1px 6px">수정</button>`:`<span style="color:#8aa0bd;font-size:10px">${r.ID?'':'📁이력'}</span>`}</td></tr>`).join(''):`<tr><td colspan="${cfg.cols.length+2}" class="empty">조회 결과 없음${ed?' (➕신규로 등록)':''}</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    const doSearch=()=>{st.F.from=g('#wr-from').value;st.F.to=g('#wr-to').value;qfRead(host,cfg.filters,st.F,'wr-f-');load();};
    g('#wr-search').onclick=doSearch;
    if(ed){g('#wr-new').onclick=()=>{st.form=cfg.newRow(st.F);render();};
      g('#wr-del').onclick=()=>del([...st.sel]);}
    host.querySelectorAll('.wr-chk').forEach(ch=>ch.onclick=()=>{const id=ch.dataset.id;ch.checked?st.sel.add(id):st.sel.delete(id);});  // ★ID는 문자열 유지(웹행 ID='YMD-SEQ' 복합키, +변환시 NaN)
    host.querySelectorAll('.wr-edit').forEach(b=>b.onclick=()=>{const r=d.rows[+b.dataset.idx];st.form=cfg.fromRow(r);render();});
    qfBind(host,cfg.filters,st.F,'wr-f-',doSearch);
    if(editing){
      g('#wr-cancel').onclick=()=>{st.form=null;render();};
      const xb=g('#wr-x'); if(xb)xb.onclick=()=>{st.form=null;render();};
      g('#wr-save').onclick=save;
      // ★확장영역 이벤트 바인딩(cfg.modalExtra 와 짝). 실패해도 폼 저장은 살아있게 try 로 격리.
      if(cfg.modalExtraBind){try{cfg.modalExtraBind(host,st.form,()=>{render();});}
                             catch(e){try{console.error('[wrShell] modalExtraBind 실패',e);}catch(_){}}}
      host.querySelectorAll('[data-fk]').forEach(el=>{
        el.oninput=()=>{st.form[el.dataset.fk]=el.value;
          const f=cfg.form.find(x=>x.k===el.dataset.fk);
          if(f&&f.search&&el.value.length>=2){fetch(`${API}/api/wr/itemsearch?q=`+encodeURIComponent(el.value)).then(r=>r.json()).then(j=>{
            const dl=host.querySelector('#wr-dl-'+f.k);if(dl)dl.innerHTML=(j.rows||[]).map(x=>`<option value="${esc(x.item)}">${esc(x.nm)}</option>`).join('');});}
        };
      });
      // 자동완성(이름표시·코드저장): 한 글자 치면 후보→클릭
      host.querySelectorAll('.wr-ac').forEach(el=>{
        const fk=el.dataset.ac, kind=el.dataset.kind, ep=el.dataset.ep, sc=!!el.dataset.showcode, box=host.querySelector('#wr-ac-'+fk); let t=null;
        el.oninput=()=>{ if(sc){st.form[fk]=el.value;} else {st.form[fk+'__nm']=el.value; st.form[fk]='';}  // 코드형=직접입력, 이름형=클릭확정
          clearTimeout(t); const q=el.value.trim();
          if(!q){box.style.display='none';return;}
          t=setTimeout(()=>fetch(`${API}${ep}?kind=${kind}&q=`+encodeURIComponent(q)).then(r=>r.json()).then(j=>{
            const rows=j.rows||[];
            box.innerHTML=rows.length?rows.map(x=>`<div class="wr-acopt" data-code="${esc(x.code)}" data-name="${esc(x.name)}" style="padding:5px 10px;cursor:pointer;font-size:12px;border-bottom:1px solid #f0f3f8"><b>${esc(sc?x.code:x.name)}</b> <span style="color:#9aa8bd;font-size:11px">${esc(sc?x.name:x.code)}</span></div>`).join(''):'<div style="padding:6px 10px;color:#999;font-size:12px">결과 없음</div>';
            box.style.display='block';
            box.querySelectorAll('.wr-acopt').forEach(o=>o.onmousedown=()=>{st.form[fk]=o.dataset.code;st.form[fk+'__nm']=o.dataset.name;el.value=sc?o.dataset.code:o.dataset.name;box.style.display='none';});
          }),180);};
        el.onblur=()=>setTimeout(()=>{if(box)box.style.display='none';},180);
      });
    }
  };
  load();
}
/* 모드 토글 셸(라이브 조회 ↔ nx 신규등록/편집) */
function wrShell(c, o){
  if(o.cfg&&o.sid&&!o.cfg.sid)o.cfg.sid=o.sid;   // 권한 sid 주입(규칙#16)
  // nxOnly: 컷오버 후 nx 단일원장 모드 — 레거시/nx 토글 없이 nx만 조회·편집
  const nxOnly=o.nxOnly;
  let mode=nxOnly?'edit':(o.default||'edit');
  const paint=()=>{
    const toggle=nxOnly?'':`<div style="display:flex;gap:6px;margin:6px 0 2px">
       <button class="btn ${mode==='live'?'active':''}" id="wm-live" style="${mode==='live'?'background:#b12a2a;color:#fff':''}">🔴 레거시 라이브조회</button>
       <button class="btn ${mode==='edit'?'active':''}" id="wm-edit" style="${mode==='edit'?'background:#1c7c3a;color:#fff':''}">✏️ 신규 등록/편집(nx)</button>
       <span class="page-sub" style="margin:0;align-self:center;color:#8aa0bd">※ 신규편집은 웹 등록데이터(nx)이며 레거시 라이브와 별개 원장입니다</span>
     </div>`;
    c.innerHTML=`<div class="page-title">${o.title}</div>
     <div class="page-sub">${o.sub}</div>
     ${toggle}
     <div id="wr-body"></div>`;
    if(!nxOnly){
      c.querySelector('#wm-live').onclick=()=>{if(mode!=='live'){mode='live';paint();}};
      c.querySelector('#wm-edit').onclick=()=>{if(mode!=='edit'){mode='edit';paint();}};
    }
    const body=c.querySelector('#wr-body');
    if(mode==='live') o.live(body); else if(o.cfg&&o.cfg._custom) o.cfg._custom(body); else wrCrud(body, o.cfg);
  };
  paint();
}
/* 라이브 조회(공용): partledger/procresult 그리드 */
function wrLiveLedger(body, kind){
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const ymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date(); const isAdj=(kind==='adj');
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),part:'',wc:''};
  let data={rows:[],cnt:0,sum_qty:0}, loading=false, msg='';
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({kind,from_ymd:F.from,to_ymd:F.to,part:F.part,wc:F.wc});
    try{const r=await fetch(`${API}/api/partledger/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패';data={rows:[],cnt:0,sum_qty:0};}
    loading=false;draw();};
  const draw=()=>{
    body.innerHTML=`
     <div class="toolbar">
       <label class="tl">${isAdj?'수정기간':'출고기간'}</label><input class="inp" type="date" id="ad-from" value="${F.from}"> ~ <input class="inp" type="date" id="ad-to" value="${F.to}">
       <label class="tl">자도번</label><input class="inp" id="ad-part" value="${esc(F.part)}" style="width:120px">
       <label class="tl">작업처</label><input class="inp" id="ad-wc" value="${esc(F.wc)}" style="width:70px">
       <button class="btn" id="ad-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt)}건 · ${isAdj?'조정':'출고'}수량합 <b>${nf(data.sum_qty)}</b></span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr><th>${isAdj?'수정일자':'출고일자'}</th><th class="num">SEQ</th>${isAdj?'<th>파트</th>':'<th>FROM파트</th><th>TO파트</th>'}<th>자도번</th><th>품명</th><th class="num">${isAdj?'수정수량':'출고수량'}</th><th class="num">단가</th><th class="num">금액</th><th>비고</th>${isAdj?'<th>도번</th><th>작업처</th>':''}<th>작업자</th><th>작업일시</th></tr></thead>
      <tbody>${loading?spinRow(isAdj?13:12):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${ymd(r.MAINT_YMD)}</td><td class="num">${r.MAINT_SEQ}</td>${isAdj?`<td class="center">${esc(r.part)}</td>`:`<td class="center">${esc(r.frompart)}</td><td class="center">${esc(r.part)}</td>`}<td><b>${esc(r.mat)}</b></td>
        <td class="bcap" title="${esc(r.nm)}" style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="num" style="color:${r.MAINT_QTY<0?'#c0392b':'#1c7c3a'}">${nf(r.MAINT_QTY)}</td><td class="num">${nf(r.MAINT_COST)}</td><td class="num">${nf(r.MAINT_AMT)}</td>
        <td class="bcap" title="${esc(r.remarks)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.remarks)}</td>
        ${isAdj?`<td>${esc(r.dobun)}</td><td class="center">${esc(r.pwc)}</td>`:''}<td>${esc(r.usr)}</td><td class="center" style="color:#8aa0bd">${esc(r.INSERT_DATETIME)}</td></tr>`).join(''):`<tr><td colspan="${isAdj?13:12}" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>body.querySelector(id);
    g('#ad-search').onclick=()=>{F.from=g('#ad-from').value;F.to=g('#ad-to').value;F.part=g('#ad-part').value;F.wc=g('#ad-wc').value;load();};
    ['#ad-part','#ad-wc'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#ad-search').click();});
  };
  load();
}
const _y6=s=>{s=''+(s||'');return s.length===6?('20'+s.slice(0,2)+'-'+s.slice(2,4)+'-'+s.slice(4,6)):s;};
const _wnf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
const _wymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
const _whms=s=>(s&&(''+s).length>=4)?`${(''+s).slice(0,2)}:${(''+s).slice(2,4)}`:(s||'');

/* ===== 거래처MASTER CRUD (nx.cust, 위하고정합) — 레거시 w_cm_master_055 유지관리 ===== */
function custMaint(host){
  const API=API_BASE;
  let opts={cust_type:[],biztag:[],yn:[],ue_date:[],ue_week:[],banks:[]};
  const st={rows:[],cnt:0,q:'',use:'',ctype:'',form:null,sel:new Set(),msg:''};
  // [key,label,type,optkey] · type: req(필수텍스트)/text/num/date/sel(드롭다운)/chk(0·1)
  const FIELDS=[
    ['cust_code','거래처코드','text'],['cust_name','거래처명','req'],
    ['cust_type','거래처구분','sel','cust_type'],['business_tag','사업자구분','sel','biztag'],
    ['in_flag','매입','chk'],['out_flag','매출','chk'],['outside_flag','외주','chk'],
    ['biz_no','사업자등록번호','text'],['resident_no','주민등록번호','text'],['corp_no','법인번호','text'],
    ['owner_name','대표자성명','text'],['biz_type','업태','text'],['biz_item','종목','text'],
    ['post_no','우편번호','text'],['address1','사업장주소','text'],['address2','상세주소','text'],
    ['tel','전화번호','text'],['fax','팩스번호','text'],['homepage','홈페이지','text'],
    ['dept_name','업체부서명','text'],['charge_name','담당자명','text'],['charge_rank','직급','text'],
    ['charge_tel','담당자전화','text'],['charge_hp','담당자H.P','text'],['charge_email','담당자이메일','text'],
    ['charge_user_id','담당사원','text'],['dlvy_day','납기일','num'],['dlvy_day2','납기일2','num'],
    ['ue_date','결제조건','sel','ue_date'],['ue_week','결제주','sel','ue_week'],
    ['bank_flag','은행/보험사','chk'],['bank_code','은행','sel','banks'],['bank_bookno','계좌번호','text'],
    ['bank_person_name','예금주','text'],['cms_no','CMS번호','text'],
    ['credit_limit','여신한도','num'],['collateral_amt','담보설정액','num'],
    ['sagub_out_flag','사급출고','chk'],['set_in_flag','세트입고','chk'],['heat_label_flag','열처리라벨','chk'],['prod_check_flag','생산확인','chk'],
    ['recv_post_no','수령지우편','text'],['recv_address','수령지주소','text'],['recv_address_dtl','수령지상세','text'],
    ['print_name','출력용거래처명','text'],['trade_start','거래시작일','date'],['trade_end','거래종료일','date'],
    ['gc_gubun','GC구분','text'],['remarks','비고','text'],['use_flag','사용여부','chk'],
  ];
  const load=async()=>{
    const qs=new URLSearchParams({q:st.q,use:st.use,ctype:st.ctype});
    try{const r=await fetch(`${API}/api/cust/list?${qs}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    render();
  };
  const fld=(f)=>{
    const [k,label,type,ok]=f, v=st.form[k]??'';
    if(type==='sel'){const os=opts[ok]||[];return `<select class="inp" data-fk="${k}" style="min-width:90px;width:auto;max-width:260px"><option value="">선택</option>${os.map(o=>`<option value="${esc(o.code)}" ${String(o.code)===String(v)?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>`;}
    if(type==='chk')return `<input type="checkbox" data-fk="${k}" ${(v===1||v==='1'||v===true)?'checked':''} style="width:18px;height:18px">`;
    if(type==='date')return `<input class="inp" data-fk="${k}" type="date" value="${esc(v)}" style="width:140px">`;
    const ro=(k==='cust_code'&&st.form._edit)?'readonly style="width:120px;background:#eef2f7"':'style="width:'+(type==='num'?90:160)+'px"';
    return `<input class="inp" data-fk="${k}" value="${esc(v)}" ${type==='num'?'inputmode="decimal"':''} ${ro}>`;
  };
  const render=()=>{
    const editing=st.form!==null;
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('basemaster'):true;   // 수정권한 게이트(규칙#16)
    host.innerHTML=`
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">검색</label><input class="inp" id="cm-q" value="${esc(st.q)}" placeholder="코드/명/대표자" style="width:150px">
       <label class="tl">거래처구분</label><select class="inp" id="cm-ct" style="width:auto"><option value="">전체</option>${opts.cust_type.map(o=>`<option value="${esc(o.code)}" ${st.ctype===o.code?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">사용</label><select class="inp" id="cm-use" style="width:auto"><option value="">전체</option><option value="1" ${st.use==='1'?'selected':''}>사용</option><option value="0" ${st.use==='0'?'selected':''}>중지</option></select>
       <button class="btn" id="cm-search">🔍 조회</button>
       ${ed?`<button class="btn" id="cm-new" style="background:#1c7c3a;color:#fff">➕ 신규</button>
       <button class="btn" id="cm-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${editing?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:640px;max-width:96vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>거래처 Maint ${st.form._edit?'— 수정 ('+esc(st.form.cust_code)+')':'— 신규'}</b><span id="cm-x" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
           <table style="border-collapse:collapse;width:100%"><tbody>${(()=>{let h='';for(let i=0;i<FIELDS.length;i+=2){const a=FIELDS[i],b=FIELDS[i+1];
             const cell=f=>f?`<td style="padding:5px 8px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:96px">${f[1]}${f[2]==='req'||f[0]==='cust_type'?'<span style="color:#c0392b">*</span>':''}</td><td style="padding:4px 8px 4px 0">${fld(f)}</td>`:'<td></td><td></td>';
             h+=`<tr>${cell(a)}${cell(b)}</tr>`;}return h;})()}</tbody></table>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
           <span style="color:#c0392b;font-size:11px">* 거래처명·거래처구분·역할(매입/매출/외주 최소1)·사업자번호는 검증됩니다.</span>
           <span><button class="btn" id="cm-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="cm-cancel">닫기</button></span></div>
       </div></div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr><th style="width:26px"></th>
        <th>거래처코드</th><th>거래처명</th><th>사업자등록번호</th><th>대표자</th><th>거래처구분</th><th>역할</th><th>사업자구분</th><th>전화번호</th><th>담당자</th><th class="center">사용</th><th style="width:46px">작업</th></tr></thead>
      <tbody>${st.rows.length?st.rows.map((r,i)=>`<tr>
        <td class="center">${ed?`<input type="checkbox" class="cm-chk" data-code="${esc(r.cust_code)}" ${st.sel.has(r.cust_code)?'checked':''}>`:''}</td>
        <td><b>${esc(r.cust_code)}</b></td><td class="cap" title="${esc(r.cust_name)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_name)}</td>
        <td>${esc(r.biz_no)}</td><td>${esc(r.owner_name)}</td><td>${esc(r.cust_type_nm)}</td><td>${esc(r.roles)}</td><td>${esc(r.biztag_nm)}</td>
        <td>${esc(r.tel)}</td><td>${esc(r.charge_name)}</td><td class="center">${r.use_flag?'<span class="bdg ok">사용</span>':'<span class="bdg off">중지</span>'}</td>
        <td class="center">${ed?`<button class="btn cm-edit" data-idx="${i}" style="padding:1px 6px;font-size:10px">수정</button>`:''}</td></tr>`).join(''):`<tr><td colspan="12" class="empty">조회 결과 없음${ed?' (➕신규로 등록)':''}</td></tr>`}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#cm-search').onclick=()=>{st.q=g('#cm-q').value;st.ctype=g('#cm-ct').value;st.use=g('#cm-use').value;load();};
    g('#cm-q').onkeyup=e=>{if(e.key==='Enter')g('#cm-search').click();};
    if(ed){
      g('#cm-new').onclick=async()=>{let code='';try{code=(await (await fetch(`${API}/api/cust/newcode`)).json()).code;}catch(e){}
        st.form={cust_code:code,use_flag:1,in_flag:1,out_flag:1,outside_flag:0,cust_type:'',business_tag:'1'};render();};
      g('#cm-del').onclick=()=>del([...st.sel]);
      host.querySelectorAll('.cm-chk').forEach(ch=>ch.onclick=()=>{const cd=ch.dataset.code;ch.checked?st.sel.add(cd):st.sel.delete(cd);});
      host.querySelectorAll('.cm-edit').forEach(b=>b.onclick=()=>{st.form=Object.assign({_edit:1},st.rows[+b.dataset.idx]);render();});
    }
    attachResizers(host);
    if(editing){
      g('#cm-cancel').onclick=g('#cm-x').onclick=()=>{st.form=null;render();};
      g('#cm-save').onclick=save;
      host.querySelectorAll('[data-fk]').forEach(el=>{
        const k=el.dataset.fk;
        if(el.type==='checkbox')el.onchange=()=>{st.form[k]=el.checked?1:0;};
        else el.oninput=()=>{st.form[k]=el.value;};
      });
    }
  };
  const save=async()=>{
    const f=st.form;
    if(!String(f.cust_name||'').trim()){alert('거래처명은 필수입니다');return;}
    if(!String(f.cust_type||'').trim()){alert('거래처구분을 선택하세요');return;}
    if(!(f.in_flag||f.out_flag||f.outside_flag)){alert('역할(매입/매출/외주) 최소 하나를 선택하세요');return;}
    try{const r=await fetch(`${API}/api/cust/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...f,user:'웹사용자'})});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료 ':'✅ 수정완료 ')+j.cust_code;st.form=null;await load();}
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 오류: '+e);}
  };
  const del=async(codes)=>{if(!codes.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(codes.length+'건을 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}/api/cust/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codes})});
      const j=await r.json();st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();await load();}
    catch(e){alert('삭제 오류: '+e);}
  };
  (async()=>{try{opts=await (await fetch(`${API}/api/cust/opts`)).json();}catch(e){}load();})();
}

/* ===== 범용 마스터 CRUD (부서·LINE-NO 등 단순 마스터 재사용) — cfg 구동 ===== */
/* cfg={sid,keyField,listEp,saveEp,delEp,cols:[{k,h,fmt?}],fields:[[k,label,type,opts?]],newDefaults,readOnly?,newcodeEp?} */
function mstCrud(host, cfg){
  const API=API_BASE;
  const st={rows:[],cnt:0,q:'',form:null,sel:new Set(),msg:''};
  const load=async()=>{
    // ★listEp 에 이미 쿼리(?kind=)가 있으면 & 로 잇는다. 응답이 orows(객체행)면 그걸 우선 사용
    //   (basemaster/list 는 rows=배열행 / orows=c0..cN 객체행 둘 다 준다).
    const _sep=cfg.listEp.includes('?')?'&':'?';
    try{const r=await fetch(`${API}${cfg.listEp}${_sep}q=`+encodeURIComponent(st.q));const j=await r.json();
      st.rows=j.orows||j.rows||[];st.cnt=j.cnt||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    render();
  };
  const kf=cfg.keyField;
  const fld=(f)=>{
    const [k,label,type,ops]=f, v=st.form[k]??'';
    if(type==='sel'){const os=ops||[];return `<select class="inp" data-fk="${k}" style="min-width:80px;width:auto;max-width:240px"><option value="">선택</option>${os.map(o=>`<option value="${esc(o.code)}" ${String(o.code)===String(v)?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>`;}
    if(type==='chk')return `<input type="checkbox" data-fk="${k}" ${(v===1||v==='1'||v===true)?'checked':''} style="width:18px;height:18px">`;
    if(type==='date')return `<input class="inp" data-fk="${k}" type="date" value="${esc(v)}" style="width:140px">`;
    const ro=(k===kf&&st.form._edit)?'readonly style="width:130px;background:#eef2f7"':'style="width:'+(type==='num'?90:180)+'px"';
    return `<input class="inp" data-fk="${k}" value="${esc(v)}" ${type==='num'?'inputmode="decimal"':''} ${ro}>`;
  };
  const render=()=>{
    const editing=st.form!==null;
    const ed=(!cfg.readOnly)&&((typeof PERM!=='undefined')?PERM.canEdit(cfg.sid||'basemaster'):true);
    host.innerHTML=`
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">검색</label><input class="inp" id="ms-q" value="${esc(st.q)}" placeholder="코드/명" style="width:150px">
       <button class="btn" id="ms-search">🔍 조회</button>
       ${cfg.readOnly?'<span style="color:#8aa0bd;font-size:12px">🔎 조회 전용 (편집은 개발›원가/BOM기준정보)</span>':(ed?`<button class="btn" id="ms-new" style="background:#1c7c3a;color:#fff">➕ 신규</button><button class="btn" id="ms-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`)}
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${editing?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:760px;max-width:96vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>${esc(cfg.title||'마스터')} ${st.form._edit?'— 수정 ('+esc(st.form[kf])+')':'— 신규'}</b><span id="ms-x" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
           <!-- ★2026-08-23 입력칸이 잘려 가로스크롤 생기던 것 수정: 라벨=고정폭, 입력=남는폭 채움(table-layout:fixed).
                fld() 의 인라인 width 는 .ms-in 의 width:100% 로 덮는다(min-width 0 = flex/table 축소 허용). -->
           <table style="border-collapse:collapse;width:100%;table-layout:fixed"><tbody>${(()=>{let h='';for(let i=0;i<cfg.fields.length;i+=2){const a=cfg.fields[i],b=cfg.fields[i+1];
             const cell=f=>f?`<td style="padding:5px 8px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:104px">${f[1]}${f[2]==='req'?'<span style="color:#c0392b">*</span>':''}</td><td style="padding:4px 8px 4px 0">${fld(f)}</td>`:'<td style="width:104px"></td><td></td>';
             h+=`<tr>${cell(a)}${cell(b)}</tr>`;}return h;})()}</tbody></table>
           <style>.wr-modal .inp,.wr-modal select.inp{width:100%!important;min-width:0!important;max-width:none!important;box-sizing:border-box}
                  .wr-modal input[type=checkbox]{width:18px!important}</style>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:flex-end;gap:8px">
           <button class="btn" id="ms-save" style="background:#1b6ec2;color:#fff">💾 저장</button><button class="btn" id="ms-cancel">닫기</button></div>
       </div></div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>${ed?'<th style="width:26px"></th>':''}${cfg.cols.map(col=>`<th class="${col.cls||''}">${col.h}</th>`).join('')}${ed?'<th style="width:46px">작업</th>':''}</tr></thead>
      <tbody>${st.rows.length?st.rows.map((r,i)=>`<tr>
        ${ed?`<td class="center"><input type="checkbox" class="ms-chk" data-code="${esc(r[kf])}" ${st.sel.has(r[kf])?'checked':''}></td>`:''}
        ${cfg.cols.map((col,ci)=>`<td class="${col.cls||''}" ${col.cap?`title="${esc(r[col.k]||'')}" style="max-width:${col.cap===true?150:col.cap}px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"`:''}>${ci===0?'<b>':''}${col.fmt?col.fmt(r):esc(r[col.k]??'')}${ci===0?'</b>':''}</td>`).join('')}
        ${ed?`<td class="center"><button class="btn ms-edit" data-idx="${i}" style="padding:1px 6px;font-size:10px">수정</button></td>`:''}</tr>`).join(''):`<tr><td colspan="${cfg.cols.length+(ed?2:0)}" class="empty">조회 결과 없음${ed?' (➕신규로 등록)':''}</td></tr>`}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#ms-search').onclick=()=>{st.q=g('#ms-q').value;load();};
    g('#ms-q').onkeyup=e=>{if(e.key==='Enter')g('#ms-search').click();};
    if(ed){
      g('#ms-new').onclick=async()=>{let d=Object.assign({},cfg.newDefaults||{});
        if(cfg.newcodeEp){try{d[kf]=(await (await fetch(`${API}${cfg.newcodeEp}`)).json()).code;}catch(e){}}
        st.form=d;render();};
      g('#ms-del').onclick=()=>del([...st.sel]);
      host.querySelectorAll('.ms-chk').forEach(ch=>ch.onclick=()=>{const cd=ch.dataset.code;ch.checked?st.sel.add(cd):st.sel.delete(cd);});
      host.querySelectorAll('.ms-edit').forEach(b=>b.onclick=()=>{st.form=Object.assign({_edit:1},st.rows[+b.dataset.idx]);render();});
    }
    attachResizers(host);
    if(editing){
      g('#ms-cancel').onclick=g('#ms-x').onclick=()=>{st.form=null;render();};
      g('#ms-save').onclick=save;
      host.querySelectorAll('[data-fk]').forEach(el=>{const k=el.dataset.fk;
        if(el.type==='checkbox')el.onchange=()=>{st.form[k]=el.checked?1:0;};else el.oninput=()=>{st.form[k]=el.value;};});
    }
  };
  const save=async()=>{
    for(const f of cfg.fields){if(f[2]==='req'&&!String(st.form[f[0]]??'').trim()){alert(f[1]+'은(는) 필수입니다');return;}}
    if(!String(st.form[kf]??'').trim()){alert('코드는 필수입니다');return;}
    // cfg.kind 가 있으면 payload 에 실어 보낸다(조립/단품 공정마스터처럼 한 엔드포인트가 종류를 받는 경우)
    try{const r=await fetch(`${API}${cfg.saveEp}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...st.form,...(cfg.kind?{kind:cfg.kind}:{}),user:'웹사용자',uuser:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자')})});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료':'✅ 수정완료');st.form=null;await load();}
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 오류: '+e);}
  };
  const del=async(codes)=>{if(!codes.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(codes.length+'건을 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}${cfg.delEp}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codes,...(cfg.kind?{kind:cfg.kind}:{})})});
      const j=await r.json();st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();await load();}
    catch(e){alert('삭제 오류: '+e);}
  };
  load();
}
const MST_CFG={
  dept:{sid:'basemaster',title:'부서 마스터',keyField:'dept_code',listEp:'/api/dept/list',saveEp:'/api/dept/save',delEp:'/api/dept/delete',
    cols:[{k:'dept_code',h:'부서코드'},{k:'dept_desc',h:'부서명',cap:180},{k:'sort_key',h:'정렬',cls:'num'},{k:'fin_dept_code',h:'재무부서'},{k:'dept_from_ymd',h:'적용시작'},{k:'dept_to_ymd',h:'적용종료'},{k:'use_flag',h:'사용',cls:'center',fmt:r=>r.use_flag?'<span class="bdg ok">사용</span>':'<span class="bdg off">중지</span>'}],
    fields:[['dept_code','부서코드','text'],['dept_desc','부서명','req'],['sort_key','정렬순서','num'],['use_flag','사용여부','chk'],['dept_desch','한자명','text'],['dept_from_ymd','적용시작','text'],['dept_to_ymd','적용종료','text'],['fin_dept_code','재무부서','text'],['fin_from_ymd','재무시작','text'],['fin_to_ymd','재무종료','text'],['enterprise_dept','전사부서','text'],['wh_code','창고','text'],['remarks','비고','text']],
    newDefaults:{use_flag:1,sort_key:0}},
  line:{sid:'basemaster',title:'라인 마스터',keyField:'line_no',listEp:'/api/line/list',saveEp:'/api/line/save',delEp:'/api/line/delete',org:'nx.line_no',
    // ★명칭·구성을 레거시 「LINE-NO MASTER」와 동일하게(2026-08-27).
    //   maint_day/maint_hhmm = 라인당김(변경일자·변경시간)
    //   cust_maint_day = 직납당김 — 파트별계획 없는 직납품에 추가로 적용되는 당김일수(CA=1).
    //     STEP7 의 nx.plan_direct_pull 이 이 값을 읽는다.
    //   ⛔연결거래처(link_cust_code)는 미사용 항목이라 제외(사용자 확인).
    cols:[{k:'line_no',h:'라인번호',cap:140},{k:'apply_ymd',h:'적용일'},{k:'maint_day',h:'변경일자',cls:'num'},{k:'maint_hhmm',h:'변경시간',cls:'center',fmt:r=>{let v=String(r.maint_hhmm||'').replace(/\D/g,'');if(!v)return '';v=v.padStart(4,'0').slice(-4);return v.slice(0,2)+':'+v.slice(2);}},{k:'cust_maint_day',h:'직납당김',cls:'num'}],
    fields:[['line_no','라인번호','req'],['apply_ymd','적용일(YYMMDD)','text'],['maint_day','변경일자','num'],['maint_hhmm','변경시간(HHMM)','text'],['cust_maint_day','직납당김','num']],
    newDefaults:{maint_day:0,maint_hhmm:'0000'}},
  // ★2026-08-23 조립/단품 공정마스터 등록·수정·삭제 추가(기존엔 조회만 — 거래처·부서·라인만 편집 가능했음).
  //   저장/삭제는 nx 원장(CLAUDE.md §1). 목록 컬럼키는 /api/basemaster/list 가 c0..cN 으로 주므로
  //   listEp 를 basemaster/list?kind= 로 두고 keyField 는 코드컬럼 인덱스(c0)를 쓴다.
  //   행/폼 키는 목록 응답과 같은 c0..cN 으로 통일(수정 시 기존값이 그대로 폼에 채워지도록).
  //   백엔드 procmaster_save 가 c0=코드, c1.. 을 각 컬럼으로 매핑한다.
  assem:{sid:'basemaster',title:'조립공정 마스터',kind:'assem',keyField:'c0',
    listEp:'/api/basemaster/list?kind=assem',saveEp:'/api/procmaster/save',delEp:'/api/procmaster/delete',org:'nx.CS_M_ASSEM_PROC',
    cols:[{k:'c0',h:'공정코드'},{k:'c1',h:'공정명',cap:200},{k:'c2',h:'표준ST',cls:'num'},{k:'c3',h:'정렬',cls:'num'},{k:'c4',h:'사용',cls:'center'}],
    fields:[['c0','공정코드','req'],['c1','공정명','req'],['c2','표준ST','num'],['c3','정렬순서','num'],
            ['c4','사용여부','sel',[{code:'Y',nm:'사용'},{code:'N',nm:'중지'}]]],
    newDefaults:{c4:'Y',c3:0,c2:0}},
  proc:{sid:'basemaster',title:'단품공정 마스터',kind:'proc',keyField:'c0',
    listEp:'/api/basemaster/list?kind=proc',saveEp:'/api/procmaster/save',delEp:'/api/procmaster/delete',org:'nx.CS_M_PROC',
    cols:[{k:'c0',h:'공정코드'},{k:'c1',h:'공정명',cap:200},{k:'c2',h:'대분류'},{k:'c3',h:'정렬',cls:'num'},{k:'c4',h:'표준UPH',cls:'num'},{k:'c5',h:'사용',cls:'center'}],
    fields:[['c0','공정코드','req'],['c1','공정명','req'],['c2','대분류','text'],['c3','정렬순서','num'],['c4','표준UPH','num'],
            ['c5','사용여부','sel',[{code:'Y',nm:'사용'},{code:'N',nm:'중지'}]]],
    newDefaults:{c5:'Y',c3:0,c4:0}},
};

/* ===== 라인별달력 (LG 라인스케줄 매트릭스 + 엑셀 업로드) — 생산계획 가동캘린더 ===== */
function lineCalView(host){
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  // ★시작주 = 당일(2026-08-27 요청). 종전엔 그 주 월요일로 맞춰 지난 날짜가 앞에 붙었다.
  const T=new Date();
  const st={data:null,from:iso(T),weeks:4,anchor:iso(T),msg:'',busy:false};
  const codeSty=(v)=>{const s=(v||'').trim();
    if(!s)return 'background:#eaedf1;color:#c2c8d0';     // 빈칸=휴무
    const n=parseFloat(s);
    if(!isNaN(n)){
      if(n>10) return 'background:#e23b3b;color:#fff';    // 10 초과(10.5·11) = 빨강
      if(n>=9) return 'background:#37cde6;color:#04303a'; // 9~10 = 하늘색
    }
    return 'background:#232a33;color:#fff';};             // 나머지(8·7.5·재작업·SKD·rac이동 등) = 검정
  const load=async()=>{
    try{const r=await fetch(`${API}/api/linecal/matrix?from_ymd=${st.from}&weeks=${st.weeks}`);st.data=await r.json();}
    catch(e){st.msg='백엔드 연결 실패';}
    render();};
  const doUpload=async(f)=>{
    if(!f)return;
    if(!st.anchor){alert('기준일(적용날짜)을 입력하세요');return;}
    st.busy=true;render();
    const fd=new FormData();fd.append('file',f);fd.append('anchor_ymd',st.anchor);
    try{const r=await fetch(`${API}/api/linecal/upload`,{method:'POST',body:fd});const j=await r.json();
      if(r.ok&&j.ok){st.msg=`✅ 업로드 완료: ${j.recs}건·특수일 ${j.events} (${j.date_from}~${j.date_to})`;
        // 업로드 기준일 주 월요일로 창 이동
        st.from=j.anchor;await load();}   // ★업로드 기준일 그대로(월요일 보정 안 함)
      else{alert('업로드 실패: '+(j.detail||JSON.stringify(j)));}}
    catch(e){alert('업로드 오류: '+e);}
    st.busy=false;render();};
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('basemaster'):true;
    const d=st.data;
    // ★스크롤 1개만(CLAUDE.md §3) — 화면 루트를 flex 컬럼으로,
    //   업로드박스·툴바는 flex:0 0 auto, 표 영역만 flex:1;min-height:0;overflow:auto.
    host.style.cssText='display:flex;flex-direction:column;height:100%;min-height:0';
    host.innerHTML=`
     ${ed?`<div id="lc-drop" style="flex:0 0 auto;border:2px dashed #8fb4d6;border-radius:9px;padding:12px 14px;background:#f4f9fe;display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px">
        <span style="font-size:20px">📤</span>
        <b>LG 라인스케줄 엑셀</b>을 여기로 <b>드래그&드롭</b> 하거나
        <button class="btn" id="lc-pick">📁 파일 선택</button>
        <input type="file" id="lc-file" accept=".xlsx,.xls" style="display:none">
        <span style="margin-left:auto"></span>
        <label class="tl">기준일(적용날짜)</label><input class="inp" type="date" id="lc-anchor" value="${st.anchor}" style="width:150px">
        ${st.busy?'<span style="color:#1c47a0">⏳ 처리중…</span>':''}
      </div>`:`<div class="page-sub" style="flex:0 0 auto">🔒 업로드는 수정권한 필요 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</div>`}
     <div class="toolbar" style="gap:6px;flex:0 0 auto">
       <label class="tl">시작주(월)</label><input class="inp" type="date" id="lc-from" value="${st.from}" style="width:150px">
       <label class="tl">기간</label><select class="inp" id="lc-weeks" style="width:auto"><option value="4" ${st.weeks==4?'selected':''}>4주</option><option value="6" ${st.weeks==6?'selected':''}>6주</option><option value="8" ${st.weeks==8?'selected':''}>8주</option></select>
       <button class="btn" id="lc-go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${d?d.from+'~'+d.to:''}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="flex:0 0 auto;color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      ${d?`<table class="tbl" style="font-size:11px;border-collapse:collapse">
        <thead>
         <tr><th style="position:sticky;left:0;top:0;background:#eef2f7;z-index:4">구분</th>
           <th style="position:sticky;top:0;background:#eef2f7;z-index:3">라인</th>
           <th style="position:sticky;top:0;background:#eef2f7;z-index:3">No.</th>
           <th style="position:sticky;top:0;background:#eef2f7;z-index:3">진도</th>
           ${d.dates.map(x=>`<th class="center" style="position:sticky;top:0;background:#eef2f7;z-index:3;min-width:26px;${x.dow==='토'?'color:#2a6ad6':(x.dow==='일'?'color:#d63a3a':'')}">${x.mon}/${x.day}<br><span style="font-weight:400">${x.dow}</span></th>`).join('')}</tr>
        </thead>
        <tbody>${d.lines.length?(()=>{
          // ★3그룹으로 나눠 보여준다(2026-08-27 사용자 요청 — "공통 맨 위, 선 아래는 수기").
          //   ① 공통(기준)  ② LG 엑셀 업로드 라인  ③ 수기 입력 라인
          //   그룹 경계에 헤더행을 끼워 넣어 어디까지가 자동/수기인지 한눈에 보이게 한다.
          const G1=d.lines.filter(L=>L.common), G2=d.lines.filter(L=>!L.common&&L.lg), G3=d.lines.filter(L=>!L.common&&!L.lg);
          const NC=4+d.dates.length;
          const sep=(txt,bg,fg)=>`<tr><td colspan="${NC}" style="position:sticky;left:0;z-index:2;background:${bg};color:${fg};font-weight:700;font-size:11px;padding:3px 8px;border-top:2px solid ${fg}">${esc(txt)}</td></tr>`;
          const row=L=>`<tr${L.common?' style="background:#fff7e0;font-weight:600"':(L.lg?'':' style="background:#fcfdff"')}>
          <td style="position:sticky;left:0;background:${L.common?'#fff7e0':'#fff'};white-space:nowrap">${esc(L.gubun)}</td>
          <td class="center"><b>${esc(L.line_no)}</b>${L.common?'':(L.lg?'':'<span class="bdg" style="font-size:8px;margin-left:3px;background:#eef2f8;color:#5a6b80;border:1px solid #d3dceb;border-radius:5px;padding:0 3px" title="LG 엑셀에 없는 라인 — 수기 입력 대상">수기</span>')}</td><td class="center">${esc(L.model_no)}</td><td class="center">${esc(L.jindo)}</td>
          ${d.dates.map(x=>{let v=L.cells[x.ymd]||'',sc=(L.srcs||{})[x.ymd]||'',inh=0;
             // ★값이 없으면 공통달력을 상속(편성 규칙과 동일) — 흐리게 표시해 '기본값'임을 구분.
             if(!v&&!L.common){const b=(d.base||{})[x.ymd]||'';if(b){v=b;sc='COMMON';inh=1;}}
             // 수기(MANUAL)/미러(MIRROR)/공통은 근무유형 코드(1~7) → 라벨. LG 는 가동시간 숫자 그대로.
             const isC=sc!=='LG'&&WS_STY[v];
             let sty=isC?`background:${WS_STY[v].c};color:#fff`:codeSty(v);
             if(inh)sty+=';opacity:.38';
             // ★LG 업로드 라인도 수정 가능(2026-08-27) — 가동시간은 보존되고 근무유형 코드만 바뀐다.
             const tx=isC?WS_STY[v].t:v, canEd=ed&&!L.common;
             // ⛔근무유형 배지는 넣지 않는다(2026-08-27) — 가동시간 11 옆에 '정상'(코드2)이 붙어
             //   "11이 왜 정상?" 처럼 읽혀 혼란만 준다. 셀은 **원본 값 그대로** 보여준다.
             //   지정된 근무유형은 툴팁과 편집 팝업에서 확인한다.
             const ws2=(L.stats||{})[x.ymd]||'';
             return `<td class="center lc-cell" data-ln="${esc(L.line_no)}" data-ymd="${esc(x.ymd)}" data-src="${esc(inh?'':sc)}" title="${esc(x.ymd)} ${esc(v)}${inh?' [공통 상속]':(sc?' ['+esc(sc)+']':'')}${(sc==='LG'&&ws2&&WS_STY[ws2])?' · 근무유형 '+WS_STY[ws2].t:''}${canEd?' · 클릭하여 수정':''}" style="${sty};font-size:10px;padding:2px${canEd?';cursor:pointer':''}">${esc(tx)}</td>`;}).join('')}
        </tr>`;
          return (G1.length?sep('■ 기준 — 공통 달력 (라인에 값이 없으면 이 값을 따름)','#fff2cc','#8a6d00')+G1.map(row).join(''):'')
               + (G2.length?sep('■ LG 라인스케줄 (엑셀 자동 업로드 · 셀 클릭하여 가동시간·근무유형 수정)','#e6f0fb','#1c47a0')+G2.map(row).join(''):'')
               + (G3.length?sep('■ 수기 입력 라인 (LG 엑셀에 없음 · 셀 클릭하여 입력)','#eef6ee','#1c7c3a')+G3.map(row).join(''):'');
        })():`<tr><td colspan="${4+d.dates.length}" class="empty">데이터 없음 — 엑셀을 업로드하세요</td></tr>`}</tbody></table>`
       :`<div class="empty" style="padding:30px">불러오는 중…</div>`}</div>`;
    const g=id=>host.querySelector(id);
    g('#lc-go').onclick=()=>{st.from=g('#lc-from').value;st.weeks=+g('#lc-weeks').value;load();};
    if(ed){
      const drop=g('#lc-drop'),fi=g('#lc-file');
      g('#lc-pick').onclick=()=>fi.click();
      g('#lc-anchor').onchange=()=>{st.anchor=g('#lc-anchor').value;};
      fi.onchange=()=>{if(fi.files[0]){autoAnchor(fi.files[0].name);doUpload(fi.files[0]);}};
      drop.ondragover=e=>{e.preventDefault();drop.style.background='#e3f0ff';};
      drop.ondragleave=()=>{drop.style.background='#f4f9fe';};
      drop.ondrop=e=>{e.preventDefault();drop.style.background='#f4f9fe';const f=e.dataTransfer.files[0];if(f){autoAnchor(f.name);doUpload(f);}};
      // ★셀 클릭 = 수기 입력(2026-08-27). LG 엑셀은 8개 라인만 들어오므로 나머지는 수기로 채운다.
      //   ★LG 업로드 라인도 편집 가능 — 서버가 work_code(가동시간)는 보존하고
      //     work_stats(근무유형 코드)만 갱신한다. 특근처럼 엑셀에 없는 정보를 찍어야
      //     편성 근무일이 맞기 때문(예: C1 260829 '정상').
      host.querySelectorAll('.lc-cell').forEach(td=>{
        td.onclick=()=>openCell(td);
      });
    }
  };
  // 셀 편집 팝업 — 근무유형 드롭다운(WS_OPTS). body 에 렌더(CLAUDE.md §3 모달규칙)
  const openCell=(td)=>{
    const ln=td.dataset.ln, ymd=td.dataset.ymd, src=td.dataset.src||'';
    const _L=st.data.lines.find(x=>x.line_no===ln)||{cells:{}};
    const _cur=(_L.cells||{})[ymd]||'';
    const isLG=src==='LG';            // LG 가동시간이 들어있는 칸
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.25);z-index:1200;display:flex;align-items:center;justify-content:center';
    ov.innerHTML=`<div style="background:#fff;border-radius:10px;padding:14px 16px;width:330px;max-width:92vw;box-shadow:0 8px 30px rgba(0,0,0,.25)">
      <div style="font-weight:700;margin-bottom:8px">라인 <b>${esc(ln)}</b> · ${esc(ymd)}</div>
      <!-- ★2026-08-31 확정 규칙(편성 planrev._wd_of 와 동일):
             1) 가동시간이 있으면 → **근무**(정상). 이때 근무유형은 잠근다 —
                "가동 8h 인데 휴무" 같은 모순 상태를 아예 못 만들게 한다(사용자 확정).
             2) 가동시간을 지우면 → 근무유형을 고를 수 있고, 그 값을 따른다.
             3) 둘 다 비면 → 공통 달력. -->
      <div style="font-size:11px;color:#5a6b80;background:#eef4fb;border:1px solid #d3e0ef;border-radius:6px;padding:5px 8px;margin-bottom:9px;line-height:1.5">
         가동시간 있으면 <b>근무</b>(7.5·8=정상 · 11=잔업3h) · 지우면 근무유형 선택 · 둘 다 비면 공통</div>
      <label class="tl">가동시간</label>
      <input class="inp" id="lcx-hrs" style="width:100%;margin:3px 0 9px" autocomplete="off"
             placeholder="8 · 7.5 · 11" value="${esc(isLG?_cur:'')}">
      <label class="tl">근무유형 <span style="color:#8aa0bd;font-weight:400" id="lcx-wslab"></span></label>
      <select class="inp" id="lcx-ws" style="width:100%;margin:3px 0 9px">
        ${WS_OPTS.map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select>
      <!-- ★지금 입력값으로 편성이 어떻게 판정하는지 즉시 보여준다(오해 방지) -->
      <div id="lcx-eff" style="font-size:11.5px;font-weight:700;padding:6px 8px;border-radius:6px;margin-bottom:10px;line-height:1.45"></div>
      <div style="display:flex;gap:6px;justify-content:flex-end">
        <button class="btn ghost" id="lcx-cancel">취소</button>
        <button class="btn" id="lcx-ok">저장</button></div></div>`;
    document.body.appendChild(ov);
    const sel=ov.querySelector('#lcx-ws');
    // ★편성 판정 미리보기 — planrev._wd_of 와 같은 순서로 계산해 보여준다.
    const _baseWs=(st.data&&st.data.base)?(st.data.base[ymd]||''):'';
    const showEff=()=>{
      const h=(ov.querySelector('#lcx-hrs').value||'').trim();
      // ★가동시간이 있으면 근무유형은 잠근다 — 모순 상태(가동8h+휴무)를 못 만들게.
      const lab=ov.querySelector('#lcx-wslab');
      sel.disabled=!!h;
      sel.style.background=h?'#f1f3f6':'';
      sel.style.color=h?'#8aa0bd':'';
      if(lab) lab.textContent=h?'(가동시간 우선 — 잠김)':'';
      const w=h?'':sel.value;                       // 가동시간 있으면 근무유형 무시
      let work,src;
      if(h){ work=true; src='가동시간 '+h+' · 정상근무'; }
      else if(w){ work=['1','2','5','6','7'].includes(w); src='근무유형 '+((WS_STY[w]||{}).t||w); }
      else { work=['1','2','5','6','7'].includes(_baseWs); src='공통달력 '+((WS_STY[_baseWs]||{}).t||_baseWs||'-'); }
      const el=ov.querySelector('#lcx-eff');
      el.style.background=work?'#e9f7ef':'#fdecea';
      el.style.color=work?'#1c7c3a':'#b3261e';
      el.innerHTML=`편성 판정 <b>${work?'근무':'휴무'}</b> <span style="font-weight:400;opacity:.75">· ${esc(src)}</span>`
        +(work?'':'<span style="font-weight:400;opacity:.75"> · 계획이 앞 근무일로 당겨짐</span>');
    };
    // ★현재 근무유형 코드 = stats(별도 필드) 우선. LG 칸은 표시값이 가동시간이라 코드가 가려진다.
    const cur=((_L.stats||{})[ymd])||(isLG?'':_cur);
    if([...sel.options].some(o=>o.value===cur))sel.value=cur;
    sel.onchange=showEff; ov.querySelector('#lcx-hrs').oninput=showEff; showEff();
    const close=()=>ov.remove();
    ov.querySelector('#lcx-cancel').onclick=close;
    ov.onclick=e=>{if(e.target===ov)close();};
    ov.querySelector('#lcx-ok').onclick=async()=>{
      try{
        // ★hrs 를 항상 함께 보낸다 — 빈 문자열이면 서버가 가동시간을 지운다.
        //   가동시간이 있으면 근무유형은 **비워서** 저장한다(모순 상태 방지·판정은 가동시간으로).
        const hrsEl=ov.querySelector('#lcx-hrs');
        const _h=hrsEl?hrsEl.value.trim():'';
        const r=await fetch(`${API}/api/linecal/save`,{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({items:[{line_no:ln,ymd:ymd,ws:(_h?'':sel.value),hrs:_h}]})});
        const j=await r.json();
        st.msg=j.ok?`✅ ${esc(ln)} ${esc(ymd)} ${j.note||''}`:'저장 실패';
      }catch(e){st.msg='저장 오류: '+e;}
      close();await load();
    };
  };
  const autoAnchor=(name)=>{const m=(name||'').match(/(20\d{6})/);if(m){const s=m[1];st.anchor=`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`;}};
  load();
}

/* ===== 근무달력/파트별달력 매트릭스 (nx.work_calendar/part_calendar) — 기본조회+수정 ===== */
const WS_STY={'1':{t:'잔2',c:'#2f9e55'},'2':{t:'정상',c:'#3aa76a'},'5':{t:'잔3',c:'#1f7a44'},'6':{t:'잔4',c:'#155c33'},'7':{t:'4h',c:'#6f9e52'},'3':{t:'일',c:'#e05a5a'},'4':{t:'휴',c:'#aeb6c2'}};
const WS_OPTS=[['','—'],['2','정상'],['1','잔업2h'],['5','잔업3h'],['6','잔업4h'],['7','4h근무'],['3','일요일'],['4','휴무']];
function wcalView(host,kind){
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date(),mon=new Date(T);mon.setDate(T.getDate()-((T.getDay()+6)%7));
  const st={data:null,from:iso(mon),weeks:4,edit:false,edits:{},cellEdit:null,msg:''};
  const cellSty=v=>{const w=WS_STY[(v||'').trim()];return w?`background:${w.c};color:#fff`:'background:#f1f3f6;color:#b8c0cc';};
  const cellTxt=v=>{const w=WS_STY[(v||'').trim()];return w?w.t:'';};
  const load=async()=>{try{const r=await fetch(`${API}/api/wcal/matrix?kind=${kind}&from_ymd=${st.from}&weeks=${st.weeks}`);st.data=await r.json();}catch(e){st.msg='백엔드 연결 실패';}render();};
  const val=(row,ymd)=>{const k=row.ent+'|'+ymd;return (k in st.edits)?st.edits[k]:(row.cells[ymd]||'');};
  const save=async()=>{
    const cells=Object.keys(st.edits).map(k=>{const[ent,ymd]=k.split('|');return{ent,ymd,ws:st.edits[k]};});
    if(!cells.length){st.edit=false;render();return;}
    try{const r=await fetch(`${API}/api/wcal/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,cells,user:'웹사용자'})});
      const j=await r.json();if(r.ok&&j.ok){st.msg=`✅ ${j.saved}건 저장`;st.edits={};st.edit=false;await load();}else alert('저장실패: '+(j.detail||''));}
    catch(e){alert('저장오류: '+e);}};
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('basemaster'):true;
    const d=st.data;
    host.innerHTML=`
     <div class="toolbar" style="gap:6px;flex-wrap:wrap">
       <label class="tl">시작주(월)</label><input class="inp" type="date" id="wc-from" value="${st.from}" style="width:150px">
       <label class="tl">기간</label><select class="inp" id="wc-weeks" style="width:auto"><option value="4" ${st.weeks==4?'selected':''}>4주</option><option value="6" ${st.weeks==6?'selected':''}>6주</option><option value="8" ${st.weeks==8?'selected':''}>8주</option></select>
       <button class="btn" id="wc-go">🔍 조회</button>
       ${st.edit?`<button class="btn" id="wc-save" style="background:#1b6ec2;color:#fff">💾 저장</button><button class="btn" id="wc-cancel">취소</button>`
         :(ed?`<button class="btn" id="wc-edit" style="background:#1c7c3a;color:#fff">✎ 수정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음</span>`)}
       <span class="page-sub" style="margin:0 0 0 8px">정상/잔업=<b style="color:#2f9e55">근무</b> · <b style="color:#e05a5a">일</b> · <b style="color:#8a95a5">휴</b> ${st.edit?'· <b>셀 클릭→선택</b>':''}</span>
       <div class="spacer"></div><span class="rowcount">${d?d.from+'~'+d.to:''}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      ${d?`<table class="tbl" style="font-size:11px;border-collapse:collapse">
        <thead><tr><th style="position:sticky;left:0;background:#dfe7f2;z-index:2;min-width:120px">${kind==='work'?'근무팀':'파트'}</th>
          ${d.dates.map(x=>`<th class="center" style="min-width:44px;${x.dow==='토'?'background:#ffe0b0':(x.dow==='일'?'background:#ffd0d0':'')}">${x.mon}/${String(x.day).padStart(2,'0')}<br><span style="font-weight:400">${x.dow}</span></th>`).join('')}</tr></thead>
        <tbody>${d.rows.map(row=>`<tr>
          <td style="position:sticky;left:0;background:${row.common?'#3d6fc0':(row.indent?'#fff':'#eef3fb')};${row.common?'color:#fff;font-weight:700':(row.indent?'':'font-weight:700')};white-space:nowrap;text-align:${row.indent?'left':'center'};padding-left:${(row.indent||0)*18+8}px">${esc(row.name)}</td>
          ${d.dates.map(x=>{const v=val(row,x.ymd),ck=row.ent+'|'+x.ymd;
            if(st.edit&&st.cellEdit===ck){return `<td class="center" style="padding:0"><select class="wc-sel" data-k="${esc(ck)}" style="width:100%;font-size:10px">${WS_OPTS.map(o=>`<option value="${o[0]}" ${o[0]===v?'selected':''}>${o[1]}</option>`).join('')}</select></td>`;}
            return `<td class="center ${st.edit?'wc-cell':''}" data-k="${esc(ck)}" title="${esc((d.decode&&d.decode[v])||'')}" style="${cellSty(v)};font-size:10px;padding:2px;${st.edit?'cursor:pointer':''}">${esc(cellTxt(v))}</td>`;}).join('')}
        </tr>`).join('')}</tbody></table>`:`<div class="empty" style="padding:30px">불러오는 중…</div>`}</div>`;
    const g=id=>host.querySelector(id);
    g('#wc-go').onclick=()=>{st.from=g('#wc-from').value;st.weeks=+g('#wc-weeks').value;st.edits={};st.cellEdit=null;load();};
    if(st.edit){
      g('#wc-save').onclick=save;
      g('#wc-cancel').onclick=()=>{st.edit=false;st.edits={};st.cellEdit=null;render();};
      host.querySelectorAll('.wc-cell').forEach(td=>td.onclick=()=>{st.cellEdit=td.dataset.k;render();
        const sel=host.querySelector('.wc-sel');if(sel){sel.focus();sel.onchange=()=>{st.edits[sel.dataset.k]=sel.value;st.cellEdit=null;render();};sel.onblur=()=>{st.cellEdit=null;render();};}});
    }else if(ed){const eb=g('#wc-edit');if(eb)eb.onclick=()=>{st.edit=true;render();};}
    attachResizers(host);
  };
  load();
}

/* ================= 품질(QUALITY) 모듈 ================= */
/* 공용 읽기전용 그리드(라이브 레거시 조회 / IQC 조회). cfg={listEp,buildQS,cols,dateLabel,filters,days,filt0,sum,onRow} */
function qcRead(host, cfg){
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date(), back=cfg.days||30;
  const st={F:Object.assign({from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T)},cfg.filt0||{}),
            data:{rows:[],cnt:0}, loading:false, msg:'', sel:null, sub:null};
  const load=async()=>{st.loading=true;st.sub=null;render();
    try{const r=await fetch(`${API}${cfg.listEp}?`+new URLSearchParams(cfg.buildQS(st.F)));st.data=await r.json();st.msg='';}
    catch(e){st.msg='백엔드 연결 실패 — uvicorn app:app --port 8010';st.data={rows:[],cnt:0};}
    st.loading=false;render();};
  const pickRow=async(r)=>{if(!cfg.onRow)return;st.sel=r;st.sub={loading:true};render();
    try{st.sub=await cfg.onRow(r);}catch(e){st.sub={rows:[],err:1};}render();};
  const render=()=>{
    const d=st.data;
    host.innerHTML=`
     <div class="toolbar">
       <label class="tl">${cfg.dateLabel||'기간'}</label>
       <input class="inp" type="date" id="qr-from" value="${st.F.from}"> ~ <input class="inp" type="date" id="qr-to" value="${st.F.to}">
       ${qfFields(cfg.filters,st.F,'qr-f-')}
       <button class="btn" id="qr-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${_wnf(d.cnt||0)}건${cfg.sum?(' · '+cfg.sum(d)):''}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - ${cfg.onRow?430:330}px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>${cfg.cols.map(col=>`<th class="${col.cls||''}">${col.h}</th>`).join('')}</tr></thead>
      <tbody>${st.loading?spinRow(cfg.cols.length):((d.rows&&d.rows.length)?d.rows.map((r,i)=>`<tr class="qr-row${st.sel===r?' sel':''}" data-i="${i}" ${cfg.onRow?'style="cursor:pointer"':''}>
        ${cfg.cols.map(col=>`<td class="${col.cls||''}" ${col.title?`title="${esc(r[col.title]||'')}"`:''} ${col.cap?'style="max-width:150px;overflow:hidden;text-overflow:ellipsis"':''}>${col.fmt?col.fmt(r):esc(r[col.k]??'')}</td>`).join('')}
       </tr>`).join(''):`<tr><td colspan="${cfg.cols.length}" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>
     ${cfg.onRow?`<div style="margin-top:8px">${st.sub?(st.sub.loading?'<div class="page-sub">상세 조회중…</div>':cfg.subView(st.sub,st.sel)):'<div class="page-sub" style="color:#8aa0bd">※ 행을 클릭하면 검사 상세치수가 표시됩니다.</div>'}</div>`:''}
     <style>.qr-row.sel{background:#e8f0ff}.qr-row:hover{background:#eef4ff}</style>`;
    const g=id=>host.querySelector(id);
    const doSearch=()=>{st.F.from=g('#qr-from').value;st.F.to=g('#qr-to').value;qfRead(host,cfg.filters,st.F,'qr-f-');load();};
    g('#qr-search').onclick=doSearch;
    qfBind(host,cfg.filters,st.F,'qr-f-',doSearch);
    if(cfg.onRow)host.querySelectorAll('.qr-row').forEach(el=>el.onclick=()=>pickRow(d.rows[+el.dataset.i]));
  };
  load();
}
const _d8iso=s=>{s=''+(s||'');return s.length===8?s.slice(0,4)+'-'+s.slice(4,6)+'-'+s.slice(6,8):(s.length===6?'20'+s.slice(0,2)+'-'+s.slice(2,4)+'-'+s.slice(4,6):s);};
const _d8disp=s=>{s=''+(s||'');return s.length===8?s.slice(2,4)+'/'+s.slice(4,6)+'/'+s.slice(6,8):_wymd(s);};

/* 품질 ①: 품질불량관리 (w_qa_input_025) — QA_T_ERROR(라이브) ↔ nx.qc_error(신규편집) */
// 불량구분/작업처/색깔 코드→이름 (레거시 dw_qa_input_020 정본)
const QC_TAG=[{v:'1',t:'LQC불량'},{v:'2',t:'고객사불량'},{v:'3',t:'IQC불량'},{v:'4',t:'초품불량'},{v:'5',t:'OQC불량'},{v:'8',t:'가공'},{v:'A',t:'자주순차'},{v:'9',t:'기타'}];
const QC_WORK=[{v:'P2',t:'가공'},{v:'P1',t:'용접'},{v:'D1',t:'직납'}];
const QC_COLOR=[{v:'1',t:'검정'},{v:'2',t:'회색'},{v:'3',t:'파랑'}];
const QC_YN=[{v:'0',t:'아니오'},{v:'1',t:'예'}];
const QC_BIZ=[{v:'DGZ',t:'DGZ'},{v:'DMZ',t:'DMZ'}];
const QC_PGREG=[{v:'내부용',t:'내부용'},{v:'보고용',t:'보고용'}];
const _pgreg=v=>v==='1'?'전산':(v==='0'||v===''?'':esc(v));  // 레거시1/0 vs nx 내부용/보고용

/* ===== 레거시 스타일 기준일자 위젯(재사용): ‹ YY/MM/DD › 📅 =====
   여러 레거시 조회화면(pr_outside 계열 등) 공용. 표시=YY/MM/DD, 내부값=YYYY-MM-DD(기존 로직 호환).
   사용: 1) HTML에 legacyDateHTML(id, isoValue) 삽입  2) draw 후 bindLegacyDate(container, id, ()=>현재iso, (newIso)=>{반영+재조회})
   ‹/› = ±1일, 📅/날짜클릭 = 달력선택. onSet 콜백에서 값갱신+load() 하면 자동 재조회. */
function _isoAddDays(iso,n){var d=new Date((iso||'')+'T00:00:00');if(isNaN(d.getTime()))return iso;d.setDate(d.getDate()+n);var p=function(x){return String(x).padStart(2,'0');};return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());}
function _isoToYYMMDD(iso){var s=(iso||'').split('-');return s.length===3?(s[0].slice(2)+'/'+s[1]+'/'+s[2]):(iso||'');}
function legacyDateHTML(id,iso){
  return '<span class="ldf" style="display:inline-flex;align-items:center;gap:0;border:1px solid var(--line-2,#c9d3e0);border-radius:6px;padding:0 1px;background:#fff;vertical-align:middle;height:26px">'
    +'<button type="button" id="'+id+'-prev" title="전일" style="border:0;background:transparent;cursor:pointer;font-size:16px;line-height:1;padding:2px 7px;color:#33507d">‹</button>'
    +'<span id="'+id+'-disp" title="클릭하면 달력" style="min-width:78px;text-align:center;font-family:monospace;font-size:13px;cursor:pointer;user-select:none">'+esc(_isoToYYMMDD(iso))+'</span>'
    +'<button type="button" id="'+id+'-next" title="익일" style="border:0;background:transparent;cursor:pointer;font-size:16px;line-height:1;padding:2px 7px;color:#33507d">›</button>'
    +'<label title="달력" style="cursor:pointer;position:relative;display:inline-flex;align-items:center;padding:0 4px">📅'
      +'<input type="date" id="'+id+'-cal" value="'+esc(iso||'')+'" style="position:absolute;left:0;top:0;width:100%;height:100%;opacity:0;cursor:pointer">'
    +'</label></span>';
}
function bindLegacyDate(root,id,getIso,onSet){
  var qy=function(s){return root.querySelector(s);};
  var prev=qy('#'+id+'-prev'),next=qy('#'+id+'-next'),cal=qy('#'+id+'-cal'),disp=qy('#'+id+'-disp');
  if(prev)prev.onclick=function(){onSet(_isoAddDays(getIso(),-1));};
  if(next)next.onclick=function(){onSet(_isoAddDays(getIso(),1));};
  if(cal)cal.onchange=function(e){if(e.target.value)onSet(e.target.value);};
  if(disp)disp.onclick=function(){try{cal.showPicker();}catch(err){cal.focus();cal.click();}};
}
// 조회 그리드 전체 컬럼(레거시 순서, 전부 이름)
// 첨부 슬롯 셀 — 붙어있으면 파일명 링크(클릭=내려받기), 없으면 공란. 레거시 w_qa_input_020 동일 배치.
const _qcFileCell=(docId,label)=>{
  const id=+docId||0;
  if(!id)return '';
  return `<a href="${API_BASE}/api/doc/download?src=doc&key=${id}" target="_blank"
     onclick="event.stopPropagation()" title="${label} — 클릭하면 내려받습니다"
     style="color:#1c47a0;font-weight:600;text-decoration:underline">파일#1</a>`;
};
const qcCols=[
  {h:'구분',k:'tag_nm',cls:'center'},
  {h:'고객사라인',k:'cust_line',cls:'center'},
  {h:'사업부',k:'division',cls:'center'},
  {h:'전산등록',cls:'center',fmt:r=>_pgreg(r.pg_reg)},
  {h:'불량일자',cls:'center',fmt:r=>_wymd(r.error_ymd)},
  {h:'P/No',fmt:r=>`<b>${esc(r.item_code)}</b>`},
  {h:'품명',k:'item_desc',cap:1,title:'item_desc'},
  {h:'작업처',k:'work_nm',cls:'center'},
  {h:'생산파트',k:'part_nm',cls:'center'},
  {h:'생산설비',k:'mach_nm',cap:1,title:'mach_nm'},
  {h:'협력사',k:'partner_nm',cap:1,title:'partner_nm'},
  {h:'검사자',k:'inspector',cls:'center'},
  {h:'원인자',k:'error_member',cls:'center'},
  {h:'불량항목1',k:'ei1'},{h:'불량항목2',k:'ei2'},{h:'불량항목3',k:'ei3'},
  {h:'불량내용',cap:1,title:'error_desc',fmt:r=>`<span style="color:${r.color==='2'?'#888':(r.color==='3'?'#1a4fd0':'#111')};font-weight:600">${esc(r.error_desc)}</span>`},
  {h:'Lot',cls:'num',fmt:r=>_wnf(r.lot_qty)},
  {h:'불량수량',cls:'num',fmt:r=>`<b style="color:#c0392b">${_wnf(r.error_qty)}</b>`},
  {h:'실불량',cls:'num',fmt:r=>_wnf(r.real_qty)},
  {h:'원인',k:'error_cause',cap:1,title:'error_cause'},
  {h:'진행상황',k:'progress',cap:1,title:'progress'},
  {h:'수몰여부',cls:'center',fmt:r=>r.water_flag?'✔':''},
  {h:'재검사',cls:'center',fmt:r=>r.reinsp_flag?'✔':''},
  {h:'완료여부',cls:'center',fmt:r=>r.finish_flag?'✔':''},
  // ★첨부 3칸 — 레거시 w_qa_input_020 과 동일 배치(맨 오른쪽).
  //   등록/교체는 행 [수정] 팝업 하단의 📎 영역에서.
  {h:'첨부파일#1',cls:'center',fmt:r=>_qcFileCell(r.f_attach,'첨부파일#1')},
  {h:'대책서#1',cls:'center',fmt:r=>_qcFileCell(r.f_plan1,'대책서#1')},
  {h:'대책서#2',cls:'center',fmt:r=>_qcFileCell(r.f_plan2,'대책서#2')},
];
const _all=o=>[{v:'',t:'전체'},...o];
const qcFilters=[{k:'tag',label:'불량구분',type:'select',opts:_all(QC_TAG)},{k:'cust_line',label:'고객사라인',type:'auto',optKind:'line',width:120},
  {k:'division',label:'사업부',type:'select',opts:_all(QC_BIZ)},{k:'item',label:'품번',width:120},
  {k:'work',label:'작업처',type:'select',opts:_all(QC_WORK)},{k:'partner',label:'협력사',type:'auto',optKind:'partner',width:140},
  {k:'finish',label:'완료여부',type:'select',opts:[{v:'',t:'전체'},{v:'1',t:'완료'},{v:'0',t:'미완료'}]}];
const qcQS=(F,src)=>({from_ymd:F.from,to_ymd:F.to,tag:F.tag||'',cust_line:F.cust_line||'',division:F.division||'',
  item:F.item||'',work:F.work||'',partner:F.partner||'',finish:F.finish||'',src});

/* 품질 ②: 시방변경관리 (w_qa_spec) — QA_T_SPEC_REV(라이브) ↔ nx.qc_spec_rev(신규편집) */
const _atypeNm=v=>({'1':'즉시적용','2':'재고소진후','3':'지정일'}[String(v||'').trim()]||String(v||'').trim());

/* ================= 로그인 ================= */
// 헤더 우측 사용자 표시 + 로그아웃 (로그인 사용자 실시간 반영)
function updateHeaderUser(){
  const el=document.querySelector('.hd-user'); if(!el)return;
  const u=PERM.currentUser();
  el.innerHTML=`<span class="avatar">${esc((u.nm||'?').slice(0,1))}</span> <span>${esc(u.nm||'')}님</span>`
    +`<span class="muted" style="margin:0 8px">${esc(u.dept||u.partner||'')}${PERM.isAdmin()?' · 전권':''}</span>`
    +`<button id="btnLogout" class="btn" style="padding:2px 10px;font-size:12px">로그아웃</button>`;
  const lo=el.querySelector('#btnLogout'); if(lo)lo.onclick=doLogout;
}
function doLogout(){ if(!confirm('로그아웃 하시겠습니까?'))return;
  sessionStorage.removeItem('perm_authed'); location.reload(); }

/* ================= 사이드바 숨김/열기 (2026-08-27) =================
   넓은 그리드 화면(협력사계획현황 등)에서 본문 폭 확보용.
   ☰(헤더) 또는 Ctrl+B = 고정 토글. 숨김상태의 왼쪽 손잡이: hover=임시펼침(peek), 클릭=다시 고정.
   peek 는 사이드바를 본문 위에 띄우므로 레이아웃이 흔들리지 않는다. 상태는 localStorage 유지. */
(function initSidebarToggle(){
  const KEY='sb_hidden';
  const start=()=>{
    const body=document.getElementById('appBody'), btn=document.getElementById('sbToggle'),
          hd=document.getElementById('sbHandle'), sb=document.getElementById('sidebar');
    if(!body||!btn) return;
    let hidden=false;
    try{ hidden = localStorage.getItem(KEY)==='1'; }catch(e){}
    const apply=()=>{ body.classList.toggle('sb-off',hidden);
      if(!hidden) body.classList.remove('sb-peek');
      btn.innerHTML = hidden
        ? '<span style="font-size:14px">☰</span><span class="sb-toggle-tx">메뉴</span>'
        : '<span style="font-size:14px">✕</span><span class="sb-toggle-tx">메뉴숨김</span>';
      btn.title = (hidden?'메뉴 열기':'메뉴 숨김')+' (Ctrl+B)';
      try{ localStorage.setItem(KEY, hidden?'1':'0'); }catch(e){}
      window.dispatchEvent(new Event('resize'));   // 그리드 폭 재계산
    };
    const setHidden=v=>{ hidden=v; apply(); };
    btn.onclick=()=>setHidden(!hidden);
    // ★hover 펼침(peek) 없음 — 그리드 보다가 마우스가 왼쪽으로 가면 메뉴가 튀어나와 방해됨(2026-08-27 사용자 요청).
    //   열고 닫기는 상단 버튼(또는 Ctrl+B)으로만.
    if(hd) hd.remove();
    document.addEventListener('keydown',e=>{
      if((e.ctrlKey||e.metaKey)&&(e.key==='b'||e.key==='B')){ e.preventDefault(); setHidden(!hidden); }
    });
    apply();
  };
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',start); else start();
})();

/* ★색상 유지 엑셀 다운로드 — **진짜 xlsx 파일** 생성 (2026-08-31 전면교체) ────────
   왜 바꿨나(실측 사고): 처음엔 HTML 테이블을 .xls 로 내보냈다. 그랬더니 엑셀이
     「파일 형식 및 확장명이 일치하지 않습니다」 경고를 띄우고, [예]로 열면 HTML 파서가
     아닌 텍스트 경로로 읽혀 **서식(배경색)이 통째로 버려졌다.** 값만 남고 색이 사라진
     원인이 이것이다. 레거시 .xls 는 진짜 BIFF 바이너리라 색이 나온다.
   → 라이브러리 없이(사내망·CDN 미사용) OOXML(.xlsx)을 직접 만든다.
     xlsx = ZIP 컨테이너. ZIP 은 **무압축(stored)** 를 허용하므로 CRC32 만 직접 계산하면
     압축기 없이 유효한 파일이 된다. 서식은 styles.xml 의 정식 fill/font 로 들어가
     엑셀이 경고 없이 열고 색도 그대로 나온다.

   인자(기존과 동일 — 호출부 수정 불필요):
     fname · cols=[{h:'헤더', w:너비px, bg:'헤더배경'}]
     rows=[[{v:값, bg:'#ffff00', fg:'#c0392b', b:1, al:'center', cs:병합수} | 원시값, …], …]
     opt={sheet, title, sub, foot:[[셀…]]}
   ※ cs(가로병합)는 mergeCells 로 반영. 숫자는 숫자로, 그 외는 문자열(inlineStr)로 넣어
     '10/10' 이 날짜로 바뀌는 문제가 원천적으로 없다. */
function downloadXLS(fname, cols, rows, opt){
  opt = opt || {};
  const X = s => String(s==null?'':s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/\x00-\x08\x0b\x0c\x0e-\x1f/g,'');
  const norm = c => (c && typeof c === 'object' && !Array.isArray(c)) ? c : {v:c};
  const hex = c => String(c||'').replace('#','').toUpperCase();

  // ── 스타일 수집(중복 제거) ──
  //    한 셀의 서식 = 배경(fill) + 글자색/굵기(font) + 정렬(alignment) 조합
  const fills = ['none','gray125'];            // 0,1 은 OOXML 예약
  const fonts = [{fg:'',b:0}];                 // 0 = 기본
  const xfs = [{f:0,fl:0,al:''}];              // 0 = 기본
  const keyOf = o => `${hex(o.bg)}|${hex(o.fg)}|${o.b?1:0}|${o.al||''}`;
  const styMap = new Map([[keyOf({}),0]]);
  const styleOf = o => {
    const k = keyOf(o);
    if(styMap.has(k)) return styMap.get(k);
    let fl = 0;
    if(o.bg){ const h = hex(o.bg); fl = fills.indexOf('S'+h); if(fl<0){ fills.push('S'+h); fl = fills.length-1; } }
    let fn = 0;
    if(o.fg || o.b){
      const fk = hex(o.fg)+'|'+(o.b?1:0);
      fn = fonts.findIndex(x => (hex(x.fg)+'|'+(x.b?1:0)) === fk);
      if(fn<0){ fonts.push({fg:o.fg||'',b:o.b?1:0}); fn = fonts.length-1; }
    }
    xfs.push({f:fn, fl:fl, al:o.al||''});
    const id = xfs.length-1; styMap.set(k,id); return id;
  };

  // ── 행 구성: (제목/부제) → 헤더 → 본문 → 합계 ──
  const sheetRows = [];
  if(opt.title) sheetRows.push([{v:opt.title, b:1}]);
  if(opt.sub)   sheetRows.push([{v:opt.sub}]);
  sheetRows.push(cols.map(c => ({v:c.h, bg:c.bg||'#DCE6F1', b:1, al:'center'})));
  rows.forEach(r => sheetRows.push(r.map(norm)));
  (opt.foot||[]).forEach(r => sheetRows.push(r.map(x =>
    Object.assign({bg:'#F2F2F2', b:1}, norm(x)))));

  // ── 시트 XML ──
  const colLetter = n => { let s=''; n++; while(n>0){ const m=(n-1)%26; s=String.fromCharCode(65+m)+s; n=(n-m-1)/26; } return s; };
  const merges = [];
  let xml = '';
  sheetRows.forEach((r, ri) => {
    let cells = '', ci = 0;
    r.forEach(o => {
      const ref = colLetter(ci) + (ri+1);
      const v = o.v;
      const isNum = (typeof v === 'number' && isFinite(v))
        || (typeof v === 'string' && v !== '' && /^-?\d+(\.\d+)?$/.test(v) && !/^0\d/.test(v));
      const s = styleOf(o);
      if(v === '' || v == null){
        if(s) cells += `<c r="${ref}" s="${s}"/>`;
      }else if(isNum){
        cells += `<c r="${ref}"${s?` s="${s}"`:''}><v>${Number(v)}</v></c>`;
      }else{
        cells += `<c r="${ref}"${s?` s="${s}"`:''} t="inlineStr"><is><t xml:space="preserve">${X(v)}</t></is></c>`;
      }
      const span = Math.max(1, +o.cs || 1);
      if(span > 1) merges.push(`${ref}:${colLetter(ci+span-1)}${ri+1}`);
      ci += span;
    });
    xml += `<row r="${ri+1}">${cells}</row>`;
  });
  // 열 너비(px → 엑셀 문자폭 근사)
  const colsXml = '<cols>' + cols.map((c,i) =>
    `<col min="${i+1}" max="${i+1}" width="${Math.max(4,Math.round(((+c.w||90)/7)*10)/10)}" customWidth="1"/>`).join('') + '</cols>';
  const headRow = (opt.title?1:0) + (opt.sub?1:0) + 1;   // 헤더가 놓인 행번호
  const sheetXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetPr/>
<sheetViews><sheetView workbookViewId="0" tabSelected="1">
<pane ySplit="${headRow}" topLeftCell="A${headRow+1}" activePane="bottomLeft" state="frozen"/>
</sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>
${colsXml}<sheetData>${xml}</sheetData>
${merges.length?`<mergeCells count="${merges.length}">${merges.map(m=>`<mergeCell ref="${m}"/>`).join('')}</mergeCells>`:''}
</worksheet>`;

  // ── styles.xml ──
  const fillsXml = fills.map(f => f==='none' ? '<fill><patternFill patternType="none"/></fill>'
    : f==='gray125' ? '<fill><patternFill patternType="gray125"/></fill>'
    : `<fill><patternFill patternType="solid"><fgColor rgb="FF${f.slice(1)}"/><bgColor indexed="64"/></patternFill></fill>`).join('');
  const fontsXml = fonts.map(f =>
    `<font><sz val="10"/><name val="맑은 고딕"/>${f.b?'<b/>':''}${f.fg?`<color rgb="FF${hex(f.fg)}"/>`:''}</font>`).join('');
  const bd = '<border><left style="thin"><color rgb="FF808080"/></left><right style="thin"><color rgb="FF808080"/></right>'
           + '<top style="thin"><color rgb="FF808080"/></top><bottom style="thin"><color rgb="FF808080"/></bottom></border>';
  const xfsXml = xfs.map(x =>
    `<xf numFmtId="0" fontId="${x.f}" fillId="${x.fl}" borderId="1" applyFont="1" applyFill="1" applyBorder="1"`
    + (x.al?` applyAlignment="1"><alignment horizontal="${x.al}" vertical="center"/></xf>`
           : `><alignment vertical="center"/></xf>`)).join('');
  const stylesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="${fonts.length}">${fontsXml}</fonts>
<fills count="${fills.length}">${fillsXml}</fills>
<borders count="2"><border/>${bd}</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="${xfs.length}">${xfsXml}</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;

  const shName = X(String(opt.sheet || opt.title || 'Sheet1').slice(0,31).replace(/[\\\/\?\*\[\]:]/g,'_'));
  const files = [
    ['[Content_Types].xml', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`],
    ['_rels/.rels', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`],
    ['xl/workbook.xml', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="${shName}" sheetId="1" r:id="rId1"/></sheets></workbook>`],
    ['xl/_rels/workbook.xml.rels', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`],
    ['xl/styles.xml', stylesXml],
    ['xl/worksheets/sheet1.xml', sheetXml],
  ];

  // ── ZIP(무압축 stored) 조립 ──
  const CRCT = (()=>{ const t=new Uint32Array(256);
    for(let n=0;n<256;n++){ let c=n; for(let k=0;k<8;k++) c = (c&1) ? (0xEDB88320 ^ (c>>>1)) : (c>>>1); t[n]=c>>>0; }
    return t; })();
  const crc32 = b => { let c = 0xFFFFFFFF;
    for(let i=0;i<b.length;i++) c = CRCT[(c ^ b[i]) & 0xFF] ^ (c>>>8);
    return (c ^ 0xFFFFFFFF) >>> 0; };
  const enc = new TextEncoder();
  const parts = [], central = [];
  let off = 0;
  const u16 = n => [n&255, (n>>8)&255];
  const u32 = n => [n&255, (n>>8)&255, (n>>16)&255, (n>>>24)&255];
  files.forEach(([name, text]) => {
    const nb = enc.encode(name), db = enc.encode(text), cr = crc32(db);
    const lh = [].concat([0x50,0x4b,0x03,0x04], u16(20), u16(0x0800), u16(0), u16(0), u16(0),
      u32(cr), u32(db.length), u32(db.length), u16(nb.length), u16(0));
    parts.push(new Uint8Array(lh), nb, db);
    central.push({nb, cr, len:db.length, off});
    off += lh.length + nb.length + db.length;
  });
  const cd = [];
  central.forEach(c => {
    const h = [].concat([0x50,0x4b,0x01,0x02], u16(20), u16(20), u16(0x0800), u16(0), u16(0), u16(0),
      u32(c.cr), u32(c.len), u32(c.len), u16(c.nb.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(c.off));
    cd.push(new Uint8Array(h), c.nb);
  });
  const cdLen = cd.reduce((s,x)=>s+x.length, 0);
  const eocd = new Uint8Array([].concat([0x50,0x4b,0x05,0x06], u16(0), u16(0),
    u16(central.length), u16(central.length), u32(cdLen), u32(off), u16(0)));
  const blob = new Blob(parts.concat(cd, [eocd]),
    {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});

  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = fname.replace(/\.(xls|csv)$/i,'') + '.xlsx';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href), 4000);
}
