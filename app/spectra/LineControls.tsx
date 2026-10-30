'use client';
import {useEffect,useState} from 'react';
import {commonLineIds,LINE_GROUPS,SPECTRAL_LINES} from '@/lib/spectral-lines';
export default function LineControls({selected,onSelect,velocity,onVelocity,enabled,z}:{selected:string[];onSelect:(ids:string[])=>void;velocity:number;onVelocity:(v:number)=>void;enabled:boolean;z:number|null}){
 const [draft,setDraft]=useState(String(velocity));
 useEffect(()=>setDraft(String(velocity)),[velocity]);
 const valid=draft.trim()!==''&&Number.isFinite(Number(draft))&&Math.abs(Number(draft))<=50000;
 function update(value:string){setDraft(value);if(value.trim()!==''&&Number.isFinite(Number(value))&&Math.abs(Number(value))<=50000)onVelocity(Number(value))}
 return <div className="line-tools">
  <details className="line-chooser"><summary>Choose line markers <span>{selected.length} selected · {enabled?'shown':'hidden'}</span></summary><div className="line-chooser-body">
   <div className="line-presets"><button onClick={()=>onSelect(commonLineIds())}>Common lines</button><button onClick={()=>onSelect(SPECTRAL_LINES.map(l=>l.id))}>Select all lines</button><button onClick={()=>onSelect([])}>Clear lines</button></div>
   <div className="line-groups">{LINE_GROUPS.map(group=>{const lines=SPECTRAL_LINES.filter(l=>l.group===group),n=lines.filter(l=>selected.includes(l.id)).length;return <fieldset key={group}><legend><label><input type="checkbox" checked={n===lines.length} ref={el=>{if(el)el.indeterminate=n>0&&n<lines.length}} onChange={e=>onSelect([...selected.filter(id=>!lines.some(l=>l.id===id)),...(e.target.checked?lines.map(l=>l.id):[])])}/>{group}</label></legend>{lines.map(l=><label className="line-choice" key={l.id}><input type="checkbox" checked={selected.includes(l.id)} onChange={e=>onSelect(e.target.checked?[...selected,l.id]:selected.filter(id=>id!==l.id))}/><span>{l.label}</span><span className="mono">{l.wave.toFixed(4)} µm</span></label>)}</fieldset>})}</div>
   <p>Approximate rest wavelengths; multiplets and CO use representative values. Reference markers do not confirm a detection. <a href="https://arxiv.org/abs/2505.18507" target="_blank" rel="noreferrer">HISS NIR references ↗</a> · <a href="https://arxiv.org/abs/2211.00038" target="_blank" rel="noreferrer">JWST MIR lines ↗</a> · <a href="https://arxiv.org/abs/2404.17043" target="_blank" rel="noreferrer">MIRI/MRS references ↗</a> · <a href="https://irsa.ipac.caltech.edu/data/SPITZER/docs/irs/irsinstrumenthandbook/" target="_blank" rel="noreferrer">IRS reference lines ↗</a></p>
  </div></details>
  {enabled&&<div className="line-velocity" role="group" aria-label="Line marker velocity"><label>Velocity shift <span className="velocity-field"><input aria-label="Velocity shift in km/s" type="number" min="-50000" max="50000" step="100" value={draft} onChange={e=>update(e.target.value)}/><span>km/s</span></span></label><input aria-label="Velocity shift slider in km/s" type="range" min="-50000" max="50000" step="100" value={velocity} onChange={e=>update(e.target.value)}/><button onClick={()=>update('0')}>Reset velocity</button><p>Positive = blueshift; negative = redshift. Only the markers move.</p>{!valid&&<p role="alert">Enter a velocity between −50,000 and +50,000 km/s.</p>}</div>}
  {z===null&&<p className="line-missing">Line markers need a known catalogue redshift.</p>}
 </div>
}
