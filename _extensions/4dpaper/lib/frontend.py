from __future__ import annotations
import sys
import base64 as _b64
import json
from pathlib import Path
import re
from lib.utils import is_cache_valid

_GOLDEN_TOPBAR_JS = '  function _b64ToF32(b64){if(!b64)return null;var bin=atob(b64),len=bin.length,bytes=new Uint8Array(len);for(var i=0;i<len;i++)bytes[i]=bin.charCodeAt(i);return new Float32Array(bytes.buffer);}\n  function _getDecodedField(name){if(!_decodedFieldData[name]&&FIELD_DATA[name])_decodedFieldData[name]=_b64ToF32(FIELD_DATA[name]);return _decodedFieldData[name]||null;}\n  function _getDecodedTime(name){if(!_decodedTimeData[name]){var src=TIME_DATA[name]||[];_decodedTimeData[name]=src.map(_b64ToF32);}return _decodedTimeData[name]||[];}\n  function _getTimeRange(name){return TIME_GLOBAL_RANGE[name]||[0.0,1.0];}\n  function _getRenderer(){if(_renderer&&_renderer.getActors)return _renderer;var rw=window.renderWindow;if(rw&&rw.getRenderers){var rs=rw.getRenderers();for(var i=0;i<rs.length;i++){var r=rs[i];if(r&&r.getActors&&r.getActors().length>0){_renderer=r;return r;}}for(var j=0;j<rs.length;j++){if(rs[j]){_renderer=rs[j];return _renderer;}}}return null;}\n  function _findMeshActor(){if(!window.__4dp_global_probe){window.__4dp_global_probe=true;var hits=Object.keys(window).filter(function(k){return /vtk|render|view|trame|scene|loca/i.test(k);});hits.forEach(function(k){try{var v=window[k];}catch(_){}});var canvases=document.querySelectorAll("canvas");canvases.forEach(function(c,ci){var keys=Object.keys(c).filter(function(k){return /vtk|render/i.test(k);});});try{var pIfr=parent&&parent.window;}catch(_){}try{var olv=window.OfflineLocalView;if(olv){["getRenderer","getRenderWindow","getRenderers","getViewer","getView","render","scene","viewer"].forEach(function(m){});}}catch(e){}try{var cs=document.querySelectorAll("canvas");if(cs&&cs[0]){var c=cs[0];var ck=[];for(var key in c){if(/vtk|render/i.test(key))ck.push(key);}}}catch(_){}}var r=_getRenderer();if(!r){if(!window.__4dp_no_r){window.__4dp_no_r=true;}return null;}if(!window.__4dp_probed){window.__4dp_probed=true;var rw=window.renderWindow;var rs=rw&&rw.getRenderers?rw.getRenderers():[];rs.forEach(function(rr,ri){var acts=rr.getActors?rr.getActors():[];var props=rr.getViewProps?rr.getViewProps():[];var all=[].concat(acts).concat(props);all.forEach(function(a,ai){var m=a&&a.getMapper&&a.getMapper();var d=m&&m.getInputData&&m.getInputData();var pd=d&&d.getPointData&&d.getPointData();var arrs=[];if(pd&&pd.getNumberOfArrays){for(var k=0;k<pd.getNumberOfArrays();k++){var arr=pd.getArrayByIndex&&pd.getArrayByIndex(k);arrs.push(arr&&arr.getName&&arr.getName());}}});});}var acts=r.getActors?r.getActors():[];var props=r.getViewProps?r.getViewProps():[];var all=[].concat(acts).concat(props);for(var i=0;i<all.length;i++){var a=all[i],m=a&&a.getMapper&&a.getMapper(),d=m&&m.getInputData&&m.getInputData();if(d&&d.getPointData&&d.getPointData())return a;}return null;}\n  function _getScalarTarget(){_meshActor=_meshActor||_findMeshActor();if(!_meshActor){return null;}var mapper=_meshActor.getMapper&&_meshActor.getMapper();var input=mapper&&mapper.getInputData&&mapper.getInputData();var pd=input&&input.getPointData&&input.getPointData();var scalars=pd&&pd.getScalars&&pd.getScalars();if(!mapper||!input||!pd||!scalars){return null;}return {mapper:mapper,input:input,pd:pd,scalars:scalars};}\n  function _applyScalarArray(arr,range,name){var t=_getScalarTarget();if(!t||!arr){return false;}var next=t.pd&&t.pd.getArrayByName?t.pd.getArrayByName(_displayScalarName):null;if(next&&next.setData){next.setData(arr,1);}else if(t.pd&&t.pd.getScalars&&t.pd.getScalars()&&t.pd.getScalars().setData){next=t.pd.getScalars();next.setData(arr,1);}else if(t.scalars&&t.scalars.newClone){next=t.scalars.newClone();if(next.setNumberOfComponents)next.setNumberOfComponents(1);if(next.setData)next.setData(arr,1);}else if(t.scalars&&t.scalars.newInstance){next=t.scalars.newInstance({numberOfComponents:1,values:arr});}else {return false;}if(next&&next.setName)next.setName(_displayScalarName);if(next&&t.pd.addArray)t.pd.addArray(next);if(_displayScalarName&&t.pd.setActiveScalars)t.pd.setActiveScalars(_displayScalarName);if(next&&t.pd.setScalars)t.pd.setScalars(next);if(next&&next.modified)next.modified();if(t.pd.modified)t.pd.modified();if(t.input.modified)t.input.modified();if(t.mapper.setColorByArrayName)t.mapper.setColorByArrayName(_displayScalarName);if(t.mapper.setScalarModeToUsePointData)t.mapper.setScalarModeToUsePointData();if(t.mapper.setScalarVisibility)t.mapper.setScalarVisibility(true);if(range&&t.mapper.setScalarRange)t.mapper.setScalarRange(range[0],range[1]);if(t.mapper.mapScalars)t.mapper.mapScalars(t.input,1.0);if(t.mapper.modified)t.mapper.modified();if(_meshActor.modified)_meshActor.modified();var _sbrw=window.renderWindow;if(_sbrw&&_sbrw.getRenderers){var _sbrs=_sbrw.getRenderers();for(var _sbi=0;_sbi<_sbrs.length;_sbi++){var _sbp=[].concat(_sbrs[_sbi].getActors?_sbrs[_sbi].getActors():[]).concat(_sbrs[_sbi].getViewProps?_sbrs[_sbi].getViewProps():[]);for(var _sbj=0;_sbj<_sbp.length;_sbj++){var _sba=_sbp[_sbj];if(_sba.getClassName&&_sba.getClassName().indexOf(\'ScalarBar\')>=0){if(name&&_sba.setAxisLabel)_sba.setAxisLabel(name);var _sbl=_sba.getScalarsToColors&&_sba.getScalarsToColors();if(_sbl&&range&&_sbl.setMappingRange){_sbl.setMappingRange(range[0],range[1]);if(_sbl.updateRange)_sbl.updateRange();}if(_sba.modified)_sba.modified();}}}}if(window.renderWindow){window.renderWindow.render();}return true;}\n  function _emitTimeSync(){if(TIME_DATA[ACTIVE_FIELD]&&TIME_DATA[ACTIVE_FIELD].length>1)parent.postMessage({type:"4dpaper-time",fig_id:FIG_ID,idx:_timeIdx,playing:_timePlaying},"*");}\n  function _setTimeFrame(idx,silent){var frames=_getDecodedTime(ACTIVE_FIELD);if(!frames||idx<0||idx>=frames.length){return;}_timeIdx=idx;var slider=document.getElementById("cs-time-slider-__FIGSAFE__");if(slider)slider.value=String(idx);var label=document.getElementById("cs-time-val-__FIGSAFE__");if(label)label.textContent=(TIME_LABELS[idx]||String(idx));var arr=frames[idx];if(arr)_applyScalarArray(arr,_getTimeRange(ACTIVE_FIELD),ACTIVE_FIELD);if(!silent){_emitTimeSync();parent.postMessage({type:"4dpaper-field-update",fig_id:FIG_ID,data:{time:(typeof TIME_INDICES!=="undefined"?TIME_INDICES[idx]:idx)}},"*");}if(window[\'__4dp_onframe___FIGSAFE__\'])window[\'__4dp_onframe___FIGSAFE__\'](idx);}\n  function _setPlaying(v,silent){_timePlaying=!!v;var btn=document.getElementById("cs-play-__FIGSAFE__");if(btn)btn.innerHTML=_timePlaying?"&#x23F8;":"&#x25B6;";if(!_timePlaying&&_timeRaf){cancelAnimationFrame(_timeRaf);_timeRaf=0;}if(!silent)_emitTimeSync();}\n  function _tickTime(ts){if(!_timePlaying)return;if(!_timeLastTs)_timeLastTs=ts;if(ts-_timeLastTs>=180){var frames=_getDecodedTime(ACTIVE_FIELD);if(frames&&frames.length){_setTimeFrame((_timeIdx+1)%frames.length);} _timeLastTs=ts;}_timeRaf=requestAnimationFrame(_tickTime);}\n  function _bindControls(){if(_controlsBound)return;_controlsBound=true;var slider=document.getElementById("cs-time-slider-__FIGSAFE__");if(slider)slider.addEventListener("input",function(){_setPlaying(false,true);_setTimeFrame(parseInt(this.value||"0",10)||0);});var play=document.getElementById("cs-play-__FIGSAFE__");if(play)play.addEventListener("click",function(){if(_locked){if(typeof _showLockedBadge==="function")_showLockedBadge();return;}var nv=!_timePlaying;_setPlaying(nv);_timeLastTs=0;if(nv)_timeRaf=requestAnimationFrame(_tickTime);});var fieldSel=document.getElementById("cs-field-sel-__FIGSAFE__");if(fieldSel)fieldSel.addEventListener("change",function(){var f=this.value,arr=_getDecodedField(f),range=FIELD_RANGES[f];if(arr&&_applyScalarArray(arr,range,f)){ACTIVE_FIELD=f;var badge=document.getElementById("cs-field-badge-__FIGSAFE__");if(badge){badge.textContent=f;badge.style.display="inline-block";badge.style.background="rgba(74,158,255,0.18)";badge.style.color="#9ecbff";setTimeout(function(){badge.style.display="none";},900);}if(TIME_DATA[f]&&TIME_DATA[f].length>_timeIdx){_setTimeFrame(_timeIdx);}parent.postMessage({type:"4dpaper-field-update",fig_id:FIG_ID,data:{field:f}},"*");}});if(TIME_DATA[ACTIVE_FIELD]&&TIME_DATA[ACTIVE_FIELD].length>1){var label=document.getElementById("cs-time-val-__FIGSAFE__");if(label)label.textContent=(TIME_LABELS[_timeIdx]||String(_timeIdx));}}\n  function _setLocked(v){\n    _locked=v;if(v){_setPlaying(false);}\n    var w=document.getElementById("cs-lock-widget-__FIGSAFE__");\n    if(w)w.innerHTML=v?"&#x1F512;":"&#x1F513;";\n    var s=document.getElementById("cs-lock-shield-__FIGSAFE__");\n    if(s)s.style.display=v?"block":"none";\n    var rw=window.renderWindow;\n    var i=(rw&&rw.getInteractor?rw.getInteractor():null);\n    if(i&&i.setEnabled)i.setEnabled(v?0:1);\n    var c=_cont||(i&&i.getContainer?i.getContainer():null);\n    if(c&&c.style){c.style.pointerEvents=v?"none":"";c.style.touchAction=v?"none":"";}\n    if(v&&i&&i.stopAnimating)i.stopAnimating();\n  }\n  function _n3(v){var l=Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);return l<1e-10?[0,0,1]:[v[0]/l,v[1]/l,v[2]/l];}\n  function _cr(a,b){return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}\n  function _dt(a,b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}\n  function _rot(v,ax,deg){var a=_n3(ax),x=v[0],y=v[1],z=v[2],c=Math.cos(deg*Math.PI/180),s=Math.sin(deg*Math.PI/180),d=a[0]*x+a[1]*y+a[2]*z;return[x*c+(a[1]*z-a[2]*y)*s+a[0]*d*(1-c),y*c+(a[2]*x-a[0]*z)*s+a[1]*d*(1-c),z*c+(a[0]*y-a[1]*x)*s+a[2]*d*(1-c)];}\n  window.csSetView___FIGSAFE__=function(dir,vup){if(!_renderer || _locked)return;var cam=_renderer.getActiveCamera(),fp=cam.getFocalPoint(),dist=cam.getDistance(),pn=_n3(dir),up=vup?_n3(vup):((Math.abs(pn[2])>0.9)?[0,1,0]:[0,0,1]);cam.setPosition(fp[0]+pn[0]*dist,fp[1]+pn[1]*dist,fp[2]+pn[2]*dist);cam.setViewUp(up[0],up[1],up[2]);cam.setFocalPoint(fp[0],fp[1],fp[2]);_renderer.resetCameraClippingRange();if(window.renderWindow)window.renderWindow.render();_sendCam(_renderer);};\n  window.csRotate___FIGSAFE__=function(dx,dy){if(!_renderer || _locked)return;var cam=_renderer.getActiveCamera(),pos=cam.getPosition(),fp=cam.getFocalPoint(),vup=cam.getViewUp(),rel=[pos[0]-fp[0],pos[1]-fp[1],pos[2]-fp[2]],right=_n3(_cr(rel,vup)),pitch=_rot(rel,right,dy),yawAxis=_n3(vup),yaw=_rot(pitch,yawAxis,dx);cam.setPosition(fp[0]+yaw[0],fp[1]+yaw[1],fp[2]+yaw[2]);cam.setViewUp(vup[0],vup[1],vup[2]);_renderer.resetCameraClippingRange();if(window.renderWindow)window.renderWindow.render();_sendCam(_renderer);};\n  var _camTimer=null;\n  function _sendCam(r){if(_locked)return;clearTimeout(_camTimer);_camTimer=setTimeout(function(){var c=r.getActiveCamera();var d={position:c.getPosition(),focal_point:c.getFocalPoint(),view_up:c.getViewUp(),parallel_scale:c.getParallelScale(),parallel_projection:c.getParallelProjection()?1:0};parent.postMessage({type:"4dpaper-camera",fig_id:FIG_ID,camera:d},"*");},300);}\n  var _svg=null;\n  function _drawAxes(){if(!_renderer||!_svg)return;var cam=_renderer.getActiveCamera(),pos=cam.getPosition(),fp=cam.getFocalPoint(),vup=cam.getViewUp(),vd=_n3([fp[0]-pos[0],fp[1]-pos[1],fp[2]-pos[2]]),right=_n3(_cr(vd,vup)),up=_cr(right,vd),cx=28,cy=28,R=22;function proj(v){return[cx+R*_dt(v,right),cy-R*_dt(v,up)];}var axes=[{w:[1,0,0],col:"#ff6666",lcol:"#ff9999",lbl:"X",hpd:\'data-dir="1,0,0"\'},{w:[0,1,0],col:"#66cc66",lcol:"#99cc99",lbl:"Y",hpd:\'data-dir="0,1,0"\'},{w:[0,0,1],col:"#6699ff",lcol:"#99aaff",lbl:"Z",hpd:\'data-dir="0,0,1"\'}];var h="";axes.forEach(function(ax){var tip=proj(ax.w),tx=tip[0].toFixed(1),ty=tip[1].toFixed(1),dx=tip[0]-cx,dy=tip[1]-cy,len=Math.sqrt(dx*dx+dy*dy)||1,nx=-dy/len*3.5,ny=dx/len*3.5,bx1=(tip[0]-dx/len*7+nx).toFixed(1),by1=(tip[1]-dy/len*7+ny).toFixed(1),bx2=(tip[0]-dx/len*7-nx).toFixed(1),by2=(tip[1]-dy/len*7-ny).toFixed(1);h+=\'<line x1="\'+cx+\'" y1="\'+cy+\'" x2="\'+tx+\'" y2="\'+ty+\'" \'+ax.hpd+\' stroke="\'+ax.col+\'" stroke-width="2.5"/>\';h+=\'<polygon points="\'+tx+","+ty+" "+bx1+","+by1+" "+bx2+","+by2+\'" \'+ax.hpd+\' fill="\'+ax.col+\'"/>\';h+=\'<text x="\'+(tip[0]+dx/len*5).toFixed(1)+\'" y="\'+(tip[1]+dy/len*5+3).toFixed(1)+\'" \'+ax.hpd+\' font-size="9" fill="\'+ax.lcol+\'" font-family="monospace">\'+ax.lbl+\'</text>\';});_svg.innerHTML=h;}\n  function _axLoop(){_drawAxes();requestAnimationFrame(_axLoop);}\n  (function _wR(){\n    var rw=window.renderWindow;\n    var r=_getRenderer();\n    if(r){\n          var i=rw&&rw.getInteractor?rw.getInteractor():null;_cont=i?i.getContainer():null;\n          if(_cont){\n            _cont.addEventListener("mouseenter",function(){_isHovered=true;window.focus();});\n            _cont.addEventListener("mouseleave",function(){_isHovered=false;});\n            _cont.addEventListener("wheel",function(e){e.preventDefault();},{passive:false});\n          }\n          _bindControls();\n          _svg=document.getElementById("cs-svg-axes-__FIGSAFE__");_svg.addEventListener("click",function(e){var dv=e.target.getAttribute("data-dir");if(!dv)return;if(_locked){if(typeof _showLockedBadge==="function")_showLockedBadge();return;}csSetView___FIGSAFE__(dv.split(",").map(Number));});_axLoop();\n          if(TIME_DATA[ACTIVE_FIELD]&&TIME_DATA[ACTIVE_FIELD].length>1)_setTimeFrame(_timeIdx);\n          document.addEventListener("pointerup",function(){_sendCam(_renderer);});\n          document.addEventListener("mouseup",function(){_sendCam(_renderer);});\n          document.addEventListener("touchend",function(){_sendCam(_renderer);});\n          return;\n    }\n    setTimeout(_wR,200);\n  })();\n  _bindControls();\n  window.addEventListener("message",function(e){\n    if(!e.data)return;var d=e.data;\n    if(d.type==="4dpaper-camera-apply"){if(_locked)return;var r=_getRenderer();if(!r)return;var cam=d.camera,c=r.getActiveCamera();if(cam.position)c.setPosition(cam.position[0],cam.position[1],cam.position[2]);if(cam.focal_point)c.setFocalPoint(cam.focal_point[0],cam.focal_point[1],cam.focal_point[2]);if(cam.view_up)c.setViewUp(cam.view_up[0],cam.view_up[1],cam.view_up[2]);if(cam.parallel_scale!=null)c.setParallelScale(cam.parallel_scale);if(cam.parallel_projection!=null)c.setParallelProjection(!!cam.parallel_projection);r.resetCameraClippingRange();window.renderWindow.render();}\n    else if(d.type==="4dpaper-time-apply"&&d.fig_id!==FIG_ID){_setPlaying(!!d.playing,true);_timeLastTs=0;_setTimeFrame(parseInt(d.idx||"0",10)||0,true);}\n    else if(d.type==="4dpaper-lock-state"&&d.fig_id===FIG_ID)_setLocked(!!d.locked);\n    else if(d.type==="4dpaper-lock-ack"&&d.fig_id===FIG_ID){if(d.status!=="ok")_setLocked(!_locked);}\n    else if(d.type==="4dpaper-lock-all")_setLocked(!!d.locked);\n    else if(d.type==="4dpaper-hide-lock-btn"){var w=document.getElementById("cs-lock-widget-__FIGSAFE__");if(w)w.style.display="none";var s=document.getElementById("cs-lock-sep-__FIGSAFE__");if(s)s.style.display="none";}\n  });\n  window.addEventListener("keydown",function(e){if(!_renderer||!_isHovered||_locked)return;var k=e.key.toLowerCase();if(k==="x")csSetView___FIGSAFE__([1,0,0],[0,0,1]);else if(k==="y")csSetView___FIGSAFE__([0,1,0],[0,0,1]);else if(k==="z")csSetView___FIGSAFE__([0,0,1],[0,1,0]);else if(k==="i")csSetView___FIGSAFE__([1,1,1],[0,0,1]);else if(e.key==="ArrowUp")csRotate___FIGSAFE__(0,-90);else if(e.key==="ArrowDown")csRotate___FIGSAFE__(0,90);else if(e.key==="ArrowLeft")csRotate___FIGSAFE__(-90,0);else if(e.key==="ArrowRight")csRotate___FIGSAFE__(90,0);if(e.key.startsWith("Arrow"))e.preventDefault();});'

