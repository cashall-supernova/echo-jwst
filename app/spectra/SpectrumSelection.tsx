'use client';
import {groupEpochs} from '@/lib/spectrum-processing';
import {EPOCH_COLOURS} from '@/lib/spectrum-view';
import {spectrumDate,spectrumDownload} from '@/lib/spectra';
import type {SpectrumProduct} from '@/lib/spectra';
export default function SpectrumSelection({products,chosen,onChange}:{products:SpectrumProduct[];chosen:string[];onChange:(ids:string[])=>void}){
 const epochs=groupEpochs(products);
 return <aside className="spectrum-selection" aria-label="Spectra to plot"><div className="selection-title"><h3>Spectra to plot</h3><span>{chosen.length} / {products.length} shown</span></div><div className="selection-actions"><button onClick={()=>onChange(products.map(p=>p.id))}>Show all</button><button onClick={()=>onChange([])}>Hide all</button></div>
 <div className="epoch-choices">{epochs.map(e=>{const ps=products.filter(p=>e.productIds.includes(p.id)),n=ps.filter(p=>chosen.includes(p.id)).length;return <div className="epoch-choice" key={e.key}><label className="epoch-toggle"><input type="checkbox" checked={n===ps.length} ref={el=>{if(el)el.indeterminate=n>0&&n<ps.length}} onChange={ev=>onChange([...chosen.filter(id=>!e.productIds.includes(id)),...(ev.target.checked?e.productIds:[])])}/><i style={{background:EPOCH_COLOURS[e.index%EPOCH_COLOURS.length]}}/><span>{spectrumDate(e.start)}<small>Epoch {e.index+1} · {n}/{ps.length} products</small></span></label>
 <details><summary>Channels & products</summary>{ps.map(p=><div className="channel-choice" key={p.id}><label><input type="checkbox" aria-label={`Plot ${p.filename}`} checked={chosen.includes(p.id)} onChange={ev=>onChange(ev.target.checked?[...chosen,p.id]:chosen.filter(id=>id!==p.id))}/><span>{p.instrument.replace('NIRSPEC','NIRSpec')}<small>{p.configuration}</small></span></label><div className="channel-links">{p.proposal?.trim()&&<a href={`https://www.stsci.edu/jwst-program-info/program/?program=${encodeURIComponent(p.proposal.trim())}`} target="_blank" rel="noreferrer">Program {p.proposal} ↗</a>}<a href={spectrumDownload(p.uri)} target="_blank" rel="noreferrer" title={p.filename}>FITS ↗</a></div></div>)}</details></div>})}</div>
 <p>All channels in an epoch share a colour and offset.</p></aside>
}
