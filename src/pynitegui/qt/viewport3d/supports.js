import * as THREE from 'three';

const DOFS = ['DX','DY','DZ','RX','RY','RZ'];
const vector = values => new THREE.Vector3(...values);

export function supportSymbols(node, span) {
  const origin=vector(node.position), result=[];
  for(let index=0;index<6;index++){
    const fixed=node.restraints[index], spring=node.springs[index];
    if(!fixed&&!spring)continue;
    const axis=new THREE.Vector3().setComponent(index%3,1);
    // Separate rotation and translation anchors on each global axis.
    const center=origin.clone().addScaledVector(axis,-span*(index<3?.046:.085));
    result.push({node:node.name,dof:DOFS[index],index,kind:fixed?'fixed':'spring',center,axis});
  }
  return result;
}

export function drawSupports(node, span, colors, group, picks) {
  const origin=vector(node.position), symbols=supportSymbols(node,span);
  for(const symbol of symbols){
    const {index,center,axis}=symbol, spring=symbol.kind==='spring';
    const color=spring?colors.axial:colors.support, root=new THREE.Group();
    group.add(root);
    const line=points=>{
      const object=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color}));
      root.add(object);return object;
    };
    const u=new THREE.Vector3().crossVectors(axis,Math.abs(axis.y)<.8?new THREE.Vector3(0,1,0):new THREE.Vector3(1,0,0)).normalize();
    const v=new THREE.Vector3().crossVectors(axis,u), radius=span*.014;
    if(index<3){
      if(spring){
        const points=[origin.clone()];
        for(let step=0;step<=48;step++){
          const t=step/48, angle=step*Math.PI/6;
          points.push(origin.clone().lerp(center,.15+.7*t).addScaledVector(u,radius*.4*Math.cos(angle))
            .addScaledVector(v,radius*.4*Math.sin(angle)));
        }
        points.push(center.clone());line(points);
      }else{
        line([origin,center]);
      }
      const pad=new THREE.Mesh(new THREE.BoxGeometry(radius*1.6,radius*1.6,span*.003),new THREE.MeshBasicMaterial({color}));
      pad.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),axis);
      pad.position.copy(center);root.add(pad);
      for(const shift of [-.6,0,.6]){
        const start=center.clone().addScaledVector(u,radius*shift).addScaledVector(v,-radius*.8);
        line([start,start.clone().addScaledVector(v,-radius*.4).addScaledVector(u,-radius*.35)]);
      }
    }else{
      line([origin.clone().addScaledVector(axis,-span*.057),center]);
      if(spring){
        const points=[];
        for(let step=0;step<=64;step++){
          const angle=step/64*Math.PI*3, r=radius*(.3+.7*step/64);
          points.push(center.clone().addScaledVector(u,r*Math.cos(angle)).addScaledVector(v,r*Math.sin(angle)));
        }
        line(points);
        line([points.at(-1),points.at(-1).clone().addScaledVector(u,-radius*.5)]);
      }else{
        const ring=new THREE.Mesh(new THREE.TorusGeometry(radius,span*.0015,6,32),new THREE.MeshBasicMaterial({color}));
        ring.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),axis);
        ring.position.copy(center);root.add(ring);
        for(const sign of [-1,1]){
          line([center.clone().addScaledVector(u,sign*radius*.6).addScaledVector(v,-radius*.4),
                center.clone().addScaledVector(u,sign*radius*.6).addScaledVector(v,radius*.4)]);
        }
      }
    }
    root.traverse(object=>{
      if(object.isLine||object.isMesh){
        object.userData.identity=['nodes',node.name];
        object.userData.supportDof=index;
        picks.push(object);
      }
    });
  }
  return symbols;
}

export class SupportTooltip {
  constructor(){
    this.element=document.createElement('div');
    this.element.id='support-tooltip';this.element.setAttribute('role','tooltip');
    this.element.hidden=true;document.body.appendChild(this.element);
  }
  hide(){this.element.hidden=true;}
  show(node,dof,event,colors){
    const title=document.createElement('strong');title.textContent=`${node.name} | Global supports`;
    const table=document.createElement('table');
    for(const [index,detail] of (node.supportDetails||[]).entries()){
      const row=document.createElement('tr');
      if(index===dof)row.className='active-dof';
      for(const text of [detail.dof,detail.state]){
        const cell=document.createElement('td');cell.textContent=text;row.appendChild(cell);
      }
      table.appendChild(row);
    }
    this.element.replaceChildren(title,table);
    this.element.style.color=colors.text||colors.label;
    this.element.style.background=colors.canvas;
    this.element.style.borderColor=colors.support;
    this.element.hidden=false;
    const width=this.element.offsetWidth,height=this.element.offsetHeight;
    const left=event.clientX+16+width>innerWidth-8?event.clientX-width-16:event.clientX+16;
    this.element.style.left=`${Math.max(8,Math.min(left,innerWidth-width-8))}px`;
    this.element.style.top=`${Math.max(8,Math.min(event.clientY+16,innerHeight-height-8))}px`;
  }
}
