'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import type {PointerEvent as ReactPointerEvent,ReactNode} from 'react';
import LineControls from './LineControls';
import {commonLineIds,markerWavelength,SPECTRAL_LINES} from '@/lib/spectral-lines';
import {EPOCH_COLOURS,automaticEpochSpacing,boundedRange,defaultWavelengthRange,fluxExtent,smoothedFluxExtent,panRange,selectedRange,zoomRange} from '@/lib/spectrum-view';
import type {Range} from '@/lib/spectrum-view';
type NavigationMode='wavelength'|'box'|'pan';
type SavedView={bounds:[string,string,string,string];step:number|null;central:boolean};
type Gesture={start:[number,number];current:[number,number];x:Range;y:Range;step:number;mode:NavigationMode;pointer:number};
import type {SpectrumAsset,SpectrumProduct} from '@/lib/spectra';
import {spectrumDate} from '@/lib/spectra';
import {csvText,groupEpochs,median,processSegment} from '@/lib/spectrum-processing';
import type {ProcessedPoint,Processing} from '@/lib/spectrum-processing';
const colours=EPOCH_COLOURS;
const W=1100,L=82,R=128,B=60;
const number=(n:number)=>Math.abs(n)>=10000||Math.abs(n)>0&&Math.abs(n)<.001?n.toExponential(2):Number(n.toPrecision(5)).toString();
const epochLabel=(e:{index:number;start:number|null;end:number|null})=>e.start===null?'Unknown epoch':`Epoch ${e.index+1} · ${spectrumDate(e.start)}${spectrumDate(e.end)!==spectrumDate(e.start)?'–'+spectrumDate(e.end):''}`;
function download(text:string,name:string){const url=URL.createObjectURL(new Blob([text],{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
export default function SpectrumPlot({entries,products,z,loading=false,selectionPanel}:{selectionPanel?:ReactNode;loading?:boolean;entries:{product:SpectrumProduct;asset:SpectrumAsset}[];products:SpectrumProduct[];z:number|null}){
 const [rest,setRest]=useState(false),[log,setLog]=useState(false),[flagged,setFlagged]=useState(false),[errors,setErrors]=useState(false);
 const [stack,setStack]=useState(true),[normalize,setNormalize]=useState(true),[spacing,setSpacing]=useState('');
 const [bin,setBin]=useState<Processing['bin']>('none'),[binSize,setBinSize]=useState('5'),[smooth,setSmooth]=useState(1),[original,setOriginal]=useState(false);
 const [xmin,setXmin]=useState(''),[xmax,setXmax]=useState(''),[ymin,setYmin]=useState(''),[ymax,setYmax]=useState(''),[hover,setHover]=useState<number|null>(null);
 const [navMode,setNavMode]=useState<NavigationMode>('box'),[central,setCentral]=useState(true),[viewStep,setViewStep]=useState<number|null>(null),[history,setHistory]=useState<SavedView[]>([]),[gesture,setGesture]=useState<Gesture|null>(null);
 const [lineIds,setLineIds]=useState(true),[lineSelection,setLineSelection]=useState(commonLineIds),[velocity,setVelocity]=useState(0),[displayReset,setDisplayReset]=useState(0);
 const hasRedshift=z!==null&&Number.isFinite(z)&&z>-1;
 const showLines=lineIds&&hasRedshift;
 const T=showLines?120:28;
 const svgRef=useRef<SVGSVGElement>(null),gestureRef=useRef<Gesture|null>(null);
 const epochs=useMemo(()=>groupEpochs(products),[products]);
 const factor=rest&&z!==null&&z>-1?1+z:1;
 const binValid=bin==='none'||Number.isFinite(Number(binSize))&&Number(binSize)>0&&(bin!=='samples'||Number.isInteger(Number(binSize))&&Number(binSize)<=10000);
 const transformed=bin!=='none'||smooth>1;
 const processed=useMemo(()=>{
  const options:Processing={bin,size:Number(binSize),smooth,factor,flagged};
  const values=new Map<string,number[]>();
  const list=entries.flatMap(({product,asset})=>{
   const epoch=epochs.find(e=>e.productIds.includes(product.id))!;
   const v=values.get(epoch.key)||[];
   for(const seg of asset.segments)for(const [,f,,dq] of seg.points)if(f!==null&&Number.isFinite(f)&&(flagged||dq===0))v.push(Math.abs(f));
   values.set(epoch.key,v);
   return asset.segments.map(seg=>({product,segment:seg.label,epoch,colour:colours[epoch.index%colours.length],runs:processSegment(seg.points,options),raw:original&&transformed?processSegment(seg.points,{...options,bin:'none',smooth:1}):[]}));
  });
  const norms=new Map(epochs.map(e=>[e.key,normalize?(median(values.get(e.key)||[])||1):1]));
  return {list,norms};
 },[entries,epochs,bin,binSize,smooth,factor,flagged,normalize,original,transformed]);
 const visibleEpochs=epochs.filter(e=>entries.some(p=>e.productIds.includes(p.product.id)));
 const H=stack?Math.min(900,Math.max(520,280+visibleEpochs.length*50)):520;
 const model=useMemo(()=>{
  const convert=(p:ProcessedPoint,norm:number)=>{const v=normalize?p.flux/norm:p.flux*1e6;return log?(v>0?Math.log10(v):null):v};
  let lo=Infinity,hi=-Infinity;
  for(const s of processed.list)for(const run of s.runs)for(const p of run){lo=Math.min(lo,p.low);hi=Math.max(hi,p.high)}
  if(lo===hi&&Number.isFinite(lo)){lo-=.000001;hi+=.000001}
  const defaults=defaultWavelengthRange([lo,hi]);
  const x0=xmin!==''?Number(xmin):defaults[0],x1=xmax!==''?Number(xmax):defaults[1];
  const epochValues=new Map<string,number[]>(),spacingValues=new Map<string,number[]>(),epochRuns=new Map<string,(number|null)[][]>();
  for(const s of processed.list){const values=epochValues.get(s.epoch.key)||[],norm=processed.norms.get(s.epoch.key)!;
   const typical=spacingValues.get(s.epoch.key)||[];
   for(const run of s.runs)for(const p of run)if(p.wave>=x0&&p.wave<=x1){const v=convert(p,norm);if(v!==null)typical.push(v)}
   spacingValues.set(s.epoch.key,typical);
   for(const run of [...s.runs,...s.raw])for(const p of run)if(p.wave>=x0&&p.wave<=x1){const v=convert(p,norm);if(v!==null)values.push(v);if(errors&&p.error!==null)for(const flux of [p.flux-p.error,p.flux+p.error]){const e=convert({...p,flux},norm);if(e!==null)values.push(e)}}
   epochValues.set(s.epoch.key,values);
   const runs=epochRuns.get(s.epoch.key)||[];
   for(const run of [...s.runs,...s.raw]){
    const visible=run.filter(p=>p.wave>=x0&&p.wave<=x1);
    runs.push(visible.map(p=>convert(p,norm)));
    if(errors)for(const sign of [-1,1])runs.push(visible.map(p=>p.error===null?null:convert({...p,flux:p.flux+sign*p.error},norm)));
   }
   epochRuns.set(s.epoch.key,runs);
  }
  const extents=new Map([...epochValues].map(([key,v])=>[key,central?smoothedFluxExtent(epochRuns.get(key)||[]):fluxExtent(v)]));
  const autoStep=automaticEpochSpacing(spacingValues.values());
  const step=spacing!==''&&Number.isFinite(Number(spacing))&&Number(spacing)>=0?Number(spacing):viewStep??autoStep;
  const offsets=new Map(epochs.filter(e=>extents.get(e.key)).map((e,index)=>[e.key,stack?index*step:0]));
  type DrawPoint=ProcessedPoint&{y:number|null;lower:number|null;upper:number|null};
  let bottom=Infinity,top=-Infinity;
  const series=processed.list.map(s=>{
   const norm=processed.norms.get(s.epoch.key)!,offset=offsets.get(s.epoch.key)??0;
   const map=(run:ProcessedPoint[]):DrawPoint[]=>run.map(p=>{const y=convert(p,norm),lower=p.error===null?null:convert({...p,flux:p.flux-p.error},norm),upper=p.error===null?null:convert({...p,flux:p.flux+p.error},norm);return {...p,y:y===null?null:y+offset,lower:lower===null?null:lower+offset,upper:upper===null?null:upper+offset}});
   const runs=s.runs.map(map),raw=s.raw.map(map);
   const bounds=extents.get(s.epoch.key);if(bounds){bottom=Math.min(bottom,bounds[0]+offset);top=Math.max(top,bounds[1]+offset)}
   return {...s,runs,raw,norm,offset};
  });
  if(bottom===top&&Number.isFinite(bottom)){const d=Math.abs(bottom)*.1||1;bottom-=d;top+=d}
  const pad=(top-bottom)*.06;
  const y0=ymin!==''?Number(ymin):bottom-pad,y1=ymax!==''?Number(ymax):top+pad;
  const valid=binValid&&Number.isFinite(x0)&&Number.isFinite(x1)&&x1>x0&&Number.isFinite(y0)&&Number.isFinite(y1)&&y1>y0;
  const xx=(x:number)=>L+(x-x0)/(x1-x0)*(W-L-R),yy=(y:number)=>T+(1-(y-y0)/(y1-y0))*(H-T-B);
  const paths=valid?series.map(s=>{
   const draw=(runs:DrawPoint[][])=>runs.map(run=>{let d='',pen=false,dots:string[]=[];for(const p of run){if(p.y===null||p.wave<x0||p.wave>x1){pen=false;continue}const x=xx(p.wave).toFixed(2),y=yy(p.y).toFixed(2);d+=(pen?'L':'M')+x+','+y;pen=true;if(run.length===1)dots.push(`M${x},${y}h.01`)}return d+dots.join('')}).join('');
   let band='';for(const run of s.runs){let chunk:DrawPoint[]=[];const flush=()=>{if(chunk.length>1)band+='M'+chunk.map(p=>`${xx(p.wave).toFixed(2)},${yy(p.upper!).toFixed(2)}`).join('L')+'L'+chunk.slice().reverse().map(p=>`${xx(p.wave).toFixed(2)},${yy(p.lower!).toFixed(2)}`).join('L')+'Z';chunk=[]};for(const p of run){if(p.y===null||p.lower===null||p.upper===null||p.wave<x0||p.wave>x1){flush();continue}chunk.push(p)}flush()}
   return {...s,d:draw(s.runs),rawPath:draw(s.raw),band};
  }):[];
  let outside=0,visible=0;for(const s of series)for(const run of s.runs)for(const p of run)if(p.wave>=x0&&p.wave<=x1&&p.y!==null){visible++;if(p.y<y0||p.y>y1)outside++}
  return {valid,x0,x1,y0,y1,dataX0:lo,dataX1:hi,paths,series,step,autoStep,offsets,outside,visible};
 },[processed,epochs,stack,normalize,spacing,viewStep,central,log,errors,xmin,xmax,ymin,ymax,H,T,binValid]);
 const markers=useMemo(()=>!showLines||!model.valid?[]:SPECTRAL_LINES.filter(l=>lineSelection.includes(l.id)).map(l=>({...l,x:markerWavelength(l.wave,z,rest,velocity)!})).filter(l=>l.x>=model.x0&&l.x<=model.x1).sort((a,b)=>a.x-b.x),[showLines,lineSelection,z,rest,velocity,model]);
 const markerLabels:{x:number;last:number;names:string[]}[]=[];
 for(const l of markers){const prior=markerLabels.at(-1);if(prior&&l.x-prior.last<(model.x1-model.x0)*.018){prior.last=l.x;if(!prior.names.includes(l.label))prior.names.push(l.label)}else markerLabels.push({x:l.x,last:l.x,names:[l.label]})}
 const epochAnnotations=visibleEpochs.flatMap(e=>{
  const points=model.series.filter(s=>s.epoch.key===e.key).flatMap(s=>s.runs.flat()).filter(p=>p.wave>=model.x0&&p.wave<=model.x1&&p.y!==null).sort((a,b)=>a.wave-b.wave);
  if(!points.length||!model.valid)return [];
  const tail=points.slice(-25),y=median(tail.map(p=>p.y!));
  return [{epoch:e,x:points.at(-1)!.wave,y,py:Math.max(T+10,Math.min(H-B-10,T+(1-(y-model.y0)/(model.y1-model.y0))*(H-T-B)))}];
 }).sort((a,b)=>a.py-b.py);
 for(let i=1;i<epochAnnotations.length;i++)epochAnnotations[i].py=Math.max(epochAnnotations[i].py,epochAnnotations[i-1].py+18);
 for(let i=epochAnnotations.length-1;i>=0;i--)epochAnnotations[i].py=Math.min(epochAnnotations[i].py,H-B-10-(epochAnnotations.length-1-i)*18);
 const cursor=hover===null||!model.valid?null:model.x0+hover*(model.x1-model.x0);
 const nearest=useMemo(()=>{
  if(cursor===null)return [];
  const found=new Map<string,{point:ProcessedPoint;epoch:typeof epochs[number];colour:string;distance:number}>();
  for(const s of processed.list)for(const run of s.runs){if(!run.length||cursor<run[0].wave||cursor>run[run.length-1].wave)continue;let left=0,right=run.length-1;while(left<right){const mid=(left+right)>>1;if(run[mid].wave<cursor)left=mid+1;else right=mid}for(const index of [left,Math.max(0,left-1)]){const p=run[index],distance=Math.abs(p.wave-cursor);if(!found.has(s.epoch.key)||distance<found.get(s.epoch.key)!.distance)found.set(s.epoch.key,{point:p,epoch:s.epoch,colour:s.colour,distance})}}
  return [...found.values()].sort((a,b)=>a.epoch.index-b.epoch.index);
 },[cursor,processed,epochs]);
 function exportOriginal(){const rows:unknown[][]=[['product','segment','wavelength_observed_um','flux_jy','error_jy','dq']];for(const {product,asset} of entries)for(const seg of asset.segments)for(const [w,f,e,d] of seg.points)rows.push([product.filename,seg.label,w,f,e,d]);download(csvText(rows),'echo-original-spectra.csv')}
 function exportProcessed(){const rows:unknown[][]=[['product','segment','epoch','epoch_start_mjd','epoch_end_mjd','wavelength_frame','redshift','wavelength_observed_um','wavelength_um','input_low_um','input_high_um','flux_jy','error_jy','dq_or','input_samples','bin_mode','bin_size','smooth_window','include_flagged','normalization_jy','display_value','display_lower','display_upper','display_unit','epoch_offset']];for(const s of model.series)for(const run of s.runs)for(const p of run)rows.push([s.product.filename,s.segment,epochLabel(s.epoch),s.epoch.start,s.epoch.end,rest?'rest':'observed',z,p.wave*factor,p.wave,p.low,p.high,p.flux,p.error,p.dq,p.samples,bin,bin==='none'?'':binSize,smooth,flagged,normalize?s.norm:'',p.y,p.lower,p.upper,(log?'log10 ':'')+(normalize?'relative flux':'uJy'),s.offset]);download(csvText(rows),'echo-processed-spectra.csv')}
 function remember(){setHistory(h=>[...h.slice(-24),{bounds:[xmin,xmax,ymin,ymax],step:viewStep,central}])}
 function clearGesture(){gestureRef.current=null;setGesture(null)}
 function resetRange(){setXmin('');setXmax('');setYmin('');setYmax('');setViewStep(null);setCentral(true);setHistory([]);clearGesture()}
 function resetFluxView(){setYmin('');setYmax('');setViewStep(null);setHistory([]);clearGesture()}
 function changeSpacing(value:string){setSpacing(value);resetFluxView()}
 function defaultRange(){remember();setXmin('');setXmax('');setYmin('');setYmax('');setViewStep(null);setCentral(true);clearGesture()}
 function fullRange(){remember();setXmin('');setXmax(Number.isFinite(model.dataX1)?String(model.dataX1):'');setYmin('');setYmax('');setViewStep(null);setCentral(true);clearGesture()}
 function undo(){const previous=history.at(-1);if(!previous)return;setHistory(h=>h.slice(0,-1));setXmin(previous.bounds[0]);setXmax(previous.bounds[1]);setYmin(previous.bounds[2]);setYmax(previous.bounds[3]);setViewStep(previous.step);setCentral(previous.central);clearGesture()}
 function fitY(robust=true){remember();setYmin('');setYmax('');setViewStep(null);setCentral(robust)}
 function applyView(x:Range,y:Range|null,heldStep:number|null){
  if(!x.every(Number.isFinite)||x[1]<=x[0]||y&&(!y.every(Number.isFinite)||y[1]<=y[0]))return;
  remember();setXmin(String(x[0]));setXmax(String(x[1]));setYmin(y?String(y[0]):'');setYmax(y?String(y[1]):'');setViewStep(heldStep);setHover(null);
 }
 function zoom(factor:number,anchor:[number,number]=[.5,.5],both=navMode==='box'){
  if(!model.valid)return;
  const x=boundedRange(zoomRange([model.x0,model.x1],factor,anchor[0]),[model.dataX0,model.dataX1]);
  applyView(x,both?zoomRange([model.y0,model.y1],factor,1-anchor[1]):null,both?model.step:null);
 }
 function point(svg:SVGSVGElement,clientX:number,clientY:number):[number,number]|null {
  const matrix=svg.getScreenCTM();if(!matrix)return null;const p=svg.createSVGPoint();p.x=clientX;p.y=clientY;const q=p.matrixTransform(matrix.inverse());return [(q.x-L)/(W-L-R),(q.y-T)/(H-T-B)];
 }
 function beginDrag(e:ReactPointerEvent<SVGSVGElement>){
  const p=point(e.currentTarget,e.clientX,e.clientY);if(e.button!==0||!model.valid||!p||p.some(v=>v<0||v>1))return;
  e.preventDefault();e.currentTarget.focus();e.currentTarget.setPointerCapture(e.pointerId);
  const g:Gesture={start:p,current:p,x:[model.x0,model.x1],y:[model.y0,model.y1],step:model.step,mode:e.altKey?'pan':e.shiftKey?'box':navMode,pointer:e.pointerId};gestureRef.current=g;setGesture(g);
 }
 function moveDrag(e:ReactPointerEvent<SVGSVGElement>){
  const p=point(e.currentTarget,e.clientX,e.clientY);if(!p)return;
  if(gestureRef.current){const g={...gestureRef.current,current:p.map(v=>Math.max(0,Math.min(1,v))) as [number,number]};gestureRef.current=g;setGesture(g)}
  else setHover(p[0]>=0&&p[0]<=1&&p[1]>=0&&p[1]<=1?p[0]:null);
 }
 function endDrag(e:ReactPointerEvent<SVGSVGElement>){
  const g=gestureRef.current;if(!g||g.pointer!==e.pointerId)return;
  if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);clearGesture();
  const dx=g.current[0]-g.start[0],dy=g.current[1]-g.start[1];
  if(g.mode==='pan'){if(Math.abs(dx)+Math.abs(dy)<.005)return;applyView(boundedRange(panRange(g.x,-dx),[model.dataX0,model.dataX1]),panRange(g.y,dy),g.step)}
  else {if(Math.abs(dx)<.005||g.mode==='box'&&Math.abs(dy)<.005)return;applyView(selectedRange(g.x,g.start[0],g.current[0]),g.mode==='box'?selectedRange(g.y,1-g.start[1],1-g.current[1]):null,g.mode==='box'?g.step:null)}
 }
 useEffect(()=>{
  const svg=svgRef.current;if(!svg)return;
  const wheel=(e:WheelEvent)=>{if(!(e.ctrlKey||e.metaKey)||!model.valid)return;const p=point(svg,e.clientX,e.clientY);if(!p||p.some(v=>v<0||v>1))return;e.preventDefault();zoom(Math.exp(Math.max(-300,Math.min(300,e.deltaY))*.002),p)};
  svg.addEventListener('wheel',wheel,{passive:false});return()=>svg.removeEventListener('wheel',wheel);
 },[model,navMode]);
 function resetProcessing(){setDisplayReset(n=>n+1);setLineIds(true);setLineSelection(commonLineIds());setVelocity(0);setNavMode('box');setBin('none');setBinSize('5');setSmooth(1);setOriginal(false);setNormalize(true);setStack(true);setSpacing('');setLog(false);setRest(false);setFlagged(false);setErrors(false);resetRange()}
 const axisTitle=(log?'log₁₀ ':'')+(normalize?'Relative Fν':'Observed Fν (µJy)')+(stack?' + epoch offset':'');
 const sampleCount=processed.list.reduce((n,s)=>n+s.runs.reduce((n,r)=>n+r.length,0),0);
 return <section className="spectrum-plot hiss-spectrum">
  <div className="spectrum-top-controls">
   <div className="segmented" role="group" aria-label="Wavelength frame"><button aria-pressed={rest} disabled={!hasRedshift} onClick={()=>{setRest(true);resetRange()}}>Rest</button><button aria-pressed={!rest} onClick={()=>{setRest(false);resetRange()}}>Observed</button></div>
   <div className="segmented" role="group" aria-label="Spectrum layout"><button aria-pressed={stack} onClick={()=>{setStack(true);resetFluxView()}}>Stacked</button><button aria-pressed={!stack} onClick={()=>{setStack(false);resetFluxView()}}>Overlaid</button></div>
   <div className="segmented" role="group" aria-label="Flux scale"><button aria-pressed={!log} onClick={()=>{setLog(false);setSpacing('');resetFluxView()}}>Linear</button><button aria-pressed={log} onClick={()=>{setLog(true);setSpacing('');resetFluxView()}}>Log</button></div>
   <label className="plot-check"><input type="checkbox" checked={lineIds} disabled={!hasRedshift} onChange={e=>setLineIds(e.target.checked)}/> Line IDs</label>
   <label className="plot-check"><input type="checkbox" checked={normalize} onChange={e=>{setNormalize(e.target.checked);setSpacing('');resetFluxView()}}/> Normalize epochs</label>
   <button className="text-button" onClick={resetProcessing}>Reset display</button>
  </div>
  <LineControls key={`${hasRedshift}-${displayReset}`} selected={lineSelection} onSelect={ids=>{setLineSelection(ids);setLineIds(true)}} velocity={velocity} onVelocity={setVelocity} enabled={showLines} z={z}/>
  <details className="processing-options"><summary>Processing & offsets <span>{bin==='none'?'Native samples':`Binning: ${binSize} ${bin==='samples'?'samples':'µm'}`}{smooth>1?` · smoothing ${smooth}`:''}{stack&&visibleEpochs.length>1?` · epoch spacing ${number(model.step)}`:''}</span></summary>
  <div className="plot-toolbar">
   {stack&&visibleEpochs.length>1&&<div className="epoch-spacing-controls"><label>Epoch spacing<input aria-label="Epoch spacing" type="number" min="0" step="any" value={spacing} placeholder={`Auto: ${number(model.autoStep)}`} onChange={e=>changeSpacing(e.target.value)}/></label><button className="btn" disabled={!model.valid||model.step===0} onClick={()=>changeSpacing(String(model.step*.75))}>Closer</button><button className="btn" disabled={!model.valid} onClick={()=>changeSpacing(String((model.step||model.autoStep)*1.25))}>Farther</button><button className="btn" aria-pressed={spacing===''&&viewStep===null} onClick={()=>changeSpacing('')}>Auto spacing</button></div>}
  </div>
  {stack&&visibleEpochs.length>1&&<p className="spacing-help">{spacing!==''?'Manual':viewStep!==null?'Held':'Automatic'} spacing: {number(model.step)} between visible epochs. Auto uses the typical middle 80% flux range, so isolated spikes do not force large gaps. Peaks may overlap; all samples are retained.</p>}
  <div className="plot-toolbar processing-toolbar">
   <label>Binning<select aria-label="Spectral binning" value={bin} onChange={e=>{const v=e.target.value as Processing['bin'];setBin(v);setBinSize(v==='wavelength'?'0.02':'5');resetFluxView()}}><option value="none">Off · native samples</option><option value="samples">Samples per bin</option><option value="wavelength">Wavelength width</option></select></label>
   {bin!=='none'&&<label>{bin==='samples'?'Samples per bin':`Bin width (µm, ${rest?'rest':'observed'})`}<input aria-label="Bin size" type="number" min={bin==='samples'?1:.000001} max={bin==='samples'?10000:undefined} step={bin==='samples'?1:'any'} value={binSize} onChange={e=>{setBinSize(e.target.value);resetFluxView()}}/></label>}
   <label>Boxcar smoothing<select aria-label="Spectrum smoothing" value={smooth} onChange={e=>{setSmooth(Number(e.target.value));resetFluxView()}}>{[1,3,7,15].map(n=><option key={n} value={n}>{n===1?'Off':`${n} ${bin==='none'?'samples':'bins'}`}</option>)}</select></label>
   <label className="plot-check"><input type="checkbox" checked={original} disabled={!transformed} onChange={e=>setOriginal(e.target.checked)}/> Show original trace</label>
   <label className="plot-check"><input type="checkbox" checked={errors} onChange={e=>setErrors(e.target.checked)}/> 1σ uncertainty</label>
   <label className="plot-check"><input type="checkbox" checked={flagged} onChange={e=>setFlagged(e.target.checked)}/> Include flagged samples</label>
  </div>
  </details>
  <div className="spectral-workspace"><div className="spectrum-canvas">
  <div className="plot-navigation" aria-label="Plot navigation">
   <div className="plot-mode"><button className="btn" aria-pressed={navMode==='wavelength'} onClick={()=>setNavMode('wavelength')}>Zoom wavelengths</button><button className="btn" aria-pressed={navMode==='box'} onClick={()=>setNavMode('box')}>Box zoom</button><button className="btn" aria-pressed={navMode==='pan'} onClick={()=>setNavMode('pan')}>Pan</button></div>
   <button className="btn" aria-label="Zoom in" disabled={!model.valid} onClick={()=>zoom(.5)}>＋</button><button className="btn" aria-label="Zoom out" disabled={!model.valid} onClick={()=>zoom(2)}>−</button>
   <button className="btn" disabled={!history.length} onClick={undo}>Undo zoom</button><button className="btn" aria-pressed={central&&ymin===''&&ymax===''} onClick={()=>fitY(true)}>Auto Y</button><button className="btn" aria-pressed={!central&&ymin===''&&ymax===''} onClick={()=>fitY(false)}>Show all flux</button><button className="btn" onClick={defaultRange}>Default range ≤22 µm</button><button className="btn" onClick={fullRange}>All wavelengths</button>
  </div>
  <details className="navigation-help"><summary>Drag a box to zoom · double-click for ≤22 µm <span>More controls</span></summary><p>Choose Zoom wavelengths to fit the flux axis automatically, or Pan to move the view. Shift+drag: box zoom · Alt+drag: pan · Ctrl/⌘+wheel: zoom. Keyboard: +/− zoom, arrows pan, Home restores the default view up to 22 µm. Auto Y estimates the range from median-smoothed flux; Show all flux includes every peak.</p></details>
  <div className="processing-status" role="status">{entries.length} products · {visibleEpochs.length} epochs · {sampleCount.toLocaleString()} displayed samples{transformed?' · processed view':' · native sampling'}{!binValid?' · Enter a positive bin size (1–10,000 whole samples).':''}</div>
  {model.valid?<svg ref={svgRef} className={'spectral-svg interactive-spectrum '+(navMode==='pan'?'pan-mode':'zoom-mode')} viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0} aria-label={`Interactive JWST spectra: ${axisTitle} against wavelength in micrometres`} onPointerDown={beginDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={clearGesture} onLostPointerCapture={clearGesture} onPointerLeave={()=>{if(!gestureRef.current)setHover(null)}} onDoubleClick={defaultRange} onKeyDown={e=>{if(e.key==='Escape'){clearGesture();return}if(['+','=','-','Home','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();if(e.key==='Home')defaultRange();else if(e.key==='+'||e.key==='=')zoom(.5);else if(e.key==='-')zoom(2);else {const dx=e.key==='ArrowLeft'?-.2:e.key==='ArrowRight'?.2:0,dy=e.key==='ArrowDown'?-.2:e.key==='ArrowUp'?.2:0;applyView(boundedRange(panRange([model.x0,model.x1],dx),[model.dataX0,model.dataX1]),panRange([model.y0,model.y1],dy),model.step)}}}}>
   <defs><clipPath id="spectrum-clip"><rect x={L} y={T} width={W-L-R} height={H-T-B}/></clipPath></defs><rect x={L} y={T} width={W-L-R} height={H-T-B} fill="#fbfcfa"/>
   <g className="spectral-line-markers" aria-label="Spectral reference markers">{markers.map(l=>{const x=L+(l.x-model.x0)/(model.x1-model.x0)*(W-L-R);return <line key={l.id} data-line-id={l.id} data-wavelength={l.x} x1={x} x2={x} y1={T} y2={H-B} stroke="#9b9eab" strokeDasharray="3 5" strokeWidth=".85"><title>{l.label} · rest {l.wave} µm · displayed {number(l.x)} µm</title></line>})}{markerLabels.map((l,i)=>{const x=L+((l.x+l.last)/2-model.x0)/(model.x1-model.x0)*(W-L-R),label=l.names.join('/');return <text key={i} transform={`translate(${x} ${T-8}) rotate(-65)`} fontSize="11" textAnchor="start"><title>{label}</title>{label.length>18?label.slice(0,16)+'…':label}</text>})}</g>
   {Array.from({length:6},(_,i)=>{const v=model.y0+(model.y1-model.y0)*i/5,py=T+(1-i/5)*(H-T-B);return <g key={i}><line x1={L} x2={W-R} y1={py} y2={py} stroke="#e2e8e1"/><text x={L-12} y={py+4} textAnchor="end">{number(v)}</text></g>})}
   {Array.from({length:7},(_,i)=>{const x=model.x0+(model.x1-model.x0)*i/6,px=L+(W-L-R)*i/6;return <g key={i}><line x1={px} x2={px} y1={T} y2={H-B} stroke="#edf0ec"/><text x={px} y={H-B+26} textAnchor="middle">{number(x)}</text></g>})}
   <g clipPath="url(#spectrum-clip)"><g transform={gesture?.mode==='pan'?`translate(${(gesture.current[0]-gesture.start[0])*(W-L-R)} ${(gesture.current[1]-gesture.start[1])*(H-T-B)})`:undefined}>{model.paths.map((s,i)=><g key={i}>{original&&transformed&&<path d={s.rawPath} stroke={s.colour} strokeOpacity=".2" strokeWidth=".65" fill="none"/>}{errors&&<path d={s.band} fill={s.colour} fillOpacity=".12"/>}<path d={s.d} stroke={s.colour} strokeWidth="1.15" strokeLinecap="round" fill="none" vectorEffect="non-scaling-stroke"/></g>)}</g></g>
   {stack&&epochAnnotations.map(a=><g className="epoch-annotation" key={a.epoch.key}><line x1={L+(a.x-model.x0)/(model.x1-model.x0)*(W-L-R)} x2={W-R+5} y1={T+(1-(a.y-model.y0)/(model.y1-model.y0))*(H-T-B)} y2={a.py} stroke={colours[a.epoch.index%colours.length]} strokeWidth=".7" strokeOpacity=".4" clipPath="url(#spectrum-clip)"/><text x={W-R+10} y={a.py+4} style={{fill:colours[a.epoch.index%colours.length]}}>{spectrumDate(a.epoch.start)}</text></g>)}
   <line x1={L} x2={W-R} y1={H-B} y2={H-B} stroke="#90a298"/><line x1={L} x2={L} y1={T} y2={H-B} stroke="#90a298"/><text x={(W+L-R)/2} y={H-14} textAnchor="middle">{rest?'Rest-frame':'Observed'} wavelength (µm)</text><text transform={`translate(23 ${(H-B+T)/2}) rotate(-90)`} textAnchor="middle">{axisTitle}</text>{cursor!==null&&<line x1={L+hover!*(W-L-R)} x2={L+hover!*(W-L-R)} y1={T} y2={H-B} stroke="#9aaa9c" strokeDasharray="4 4"/>}
   {gesture&&gesture.mode!=='pan'&&<rect className="zoom-selection" x={L+Math.min(gesture.start[0],gesture.current[0])*(W-L-R)} y={gesture.mode==='box'?T+Math.min(gesture.start[1],gesture.current[1])*(H-T-B):T} width={Math.abs(gesture.current[0]-gesture.start[0])*(W-L-R)} height={gesture.mode==='box'?Math.abs(gesture.current[1]-gesture.start[1])*(H-T-B):H-T-B}/>}
  </svg>:<div className="plot-empty">{!entries.length?(loading?'Loading spectra…':'Choose an epoch or channel in Spectra to plot.') : !binValid?'Enter a valid bin size.':'No usable samples in this range. Adjust the limits or choose All wavelengths to include data beyond 22 µm.'}</div>}
  <div className="view-readout" aria-live="polite">{model.valid?`${number(model.x0)}–${number(model.x1)} µm · Y ${number(model.y0)} to ${number(model.y1)} · ${model.visible.toLocaleString()} samples in wavelength view · ${model.outside.toLocaleString()} outside Y limits`:''}{central&&ymin===''&&ymax===''?' · Auto Y uses a 7-sample median and the central 98% within each epoch and the visible wavelengths. Traces and exports retain all samples; Show all flux reveals clipped peaks.':''}{viewStep!==null&&stack?' · Epoch spacing held during box zoom/pan; Auto Y recalculates it.':''}</div>
  <div className="plot-legend">{visibleEpochs.map(e=><span key={e.key}><i style={{background:colours[e.index%colours.length]}}/>{epochLabel(e)} · {entries.filter(p=>e.productIds.includes(p.product.id)).length} products{!model.offsets.has(e.key)?' · no samples in view':stack?` · offset +${number(model.offsets.get(e.key)||0)}`:''}</span>)}</div>
  <div className="plot-cursor" aria-live="off">{cursor===null?'Move over the plot for processed flux in µJy, before normalization and offsets.':nearest.map(({point:p,epoch:e,colour})=><span key={e.key} style={{color:colour}}>{e.start===null?'Undated':`Epoch ${e.index+1}`}: {number(p.wave)} µm · {number(p.flux*1e6)} µJy{p.error!==null?` ± ${number(p.error*1e6)}`:''}</span>)}</div>
  <div className="plot-limits"><span>Plot range</span>{[['Wavelength minimum',xmin,setXmin],['Wavelength maximum',xmax,setXmax],['Flux minimum',ymin,setYmin],['Flux maximum',ymax,setYmax]].map(([label,value,setter])=><label key={label as string}><span>{label as string}</span><input aria-label={label as string} type="number" step="any" placeholder={label==='Wavelength maximum'?'Auto ≤22':'Auto'} value={value as string} onChange={e=>(setter as (v:string)=>void)(e.target.value)}/></label>)}<button className="text-button" onClick={defaultRange}>Reset range</button></div>
  </div>{selectionPanel}</div>
  <div className="plot-exports"><button className="btn" onClick={exportOriginal} disabled={loading||!entries.length}>Export original CSV</button><button className="btn" onClick={exportProcessed} disabled={!binValid||loading||!entries.length}>Export processed CSV</button></div>
  <details className="plot-method"><summary>Display, processing & data notes</summary><p className="spectral-note">The initial wavelength view ends at 22 µm, or the last available wavelength when shorter. All wavelengths restores the full coverage. Auto Y applies a centred 7-sample moving median separately within continuous runs and uses the resulting 1st–99th percentiles per epoch; masks, non-finite values and gaps are not bridged. This changes axis limits only. Narrow peaks can fall outside the view; Show all flux includes their full range.</p><p className="spectral-note">A new epoch begins after a gap of more than 24 hours between consecutive observation start times; exactly 24 hours stays in one epoch. All channels and orders in an epoch share its colour and offset. Unknown times form a separate group. {normalize?'Each epoch is divided by the median absolute flux of its selected, quality-filtered native samples, using one scale across its products. Zero-only epochs use a scale of 1 Jy.':'Flux is shown in µJy.'} {stack?'Offsets are arbitrary display shifts.':''} {log?'Log₁₀ is applied before the epoch offset; non-positive flux and uncertainty bands crossing zero are hidden.':''}</p>
  <p className="spectral-note">Binning takes the arithmetic mean of samples within each segment, with no interpolation or averaging between products. Wavelength bins start at integer multiples of the chosen width in the displayed frame. Smoothing is a centred moving mean after binning; edge windows are shorter. Masks and wavelength gaps split processing. Errors propagate as √Σσ²/N when every contributing error is available, assuming independent inputs; resampled archive pixels and neighbouring smoothed points can be correlated. {flagged?'Quality-flagged samples are included.':'Nonzero-DQ samples are excluded.'} {rest?'Wavelength alone is divided by (1 + z); physical flux remains observed-frame.':''} Original FITS and CSV samples remain unchanged. Products can share input exposures and are not independent measurements.</p></details>
 </section>;
}
