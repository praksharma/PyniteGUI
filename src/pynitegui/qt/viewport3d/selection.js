import * as THREE from 'three';

function crosses(a,b,rect){
  let low=0,high=1;
  const dx=b.x-a.x,dy=b.y-a.y;
  for(const [p,q] of [[-dx,a.x-rect.min.x],[dx,rect.max.x-a.x],[-dy,a.y-rect.min.y],[dy,rect.max.y-a.y]]){
    if(p===0){if(q<0)return false;continue;}
    const t=q/p;
    if(p<0)low=Math.max(low,t);else high=Math.min(high,t);
    if(low>high)return false;
  }
  return true;
}

export function rectangleSelection(data,camera,width,height,from,to){
  const rect=new THREE.Box2(new THREE.Vector2(Math.min(from[0],to[0]),Math.min(from[1],to[1])),
    new THREE.Vector2(Math.max(from[0],to[0]),Math.max(from[1],to[1])));
  const crossing=to[0]<from[0],points=new Map(),selected=[];
  for(const node of data.nodes){
    const p=new THREE.Vector3(...node.position).project(camera);
    if(p.z < -1 || p.z > 1)continue;
    const screen=new THREE.Vector2((p.x+1)*width/2,(1-p.y)*height/2);
    points.set(node.name,screen);
    if(rect.containsPoint(screen))selected.push(['nodes',node.name]);
  }
  for(const member of data.members){
    const a=points.get(member.start),b=points.get(member.end);
    if(a&&b&&(crossing?crosses(a,b,rect):rect.containsPoint(a)&&rect.containsPoint(b)))selected.push(['members',member.name]);
  }
  return selected;
}

export function attachBoxSelection(canvas,camera,controls,getData,stopMotion,selectMany,selectAt){
  const overlay=document.createElement('div');overlay.id='selection-box';overlay.hidden=true;document.body.appendChild(overlay);
  let drag=null;
  function cancel(){
    if(!drag)return;
    const pointer=drag.pointer;
    drag=null;overlay.hidden=true;controls.enabled=true;
    if(canvas.hasPointerCapture(pointer))canvas.releasePointerCapture(pointer);
  }
  canvas.addEventListener('pointerdown',event=>{
    const data=getData();
    if(event.button!==0||data.mode!=='select'||!(data.boxSelect||event.shiftKey))return;
    event.stopImmediatePropagation();stopMotion();controls.enabled=false;
    drag={from:[event.clientX,event.clientY],pointer:event.pointerId,extend:event.ctrlKey||event.metaKey};
    canvas.setPointerCapture(event.pointerId);
  },true);
  canvas.addEventListener('pointermove',event=>{
    if(!drag)return;
    event.stopImmediatePropagation();overlay.hidden=false;
    const [x,y]=drag.from;
    Object.assign(overlay.style,{left:Math.min(x,event.clientX)+'px',top:Math.min(y,event.clientY)+'px',
      width:Math.abs(x-event.clientX)+'px',height:Math.abs(y-event.clientY)+'px',
      borderStyle:event.clientX<x?'dashed':'solid',borderColor:getData().colors.accent});
  },true);
  canvas.addEventListener('pointerup',event=>{
    if(!drag||event.pointerId!==drag.pointer)return;
    event.stopImmediatePropagation();
    const {from,extend}=drag,to=[event.clientX,event.clientY];
    cancel();
    if(Math.hypot(to[0]-from[0],to[1]-from[1])<5){selectAt(event);return;}
    selectMany(rectangleSelection(getData(),camera,canvas.clientWidth,canvas.clientHeight,from,to),extend);
  },true);
  canvas.addEventListener('pointercancel',cancel);
  canvas.addEventListener('lostpointercapture',cancel);
  addEventListener('keydown',event=>{if(event.key==='Escape')cancel();});
  addEventListener('resize',cancel);
  return {cancel};
}
