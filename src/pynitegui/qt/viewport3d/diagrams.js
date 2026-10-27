import * as THREE from 'three';

export function diagramPoints(member, diagram) {
  if(!diagram || !member.diagramValues || !member.points)return [];
  if(diagram.style==='colour')return member.points.map(point=>new THREE.Vector3(...point));
  const direction=new THREE.Vector3(...member.axes[diagram.axis]);
  return member.points.map((point,i)=>new THREE.Vector3(...point).addScaledVector(direction,member.diagramValues[i]*diagram.factor));
}

export function diagramLabelIndices(values, diagram) {
  const indices=new Set();
  if(diagram.endValues??Boolean(diagram.values)){indices.add(0);indices.add(values.length-1);}
  if(diagram.extrema??Boolean(diagram.values)){
    let low=0,high=0;
    values.forEach((value,i)=>{if(value<values[low])low=i;if(value>values[high])high=i;});
    indices.add(low);indices.add(high);
  }
  return [...indices].sort((a,b)=>a-b);
}

export function signedSpans(points, values) {
  const spans=[];
  for(let i=1;i<points.length;i++){
    const a=new THREE.Vector3(...points[i-1]),b=new THREE.Vector3(...points[i]);
    if(a.distanceToSquared(b)<1e-20)continue;
    const left=values[i-1],right=values[i];
    if(left*right<0){
      const zero=a.clone().lerp(b,left/(left-right));
      spans.push([a,zero,left/2],[zero,b,right/2]);
    }else spans.push([a,b,(left+right)/2]);
  }
  return spans;
}

export function signedColor(value, diagram) {
  const [negative,zero,positive]=diagram.signedColors;
  const amount=diagram.colourBound?Math.min(1,Math.abs(value)/diagram.colourBound):0;
  // Interpolate encoded RGB, matching the native QColor ramp.
  const start=new THREE.Color(zero),end=new THREE.Color(value>=0?positive:negative);
  start.convertLinearToSRGB();end.convertLinearToSRGB();
  return start.lerp(end,amount).convertSRGBToLinear();
}

export function drawColourMap(member, diagram, group, radius) {
  const spans=signedSpans(member.points,member.diagramValues);
  const length=new THREE.Vector3(...member.points[0]).distanceTo(new THREE.Vector3(...member.points.at(-1)))||1;
  const up=new THREE.Vector3(0,1,0),matrix=new THREE.Matrix4(),rotation=new THREE.Quaternion();
  for(const sign of [-1,0,1]){
    const selected=spans.filter(span=>Math.sign(span[2])===sign);
    if(!selected.length)continue;
    // Instanced strokes stay visible over the reference cylinders. Browser GL
    // line widths are commonly fixed at one pixel and cannot show this map.
    const mesh=new THREE.InstancedMesh(new THREE.CylinderGeometry(1,1,1,8),new THREE.MeshBasicMaterial({depthTest:false}),selected.length);
    mesh.renderOrder=5;mesh.userData.signedPattern=sign<0?'dashed':sign>0?'solid':'dotted';
    selected.forEach(([a,b,value],i)=>{
      const delta=b.clone().sub(a),scale=new THREE.Vector3(radius||length*.004,delta.length()*(sign<0?.68:sign===0?.2:1),radius||length*.004);
      rotation.setFromUnitVectors(up,delta.normalize());
      mesh.setMatrixAt(i,matrix.compose(a.clone().add(b).multiplyScalar(.5),rotation,scale));
      mesh.setColorAt(i,signedColor(value,diagram));
    });
    mesh.computeBoundingSphere();group.add(mesh);
  }
}

export function drawDiagram(member, diagram, group, line, label, colors, radius) {
  const points=diagram?.style==='colour' && member.points && member.diagramValues?member.points.map(p=>new THREE.Vector3(...p)):diagramPoints(member,diagram);
  if(!points.length)return;
  if(diagram.style==='colour'){
    drawColourMap(member,diagram,group,radius);
    for(const i of diagramLabelIndices(member.diagramValues,diagram)){
      const value=member.diagramValues[i]*diagram.displayFactor;
      label(`${diagram.ids===false?'':member.name+' '}${diagram.label} ${value.toPrecision(4)} ${diagram.unit}`,points[i],signedColor(member.diagramValues[i],diagram).getStyle(),undefined,true);
    }
    return;
  }
  const color=colors[diagram.color], vertices=[];
  for(let i=1;i<points.length;i++){
    // Adjacent equal stations encode load jumps, not a finite ribbon span.
    const a=new THREE.Vector3(...member.points[i-1]), b=new THREE.Vector3(...member.points[i]);
    if(a.distanceToSquared(b)<1e-20)continue;
    const left=member.diagramValues[i-1],right=member.diagramValues[i];
    if(left*right<0){
      // Split at zero so opposite-sign lobes do not form overlapping bow ties.
      const zero=a.clone().lerp(b,left/(left-right));
      vertices.push(...a.toArray(),...zero.toArray(),...points[i-1].toArray(),
        ...zero.toArray(),...b.toArray(),...points[i].toArray());
    }else vertices.push(...a.toArray(),...b.toArray(),...points[i].toArray(),
      ...a.toArray(),...points[i].toArray(),...points[i-1].toArray());
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
  group.add(new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color,side:THREE.DoubleSide,transparent:true,opacity:.22,depthWrite:false})));
  line(points,color);
  line([new THREE.Vector3(...member.points[0]),points[0]],color);
  line([new THREE.Vector3(...member.points.at(-1)),points.at(-1)],color);
  for(const i of diagramLabelIndices(member.diagramValues,diagram)){
    const value=member.diagramValues[i]*diagram.displayFactor;
    label(`${diagram.ids===false?'':member.name+' '}${diagram.label} ${value.toPrecision(4)} ${diagram.unit}`,points[i],color,undefined,true);
  }
}

export function legendLines(diagram) {
  if(!diagram)return [];
  if(diagram.style==='colour')return [`${diagram.label} (${diagram.unit}) | ${diagram.combination}`,
    `Sampled range: ${diagram.minimum.toPrecision(5)} to ${diagram.maximum.toPrecision(5)}`,
    `Shared scale (all analyzed combinations): ${(-diagram.colourBound*diagram.displayFactor).toPrecision(5)} / 0 / ${(diagram.colourBound*diagram.displayFactor).toPrecision(5)}`,
    'Negative blue/dashed | zero grey/dotted | positive orange/solid',
    diagram.kind==='axial'?'N positive in compression':'PyNite local signs'];
  return [`${diagram.label} (${diagram.unit}) | ${diagram.combination}`,
    `Sampled range: ${diagram.minimum.toPrecision(5)} to ${diagram.maximum.toPrecision(5)}`,
    `Offset: +local ${['x','y','z'][diagram.axis]} | ${diagram.kind==='axial'?'N positive in compression':'PyNite local signs'}`];
}
