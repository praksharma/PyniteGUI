import * as THREE from 'three';

export function diagramPoints(member, diagram) {
  if(!diagram || !member.diagramValues || !member.points)return [];
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

export function drawDiagram(member, diagram, group, line, label, colors) {
  const points=diagramPoints(member,diagram);
  if(!points.length)return;
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
  return [`${diagram.label} (${diagram.unit}) | ${diagram.combination}`,
    `Sampled range: ${diagram.minimum.toPrecision(5)} to ${diagram.maximum.toPrecision(5)}`,
    `Offset: +local ${['x','y','z'][diagram.axis]} | ${diagram.kind==='axial'?'N positive in compression':'PyNite local signs'}`];
}
