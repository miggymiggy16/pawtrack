(function(){
  var form=document.getElementById('idvScanForm'); if(!form) return;
  var panels=[1,2,3,4,5].map(function(n){return document.getElementById('idv-panel-'+n);});
  var steps=[].slice.call(document.querySelectorAll('.idv-step'));
  var status=document.getElementById('idvStatus');
  var video=document.getElementById('idvVideo'), placeholder=document.getElementById('idvPlaceholder');
  var startBtn=document.getElementById('idvStart'), capBtn=document.getElementById('idvCapture'), retakeBtn=document.getElementById('idvRetake');
  var instr=[].slice.call(document.querySelectorAll('.idv-instructions li'));
  var POSES=['Look straight at the camera.','Look to the left.','Look to the right.','Move closer to the camera.','Move slightly farther away.'];
  var step=0, blobs=[], stream=null, busy=false;
  function setStatus(m,k){status.textContent=m||'';status.className='face-status'+(k?' '+k:'');}
  function show(n){panels.forEach(function(p,i){p.hidden=(i+1)!==n;});steps.forEach(function(s,i){s.classList.toggle('active',i+1===n);s.classList.toggle('done',i+1<n);});}
  function mark(){
    instr.forEach(function(li,i){li.classList.toggle('active',i===step);li.classList.toggle('done',i<step);});
    capBtn.textContent=step<POSES.length?('Capture pose '+(step+1)+' of 5'):'Verify face';
  }
  form.addEventListener('submit',async function(e){
    e.preventDefault();
    if(!document.getElementById('idv_consent').checked){setStatus('Please consent to ID and facial data processing.','error');return;}
    setStatus('Scanning ID...','');
    try{
      var res=await fetch(PAW_SETTINGS_URLS.scan,{method:'POST',body:new FormData(form),headers:{'Accept':'application/json'}});
      var d=await res.json();
      if(!res.ok||!d.ok){setStatus(d.error||'ID scan failed.','error');return;}
      var f=d.fields||{};
      document.getElementById('idvFields').innerHTML=['full_name','date_of_birth','id_number','address','expiry_date'].map(function(k){
        return '<div style="grid-column:'+(k==='address'?'1/-1':'auto')+'"><span>'+k.replace('_',' ')+'</span>'+String(f[k]||'-')+'</div>';
      }).join('');
      setStatus('ID scanned successfully.','ok');show(2);
    }catch(err){setStatus(err.message||'Scan failed','error');}
  });
  document.getElementById('idvToFace').addEventListener('click',function(){show(3);mark();});
  async function startCam(){
    if(stream)return;
    try{
      stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:640},height:{ideal:480}},audio:false});
      video.srcObject=stream;await video.play();video.classList.add('live');if(placeholder)placeholder.hidden=true;
      startBtn.textContent='Stop camera';capBtn.disabled=false;setStatus('Camera ready. Capture each pose.','ok');mark();
    }catch(err){setStatus(err.message||'Camera error','error');}
  }
  function stopCam(){if(stream)stream.getTracks().forEach(function(t){t.stop();});stream=null;video.srcObject=null;video.classList.remove('live');if(placeholder)placeholder.hidden=false;startBtn.textContent='Start camera';capBtn.disabled=true;}
  startBtn.addEventListener('click',function(){if(stream)stopCam();else startCam();});
  function capture(){return new Promise(function(res,reject){var w=video.videoWidth||0,h=video.videoHeight||0;if(!w||!h){reject(new Error('Camera not ready.'));return;}var c=document.createElement('canvas');c.width=w;c.height=h;c.getContext('2d').drawImage(video,0,0,w,h);c.toBlob(function(b){b?res(b):reject(new Error('Capture failed.'));},'image/jpeg',0.9);});}
  capBtn.addEventListener('click',async function(){
    if(busy||!stream)return;busy=true;capBtn.disabled=true;
    try{
      if(step<POSES.length){blobs.push(await capture());step++;mark();setStatus('Pose saved. Next: '+(step<POSES.length?POSES[step]:'Verify face.'),'ok');return;}
      show(4);setStatus('Comparing your face with the ID photo...','');
      var fd=new FormData();fd.append('csrf_token',document.getElementById('pawCsrf').value);
      blobs.forEach(function(b,i){fd.append('face_image',b,'pose'+(i+1)+'.jpg');});
      var res=await fetch(PAW_SETTINGS_URLS.face,{method:'POST',body:fd,headers:{'Accept':'application/json'}});
      var d=await res.json();
      if(!res.ok||!d.ok){show(3);setStatus(d.error||'Face did not match. Retake the captures.','error');retakeBtn.hidden=false;return;}
      document.getElementById('idvResultTitle').textContent='Verification successful';
      document.getElementById('idvResultMsg').textContent=d.message+' Match score: '+d.score;
      var st=document.getElementById('idv-status');
      if(st) st.innerHTML='Status: <b style="color:var(--ok)">verified</b> just now';
      setStatus('','ok');show(5);stopCam();
      setTimeout(function(){ window.location.reload(); }, 2500);
    }catch(err){setStatus(err.message||'Error','error');retakeBtn.hidden=false;}
    finally{busy=false;if(stream)capBtn.disabled=false;}
  });
  retakeBtn.addEventListener('click',function(){step=0;blobs=[];retakeBtn.hidden=true;mark();setStatus('Retake the captures. Follow the highlighted instructions.','');});
  document.getElementById('idvAgain').addEventListener('click',function(){window.location.reload();});
})();
