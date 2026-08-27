var F1L = [];
function f1ScrollToMedia(){
  var g=document.getElementById('gallery');
  if(g&&!g.classList.contains('is-empty'))g.scrollIntoView({behavior:'smooth',block:'start'});
}
function f1ToggleExpand(id){
  var el=document.querySelector('[data-expand="'+id+'"]');
  if(!el)return;
  el.classList.toggle('is-expanded');
}
/* «Показать полностью…» — разворот длинного текста в ленте */
function f1Expand(btn){
  var w=btn.parentElement;
  w.classList.add('is-open');
  btn.remove();
}
/* Копирование ссылки на пост */
function f1Share(btn){
  var url=window.location.origin+btn.getAttribute('data-url');
  function done(){ btn.textContent='✓ Скопировано';
    setTimeout(function(){ btn.textContent='🔗 Ссылка'; },1400); }
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(url).then(done);
  } else {
    var ta=document.createElement('textarea');
    ta.value=url; document.body.appendChild(ta); ta.select();
    try{document.execCommand('copy');done();}catch(e){}
    ta.remove();
  }
}
document.addEventListener('click',function(e){
  var t=e.target.closest('a[href^="#"]');
  if(t){e.preventDefault();var g=document.getElementById('gallery');
    if(g)g.scrollIntoView({behavior:'smooth'});}
});
