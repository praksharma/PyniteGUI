import * as THREE from 'three';

export function hitIdentity(hit){
  return hit?.object.userData.identities?.[hit.instanceId] || hit?.object.userData.identity;
}

export function drawFrame(data,radius,group,picks){
  const nodes=new Map(data.nodes.map(node=>[node.name,new THREE.Vector3(...node.position)]));
  const selected=new Set(data.selection.map(([kind,name])=>`${kind}:${name}`));
  const matrix=new THREE.Matrix4(),rotation=new THREE.Quaternion(),scale=new THREE.Vector3();
  const up=new THREE.Vector3(0,1,0);
  function batch(definitions,geometry,kind,transform,color){
    if(!definitions.length){geometry.dispose();return;}
    const mesh=new THREE.InstancedMesh(geometry,new THREE.MeshStandardMaterial(),definitions.length);
    mesh.userData.identities=definitions.map(item=>[kind,item.name]);
    mesh.userData.nodeInstances=kind==='nodes';
    definitions.forEach((item,index)=>{
      mesh.setMatrixAt(index,transform(item));
      mesh.setColorAt(index,new THREE.Color(selected.has(`${kind}:${item.name}`)?data.colors.accent:color(item)));
    });
    mesh.computeBoundingBox();mesh.computeBoundingSphere();
    group.add(mesh);picks.push(mesh);
  }
  batch(data.members,new THREE.CylinderGeometry(1,1,1,10),'members',member=>{
    const a=nodes.get(member.start),b=nodes.get(member.end),delta=b.clone().sub(a);
    const r=radius*(member.kind==='truss'?.7:1);
    scale.set(r,delta.length(),r);rotation.setFromUnitVectors(up,delta.normalize());
    return matrix.compose(a.clone().add(b).multiplyScalar(.5),rotation,scale);
  },member=>member.kind==='truss'?data.colors.axial:data.colors.member);
  batch(data.nodes,new THREE.SphereGeometry(1,12,8),'nodes',node=>{
    scale.setScalar(radius*1.8);rotation.identity();
    return matrix.compose(nodes.get(node.name),rotation,scale);
  },()=>data.colors.member);
}
