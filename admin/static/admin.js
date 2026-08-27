/* FANS1 Admin client */
var editingId = null;
var mediaItems = [];   // {url, type, preview(свой URL blob для превью)}
var postsCache = [];

function $(id){ return document.getElementById(id); }
function esc(s){ var d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML; }

function fmtDateRu(iso){
  var M=['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
  try{ var d=iso.slice(0,10).split('-'); return (+d[2])+' '+M[d[1]-1]+' '+d[0]; }catch(e){ return iso||''; }
}

function setStatus(el, msg, cls){ el.textContent=msg||''; el.className='hint'+(cls?' '+cls:''); }

/* ---------------- настройки облака ---------------- */
function loadCfg(){
  fetch('/api/config').then(function(r){return r.json();}).then(function(c){
    var b=$('cloudBadge');
    if(c.configured){
      b.textContent='облако: '+(c.provider==='imgbb'?'imgbb':'cloudinary');
      b.classList.add('ok');
    } else {
      b.textContent='медиа: локально';
    }
    document.querySelectorAll('input[name=prov]').forEach(function(r){
      r.checked = (r.value===c.provider);
    });
    $('cCloud').value = c.cloudinary_cloud||'';
    $('mImgbb').textContent = c.imgbb_key_masked?('сохранён '+c.imgbb_key_masked):'';
    $('mPreset').textContent = c.cloudinary_preset_masked?('сохранён '+c.cloudinary_preset_masked):'';
  }).catch(function(){ $('cloudBadge').textContent='конфиг недоступен'; });
}
function saveCfg(){
  var prov='';
  document.querySelectorAll('input[name=prov]').forEach(function(r){ if(r.checked) prov=r.value; });
  var body={provider:prov,
            imgbb_key:$('cImgbb').value.trim(),
            cloudinary_cloud:$('cCloud').value.trim(),
            cloudinary_preset:$('cPreset').value.trim()};
  fetch('/api/config/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)}).then(function(r){return r.json();}).then(function(j){
    if(j.ok){ setStatus($('cfgStatus'),'сохранено ✓','okc'); $('cImgbb').value=''; $('cPreset').value=''; loadCfg(); }
    else setStatus($('cfgStatus'),j.error||'ошибка','err');
  }).catch(function(e){ setStatus($('cfgStatus'),'ошибка сети','err'); });
}

/* ---------------- загрузка файлов ---------------- */
function pickFiles(){ $('fFiles').click(); }
function handleFiles(list){
  var files=Array.prototype.slice.call(list||[]);
  if(!files.length) return;
  var fd=new FormData();
  files.forEach(function(f){ fd.append('file', f, f.name); });
  var dz=$('upStatus');
  setStatus(dz,'загрузка в облако… ('+files.length+' файл(ов))');
  $('btnPublish').disabled=true;
  fetch('/api/upload',{method:'POST',body:fd})
    .then(function(r){return r.json();})
    .then(function(j){
      $('btnPublish').disabled=false;
      if(!j.ok){ setStatus(dz,'ошибка: '+(j.error||''),'err'); return; }
      (j.files||[]).forEach(function(f){
        if(!f.ok){ setStatus(dz,f.file+': '+(f.error||'не удалось'),'err'); return; }
        mediaItems.push({url:f.url, type:f.kind, blob:f._blob||null,
                         preview:f.preview||f.url});
        if(f.warning) setStatus(dz,f.warning,'err'); else setStatus(dz,'загружено ✓','okc');
      });
      renderMedia();
    })
    .catch(function(e){ $('btnPublish').disabled=false; setStatus(dz,'ошибка сети: '+e,'err'); });
}

function renderMedia(){
  var g=$('mediaGrid'); g.innerHTML='';
  mediaItems.forEach(function(m,i){
    var d=document.createElement('div'); d.className='mg-item';
    if(m.type==='video'){
      var v=document.createElement('video');
      v.src=m.preview||m.url; v.muted=true; v.preload='metadata';
      if(m.poster) v.poster=m.poster;
      d.appendChild(v);
      var b=document.createElement('span'); b.className='mg-badge'; b.textContent='видео';
      d.appendChild(b);
    } else {
      var im=document.createElement('img');
      im.src=m.preview||m.url; im.alt='';
      d.appendChild(im);
    }
    var x=document.createElement('button'); x.className='mg-x'; x.type='button';
    x.textContent='×'; x.title='убрать из поста';
    x.onclick=function(){ mediaItems.splice(i,1); renderMedia(); };
    d.appendChild(x);
    g.appendChild(d);
  });
}

/* ---------------- drag & drop ---------------- */
function initDropzone(){
  var dz=$('dropzone');
  dz.addEventListener('click', pickFiles);
  $('fFiles').addEventListener('change', function(e){ handleFiles(e.target.files); e.target.value=''; });
  ['dragenter','dragover'].forEach(function(ev){
    dz.addEventListener(ev, function(e){ e.preventDefault(); dz.classList.add('drag'); });
  });
  ['dragleave','drop'].forEach(function(ev){
    dz.addEventListener(ev, function(e){ e.preventDefault(); dz.classList.remove('drag'); });
  });
  dz.addEventListener('drop', function(e){ handleFiles(e.dataTransfer.files); });
}

/* ---------------- slug ---------------- */
function translit(s){
  var TR={'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i',
    'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u',
    'ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'};
  return s.toLowerCase().split('').map(function(ch){return TR[ch]!==undefined?TR[ch]:ch;})
    .join('').replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,60);
}
function regenSlug(){
  var s=translit($('fTitle').value||'post');
  if(editingId){ /* при правке не перезаписываем молча */ }
  $('fSlug').value=s;
}

