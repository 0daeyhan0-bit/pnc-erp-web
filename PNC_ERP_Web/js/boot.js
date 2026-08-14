/* ===== PNC ERP boot.js — 부팅/로그인 초기화 (app.js 분할 9/9, 순수이동·마지막로드) ===== */
// 이전에 저장된 사용자 목록(localStorage)에 슈퍼 계정이 없으면 주입 → 어떤 환경에서도 슈퍼 계정 보장
function ensureSuperAccount(){
  try{const raw=localStorage.getItem('perm_users'); if(!raw)return; // 미저장 시 SEED_USERS에 이미 포함
    const arr=JSON.parse(raw); let changed=false;
    // 슈퍼 + 시드계정(TEST1~4 포함) 중 없는 것 주입 → 기존 브라우저에서도 4계정 보장
    SEED_USERS.forEach(su=>{ if(!arr.some(u=>u.id===su.id)){arr.push(JSON.parse(JSON.stringify(su)));changed=true;} });
    if(changed)localStorage.setItem('perm_users',JSON.stringify(arr));
  }catch(e){}
}

let _appBooted=false;
function bootApp(){
  if(_appBooted)return; _appBooted=true;
  buildTree();
  openTab('dash','대시보드');
  // 서버 권한 로드(전 PC 공통) → 로드되면 메뉴 재구성
  try{PERM.loadFromServer().then(ok=>{if(ok){try{buildTree();updateHeaderUser();}catch(_){}}});}catch(_){}
  document.getElementById('globalSearch').onkeyup=e=>{
    if(e.key==='Enter'){const q=e.target.value.trim();if(!q)return;
      openTab('items','품목 조회');
      setTimeout(()=>{const pg=tabs['items'].pg;pg.querySelector('#q').value=q;pg.querySelector('#go').click();},50);}
  };
  updateHeaderUser();
}

