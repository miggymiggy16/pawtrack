/* DEMO ONLY: typing /bypass anywhere skips face verification. Remove for production. */
(function(){
  var code='/bypass', typed='';
  document.addEventListener('keydown', async function(e){
    if(e.key.length!==1) return;
    typed += e.key;
    if(typed.length>code.length) typed=typed.slice(-code.length);
    if(typed===code){
      typed='';
      var st=document.getElementById('login-face-status');
      if(st) st.textContent='Bypass accepted (demo). Signing in...';
      var tok=document.querySelector('meta[name="csrf-token"]');
      var fd=new FormData(); fd.append('csrf_token', tok?tok.content:'');
      try{
        var r=await fetch(window.PAW_BYPASS_URL,{method:'POST',body:fd,headers:{'Accept':'application/json'}});
        var d=await r.json();
        if(d.redirect) window.location.href=d.redirect;
      }catch(err){ if(st) st.textContent='Bypass failed.'; }
    }
  });
})();
