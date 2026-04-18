(function(){

  /* ── Camera overlay: lives in this document (paper preview) ──────── */
  if (!document.getElementById('fourd-cam-overlay')) {
    function _mk(t,c,h){var e=document.createElement(t);if(c)e.style.cssText=c;if(h)e.innerHTML=h;return e;}
    var _ov=_mk('div',
      'display:none;position:fixed;top:0;left:0;width:100%;height:100%;'+
      'z-index:2147483647;background:rgba(0,0,0,0.85);'+
      'align-items:center;justify-content:center;padding:24px;box-sizing:border-box;');
    _ov.id='fourd-cam-overlay';
    var _in=_mk('div',
      'width:100%;max-width:1200px;height:100%;display:flex;flex-direction:column;'+
      'background:#1a1a2e;border-radius:8px;padding:12px;'+
      'box-sizing:border-box;box-shadow:0 8px 32px rgba(0,0,0,0.6);');
    var _hd=_mk('div','display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-shrink:0;');
    var _tx=_mk('span','color:#aaa;font-size:12px;font-family:monospace;',
      '\uD83D\uDCF7 Camera Setup \u2014 rotate the figure to your desired viewpoint');
    var _cb=_mk('button','background:none;border:none;color:#999;font-size:20px;cursor:pointer;padding:0 4px;flex-shrink:0;','\u2715');
    _cb.onclick=function(){_ov.style.display='none';};
    _hd.appendChild(_tx); _hd.appendChild(_cb);
    var _sb=_mk('div',
      'display:flex;justify-content:space-between;align-items:center;'+
      'margin-bottom:6px;flex-shrink:0;padding:6px 10px;background:#0d1117;border-radius:4px;');
    _sb.id='fourd-cam-stbar';
    var _st=_mk('span','color:#888;font-size:11px;font-family:monospace;',
      'Rotate then release \u2014 camera position saves automatically');
    _st.id='fourd-cam-sttxt';
    var _sr=_mk('span','color:#555;font-size:11px;font-family:monospace;',
      'After saving \u2192 click \u201cRebuild HTML\u201d to apply');
    _sb.appendChild(_st); _sb.appendChild(_sr);
    var _fr=_mk('iframe','flex:1;min-height:0;width:100%;border:none;border-radius:4px;display:block;');
    _fr.id='fourd-cam-iframe'; _fr.frameBorder='0';
    var _ft=_mk('p','color:#555;font-size:10px;margin:4px 0 0;text-align:right;font-family:monospace;flex-shrink:0;');
    _ft.id='fourd-cam-figid';
    _in.appendChild(_hd); _in.appendChild(_sb); _in.appendChild(_fr); _in.appendChild(_ft);
    _ov.appendChild(_in);
    document.body.appendChild(_ov);
  }

  /* ── Message handler: camera open, camera sync, field update, locking ── */
  window.addEventListener("message",function(e){
    if(!e.data)return;

    if(e.data.type==="4dpaper-open-camera"){
      var _o=document.getElementById('fourd-cam-overlay');
      var _f=document.getElementById('fourd-cam-iframe');
      var _lb=document.getElementById('fourd-cam-figid');
      var _ss=document.getElementById('fourd-cam-sttxt');
      if(_lb)_lb.textContent='fig id: '+e.data.fig_id;
      if(_f)_f.src=e.data.preview_src+'?t='+Date.now();
      if(_ss){_ss.textContent='Rotate then release \u2014 camera position saves automatically';_ss.style.color='#888';}
      if(_o)_o.style.display='flex';

    } else if(e.data.type==="4dpaper-camera"){
      /* Check if message comes from a sync-panel subfigure (has data-panel attr) */
      var panelId=null;
      var allPanelFrames=document.querySelectorAll("iframe[data-panel]");
      for(var _pi=0;_pi<allPanelFrames.length;_pi++){
        if(allPanelFrames[_pi].contentWindow===e.source){
          panelId=allPanelFrames[_pi].getAttribute("data-panel");break;
        }
      }
      var camId=panelId||e.data.fig_id;
      var _f2=document.getElementById('fourd-cam-iframe');
      var _ss2=document.getElementById('fourd-cam-sttxt');
      fetch('/camera/'+camId,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(e.data.camera)
      }).then(function(r){
        if(_ss2){
          if(r.ok){_ss2.textContent='\u2713 Camera saved \u2014 click \u201cRebuild HTML\u201d to apply';_ss2.style.color='#4caf50';}
          else{_ss2.textContent='\u2717 Save failed (server error)';_ss2.style.color='#f44336';}
        }
        if(panelId){
          /* Sync panel: broadcast camera-apply + ack to all subfigures in this panel */
          var ack={type:'4dpaper-camera-ack',fig_id:'*',status:r.ok?'ok':'error'};
          var pFrames=document.querySelectorAll('iframe[data-panel="'+panelId+'"]');
          for(var _pj=0;_pj<pFrames.length;_pj++){
            pFrames[_pj].contentWindow.postMessage({type:'4dpaper-camera-apply',camera:e.data.camera},'*');
            pFrames[_pj].contentWindow.postMessage(ack,'*');
          }
        } else {
          var ack2={type:'4dpaper-camera-ack',fig_id:camId,status:r.ok?'ok':'error'};
          if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(ack2,'*');
          if(e.source&&e.source!==(_f2&&_f2.contentWindow))e.source.postMessage(ack2,'*');
        }
      }).catch(function(){
        if(_ss2){_ss2.textContent='\u2717 Save failed (network error)';_ss2.style.color='#f44336';}
        if(panelId){
          var ack3={type:'4dpaper-camera-ack',fig_id:'*',status:'error'};
          var pFrames2=document.querySelectorAll('iframe[data-panel="'+panelId+'"]');
          for(var _pk=0;_pk<pFrames2.length;_pk++){pFrames2[_pk].contentWindow.postMessage(ack3,'*');}
        } else {
          var ack4={type:'4dpaper-camera-ack',fig_id:camId,status:'error'};
          if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(ack4,'*');
          if(e.source&&e.source!==(_f2&&_f2.contentWindow))e.source.postMessage(ack4,'*');
        }
      });

    } else if(e.data.type==="4dpaper-field-update"){
      var figId2=e.data.fig_id;
      fetch('/field/'+figId2,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(e.data.data)
      }).then(function(r){
        if(r.ok&&e.source)e.source.postMessage({type:'4dpaper-field-ack',fig_id:figId2,status:'ok'},'*');
      }).catch(function(){
        if(e.source)e.source.postMessage({type:'4dpaper-field-ack',fig_id:figId2,status:'error'},'*');
      });

    } else if(e.data.type==="4dpaper-lock-query"){
      var lockFigId=e.data.fig_id;
      fetch("/camera-lock/"+lockFigId)
        .then(function(r){return r.json();})
        .then(function(d){
          if(e.source)e.source.postMessage(
            {type:"4dpaper-lock-state",fig_id:lockFigId,locked:!!d.locked},"*");
        }).catch(function(){
          if(e.source)e.source.postMessage(
            {type:"4dpaper-lock-state",fig_id:lockFigId,locked:false},"*");
        });

    } else if(e.data.type==="4dpaper-lock-toggle"){
      var lockFigId2=e.data.fig_id;
      fetch("/camera-lock/"+lockFigId2,{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({locked:!!e.data.locked})
      }).then(function(r){
        if(e.source)e.source.postMessage(
          {type:"4dpaper-lock-ack",fig_id:lockFigId2,status:r.ok?"ok":"error"},"*");
      }).catch(function(){
        if(e.source)e.source.postMessage(
          {type:"4dpaper-lock-ack",fig_id:lockFigId2,status:"error"},"*");
      });
    }
  });
})();
