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
function f1Copy(el){
  navigator.clipboard.writeText(window.location.origin+el.getAttribute('href')).then(function(){
    el.dataset.copied='1';setTimeout(function(){el.removeAttribute('data-copied');},1200);
  });
}
document.addEventListener('click',function(e){
  var t=e.target.closest('a[href^="#"]');
  if(t){e.preventDefault();var g=document.getElementById('gallery');
    if(g)g.scrollIntoView({behavior:'smooth'});}
});
