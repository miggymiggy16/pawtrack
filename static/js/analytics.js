const D = window.PAW_ANALYTICS;
const K = o => Object.keys(o), V = o => Object.values(o);
if (pawCharts()) {
  pawChart('c1','doughnut',K(D.species),V(D.species));
  pawChart('c2','doughnut',K(D.ownership),V(D.ownership));
  pawChart('c3','pie',K(D.sex),V(D.sex));
  pawChart('c4','bar',K(D.breeds),V(D.breeds),{label:'Animals',horizontal:true});
  pawChart('c5','bar',K(D.status_counts),V(D.status_counts),{label:'Animals'});
  pawChart('c6','bar',['Upcoming','Due Today','Overdue'],[D.vax['Upcoming'],D.vax['Due Today'],D.vax['Overdue']],{label:'Records',colors:['#7FB4F5','#F5A04A','#F26B6B']});
  pawChart('c7','line',K(D.monthly),V(D.monthly),{label:'Vaccinations'});
  pawChart('c8','bar',K(D.top_vaccines),V(D.top_vaccines),{label:'Times given',horizontal:true});
  pawChart('c9','bar',K(D.species_cov),V(D.species_cov),{label:'Coverage %',max:100});
  pawChart('c10','bar',K(D.ownership_cov),V(D.ownership_cov),{label:'Coverage %',max:100});
  pawChart('c11','bar',K(D.value_by_cat),V(D.value_by_cat),{label:'Value'});
  pawChart('c12','bar',['Low stock','Out of stock','Expired','Expiring soon'],[D.inv.low,D.inv.out,D.inv.expired,D.inv.expiring],{label:'Items',colors:['#F5A04A','#F26B6B','#C94444','#FFD2A1']});
}