/* ---------------- публикация ---------------- */
function publish(){
  var title=$('fTitle').value.trim(), body=$('fBody').value.trim();
  if(!title && !body){ setStatus($('pubStatus'),'нужен заголовок или текст','err'); return; }
  var tags=$('fTags').value.split(',').map(function(t){return t.trim();}).filter(Boolean);
  var payload={title:title, body:body, tags:tags,
               slug:$('fSlug').value.trim(), media:mediaItems,
               editing_id:editingId};
  var btn=$('btnPublish');
  btn.disabled=true; setStatus($('pubStatus'),'публикую и пересобираю сайт…');
  fetch('/api/post/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)})
  .then(function(r){return r.json();})
  .then(function(j){
    btn.disabled=false;
    if(!j.ok){ setStatus($('pubStatus'),(j.error||'ошибка').slice(0,300),'err'); return; }
    setStatus($('pubStatus'), j.post.new?'опубликовано ✓':'обновлено ✓','okc');
    clearForm(false);
    loadPosts();
  })
  .catch(function(e){ btn.disabled=false; setStatus($('pubStatus'),'ошибка сети: '+e,'err'); });
}

function clearForm(resetBanner){
  $('fTitle').value=''; $('fBody').value=''; $('fTags').value=''; $('fSlug').value='';
  mediaItems=[]; renderMedia();
  editingId=null;
  $('edTitleBar').textContent='Новый пост';
  $('editBanner').classList.add('hidden');
  setStatus($('pubStatus'),''); setStatus($('upStatus'),'');
  if(resetBanner!==false) loadPosts();
}

/* ---------------- список постов ---------------- */
function loadPosts(){
  fetch('/api/posts').then(function(r){return r.json();}).then(function(j){
    postsCache=j.posts||[];
    var el=$('postList');
    if(!postsCache.length){ el.innerHTML='<p class="hint">Постов пока нет. Напиши первый слева!</p>'; return; }
    el.innerHTML='';
    postsCache.forEach(function(p){
      var row=document.createElement('div'); row.className='pi';
      var thumb = p.thumb
        ? '<img class="pi__thumb" src="'+esc(p.thumb)+'" alt="">'
        : '<div class="pi__noimg">🏎️</div>';
      row.innerHTML = thumb+
        '<div class="pi__body"><p class="pi__t">'+esc(p.title||'(без заголовка)')+'</p>'+
        '<div class="pi__meta">'+esc(fmtDateRu(p.date))+' · медиа: '+p.media_n+' · /post/'+esc(p.slug)+'/</div>'+
        '<div class="pi__acts">'+
        '<button class="ed" type="button">изменить</button>'+
        '<a href="/site/post/'+encodeURIComponent(p.slug)+'/" target="_blank">открыть</a>'+
        '<button class="del" type="button">удалить</button>'+
        '</div></div>';
      row.querySelector('.ed').onclick=function(){ startEdit(p.id); };
      row.querySelector('.del').onclick=function(){ delPost(p.id, p.title); };
      el.appendChild(row);
    });
  });
}

function startEdit(id){
  fetch('/api/posts').then(function(r){return r.json();}).then(function(j){
    var p=(j.posts||[]).filter(function(x){return x.id===id;})[0];
    if(!p) return;
    editingId=id;
    $('fTitle').value=p.title||'';
    $('fBody').value=p.body||'';
    $('fTags').value=(p.tags||[]).join(', ');
    $('fSlug').value=p.slug||'';
    mediaItems=(p.media||[]).map(function(m){
      return {url:m.url, type:m.type, preview:m.url, poster:m.poster};
    });
    renderMedia();
    $('edTitleBar').textContent='Редактирование поста';
    $('editBanner').classList.remove('hidden');
    window.scrollTo({top:0, behavior:'smooth'});
  });
}

function delPost(id,title){
  if(!confirm('Удалить пост «'+(title||id)+'»? Восстановить нельзя.')) return;
  fetch('/api/post/delete',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:id})})
  .then(function(r){return r.json();})
  .then(function(j){
    if(j.ok){ if(editingId===id) clearForm(); loadPosts(); }
    else alert('Не удалось: '+(j.error||'?'));
  });
}

/* ---------------- деплой на Vercel ---------------- */
function deploySite(){
  var btn=$('btnDeploy');
  btn.disabled=true;
  var st=$('pubStatus'); setStatus(st,'выкладываю на fans1.vercel.app… (15–40 сек)');
  fetch('/api/deploy',{method:'POST'})
    .then(function(r){return r.json();})
    .then(function(j){
      btn.disabled=false;
      if(j.ok){ setStatus(st,'сайт обновлён ✓ https://fans1.vercel.app','okc'); }
      else { setStatus(st,'ошибка деплоя — см. лог в терминале сервера','err'); console.error(j.log||j.error); }
    })
    .catch(function(e){ btn.disabled=false; setStatus(st,'ошибка сети: '+e,'err'); });
}

/* ---------------- init ---------------- */
document.addEventListener('DOMContentLoaded', function(){
  loadCfg(); loadPosts(); initDropzone();
  $('btnPublish').onclick=publish;
  $('btnDeploy').onclick=deploySite;
  $('btnClear').onclick=function(){ clearForm(); };
  $('btnCfgSave').onclick=saveCfg;
  $('btnRegenSlug').onclick=regenSlug;
  $('fTitle').addEventListener('blur', function(){
    if(!$('fSlug').value) $('fSlug').value=translit($('fTitle').value);
  });
  $('fTitle').addEventListener('input', function(){
    if(!editingId) $('fSlug').value=translit($('fTitle').value);
  });
});