// 전체화면 로그인 오버레이 (미인증 시 앱 부팅 차단)
function showLogin(){
  if(document.getElementById('loginOverlay'))return;
  const ov=document.createElement('div'); ov.id='loginOverlay';
  ov.innerHTML=`
    <style>
      #loginOverlay{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;
        background:linear-gradient(135deg,#16305c 0%,#26568f 60%,#2f6db3 100%)}
      #loginOverlay .lg-card{width:360px;max-width:92vw;background:#fff;border-radius:14px;
        box-shadow:0 24px 70px rgba(10,25,55,.45);padding:30px 30px 22px}
      #loginOverlay .lg-brand{display:flex;align-items:center;gap:12px;margin-bottom:22px}
      #loginOverlay .lg-mark{width:44px;height:44px;border-radius:11px;background:linear-gradient(135deg,#1c47a0,#2f6db3);
        color:#fff;font-weight:800;font-size:24px;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(28,71,160,.4)}
      #loginOverlay .lg-t{font-size:22px;font-weight:800;color:#16305c;line-height:1.1}
      #loginOverlay .lg-t span{color:#2f6db3;margin-left:2px}
      #loginOverlay .lg-sub{font-size:11.5px;color:#8494ac;margin-top:3px}
      #loginOverlay .lg-field{margin-bottom:13px}
      #loginOverlay .lg-field label{display:block;font-size:12px;font-weight:700;color:#43587e;margin-bottom:5px}
      #loginOverlay .lg-field input{width:100%;box-sizing:border-box;padding:10px 12px;font-size:14px;
        border:1px solid #cdd7e6;border-radius:8px;outline:none;transition:border .15s,box-shadow .15s}
      #loginOverlay .lg-field input:focus{border-color:#2f6db3;box-shadow:0 0 0 3px rgba(47,109,179,.15)}
      #loginOverlay .lg-err{background:#fdecec;color:#c0392b;font-size:12px;padding:8px 11px;border-radius:7px;margin-bottom:12px;border:1px solid #f3c9c9}
      #loginOverlay .lg-btn{width:100%;padding:11px;font-size:15px;font-weight:700;color:#fff;border:none;border-radius:9px;
        background:linear-gradient(90deg,#1c47a0,#2f6db3);cursor:pointer;box-shadow:0 5px 15px rgba(28,71,160,.35)}
      #loginOverlay .lg-btn:active{transform:translateY(1px)}
      #loginOverlay .lg-foot{margin-top:16px;text-align:center;font-size:11px;color:#9aa8bd}
    </style>
    <div class="lg-card">
      <div class="lg-brand"><span class="lg-mark">P</span>
        <div><div class="lg-t">PNC<span>ERP</span></div><div class="lg-sub">피앤씨인더스트리 차세대 ERP</div></div></div>
      <div class="lg-field"><label>아이디</label><input id="lg-id" autocomplete="username" placeholder="아이디"></div>
      <div class="lg-field"><label>비밀번호</label><input id="lg-pw" type="password" autocomplete="current-password" placeholder="비밀번호"></div>
      <div id="lg-err" class="lg-err" style="display:none"></div>
      <button id="lg-login" class="lg-btn">로그인</button>
      <div class="lg-foot">계정 문의 · 전산담당 (pncind@pncind.co.kr)</div>
    </div>`;
  document.body.appendChild(ov);
  const g=id=>ov.querySelector(id);
  const err=m=>{const e=g('#lg-err');e.textContent=m||'';e.style.display=m?'block':'none';};
  const submit=()=>{
    const id=g('#lg-id').value.trim(), pw=g('#lg-pw').value;
    if(!id||!pw){err('아이디와 비밀번호를 입력하세요.');return;}
    const u=getUsers().find(x=>x.id===id);
    if(!u||String(u.pw)!==String(pw)){err('아이디 또는 비밀번호가 올바르지 않습니다.');return;}
    if(u.status&&u.status!=='사용'){err('사용 중지된 계정입니다. 전산담당에 문의하세요.');return;}
    sessionStorage.setItem('perm_authed',id);
    PERM.setUser(id);
    ov.remove();
    bootApp();
  };
  g('#lg-login').onclick=submit;
  [g('#lg-id'),g('#lg-pw')].forEach(el=>el.onkeyup=e=>{if(e.key==='Enter')submit();});
  // ★슈퍼 계정 자동 입력 — 로그인 창이 뜨면 아이디/비번을 미리 채우고 로그인 버튼에 포커스(Enter 즉시 진입)
  if(DEV_AUTOLOGIN){const su=getUsers().find(u=>u.id===DEV_AUTOLOGIN);
    if(su){g('#lg-id').value=su.id; g('#lg-pw').value=su.pw;
      setTimeout(()=>{const b=g('#lg-login');if(b)b.focus();},30); return;}}
  setTimeout(()=>{const f=g('#lg-id');if(f)f.focus();},30);
}

/* ---- init ---- */
(async function(){
  ensureSuperAccount();                         // 슈퍼 계정 항상 보장
  try{await PERM.loadUsersFromServer();}catch(e){}   // ★서버 계정목록(전 PC 공통) 병합 후 로그인 — 다른 PC에서 만든 계정도 로그인 가능
  ensureSuperAccount();
  const authed=sessionStorage.getItem('perm_authed');
  if(authed && getUsers().some(u=>u.id===authed && (!u.status||u.status==='사용'))){
    PERM.setUser(authed); bootApp(); return;
  }
  // ★개발용 자동 로그인 — 로그인 화면 없이 슈퍼 계정으로 바로 진입해 메뉴 확인
  if(DEV_AUTOLOGIN){const su=getUsers().find(u=>u.id===DEV_AUTOLOGIN && (!u.status||u.status==='사용'));
    if(su){sessionStorage.setItem('perm_authed',su.id); PERM.setUser(su.id); bootApp(); return;}}
  showLogin();
})();
