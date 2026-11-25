if (pawCharts()) {
  pawChart('cMonthly','bar',PAW_DASH.labels,PAW_DASH.vaccinations,{label:'Vaccinations'});
  const S = PAW_DASH.status;
  pawChart('cStatus','doughnut',Object.keys(S),Object.values(S));
}
/* mobile-only charts */
if (window.matchMedia('(max-width: 700px)').matches && typeof Chart !== 'undefined') {
  const ML = PAW_DASH.labels, MV = PAW_DASH.vaccinations;
  Chart.defaults.font.family = 'Poppins, sans-serif';
  new Chart(document.getElementById('mMonthly'), {type:'bar', data:{labels:ML, datasets:[{data:MV, backgroundColor:['#8FB4F4','#2E5FD0','#1E40AF','#7EA6F0','#1E40AF','#8FB4F4'], borderRadius:5, barPercentage:0.62}]}, options:{plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{color:'#9AA6B2',font:{size:9}}},y:{beginAtZero:true,grid:{color:'rgba(0,0,0,.06)'},ticks:{color:'#9AA6B2',font:{size:10},stepSize:1}}},maintainAspectRatio:false,responsive:true}});
  const S = PAW_DASH.status;
  new Chart(document.getElementById('mStatus'), {type:'doughnut', data:{labels:Object.keys(S), datasets:[{data:Object.values(S), backgroundColor:['#2E5FD0','#8FB4F4','#1E40AF','#C9D8F5'], borderWidth:0}]}, options:{cutout:'64%',plugins:{legend:{display:false}},maintainAspectRatio:false,responsive:true}});
  const leg = document.getElementById('mLegend');
  if (leg) { Object.entries(S).forEach(function(e,i){ var colors=['#2E5FD0','#8FB4F4','#1E40AF','#C9D8F5']; leg.insertAdjacentHTML('beforeend','<span class="m-lgi"><i style="background:'+colors[i%4]+'"></i>'+e[0]+'</span>'); }); }
}