_GOLDEN_TOPBAR_JS = _GOLDEN_TOPBAR_JS.replace(
    """var _camTimer=null;
  function _sendCam(r){if(_locked)return;clearTimeout(_camTimer);_camTimer=setTimeout(function(){var c=r.getActiveCamera();var d={position:c.getPosition(),focal_point:c.getFocalPoint(),view_up:c.getViewUp(),parallel_scale:c.getParallelScale(),parallel_projection:c.getParallelProjection()?1:0};parent.postMessage({type:"4dpaper-camera",fig_id:FIG_ID,camera:d},"*");},300);}
""",
    """var _camLastSent=0;
  function _postCam(r){var c=r.getActiveCamera();var d={position:c.getPosition(),focal_point:c.getFocalPoint(),view_up:c.getViewUp(),parallel_scale:c.getParallelScale(),parallel_projection:c.getParallelProjection()?1:0};parent.postMessage({type:"4dpaper-camera",fig_id:FIG_ID,camera:d},"*");}
  function _sendCam(r){if(_locked)return;var now=Date.now();if(now-_camLastSent<40)return;_camLastSent=now;_postCam(r);}
""",
)
_GOLDEN_TOPBAR_JS = _GOLDEN_TOPBAR_JS.replace(
    """function _emitTimeSync(){if(TIME_DATA[ACTIVE_FIELD]&&TIME_DATA[ACTIVE_FIELD].length>1)parent.postMessage({type:"4dpaper-time",fig_id:FIG_ID,idx:_timeIdx,playing:_timePlaying},"*");}""",
    """function _emitTimeSync(){if(TIME_DATA[ACTIVE_FIELD]&&TIME_DATA[ACTIVE_FIELD].length>1)parent.postMessage({type:"4dpaper-time",fig_id:FIG_ID,idx:_timeIdx,source_idx:(typeof TIME_INDICES!=="undefined"?TIME_INDICES[_timeIdx]:_timeIdx),playing:_timePlaying},"*");}""",
)
_GOLDEN_TOPBAR_JS = _GOLDEN_TOPBAR_JS.replace(
    """else if(d.type==="4dpaper-time-apply"&&d.fig_id!==FIG_ID){_setPlaying(!!d.playing,true);_timeLastTs=0;_setTimeFrame(parseInt(d.idx||"0",10)||0,true);}""",
    """else if(d.type==="4dpaper-time-apply"&&d.fig_id!==FIG_ID){_setPlaying(!!d.playing,true);_timeLastTs=0;var _ti=parseInt(d.idx||"0",10)||0;if(d.source_idx!=null&&typeof TIME_INDICES!=="undefined"&&TIME_INDICES.length){var _src=parseInt(d.source_idx||"0",10)||0,_best=0,_bd=Math.abs(TIME_INDICES[0]-_src);for(var _i=1;_i<TIME_INDICES.length;_i++){var _dd=Math.abs(TIME_INDICES[_i]-_src);if(_dd<_bd){_best=_i;_bd=_dd;}}_ti=_best;}_setTimeFrame(_ti,true);}""",
)
# Queue camera-apply if renderer not ready yet; apply when _wR() finds the renderer.
_GOLDEN_TOPBAR_JS = _GOLDEN_TOPBAR_JS.replace(
    'if(d.type==="4dpaper-camera-apply"){if(_locked)return;var r=_getRenderer();if(!r)return;',
    'if(d.type==="4dpaper-camera-apply"){if(_locked)return;var r=_getRenderer();if(!r){_pendingCam=d.camera;return;}',
)
_GOLDEN_TOPBAR_JS = _GOLDEN_TOPBAR_JS.replace(
    '          document.addEventListener("pointerup",function(){_sendCam(_renderer);});\n          document.addEventListener("mouseup",function(){_sendCam(_renderer);});\n          document.addEventListener("touchend",function(){_sendCam(_renderer);});\n          return;\n    }\n    setTimeout(_wR,200);\n  })();',
    '          document.addEventListener("pointerup",function(){_sendCam(_renderer);});\n          document.addEventListener("mouseup",function(){_sendCam(_renderer);});\n          document.addEventListener("touchend",function(){_sendCam(_renderer);});\n          if(_pendingCam&&!_locked){var _pc=_pendingCam;_pendingCam=null;var _pcc=r.getActiveCamera();if(_pc.position)_pcc.setPosition(_pc.position[0],_pc.position[1],_pc.position[2]);if(_pc.focal_point)_pcc.setFocalPoint(_pc.focal_point[0],_pc.focal_point[1],_pc.focal_point[2]);if(_pc.view_up)_pcc.setViewUp(_pc.view_up[0],_pc.view_up[1],_pc.view_up[2]);if(_pc.parallel_scale!=null)_pcc.setParallelScale(_pc.parallel_scale);if(_pc.parallel_projection!=null)_pcc.setParallelProjection(!!_pc.parallel_projection);r.resetCameraClippingRange();window.renderWindow.render();}\n          return;\n    }\n    setTimeout(_wR,200);\n  })();',
)
def _generate_optimized_timeseries_html(
    ts_id: str,
    src: Path,
    step_indices: list[int],
    field: str,
    fields_attr: str,
    figures_dir: Path,
    style: dict,
    caption: str = "",
) -> None:
    """Generate composite HTML for timeseries with identical mesh (simplified approach).

    Strategy: Generate individual frame HTMLs then create a composite viewer that
    loads them via iframes in a grid, reducing redundancy in the manifest/Lua layer
    while keeping the per-frame HTML generation working.
    """
    try:
        from scripts.data_loader import SimulationData

        sim = SimulationData(str(src)).load()
        available_fields = [f.strip() for f in fields_attr.split(",") if f.strip()] if fields_attr else []
        if field and field not in available_fields:
            available_fields.insert(0, field)
        if not available_fields:
            available_fields = [field]

        print(f"Generating optimized timeseries for {ts_id}…", file=sys.stderr)

        # Generate individual frame HTMLs using existing function
        code_deps = [Path(__file__), Path(__file__).with_name("render.py")]
        frame_ids = []
        total_size = 0
        for frame_idx, time_idx in enumerate(step_indices):
            frame_id = f"{ts_id}-frame-{frame_idx}"
            frame_ids.append(frame_id)

            out_html = figures_dir / f"{frame_id}.html"
            out_png = figures_dir / f"{frame_id}.png"
            if not is_cache_valid(out_html, src, extra_deps=code_deps) or not out_png.exists():
                print(f"  Generating {frame_id}…", file=sys.stderr)
                try:
                    from lib.render import generate_html_figure, generate_png_figure
                    generate_html_figure(
                        src, field, str(time_idx), out_html,
                        fig_id=frame_id, available_fields=available_fields,
                        background=style["background"],
                        axis_color=style["axis_color"],
                        cmap=style["cmap"],
                        decimate="auto",
                        show_lock_btn=False,
                        show_colorbar=(frame_idx == 0),
                        show_orientation=(frame_idx == 0),
                        broadcast_group=ts_id,
                    )
                    generate_png_figure(
                        src, field, str(time_idx), out_png,
                        fig_id=frame_id, camera_fig_id=ts_id,
                        show_colorbar=(frame_idx == 0), decimate="auto"
                    )
                except Exception as exc:
                    print(f"ERROR generating frame {frame_id}: {exc}", file=sys.stderr)
                    raise

            frame_size = out_html.stat().st_size
            total_size += frame_size
            print(f"    {frame_id}: {frame_size//1024} KB", file=sys.stderr)

        # Generate composite viewer HTML
        composite_html = _build_timeseries_composite_html(
            ts_id=ts_id,
            frame_ids=frame_ids,
            step_indices=step_indices,
            available_fields=available_fields,
            caption=caption,
            figures_dir=figures_dir,
        )

        output_path = figures_dir / f"{ts_id}.html"
        output_path.write_text(composite_html, encoding='utf-8')

        composite_size = output_path.stat().st_size
        print(f"Generated composite timeseries: {output_path} ({composite_size//1024} KB)", file=sys.stderr)
        print(f"  Total: {(total_size + composite_size)//1024} KB", file=sys.stderr)

        # Generate manifest file (for Lua filter compatibility)
        manifest = {
            "id": ts_id,
            "subfigures": frame_ids,
            "layout": f"{len(frame_ids)}x1",
            "caption": caption,
            "time_indices": step_indices,
        }
        manifest_path = figures_dir / f"{ts_id}.manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        print(f"Wrote manifest: {manifest_path}", file=sys.stderr)

    except Exception as exc:
        print(f"ERROR generating optimized timeseries {ts_id}: {exc}", file=sys.stderr)
        raise

