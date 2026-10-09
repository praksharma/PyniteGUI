import * as THREE from 'three';

// Bound retained textures, including entries currently used by sprites. When
// the cache is full of live entries, extra labels are transient and disposed
// with their sprites rather than evicting textures still needed by the scene.
export class LabelTextures {
  constructor(maxBytes=8*1024*1024,maxEntries=512){
    this.maxBytes=maxBytes;this.maxEntries=maxEntries;this.entries=new Map();
    this.bytes=0;this.hits=0;this.misses=0;
  }
  acquire(text,color){
    const key=JSON.stringify([text,color]);
    let entry=this.entries.get(key);
    if(entry){
      this.entries.delete(key);this.entries.set(key,entry);
      entry.users++;this.hits++;return entry;
    }
    this.misses++;
    const canvas=document.createElement('canvas'),context=canvas.getContext('2d');
    context.font='24px sans-serif';const width=Math.ceil(context.measureText(text).width)+12;
    canvas.width=width;canvas.height=36;context.font='24px sans-serif';
    context.fillStyle=color;context.fillText(text,6,26);
    // Canvas RGBA backing plus an allowance for GPU mipmaps.
    const bytes=Math.ceil(width*36*4*4/3);
    entry={texture:new THREE.CanvasTexture(canvas),width,bytes,users:1,cached:false};
    if(bytes<=this.maxBytes&&this.maxEntries>0){
      for(const [oldKey,old] of this.entries){
        if(this.entries.size<this.maxEntries&&this.bytes+bytes<=this.maxBytes)break;
        if(!old.users)this.remove(oldKey,old);
      }
      if(this.entries.size<this.maxEntries&&this.bytes+bytes<=this.maxBytes){
        entry.cached=true;this.entries.set(key,entry);this.bytes+=bytes;
      }
    }
    return entry;
  }
  release(entry){
    entry.users--;
    if(!entry.cached&&!entry.users)entry.texture.dispose();
  }
  remove(key,entry){
    this.entries.delete(key);this.bytes-=entry.bytes;
    entry.cached=false;entry.texture.dispose();
  }
  clearUnused(){
    for(const [key,entry] of this.entries)if(!entry.users)this.remove(key,entry);
  }
  state(){return {entries:this.entries.size,bytes:this.bytes,hits:this.hits,misses:this.misses,
    maxBytes:this.maxBytes,maxEntries:this.maxEntries};}
}
