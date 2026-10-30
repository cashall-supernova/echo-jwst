'use client';
import {archiveFetch,sitePath} from '@/lib/archive-client';
import ArchiveImage from './ArchiveImage';
import {useEffect,useMemo,useRef,useState} from 'react';
import {DisplayPixels,readDisplayFits,renderDisplay} from '@/lib/fits-display';
import {clampImageView,FIT_IMAGE,MAX_IMAGE_ZOOM,zoomImageAt} from '@/lib/image-view';

type ImageSource={id:string;png?:string;fits?:string;center?:number[];kind?:string};
export default function FitsViewer({image,label}:{image:ImageSource;label:string}){
 const [pixels,setPixels]=useState<DisplayPixels|null>(null),[error,setError]=useState('');
 const [black,setBlack]=useState(1),[white,setWhite]=useState(99.5),[strength,setStrength]=useState(10),[crosshair,setCrosshair]=useState(true);
 const [view,setView]=useState(FIT_IMAGE),[dragging,setDragging]=useState(false);
 const canvas=useRef<HTMLCanvasElement>(null);
 const viewport=useRef<HTMLDivElement>(null);
 const drag=useRef<{id:number;x:number;y:number}|null>(null);
 useEffect(()=>{
  const element=viewport.current;if(!element)return;
  const wheel=(event:WheelEvent)=>{
   event.preventDefault();
   const bounds=element.getBoundingClientRect();
   const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?bounds.height:1);
   const anchor={x:(event.clientX-bounds.left)/bounds.width-.5,y:(event.clientY-bounds.top)/bounds.height-.5};
   setView(current=>zoomImageAt(current,Math.exp(-Math.max(-300,Math.min(300,delta))*.003),anchor));
  };
  element.addEventListener('wheel',wheel,{passive:false});
  return()=>element.removeEventListener('wheel',wheel);
 },[]);
 useEffect(()=>{
  const controller=new AbortController();
  archiveFetch(image.fits||`/api/stamps/${image.id}.fits`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('FITS pixels could not be loaded.');return r.arrayBuffer()}).then(b=>setPixels(readDisplayFits(b))).catch(e=>{if(e.name!=='AbortError')setError(e.message)});
  return()=>controller.abort();
 },[image.id,image.fits]);
 const rendered=useMemo(()=>pixels?renderDisplay(pixels,black,white,strength):null,[pixels,black,white,strength]);
 useEffect(()=>{if(canvas.current&&rendered&&pixels){canvas.current.getContext('2d')?.putImageData(new ImageData(rendered.rgba,pixels.width,pixels.height),0,0)}},[rendered,pixels]);
 function preset(b:number,w:number,s:number){setBlack(b);setWhite(w);setStrength(s)}
 function download(){canvas.current?.toBlob(blob=>{if(!blob)return;const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`${label.replaceAll(' ','-')}-display.png`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})}
 return <div className="fits-viewer"><div ref={viewport} className={`modal-image image-viewport${view.scale>1?' is-zoomed':''}${dragging?' is-dragging':''}`} tabIndex={0} role="group" aria-label="Image zoom and pan. Plus and minus to zoom, arrow keys to pan, zero to reset."
  onPointerDown={event=>{if(event.button!==0||drag.current)return;event.currentTarget.focus();event.currentTarget.setPointerCapture(event.pointerId);drag.current={id:event.pointerId,x:event.clientX,y:event.clientY};setDragging(true)}}
  onPointerMove={event=>{const previous=drag.current;if(!previous||previous.id!==event.pointerId)return;const bounds=event.currentTarget.getBoundingClientRect();const dx=(event.clientX-previous.x)/bounds.width,dy=(event.clientY-previous.y)/bounds.height;drag.current={id:event.pointerId,x:event.clientX,y:event.clientY};setView(current=>clampImageView({...current,x:current.x+dx,y:current.y+dy}))}}
  onPointerUp={event=>{if(drag.current?.id===event.pointerId){event.currentTarget.releasePointerCapture(event.pointerId);drag.current=null;setDragging(false)}}}
  onPointerCancel={()=>{drag.current=null;setDragging(false)}} onLostPointerCapture={()=>{drag.current=null;setDragging(false)}}
  onKeyDown={event=>{
   if(['+','=','-','0','Home','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))event.preventDefault();
   if(event.key==='+'||event.key==='=')setView(current=>zoomImageAt(current,1.5));
   else if(event.key==='-')setView(current=>zoomImageAt(current,1/1.5));
   else if(event.key==='0'||event.key==='Home')setView(FIT_IMAGE);
   else if(event.key.startsWith('Arrow'))setView(current=>clampImageView({...current,x:current.x+(event.key==='ArrowLeft'?.1:event.key==='ArrowRight'?-.1:0),y:current.y+(event.key==='ArrowUp'?.1:event.key==='ArrowDown'?-.1:0)}));
  }}>
  <div className="image-plane" style={{transform:`translate(${view.x*100}%,${view.y*100}%) scale(${view.scale})`}}>
   {pixels?<canvas ref={canvas} width={pixels.width} height={pixels.height} role="img" aria-label={label+'; adjustable FITS display'}/>:<ArchiveImage src={image.png||`/api/stamps/${image.id}.png`} alt={label} draggable={false}/>}
   {crosshair&&<span className="crosshair" style={{left:`${(image.center?.[0]??.5)*100}%`,top:`${(image.center?.[1]??.5)*100}%`,transform:`scale(${1/view.scale})`}}/>}
  </div>
  {image.kind==='rgb'&&<span className="orientation">N ↑ · E ←</span>}
 </div><div className="display-controls">
  <div className="image-zoom-controls" role="group" aria-label="Image zoom controls">
   <button aria-label="Zoom out" disabled={view.scale<=1} onClick={()=>setView(current=>zoomImageAt(current,1/1.5))}>−</button>
   <output aria-label="Image magnification">{view.scale.toFixed(1)}×</output>
   <button aria-label="Zoom in" disabled={view.scale>=MAX_IMAGE_ZOOM} onClick={()=>setView(current=>zoomImageAt(current,1.5))}>+</button>
   <button className="image-zoom-reset" onClick={()=>setView(FIT_IMAGE)}>Reset view</button>
  </div>
  <p className="image-zoom-help">Scroll to zoom · drag to pan. Zoom changes the view, not the image resolution.</p>
  <div className="control-heading"><b>Display contrast</b><label><input type="checkbox" checked={crosshair} onChange={e=>setCrosshair(e.target.checked)}/> Crosshair</label></div>
  {error?<p role="alert">{error} Showing the saved preview; FITS download is still available.</p>:!pixels?<p role="status">Loading calibrated pixels…</p>:<>
   <div className="preset-buttons"><button onClick={()=>preset(1,99.5,10)}>Auto</button><button onClick={()=>preset(1,97,30)}>Faint structure</button><button onClick={()=>preset(0,100,3)}>Bright cores</button></div>
   <label className="stretch-slider">Black percentile <input aria-label="Black percentile" type="range" min="0" max="50" step="0.1" value={black} onChange={e=>setBlack(Number(e.target.value))}/><output>{black.toFixed(1)}%</output></label>
   <label className="stretch-slider">White percentile <input aria-label="White percentile" type="range" min="50.1" max="100" step="0.1" value={white} onChange={e=>setWhite(Number(e.target.value))}/><output>{white.toFixed(1)}%</output></label>
   <label className="stretch-slider">Asinh strength <input aria-label="Asinh strength" type="range" min="0" max="100" step="1" value={strength} onChange={e=>setStrength(Number(e.target.value))}/><output>{strength===0?'Linear':strength}</output></label>
   <p className="display-readout">{pixels.channels.length===1?`Display limits ${rendered!.limits[0].map(n=>n.toPrecision(4)).join(' to ')} ${pixels.unit}. `:'Each colour channel is scaled independently. '}Above white limit: {(rendered!.clipped*100).toFixed(2)}% of valid pixels.</p>
   <button className="text-button" onClick={download}>Download full display PNG ↓</button>
  </>}
  <p className="display-note">Changes affect the display only. Faint structure can include noise; a visible feature is not a confirmed SN detection.</p>
 </div></div>
}
