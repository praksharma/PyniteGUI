import * as THREE from 'three';

export function planeAxis(plane){return {XY:2,XZ:1,YZ:0}[plane];}

export function snappedMove(ray,plane,start,grab,grid){
  const axis=planeAxis(plane),normal=new THREE.Vector3().setComponent(axis,1);
  if(Math.abs(ray.direction.dot(normal))<1e-6)return null;
  const point=ray.intersectPlane(new THREE.Plane(normal,-start[axis]),new THREE.Vector3());
  if(!point)return null;
  point.sub(grab).add(new THREE.Vector3(...start));
  for(let i=0;i<3;i++)point.setComponent(i,i===axis?start[i]:Math.round(point.getComponent(i)/grid)*grid);
  return point.toArray();
}

export function attachNodeDrag(canvas,camera,controls,getData,pickNode,ray,stopMotion,preview,restore,commit,unavailable){
  let drag=null;
  function finish(){
    const previous=drag;
    if(!previous)return null;
    drag=null;
    controls.enabled=true;
    if(previous&&canvas.hasPointerCapture(previous.pointer))canvas.releasePointerCapture(previous.pointer);
    return previous;
  }
  function cancel(revert=true){
    const previous=finish();
    if(previous&&revert&&previous.moved)restore(previous.snapshot);
  }
  canvas.addEventListener('pointerdown',event=>{
    if(drag&&event.button===2){event.stopImmediatePropagation();event.preventDefault();cancel();return;}
    const data=getData();
    if(event.button!==0||data.mode!=='select'||!data.moveNodes||data.boxSelect||event.shiftKey||event.ctrlKey||event.metaKey)return;
    const node=pickNode(event);
    if(!node)return;
    event.stopImmediatePropagation();event.preventDefault();stopMotion();
    const axis=planeAxis(data.plane),normal=new THREE.Vector3().setComponent(axis,1),pointerRay=ray(event);
    const grab=Math.abs(camera.getWorldDirection(new THREE.Vector3()).dot(normal))<1e-3||Math.abs(pointerRay.direction.dot(normal))<1e-6?null:
      pointerRay.intersectPlane(new THREE.Plane(normal,-node.position[axis]),new THREE.Vector3());
    if(!grab){unavailable();return;}
    controls.enabled=false;
    drag={node:node.name,start:[...node.position],target:[...node.position],plane:data.plane,grab,
      snapshot:data,pointer:event.pointerId,from:[event.clientX,event.clientY],moved:false};
    canvas.setPointerCapture(event.pointerId);
  },true);
  canvas.addEventListener('pointermove',event=>{
    if(!drag||event.pointerId!==drag.pointer)return;
    event.stopImmediatePropagation();
    if(Math.hypot(event.clientX-drag.from[0],event.clientY-drag.from[1])<5&&!drag.moved)return;
    const target=snappedMove(ray(event),drag.plane,drag.start,drag.grab,drag.snapshot.grid);
    if(!target)return;
    drag.target=target;drag.moved=true;preview(drag.node,target,drag.snapshot);
  },true);
  canvas.addEventListener('pointerup',event=>{
    if(!drag||event.pointerId!==drag.pointer)return;
    event.stopImmediatePropagation();event.preventDefault();
    const previous=finish();
    if(previous.moved)restore(previous.snapshot);
    if(previous.moved&&previous.target.some((value,i)=>Math.abs(value-previous.start[i])>1e-8)){
      commit({node:previous.node,start:previous.start,target:previous.target,plane:previous.plane,revision:previous.snapshot.revision});
    }else if(!previous.moved){
      // Clicks still select; only the completed drag changes engineering data.
      canvas.dispatchEvent(new CustomEvent('nodeDragClicked',{detail:previous.node}));
    }
  },true);
  canvas.addEventListener('pointercancel',()=>cancel());
  canvas.addEventListener('lostpointercapture',()=>cancel());
  addEventListener('keydown',event=>{if(event.key==='Escape')cancel();});
  addEventListener('blur',()=>cancel());
  addEventListener('resize',()=>cancel());
  return {cancel,active:()=>drag!==null};
}
