import * as THREE from 'three';
import {ViewHelper} from './vendor/ViewHelper.js';

const views = {posX:3,posY:2,posZ:1,negX:6,negY:5,negZ:4};
const names = {posX:'Right YZ',posY:'Top XZ',posZ:'Front XY',negX:'Left YZ',negY:'Bottom XZ',negZ:'Back XY'};

export class OrientationGizmo {
  constructor(camera, controls, renderer, orient, notify, stopMotion) {
    this.helper = new ViewHelper(camera, renderer.domElement);
    this.helper.center = controls.target;
    this.helper.setLabels('X','Y','Z');
    const negative=this.helper.children.filter(obj=>obj.isSprite&&obj.userData.type.startsWith('neg'));
    negative[0].material.map.dispose();negative[0].material.dispose();
    for(const sprite of negative){
      const canvas=document.createElement('canvas');canvas.width=canvas.height=64;
      const context=canvas.getContext('2d');context.fillStyle='#526773';context.beginPath();context.arc(32,32,18,0,Math.PI*2);context.fill();
      context.font='22px sans-serif';context.textAlign='center';context.fillStyle='#ffffff';context.fillText('-'+sprite.userData.type.at(-1),32,40);
      const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
      sprite.material=new THREE.SpriteMaterial({map:texture,toneMapped:false});
    }
    this.camera = camera; this.controls = controls; this.renderer = renderer; this.notify = notify;
    this.pad = document.createElement('div');
    this.pad.id = 'orientation-gizmo'; this.pad.tabIndex = 0;
    this.pad.setAttribute('role','group'); this.pad.setAttribute('aria-label','View orientation');
    this.pad.title = 'View orientation';
    const home = document.createElement('button');
    home.className = 'gizmo-home'; home.textContent = 'ISO'; home.title = 'Isometric view';
    home.setAttribute('aria-label','Isometric view');
    home.addEventListener('pointerup',event=>event.stopPropagation());
    home.addEventListener('click',()=>orient(0));
    this.pad.appendChild(home); document.body.appendChild(this.pad);
    this.pad.addEventListener('pointerup',event=>{
      if(event.button !== 0)return;
      stopMotion();
      this.helper.quaternion.copy(camera.quaternion).invert();
      this.helper.updateMatrixWorld(true);
      if(this.helper.handleClick(event))controls.enabled = false;
    });
    this.pad.addEventListener('pointermove',event=>{
      const nearest=this.axes().find(axis=>Math.hypot(axis.x-event.clientX,axis.y-event.clientY)<14);
      this.pad.title=nearest?names[nearest.type]:'View orientation';
    });
    this.pad.addEventListener('keydown',event=>{
      if(event.target!==this.pad)return;
      const key=event.key.toUpperCase(), positive={X:3,Y:2,Z:1}, negative={X:6,Y:5,Z:4};
      if(key==='HOME'||positive[key]){event.preventDefault();orient(key==='HOME'?0:(event.shiftKey?negative:positive)[key]);}
    });
  }
  cancel(){this.helper.animating=false;this.controls.enabled=true;}
  update(delta){
    if(!this.helper.animating)return false;
    this.helper.update(delta);
    if(!this.helper.animating){
      this.camera.up.set(0,1,0).applyQuaternion(this.camera.quaternion);
      this.controls.enabled=true;this.controls.update();
      const direction=this.camera.position.clone().sub(this.controls.target).normalize();
      const type=Object.keys(views).find(type=>direction.dot(new THREE.Vector3(
        type.endsWith('X')?(type.startsWith('pos')?1:-1):0,
        type.endsWith('Y')?(type.startsWith('pos')?1:-1):0,
        type.endsWith('Z')?(type.startsWith('pos')?1:-1):0))>.9999);
      if(type)this.notify(views[type]);
    }
    return true;
  }
  render(){this.helper.render(this.renderer);}
  axes(){
    const rect=this.renderer.domElement.getBoundingClientRect();
    const inverse=this.camera.quaternion.clone().invert();
    return this.helper.children.filter(obj=>obj.isSprite).map(obj=>{
      const p=obj.position.clone().applyQuaternion(inverse);
      return {type:obj.userData.type,x:rect.right-64+p.x*32,y:rect.bottom-64-p.y*32,depth:p.z};
    }).sort((a,b)=>b.depth-a.depth);
  }
}
