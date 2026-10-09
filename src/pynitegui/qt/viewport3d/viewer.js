import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {OrientationGizmo} from './gizmo.js';
import {diagramPoints, drawDiagram, legendLines} from './diagrams.js';
import {attachBoxSelection} from './selection.js';
import {drawSupports, SupportTooltip} from './supports.js';
import {attachNodeDrag,planeAxis} from './node_drag.js';
import {drawFrame,hitIdentity,recolorFrame} from './frame_meshes.js';
import {LabelTextures} from './label_textures.js';

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100000);
const renderer = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
document.body.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
renderer.autoClear = false;
renderer.info.autoReset = false;
function notifyOrientation(index){window.pyniteBridge?.orientation(index);window.dispatchEvent(new CustomEvent('viewOriented',{detail:index}));}
const gizmo = new OrientationGizmo(camera,controls,renderer,orient,notifyOrientation,stopMotion);
controls.addEventListener('start',()=>notifyOrientation(7));
controls.enableDamping = true;
controls.screenSpacePanning = true;
scene.add(new THREE.HemisphereLight(0xffffff, 0x708080, 2));
const light = new THREE.DirectionalLight(0xffffff, 2);
light.position.set(1, 2, 3); scene.add(light);
let group = new THREE.Group(), data = {nodes:[],members:[],loads:[],grid:12,mode:'select'}, picks=[], supports=[], start=null, preview=null, span=240, rendering=true;
const supportTooltip=new SupportTooltip();
controls.addEventListener('start',()=>supportTooltip.hide());
controls.addEventListener('change',()=>supportTooltip.hide());
scene.add(group);
const labelTextures=new LabelTextures();
let sceneSignature=null,rebuilds=0,incrementalUpdates=0;
const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
const vector = a => new THREE.Vector3(...a);
const axisColors = [0xd65058,0x21955c,0x3786bd];
const nodeDrag=attachNodeDrag(renderer.domElement,camera,controls,()=>data,event=>{
  ray(event);const hit=raycaster.intersectObjects(picks).find(hit=>hit.object.userData.nodeInstances);
  return hit?data.nodes.find(node=>node.name===hitIdentity(hit)[1]):null;
},event=>{ray(event);return raycaster.ray;},()=>{supportTooltip.hide();gizmo.cancel();stopMotion();},
  (name,position,snapshot)=>{
    update({...snapshot,nodes:snapshot.nodes.map(node=>node.name===name?{...node,position}:node),
      members:snapshot.members.map(member=>({...member,points:undefined,displacements:undefined,diagramValues:undefined})),
      selection:[['nodes',name]],offset:position[planeAxis(snapshot.plane)],deformed:false,diagram:null,loads:[],localAxes:false},true);
    window.pyniteBridge?.coordinates(...position);
  },snapshot=>update(snapshot,true),request=>{
    window.pyniteBridge?.move_node(JSON.stringify(request));
    window.dispatchEvent(new CustomEvent('nodeMoved',{detail:request}));
  },()=>{window.pyniteBridge?.move_unavailable();window.dispatchEvent(new CustomEvent('nodeMoveUnavailable'));});
const boxSelection=attachBoxSelection(renderer.domElement,camera,controls,()=>data,()=>{supportTooltip.hide();gizmo.cancel();stopMotion();},
  (selections,extend)=>{window.pyniteBridge?.select_many(JSON.stringify(selections),extend);window.dispatchEvent(new CustomEvent('modelBoxSelected',{detail:{selections,extend}}));},selectAt);