def _build_timeseries_composite_html(
    ts_id: str,
    frame_ids: list[str],
    step_indices: list[int],
    available_fields: list[str],
    caption: str = "",
    figures_dir: Path | None = None,
) -> str:
    """Build composite HTML for timeseries with iframe grid layout."""

    # Use sibling file paths for child viewers when generating inside figures_dir.
    # Nested vtk.js pages render more reliably this way in static hosts such as
    # GitHub Pages than when embedded via srcdoc.
    frames_html_parts = []
    for i, fid in enumerate(frame_ids):
        if figures_dir:
            frame_path = figures_dir / f"{fid}.html"
            if frame_path.exists():
                frames_html_parts.append(
                    f'    <div class="frame-container">'
                    f'      <iframe src="{fid}.html" frameborder="0" class="frame-iframe"></iframe>'
                    f'      <div class="frame-label">Frame {i} (t={step_indices[i]})</div>'
                    f'    </div>'
                )
            else:
                frames_html_parts.append(
                    f'    <div class="frame-container" style="background:#222;display:flex;align-items:center;justify-content:center;">'
                    f'      <div style="color:#888;">⚠ Frame {i} not found</div>'
                    f'    </div>'
                )
        else:
            # Fallback: use external src (for standalone composite generation)
            frames_html_parts.append(
                f'    <div class="frame-container">'
                f'      <iframe src="/state/figures/{fid}.html" frameborder="0" class="frame-iframe"></iframe>'
                f'      <div class="frame-label">Frame {i} (t={step_indices[i]})</div>'
                f'    </div>'
            )

    frames_html = "\n".join(frames_html_parts)

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Timeseries: {ts_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0d1117; color: #c9d1d9; }}
        .container {{ display: flex; flex-direction: column; height: 100vh; }}
        .header {{ padding: 16px; background: #161b22; border-bottom: 1px solid #30363d; }}
        .header h1 {{ font-size: 24px; margin-bottom: 4px; }}
        .header p {{ font-size: 13px; color: #8b949e; }}
        .controls {{ padding: 12px 16px; background: #0d1117; border-bottom: 1px solid #30363d; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }}
        .control-group {{ display: flex; gap: 8px; align-items: center; }}
        .control-group label {{ font-size: 13px; display: flex; align-items: center; gap: 6px; }}
        select {{ padding: 6px 10px; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; font-size: 12px; }}
        input[type="range"] {{ flex: 1; min-width: 200px; height: 6px; -webkit-appearance: none; background: transparent; }}
        input[type="range"]::-webkit-slider-thumb {{ -webkit-appearance: none; appearance: none; width: 12px; height: 12px; border-radius: 50%; background: #238636; cursor: pointer; }}
        input[type="range"]::-moz-range-thumb {{ width: 12px; height: 12px; border-radius: 50%; background: #238636; cursor: pointer; border: none; }}
        .play-btn {{ padding: 6px 12px; background: #238636; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; }}
        .play-btn:hover {{ background: #2ea043; }}
        .grid-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 8px;
            flex: 1;
            overflow: auto;
            padding: 8px;
            background: #010409;
        }}
        .frame-container {{
            position: relative;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .frame-iframe {{
            flex: 1;
            min-height: 400px;
            border: none;
        }}
        .frame-label {{
            padding: 8px 12px;
            background: #0d1117;
            border-top: 1px solid #30363d;
            font-size: 12px;
            color: #8b949e;
            font-family: monospace;
        }}
        .sync-btn {{
            padding: 6px 12px;
            background: #238636;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
        }}
        .sync-btn:hover {{ background: #2ea043; }}
        .sync-btn.active {{ background: #1f6feb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{ts_id}</h1>
            {f'<p>{caption}</p>' if caption else ''}
        </div>

        <div class="controls">
            <div class="control-group">
                <button id="playBtn" class="play-btn">▶ Play</button>
                <input type="range" id="timelineSlider" min="0" max="{len(frame_ids) - 1}" value="0" style="flex: 0.3;">
                <span id="frameDisplay" style="font-size: 12px; color: #8b949e; min-width: 60px;">Frame 0/{len(frame_ids) - 1}</span>
            </div>
            <div class="control-group">
                <label for="fieldSelect">Field:</label>
                <select id="fieldSelect">
                    {chr(10).join(f'                    <option value="{f}">{f}</option>' for f in available_fields)}
                </select>
            </div>
            <button id="syncBtn" class="sync-btn">Sync Cameras (Off)</button>
        </div>

        <div class="grid-container" id="gridContainer">
{frames_html}
        </div>
    </div>

    <script>
        const FRAME_IDS = {json.dumps(frame_ids)};
        const AVAILABLE_FIELDS = {json.dumps(available_fields)};
        const N_FRAMES = FRAME_IDS.length;
        const PLAY_FPS = 2;

        let syncCameras = false;
        let isPlaying = false;
        let currentFrame = 0;
        let playInterval = null;

        function getAllViewers() {{
            return Array.from(document.querySelectorAll('.frame-iframe')).map(
                (iframe) => iframe.contentWindow
            ).filter(Boolean);
        }}

        function updateFrameDisplay() {{
            document.getElementById('frameDisplay').textContent = `Frame ${{currentFrame}}/${{N_FRAMES - 1}}`;
            document.getElementById('timelineSlider').value = currentFrame;
        }}

        function broadcastFrameSeek(frameIdx) {{
            currentFrame = Math.max(0, Math.min(frameIdx, N_FRAMES - 1));
            updateFrameDisplay();
            // DO NOT send frame index to child iframes — each frame has its own embedded timeline.
            // Frames are independent visualizations of their assigned timestep.
            // Only field and play state should be synchronized across frames.
        }}


        // Play button control — animates the frame index display in the composite viewer,
        // but does NOT control individual frame playback (frames are static timesteps).
        document.getElementById('playBtn').addEventListener('click', (e) => {{
            isPlaying = !isPlaying;
            const btn = e.target;
            btn.textContent = isPlaying ? '⏸ Pause' : '▶ Play';

            if (isPlaying) {{
                playInterval = setInterval(() => {{
                    currentFrame = (currentFrame + 1) % N_FRAMES;
                    updateFrameDisplay();
                    broadcastFrameSeek(currentFrame);
                }}, 1000 / PLAY_FPS);
            }} else {{
                clearInterval(playInterval);
            }}
            console.log('Composite play state:', isPlaying, 'currentFrame:', currentFrame);
        }});

        // Timeline slider control
        document.getElementById('timelineSlider').addEventListener('input', (e) => {{
            const frameIdx = parseInt(e.target.value);
            broadcastFrameSeek(frameIdx);
            // Stop playback when user drags slider
            if (isPlaying) {{
                isPlaying = false;
                clearInterval(playInterval);
                document.getElementById('playBtn').textContent = '▶ Play';
            }}
        }});

        // Sync cameras toggle
        document.getElementById('syncBtn').addEventListener('click', (e) => {{
            syncCameras = !syncCameras;
            e.target.textContent = `Sync Cameras (${{syncCameras ? 'On' : 'Off'}})`;
            e.target.classList.toggle('active', syncCameras);
            console.log('Sync cameras:', syncCameras);
        }});

        // Field selector (propagate to all frames)
        document.getElementById('fieldSelect').addEventListener('change', (e) => {{
            const field = e.target.value;
            console.log('Field changed to:', field);
            getAllViewers().forEach((viewerWindow) => {{
                if (viewerWindow) {{
                    viewerWindow.postMessage({{
                        type: '4dpaper-timeseries-field',
                        field: field
                    }}, '*');
                }}
            }});
        }});

        // Setup camera sync via postMessage
        window.addEventListener('message', (e) => {{
            if (e.data.type !== '4dpaper-camera') return;

            const firstViewer = document.getElementById(FRAME_IDS[0]);
            const isFirst = firstViewer && (e.source === firstViewer.contentWindow);

            if (!syncCameras && !isFirst) return;

            getAllViewers().forEach((viewerWindow) => {{
                if (viewerWindow && viewerWindow !== e.source) {{
                    viewerWindow.postMessage({{
                        type: '4dpaper-camera-apply',
                        camera: e.data.camera
                    }}, '*');
                }}
            }});
        }});

        updateFrameDisplay();
        console.log('Timeseries composite loaded with', FRAME_IDS.length, 'frames');
    </script>
</body>
</html>'''

def _controls_strip_snippet(
    fig_id: str,
    show_lock_btn: bool = True,
    show_orientation: bool = True,
    fields_to_embed: list[str] | None = None,
    active_field: str = "",
    field_data_b64: dict | None = None,
    field_ranges: dict | None = None,
    time_labels: list[str] | None = None,
    time_data_b64: dict | None = None,
    time_global_range: dict | None = None,
    time_idx: int = 0,
    time_field: str = "",
    broadcast_group: str = "",
) -> str:
    """Return the golden top-bar HTML + IIFE JS for one figure.

    Reproduces the May-2026 reference figure UI: a fixed 26px top bar with an
    inline field selector, play/pause button, time slider + value, and a
    bottom-left axis widget. Lock state is driven externally via postMessage
    (panel lock-all / dashboard), matching the reference figures.

    `time_data_b64` and `time_global_range` are per-field dicts
    (``{field: [b64_frame, ...]}`` and ``{field: [min, max]}``) so the field
    switcher animates the correct field while playing.
    """
    fig_id_safe = fig_id.replace("</", "").replace('"', "").replace("-", "_")

    fields = list(fields_to_embed or ([active_field] if active_field else []))
    has_fields = len(fields) > 1

    tdata = time_data_b64 if isinstance(time_data_b64, dict) else {}
    tglobal = time_global_range if isinstance(time_global_range, dict) else {}
    active_frames = tdata.get(active_field or time_field) or []
    has_time = bool(time_labels and len(time_labels) > 1 and len(active_frames) > 1)
    n_time = len(active_frames)

    # Nothing to render (e.g. plotly graph): emit no markup and no JS so we
    # never inject a vtk renderer-polling loop into a non-vtk page.
    if not has_fields and not has_time and not show_orientation:
        return ""

    # ── Top bar markup ───────────────────────────────────────────────────────
    topbar = ""
    if has_fields or has_time or show_lock_btn:
        inner = ""
        if has_fields:
            opts = "".join(
                f'<option value="{f}"{" selected" if f == active_field else ""}'
                ' style="background:#1c1c28;color:#ddd;">' + f + '</option>'
                for f in fields
            )
            inner += (
                '<label style="display:flex;align-items:center;gap:2px;flex-shrink:0;">'
                f'<select id="cs-field-sel-{fig_id_safe}" style="background:transparent;'
                'border:none;color:#ddd;font-family:system-ui,sans-serif;font-size:10px;'
                'cursor:pointer;outline:none;max-width:90px;padding:0 2px 0 0;'
                '-webkit-appearance:none;-moz-appearance:none;appearance:none;">'
                f'{opts}</select>'
                '<span style="color:#777;font-size:8px;flex-shrink:0;'
                'pointer-events:none;margin-left:-3px;">&#9662;</span></label>'
                '<span style="width:1px;height:14px;background:rgba(255,255,255,0.15);'
                'flex-shrink:0;display:inline-block;"></span>'
            )
        if has_time:
            init_label = time_labels[time_idx] if time_idx < len(time_labels) else str(time_idx)
            inner += (
                f'<button id="cs-play-{fig_id_safe}" title="Play / pause animation" '
                'style="background:none;border:none;cursor:pointer;color:#ccc;font-size:11px;'
                'flex-shrink:0;padding:0 1px;line-height:1;">&#x25B6;</button>'
                '<span style="color:#777;font-size:9px;flex-shrink:0;">t</span>'
                f'<input type="range" id="cs-time-slider-{fig_id_safe}" min="0" '
                f'max="{n_time - 1}" value="{time_idx}" style="flex:1;min-width:30px;'
                'max-width:110px;cursor:pointer;accent-color:#4a9eff;margin:0;">'
                f'<span id="cs-time-val-{fig_id_safe}" style="color:#aaa;font-size:9px;'
                'flex-shrink:0;white-space:nowrap;font-family:monospace;">'
                f'{init_label}</span>'
            )
        inner += (
            f'<span id="cs-field-badge-{fig_id_safe}" style="display:none;padding:1px 4px;'
            'border-radius:2px;font-size:9px;flex-shrink:0;"></span>'
        )
        if show_lock_btn:
            inner += (
                f'<span id="cs-lock-cluster-{fig_id_safe}" style="margin-left:auto;display:flex;'
                'align-items:center;gap:6px;flex-shrink:0;">'
                f'<span id="cs-cam-sync-{fig_id_safe}" title="The saved camera is used for static PDF screenshots." '
                'style="display:none;padding:1px 6px;border-radius:999px;font-size:9px;'
                'line-height:1.4;font-family:system-ui,sans-serif;"></span>'
                f'<button id="cs-lock-widget-{fig_id_safe}" title="Lock / unlock camera" '
                'style="background:none;border:none;cursor:pointer;'
                'color:#ccc;font-size:12px;flex-shrink:0;padding:0 2px;line-height:1;">'
                '&#x1F513;</button>'
                '</span>'
            )
        topbar = (
            f'<div id="cs-topbar-{fig_id_safe}" style="position:fixed;top:0;left:0;right:0;'
            'z-index:9999;display:flex;align-items:center;gap:5px;'
            'background:rgba(18,18,26,0.82);border-bottom:1px solid rgba(255,255,255,0.09);'
            f'padding:0 6px;height:26px;box-sizing:border-box;">{inner}</div>'
        )

    corner = ""
    if show_orientation:
        corner = (
            f'<div id="cs-corner-{fig_id_safe}" style="position:fixed;bottom:4px;left:4px;'
            'z-index:9999;display:flex;align-items:center;gap:6px;">'
            f'<svg id="cs-svg-axes-{fig_id_safe}" width="56" height="56" '
            'style="background:transparent;border:none;border-radius:0;display:block;'
            'cursor:pointer;overflow:visible;" '
            'title="Click axis tip: ortho view \u00b7 Click axis tail: opposite view"></svg>'
            f'<span id="cs-iso-flash-{fig_id_safe}" style="font-size:9px;color:#ffe033;'
            'font-family:monospace;min-width:60px;"></span></div>'
        )

    if show_lock_btn:
        html_block_lock = (
            f'<div id="cs-lock-shield-{fig_id_safe}" style="display:none;position:fixed;'
            'inset:0;z-index:9998;cursor:not-allowed;"></div>'
        )
    else:
        html_block_lock = ""
    html_block = topbar + corner + html_block_lock

    # ── Data header + golden IIFE body ───────────────────────────────────────
    fid = json.dumps(fig_id).replace("</", "<\\/")
    af = json.dumps(active_field or time_field).replace("</", "<\\/")
    fd = json.dumps(field_data_b64 or {}).replace("</", "<\\/")
    fr = json.dumps(field_ranges or {})
    td = json.dumps(tdata).replace("</", "<\\/")
    tl = json.dumps(time_labels or [])
    tgr = json.dumps(tglobal)
    header = (
        "  var FIG_ID=" + fid + ", _locked=false, _renderer=null, _isHovered=false, "
        "_cont=null, _meshActor=null, _controlsBound=false, _timeIdx=" + str(int(time_idx))
        + ", _timePlaying=false, _timeRaf=0, _timeLastTs=0, _pendingCam=null, "
        '_displayScalarName="__4dpaper_display__";\n'
        "  var ACTIVE_FIELD=" + af + ", FIELD_DATA=" + fd + ", FIELD_RANGES=" + fr
        + ", TIME_DATA=" + td + ", TIME_LABELS=" + tl + ", TIME_GLOBAL_RANGE=" + tgr
        + ", _decodedFieldData={}, _decodedTimeData={};\n"
    )

    js_body = _GOLDEN_TOPBAR_JS.replace("__FIGSAFE__", fig_id_safe)

    # BroadcastChannel-based peer sync (timeseries frames only).
    # When broadcast_group is set, each frame opens a named channel, broadcasts its
    # camera to all sibling frames, and listens for cameras from siblings.
    # BroadcastChannel messages are NOT received by the sender, so no loop occurs.
    if broadcast_group:
        bc_name = json.dumps("4dpaper-ts-" + broadcast_group)
        bc_init = (
            "  var _BC4TS=null;"
            "try{_BC4TS=new BroadcastChannel(" + bc_name + ");}catch(e){}\n"
            "  if(_BC4TS){_BC4TS.onmessage=function(ev){"
            "if(!ev.data||ev.data.type!==\"4dpaper-camera-apply\")return;"
            "if(_locked)return;"
            "var r=_getRenderer();if(!r){_pendingCam=ev.data.camera;return;}"
            "var cam=ev.data.camera,c=r.getActiveCamera();"
            "if(cam.position)c.setPosition(cam.position[0],cam.position[1],cam.position[2]);"
            "if(cam.focal_point)c.setFocalPoint(cam.focal_point[0],cam.focal_point[1],cam.focal_point[2]);"
            "if(cam.view_up)c.setViewUp(cam.view_up[0],cam.view_up[1],cam.view_up[2]);"
            "if(cam.parallel_scale!=null)c.setParallelScale(cam.parallel_scale);"
            "if(cam.parallel_projection!=null)c.setParallelProjection(!!cam.parallel_projection);"
            "r.resetCameraClippingRange();window.renderWindow.render();"
            "};}\n"
        )
        # Also make _postCam broadcast to the channel so siblings get notified directly.
        js_body = js_body.replace(
            'parent.postMessage({type:"4dpaper-camera",fig_id:FIG_ID,camera:d},"*");}',
            'parent.postMessage({type:"4dpaper-camera",fig_id:FIG_ID,camera:d},"*");'
            'if(_BC4TS)_BC4TS.postMessage({type:"4dpaper-camera-apply",camera:d});}',
        )
        header = bc_init + header
    # Lock widget wiring (relay.js handles 4dpaper-lock-query / 4dpaper-lock-toggle).
    # _setLocked / _locked / FIG_ID live in the IIFE body above this snippet.
    lock_js = ""
    if show_lock_btn:
        lock_js = (
            '\n  function _setCamSyncStatus(state){var _cs=document.getElementById("cs-cam-sync-' + fig_id_safe + '");'
            'if(!_cs)return;'
            'if(state==="saving"){_cs.style.display="inline-block";_cs.textContent="Saving camera";_cs.style.background="rgba(74,158,255,0.18)";_cs.style.color="#9ecbff";return;}'
            'if(state==="ok"){_cs.style.display="inline-block";_cs.textContent="Camera synced";_cs.style.background="rgba(76,175,80,0.18)";_cs.style.color="#9be7a1";setTimeout(function(){_cs.style.display="none";},1200);return;}'
            'if(state==="error"){_cs.style.display="inline-block";_cs.textContent="Camera save failed";_cs.style.background="rgba(244,67,54,0.18)";_cs.style.color="#ffb3ad";setTimeout(function(){_cs.style.display="none";},1800);return;}'
            '_cs.style.display="none";}'
            '\n  var _origSendCam=_sendCam;'
            '_sendCam=function(r){_setCamSyncStatus("saving");_origSendCam(r);};'
            '\n  window.addEventListener("message",function(e){'
            'if(!e.data)return;var d=e.data;'
            'if(d.type==="4dpaper-camera-ack"&&(d.fig_id===FIG_ID||d.fig_id==="*")){'
            '_setCamSyncStatus(d.status==="ok"?"ok":"error");}});'
            '\n  (function(){var _lw=document.getElementById("cs-lock-widget-' + fig_id_safe + '");'
            'if(_lw)_lw.addEventListener("click",function(){var nv=!_locked;_setLocked(nv);'
            'parent.postMessage({type:"4dpaper-lock-toggle",fig_id:FIG_ID,locked:nv},"*");});'
            'parent.postMessage({type:"4dpaper-lock-query",fig_id:FIG_ID},"*");})();'
        )
    js_block = "<script>\n(function(){\n" + header + js_body + lock_js + "\n})();\n</script>\n"
    return html_block + js_block

def _timeseries_sync_snippet(fig_id: str) -> str:
    """
    Add message listener for timeseries composite viewer field synchronization.

    Responds to:
    - 4dpaper-timeseries-field: change active field across all frames

    Note: Frame seeking and play state are NOT broadcast to individual frames.
    Each frame is a static visualization of a specific timestep; the composite
    viewer controls which frame is "current" in its own timeline display.
    """
    fig_id_safe = fig_id.replace("</", "").replace('"', "").replace("-", "_")
    return f"""<script>
window.addEventListener('message', function(e){{
    if(!e.data) return;
    var d = e.data;

    // Handle timeseries field change (propagate to all frames)
    if(d.type === '4dpaper-timeseries-field') {{
        var fieldSelect = document.getElementById('cs-field-sel-{fig_id_safe}');
        if(fieldSelect) {{
            fieldSelect.value = d.field;
            fieldSelect.dispatchEvent(new Event('change'));
        }}
    }}
}});
</script>"""

def _multi_actor_extension_snippet(
    overlay_field_names: list[str],
    overlay_time_data_b64: dict[str, list[str]],
    overlay_time_global_range: dict[str, list[float]],
    fig_id: str = "",
) -> str:
    """
    Return a <script> that animates overlay actors in sync with src1.

    Hooks into window['__4dp_onframe_<figsafe>'] which _GOLDEN_TOPBAR_JS calls
    from _setTimeFrame on every frame advance.  This avoids the IIFE scope
    problem: _setTimeFrame is local to the controls-strip IIFE and cannot be
    captured by a sibling script block.

    Actors are identified by insertion order: actor[0] = src1, actor[1] = src2, …
    """
    if not overlay_field_names:
        return ""
    fig_safe = fig_id.replace("-", "_").replace("</", "")
    td_json = json.dumps(overlay_time_data_b64)
    range_json = json.dumps(overlay_time_global_range)
    fields_json = json.dumps(overlay_field_names)
    hook_key = f"__4dp_onframe_{fig_safe}"
    return (
        "<script>\n(function(){\n"
        f"  var OV_TD={td_json};\n"
        f"  var OV_RANGE={range_json};\n"
        f"  var OV_FIELDS={fields_json};\n"
        "  var _ovDec={}; var _ovActs=null;\n"
        # Helper: decode base64 float32 array
        "  function _b64F32(b64){if(!b64)return null;"
        "var bin=atob(b64),len=bin.length,bytes=new Uint8Array(len);"
        "for(var i=0;i<len;i++)bytes[i]=bin.charCodeAt(i);"
        "return new Float32Array(bytes.buffer);}\n"
        # Helper: find the renderer (mirrors _getRenderer in the controls strip)
        "  function _getR(){var rw=window.renderWindow;if(!rw||!rw.getRenderers)return null;"
        "var rs=rw.getRenderers();"
        "for(var i=0;i<rs.length;i++){if(rs[i]&&rs[i].getActors&&rs[i].getActors().length>0)return rs[i];}"
        "return rs[0]||null;}\n"
        # Helper: return overlay actors (everything after actor[0])
        "  function _getOvActs(){\n"
        "    if(_ovActs)return _ovActs;\n"
        "    var r=_getR(); if(!r)return null;\n"
        "    var all=[].concat(r.getActors?r.getActors():[]).concat(r.getViewProps?r.getViewProps():[]);\n"
        "    _ovActs=all.filter(function(a){var m=a&&a.getMapper&&a.getMapper();"
        "var d=m&&m.getInputData&&m.getInputData();return!!(d&&d.getPointData&&d.getPointData());}).slice(1);\n"
        "    return _ovActs;\n  }\n"
        # Apply a scalar array to one actor
        "  function _applyOv(actor,arr,range,name){\n"
        "    if(!actor||!arr)return;\n"
        "    var m=actor.getMapper&&actor.getMapper(),"
        "inp=m&&m.getInputData&&m.getInputData(),"
        "pd=inp&&inp.getPointData&&inp.getPointData();\n"
        "    if(!pd)return;\n"
        "    var next=pd.getArrayByName?pd.getArrayByName(name):null;\n"
        "    if(next&&next.setData){next.setData(arr,1);}\n"
        "    else{var sc=pd.getScalars&&pd.getScalars();"
        "if(sc&&sc.setData){sc.setData(arr,1);next=sc;}else return;}\n"
        "    if(next.setName)next.setName(name);\n"
        "    if(pd.addArray)pd.addArray(next);\n"
        "    if(pd.setActiveScalars)pd.setActiveScalars(name);\n"
        "    if(pd.setScalars)pd.setScalars(next);\n"
        "    if(next.modified)next.modified();\n"
        "    if(pd.modified)pd.modified();\n"
        "    if(inp.modified)inp.modified();\n"
        "    if(m.setColorByArrayName)m.setColorByArrayName(name);\n"
        "    if(m.setScalarModeToUsePointData)m.setScalarModeToUsePointData();\n"
        "    if(m.setScalarVisibility)m.setScalarVisibility(true);\n"
        "    if(range&&m.setScalarRange)m.setScalarRange(range[0],range[1]);\n"
        "    if(m.modified)m.modified();\n"
        "    if(actor.modified)actor.modified();\n"
        "    if(window.renderWindow)window.renderWindow.render();\n  }\n"
        # Update all overlays at frame idx
        "  function _updateOv(idx){\n"
        "    var acts=_getOvActs(); if(!acts||!acts.length)return;\n"
        "    for(var i=0;i<OV_FIELDS.length;i++){\n"
        "      var f=OV_FIELDS[i],a=acts[i];\n"
        "      if(!a||!OV_TD[f])continue;\n"
        "      if(!_ovDec[f])_ovDec[f]=OV_TD[f].map(_b64F32);\n"
        "      var fr=_ovDec[f];\n"
        "      if(fr&&idx<fr.length&&fr[idx])_applyOv(a,fr[idx],OV_RANGE[f]||[0,1],f);\n"
        "    }\n  }\n"
        # Register the hook that _GOLDEN_TOPBAR_JS calls from _setTimeFrame
        f"  window['{hook_key}']=_updateOv;\n"
        "})();\n</script>"
    )

def _build_multi_image_sources(fig: dict, resolve_src_path) -> list[dict]:
    """Extract ordered source list from a parsed 4d-multi-image shortcode dict."""
    sources = []
    i = 1
    while f"src{i}" in fig:
        # colorbar: src1 shows by default; overlays (src2+) hide by default
        cb_default = "true" if i == 1 else "false"
        cb_val = fig.get(f"colorbar{i}", cb_default).strip().lower()
        sources.append({
            "src": resolve_src_path(fig[f"src{i}"]),
            "field": fig.get(f"field{i}", ""),
            "fields": fig.get(f"fields{i}", ""),
            "cmap": fig.get(f"cmap{i}", ""),
            "decimate": fig.get(f"decimate{i}", "auto"),
            "line_width": fig.get(f"line_width{i}", "2.0"),
            "colorbar": cb_val not in ("false", "0", "no", "off"),
            "opacity": float(fig.get(f"opacity{i}", "1.0")),
        })
        i += 1
    return sources

def _plotly_camera_sync_snippet(fig_id: str) -> str:
    """Return a small camera relay snippet for Plotly 3D graphs."""
    fid = json.dumps(fig_id).replace("</", "<\\/")
    return (
        "<script>\n(function(){\n"
        f"  var FIG_ID={fid},_graph=null,_applying=false;\n"
        "  function _sceneKeys(src){var out=[];if(!src)return out;for(var k in src){if(/^scene\\d*$/.test(k))out.push(k);}return out;}\n"
        "  function _graphDiv(){if(_graph&&_graph.on)return _graph;_graph=document.querySelector('.plotly-graph-div');return _graph;}\n"
        "  function _num(v,d){var n=Number(v);return Number.isFinite(n)?n:d;}\n"
        "  function _currentCamera(gd){\n"
        "    if(!gd)return null;\n"
        "    var layout=gd.layout||{},full=gd._fullLayout||{},keys=_sceneKeys(layout);\n"
        "    if(!keys.length)keys=_sceneKeys(full);\n"
        "    if(!keys.length&&full.scene)keys=['scene'];\n"
        "    for(var i=0;i<keys.length;i++){\n"
        "      var key=keys[i],scene=(layout&&layout[key])||(full&&full[key]);\n"
        "      if(scene&&scene.camera&&scene.camera.eye)return scene.camera;\n"
        "    }\n"
        "    return null;\n"
        "  }\n"
        "  function _payload(cam){\n"
        "    if(!cam||!cam.eye)return null;\n"
        "    var eye=cam.eye||{},center=cam.center||{},up=cam.up||{};\n"
        "    return {\n"
        "      position:[_num(eye.x,0),_num(eye.y,0),_num(eye.z,0)],\n"
        "      focal_point:[_num(center.x,0),_num(center.y,0),_num(center.z,0)],\n"
        "      view_up:[_num(up.x,0),_num(up.y,1),_num(up.z,0)],\n"
        "      parallel_projection:cam.projection&&cam.projection.type==='orthographic'?1:0\n"
        "    };\n"
        "  }\n"
        "  function _plotlyCamera(saved){\n"
        "    if(!saved||!saved.position||!saved.view_up)return null;\n"
        "    var center=saved.focal_point||[0,0,0];\n"
        "    return {\n"
        "      eye:{x:_num(saved.position[0],0),y:_num(saved.position[1],0),z:_num(saved.position[2],1)},\n"
        "      center:{x:_num(center[0],0),y:_num(center[1],0),z:_num(center[2],0)},\n"
        "      up:{x:_num(saved.view_up[0],0),y:_num(saved.view_up[1],1),z:_num(saved.view_up[2],0)},\n"
        "      projection:{type:saved.parallel_projection===1?'orthographic':'perspective'}\n"
        "    };\n"
        "  }\n"
        "  function _sendCurrent(){\n"
        "    var gd=_graphDiv(),cam=_currentCamera(gd),payload=_payload(cam);\n"
        "    if(payload)parent.postMessage({type:'4dpaper-camera',fig_id:FIG_ID,camera:payload},'*');\n"
        "  }\n"
        "  function _bind(){\n"
        "    var gd=_graphDiv();\n"
        "    if(!gd||!gd.on||gd.__4dpCamBound)return !!gd;\n"
        "    gd.__4dpCamBound=true;\n"
        "    gd.on('plotly_relayout',function(){if(_applying)return;setTimeout(_sendCurrent,0);});\n"
        "    return true;\n"
        "  }\n"
        "  (function _wait(){if(_bind())return;setTimeout(_wait,120);})();\n"
        "  window.addEventListener('message',function(e){\n"
        "    if(!e.data||e.data.type!=='4dpaper-camera-apply')return;\n"
        "    var gd=_graphDiv(),cam=_plotlyCamera(e.data.camera);\n"
        "    if(!gd||!cam||!window.Plotly||!Plotly.relayout)return;\n"
        "    var layout=gd.layout||{},full=gd._fullLayout||{},keys=_sceneKeys(layout);\n"
        "    if(!keys.length)keys=_sceneKeys(full);\n"
        "    if(!keys.length&&full.scene)keys=['scene'];\n"
        "    if(!keys.length)return;\n"
        "    var updates={};\n"
        "    for(var i=0;i<keys.length;i++)updates[keys[i]+'.camera']=cam;\n"
        "    _applying=true;\n"
        "    Promise.resolve(Plotly.relayout(gd,updates)).finally(function(){_applying=false;});\n"
        "  });\n"
        "})();\n</script>"
    )

def _build_video_html_fragment(b64: str, fig_id: str) -> str:
    """
    Build a self-contained HTML document for a video figure.

    The "Camera View" button is injected at the paper level (analysis_report.html)
    by shortcodes.lua, so it is never inside this iframe and cannot be blocked by
    the video element's compositor layer.

    Parameters
    ----------
    b64: base64-encoded MP4 bytes (for the data URI)
    fig_id: figure identifier string
    """
    return (
        f'<!DOCTYPE html>\n'
        f'<html style="height:100%;margin:0;padding:0;">\n'
        f'<head><meta charset="utf-8">'
        f'<style>html,body{{margin:0;padding:0;overflow:hidden;height:100%;width:100%;}}</style>'
        f'</head>\n'
        f'<body>\n'
        f'<div style="position:relative;width:100%;height:100%;">\n'
        f'  <video src="data:video/mp4;base64,{b64}"\n'
        f'    controls loop autoplay muted playsinline\n'
        f'    style="width:100%;height:100%;border-radius:4px;display:block;object-fit:contain;">\n'
        f'  </video>\n'
        f'</div>\n'
        f'</body>\n'
        f'</html>'
    )
