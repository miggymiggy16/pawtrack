(function(){
  var links=[].slice.call(document.querySelectorAll('.st-nav a'));
  var secs=[].slice.call(document.querySelectorAll('.st-body .st-sec'));
  if(!links.length||!secs.length) return;
  var ids=secs.map(function(s){return s.id;}), current='';
  document.body.classList.add('tabs-on');

  function show(id){
    if(ids.indexOf(id)<0) id=ids[0];
    secs.forEach(function(s){s.classList.toggle('is-active',s.id===id);});
    links.forEach(function(a){a.classList.toggle('active',a.hash==='#'+id);});
    current=id;
  }
  function wanted(){
    if(history.state&&history.state.tab) return history.state.tab;
    var q=new URLSearchParams(location.search).get('tab');
    return location.hash?location.hash.slice(1):(q||'');
  }

  document.addEventListener('click',function(e){
    var a=e.target.closest('a[href^="#"]'), id=a&&a.hash.slice(1);
    if(!a||ids.indexOf(id)<0) return;
    e.preventDefault();
    if(id!==current) history.pushState({tab:id},'',location.pathname+'#'+id);
    show(id);
    window.scrollTo({top:0,behavior:'smooth'});
  });

  document.addEventListener('submit',function(e){
    var form=e.target; if(!form.closest('.st-body')) return;
    var field=form.querySelector('input[name="tab"]');
    if(!field){field=document.createElement('input');field.type='hidden';field.name='tab';form.appendChild(field);}
    field.value=current;
  });

  window.addEventListener('popstate',function(){show(wanted());});
  show(wanted()||ids[0]);
})();