const legend=document.createElement('div');legend.id='result-legend';document.body.appendChild(legend);
function line(points, color, target=group) {
  const obj = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color}));
  target.add(obj); return obj;
}
function label(text, position, color, size=span*.035, force=false) {
  if (!data.labels&&!force) return;
  const entry=labelTextures.acquire(text,color);
  const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:entry.texture,depthTest:false}));
  sprite.position.copy(position); sprite.scale.set(size*entry.width/36,size,1);
  sprite.userData.labelTexture=entry;
  sprite.userData.labelRatio=entry.width/36;group.add(sprite);
}
function dispose() {
  const geometries=new Set(),materials=new Set(),textures=new Set();
  group.traverse(obj=>{
    if(obj.userData.labelTexture)labelTextures.release(obj.userData.labelTexture);
    if(obj.isInstancedMesh)obj.dispose();
    if(obj.geometry)geometries.add(obj.geometry);
    for(const material of (Array.isArray(obj.material)?obj.material:obj.material?[obj.material]:[])){
      materials.add(material);if(material.map&&!obj.userData.labelTexture)textures.add(material.map);
    }
  });
  textures.forEach(texture=>texture.dispose());materials.forEach(material=>material.dispose());geometries.forEach(geometry=>geometry.dispose());
  scene.remove(group); group=new THREE.Group();scene.add(group);picks=[];preview=null;
}
function grid() {
  const plane=data.plane||'XY', offset=data.offset||0, step=Math.max(data.grid,span/70), extent=Math.ceil(span*1.3/step)*step;
  const center=controls.target.clone();
  const point=(u,v)=>plane==='XY'?new THREE.Vector3(u,v,offset):plane==='XZ'?new THREE.Vector3(u,offset,v):new THREE.Vector3(offset,u,v);
  const u=plane==='YZ'?center.y:center.x, v=plane==='XY'?center.y:center.z;
  const cu=Math.round(u/step)*step, cv=Math.round(v/step)*step;
  const points=[];
  for(let value=-extent;value<=extent+.1;value+=step)points.push(point(cu+value,cv-extent),point(cu+value,cv+extent),
    point(cu-extent,cv+value),point(cu+extent,cv+value));
  group.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:data.colors.grid})));
  const origin=new THREE.Vector3(0,0,0);
  ['X','Y','Z'].forEach((text,i)=>{const dir=new THREE.Vector3().setComponent(i,1);group.add(new THREE.ArrowHelper(dir,origin,span*.16,axisColors[i],span*.025,span*.012));label(text,dir.multiplyScalar(span*.18),`#${axisColors[i].toString(16)}`);});
}
function loadArrow(position,dir,magnitude,length,identity) {
  if(!magnitude)return;
  const direction=dir.clone().multiplyScalar(Math.sign(magnitude));
  const arrow=new THREE.ArrowHelper(direction,position.clone().addScaledVector(direction,-length),length,data.colors.load,span*.018,span*.009);
  arrow.traverse(obj=>{obj.userData.identity=identity;if(obj.isLine||obj.isMesh)picks.push(obj);});group.add(arrow);
}
function moment(position,axis,value,identity) {
  if(!value)return;
  const normal=axis.clone().normalize().multiplyScalar(Math.sign(value));
  const seed=Math.abs(normal.y)<.8?new THREE.Vector3(0,1,0):new THREE.Vector3(1,0,0);
  const u=new THREE.Vector3().crossVectors(normal,seed).normalize(),v=new THREE.Vector3().crossVectors(normal,u),r=span*.038;
  const points=Array.from({length:35},(_,i)=>position.clone().addScaledVector(u,r*Math.cos(i*5/34)).addScaledVector(v,r*Math.sin(i*5/34)));
  const arc=line(points,data.colors.load);arc.userData.identity=identity;picks.push(arc);
  const tangent=u.clone().multiplyScalar(-Math.sin(5)).addScaledVector(v,Math.cos(5));
  group.add(new THREE.ArrowHelper(tangent,points.at(-1),span*.014,data.colors.load,span*.014,span*.008));
}
function update(payload,dragPreview=false) {
  if(!dragPreview)nodeDrag.cancel(false);
  boxSelection.cancel();
  supportTooltip.hide();
  // Selection and interaction tools do not alter support/load/result geometry.
  // Compare the complete remaining payload so model, units, theme, work-plane,
  // visibility and analysis changes always rebuild the affected scene.
  const {selection,mode,boxSelect,moveNodes,...appearance}=payload;
  const signature=JSON.stringify(appearance);
  const incremental=!dragPreview&&!start&&!data.localAxes&&!payload.localAxes&&signature===sceneSignature;
  if(incremental){
    data=payload;recolorFrame(data,group);interaction();incrementalUpdates++;return;
  }
  supports=[];sceneSignature=signature;rebuilds++;
  data=payload;const c=data.colors;scene.background=new THREE.Color(c.canvas);
  legend.replaceChildren(...legendLines(data.diagram).map(text=>{const row=document.createElement('div');row.textContent=text;return row;}));
  legend.hidden=!data.diagram;legend.style.color=c.text||c.label;legend.style.background=c.canvas;
  const positions=data.nodes.map(n=>vector(n.position)),box=new THREE.Box3().setFromPoints(positions);
  span=Math.max(box.isEmpty()?240:box.getSize(new THREE.Vector3()).length(),data.grid*8,1);
  const r=span*.004;raycaster.params.Line.threshold=span*.012;
  dispose();if(!data.labels)labelTextures.clearUnused();grid();
  const nodes=new Map(data.nodes.map(n=>[n.name,n])), selected=(kind,name)=>data.selection.some(s=>s[0]===kind&&s[1]===name);
  drawFrame(data,r,group,picks);
  for(const member of data.members) {
    const a=vector(nodes.get(member.start).position),b=vector(nodes.get(member.end).position);
    label(member.name+(member.kind==='truss'?' [truss]':''),a.clone().lerp(b,.5).add(new THREE.Vector3(0,span*.023,0)),c.label);
    if(data.deformed&&member.points)line(member.points.map((p,i)=>vector(p).addScaledVector(vector(member.displacements[i]),data.factor)),c.load);
    drawDiagram(member,data.diagram,group,line,label,c);
    if(data.localAxes&&selected('members',member.name))member.axes.forEach((axis,i)=>{const origin=a.clone().lerp(b,.5);group.add(new THREE.ArrowHelper(vector(axis),origin,span*.12,axisColors[i],span*.02,span*.01));label(['x','y','z'][i],origin.addScaledVector(vector(axis),span*.14),c.label);});
  }
  for(const node of data.nodes) {
    const p=vector(node.position);label(node.name,p.clone().add(new THREE.Vector3(span*.02,span*.025,0)),c.label);
    if(data.supports!==false)supports.push(...drawSupports(node,span,c,group,picks));
  }
  for(const load of data.loads) {
    let a,b;
    if(nodes.has(load.target)){a=b=vector(nodes.get(load.target).position);}
    else{const member=data.members.find(m=>m.name===load.target);a=vector(nodes.get(member.start).position);b=vector(nodes.get(member.end).position);}
    const dir=vector(load.vector),identity=['loads',load.name], maximum=Math.max(Math.abs(load.magnitude),Math.abs(load.endMagnitude),1e-30);
    if(load.kind==='distributed'){
      for(let i=0;i<9;i++){const t=i/8,p=a.clone().lerp(b,load.position+t*(load.endPosition-load.position));const value=load.magnitude+t*(load.endMagnitude-load.magnitude);loadArrow(p,dir,value,span*.085*Math.abs(value)/maximum,identity);}
    }else if(load.moment)moment(a.clone().lerp(b,load.position),dir,load.magnitude,identity);
    else loadArrow(a.clone().lerp(b,load.position),dir,load.magnitude,span*.085,identity);
    label(load.label,a.clone().lerp(b,load.position).addScaledVector(dir,-Math.sign(load.magnitude||load.endMagnitude)*span*.12),c.load,span*.028);
  }
  interaction();
  if(start)preview=line([vector(start),vector(start)],c.accent);
}
function interaction(){
  controls.mouseButtons.LEFT=data.mode==='pan'?THREE.MOUSE.PAN:THREE.MOUSE.ROTATE;
  controls.enableRotate=data.mode!=='draw';renderer.domElement.style.cursor=data.mode==='draw'||(data.mode==='select'&&data.boxSelect)?'crosshair':data.mode==='select'&&data.moveNodes?'move':'default';
}
function fit() {
  nodeDrag.cancel();
  resize();
  supportTooltip.hide();
  stopMotion();
  const points=data.nodes.map(n=>vector(n.position));
  for(const symbol of supports)for(const sign of [-1,1])points.push(symbol.center.clone().addScalar(sign*span*.02));
  if(data.deformed)for(const m of data.members)if(m.points)points.push(...m.points.map((p,i)=>vector(p).addScaledVector(vector(m.displacements[i]),data.factor)));
  for(const member of data.members)points.push(...diagramPoints(member,data.diagram));
  const box=new THREE.Box3().setFromPoints(points),center=box.isEmpty()?new THREE.Vector3():box.getCenter(new THREE.Vector3());
  const radius=Math.max(box.isEmpty()?120:box.getSize(new THREE.Vector3()).length()*.65,data.grid*5,1);
  const distance=radius/Math.sin(THREE.MathUtils.degToRad(camera.fov/2))/Math.min(1,camera.aspect);
  const direction=camera.position.clone().sub(controls.target).normalize();if(direction.length()<.1)direction.set(1,.7,1).normalize();
  controls.target.copy(center);camera.position.copy(center).addScaledVector(direction,distance);camera.near=Math.max(distance/10000,.001);camera.far=distance*100;camera.updateProjectionMatrix();controls.update();
}
function orient(index) {
  if(index<0||index>6)return;
  nodeDrag.cancel();
  gizmo.cancel();
  stopMotion();
  const direction=[new THREE.Vector3(1,.7,1),new THREE.Vector3(0,0,1),new THREE.Vector3(0,1,0),new THREE.Vector3(1,0,0),new THREE.Vector3(0,0,-1),new THREE.Vector3(0,-1,0),new THREE.Vector3(-1,0,0)][index];
  camera.up.set(0,index===2||index===5?0:1,index===2?-1:index===5?1:0);
  camera.position.copy(controls.target).add(direction);fit();notifyOrientation(index);
}
function stopMotion(){const damping=controls.enableDamping;controls.enableDamping=false;controls.update();controls.enableDamping=damping;}
function ray(event) {
  const rect=renderer.domElement.getBoundingClientRect();pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(pointer,camera);
}
function workPoint(event) {
  ray(event);
  const hits=raycaster.intersectObjects(picks).filter(h=>hitIdentity(h)?.[0]==='nodes');
  if(hits.length)return data.nodes.find(n=>n.name===hitIdentity(hits[0])[1]).position;
  const axis=(data.plane||'XY')==='XY'?2:data.plane==='XZ'?1:0;
  const normal=new THREE.Vector3().setComponent(axis,1),p=new THREE.Vector3();
  if(!raycaster.ray.intersectPlane(new THREE.Plane(normal,-(data.offset||0)),p))return null;
  [0,1,2].filter(i=>i!==axis).forEach(i=>p.setComponent(i,Math.round(p.getComponent(i)/data.grid)*data.grid));return p.toArray();
}
let down=null;
function selectAt(event){
  ray(event);const hit=raycaster.intersectObjects(picks)[0],identity=hitIdentity(hit)||['',''];
  window.pyniteBridge?.select(...identity,event.ctrlKey||event.metaKey||event.shiftKey);window.dispatchEvent(new CustomEvent('modelSelected',{detail:identity}));
}
renderer.domElement.addEventListener('nodeDragClicked',event=>{
  const identity=['nodes',event.detail];window.pyniteBridge?.select(...identity,false);
  window.dispatchEvent(new CustomEvent('modelSelected',{detail:identity}));
});
renderer.domElement.addEventListener('pointerdown',event=>{if(event.button===0)down=[event.clientX,event.clientY];});
renderer.domElement.addEventListener('pointerup',event=>{
  if(event.button!==0||!down||Math.hypot(event.clientX-down[0],event.clientY-down[1])>5)return;down=null;
  if(data.mode==='draw'){
    const point=workPoint(event);if(!point)return;
    if(start){if(vector(start).distanceTo(vector(point))<1e-8)return;window.pyniteBridge?.draw(JSON.stringify([start,point]));window.dispatchEvent(new CustomEvent('memberDrawn',{detail:[start,point]}));cancel();}
    else{start=point;preview=line([vector(point),vector(point)],data.colors.accent);}
  }else if(data.mode==='select'){
    selectAt(event);
  }
});
renderer.domElement.addEventListener('pointermove',event=>{
  supportTooltip.hide();
  ray(event);
  if(!event.buttons&&data.mode!=='draw'){
    const hit=raycaster.intersectObjects(picks)[0],identity=hitIdentity(hit);
    if(identity?.[0]==='nodes'){
      const node=data.nodes.find(node=>node.name===identity[1]);
      if(node)supportTooltip.show(node,hit.object.userData.supportDof,event,data.colors);
    }
  }
  const point=workPoint(event);if(!point)return;
  window.pyniteBridge?.coordinates(...point);
  if(preview&&start){preview.geometry.dispose();preview.geometry=new THREE.BufferGeometry().setFromPoints([vector(start),vector(point)]);}
});
renderer.domElement.addEventListener('pointerleave',()=>supportTooltip.hide());
renderer.domElement.addEventListener('pointerdown',()=>supportTooltip.hide(),true);
renderer.domElement.addEventListener('webglcontextlost',()=>{nodeDrag.cancel(false);supportTooltip.hide();rendering=false;dispose();labelTextures.clearUnused();sceneSignature=null;window.pyniteReportFailure('The graphics context was lost. Restart with software rendering if this persists.');});
window.addEventListener('pagehide',event=>{if(!event.persisted){rendering=false;dispose();labelTextures.clearUnused();}});
function cancel(){nodeDrag.cancel();supportTooltip.hide();boxSelection.cancel();down=null;start=null;if(preview){group.remove(preview);preview.geometry.dispose();preview.material.dispose();preview=null;}}
addEventListener('keydown',event=>{if(event.key==='Escape')cancel();});
function resize(){supportTooltip.hide();camera.aspect=innerWidth/Math.max(innerHeight,1);camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);}
addEventListener('resize',resize);resize();camera.position.set(500,350,500);controls.update();
function placeLabels(){
  const occupied=[],factor=2*Math.tan(THREE.MathUtils.degToRad(camera.fov/2))/innerHeight;
  for(const sprite of group.children.filter(obj=>obj.isSprite)){
    const view=sprite.position.clone().applyMatrix4(camera.matrixWorldInverse),scale=Math.max(0,-view.z)*factor*18;
    sprite.scale.set(scale*sprite.userData.labelRatio,scale,1);
    const screen=sprite.position.clone().project(camera),x=(screen.x+1)*innerWidth/2,y=(1-screen.y)*innerHeight/2;
    const width=18*sprite.userData.labelRatio,rect=[x-width/2-3,y-12,x+width/2+3,y+12];
    sprite.visible=view.z<0&&rect[0]>4&&rect[1]>4&&rect[2]<innerWidth-4&&rect[3]<innerHeight-4&&!occupied.some(r=>rect[0]<r[2]&&rect[2]>r[0]&&rect[1]<r[3]&&rect[3]>r[1]);
    if(sprite.visible)occupied.push(rect);
  }
}
let lastTime=performance.now();
function renderFrame(){placeLabels();renderer.info.reset();renderer.clear();renderer.render(scene,camera);gizmo.render();}
function animate(){if(!rendering)return;requestAnimationFrame(animate);const now=performance.now(),delta=Math.min((now-lastTime)/1000,.1);lastTime=now;if(!gizmo.update(delta))controls.update();renderFrame();}animate();
function exportImage(){
  if(!rendering)return '';
  renderFrame();
  const source=renderer.domElement,canvas=document.createElement('canvas');canvas.width=source.width;canvas.height=source.height;
  const context=canvas.getContext('2d');context.drawImage(source,0,0);
  const rows=legendLines(data.diagram),ratio=renderer.getPixelRatio();
  if(rows.length){
    context.scale(ratio,ratio);context.font='12px sans-serif';
    const width=Math.min(innerWidth-24,Math.max(...rows.map(text=>context.measureText(text).width))+20);
    context.fillStyle=data.colors.canvas;context.fillRect(12,12,width,rows.length*18+16);
    context.fillStyle=data.colors.text||data.colors.label;
    rows.forEach((text,i)=>context.fillText(text,22,35+i*18,width-20));
  }
  return canvas.toDataURL('image/png');
}
window.pyniteViewer={update,fit,orient,cancel,state:()=>({objects:group.children.length,drawCalls:renderer.info.render.calls,resources:{...renderer.info.memory},labelCache:labelTextures.state(),rebuilds,incrementalUpdates,camera:camera.position.toArray(),target:controls.target.toArray(),selection:data.selection,dragging:nodeDrag.active(),nodes:data.nodes.map(node=>({name:node.name,position:node.position}))}),project:position=>{const p=vector(position).project(camera);return[(p.x+1)*innerWidth/2,(1-p.y)*innerHeight/2];}};
window.pyniteViewer.exportImage=exportImage;
window.pyniteViewer.diagnostics=()=>{
  const gl=renderer.getContext(),debug=gl.getExtension('WEBGL_debug_renderer_info');
  return {lost:gl.isContextLost(),renderer:gl.getParameter(debug?debug.UNMASKED_RENDERER_WEBGL:gl.RENDERER),
    vendor:gl.getParameter(debug?debug.UNMASKED_VENDOR_WEBGL:gl.VENDOR),version:gl.getParameter(gl.VERSION),
    shader:gl.getParameter(gl.SHADING_LANGUAGE_VERSION),source:debug?'Unmasked WebGL driver':'Masked WebGL information'};
};
window.pyniteViewer.diagramPoints=()=>data.members.map(member=>({name:member.name,points:diagramPoints(member,data.diagram).map(point=>point.toArray())}));
window.pyniteViewer.gizmoAxes=()=>gizmo.axes();
window.pyniteViewer.supportSymbols=()=>supports.map(symbol=>({node:symbol.node,dof:symbol.dof,kind:symbol.kind,center:symbol.center.toArray()}));
window.pyniteRendererReady=true;window.pyniteBridge?.ready();
