import assert from 'node:assert/strict';
import {readDisplayFits,renderDisplay} from '../lib/fits-display.ts';

function fixture(planes){
 const cards=[['SIMPLE','T'],['BITPIX','-32'],['NAXIS',planes.length===1?'2':'3'],['NAXIS1','2'],['NAXIS2','2'],...(planes.length>1?[['NAXIS3',String(planes.length)]]:[]),['BUNIT',"'MJy/sr'"]];
 const header=cards.map(([k,v])=>(k.padEnd(8)+'= '+v).padEnd(80)).join('')+'END'.padEnd(80);
 const buffer=new ArrayBuffer(2880+planes.length*16),view=new DataView(buffer);
 new Uint8Array(buffer).set(new TextEncoder().encode(header));
 planes.flat().forEach((v,i)=>view.setFloat32(2880+4*i,v,false));return buffer;
}
const gray=readDisplayFits(fixture([[1,2,3,100]]));
assert.deepEqual(Array.from(gray.channels[0]),[1,2,3,100]);
const linear=renderDisplay(gray,0,100,0);
assert.equal(linear.rgba[4],255); // FITS upper row is displayed at the top.
assert.equal(linear.rgba[8],0);
assert.equal(linear.clipped,0);
assert.ok(renderDisplay(gray,0,80,10).clipped>0);
const rgb=readDisplayFits(fixture([[0,1,2,3],[3,2,1,0],[0,NaN,1,2]]));
const rendered=renderDisplay(rgb,0,100,0);
assert.deepEqual(Array.from(rendered.rgba.slice(12,16)),[0,0,0,255]); // missing band masks RGB pixel
assert.throws(()=>readDisplayFits(new ArrayBuffer(20)),/not supported/);
assert.throws(()=>readDisplayFits(fixture([[1,2,3,4]]).slice(0,2884)),/incomplete/);
console.log('FITS reader / endian / orientation / mask / clipping checks passed');
