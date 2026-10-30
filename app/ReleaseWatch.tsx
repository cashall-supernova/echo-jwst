'use client';
import {Clock3,ArrowUpRight} from 'lucide-react';
import {ReleaseRecord,Supernova,mjdDate,mastUrl} from '@/lib/catalog';

const day=(mjd:number|null)=>mjd===null?'Not listed':mjdDate(mjd);
export default function ReleaseWatch({sn,checkedAt}:{sn:Supernova;checkedAt?:string}){
 const records=sn.releaseWatch||[];
 if(!records.length)return null;
 const waiting=records.filter(r=>r.status==='exclusive'),history=records.filter(r=>r.status!=='exclusive');
 function group(rows:ReleaseRecord[]){
  const groups=new Map<string,ReleaseRecord[]>();
  for(const r of rows){const key=[r.instrument,r.filter,r.proposal,day(r.start),day(r.release),r.status].join('|');groups.set(key,[...(groups.get(key)||[]),r])}
  return [...groups.values()].sort((a,b)=>(a[0].release??Infinity)-(b[0].release??Infinity)||a[0].filter.localeCompare(b[0].filter));
 }
 function table(rows:ReleaseRecord[]){return <div className="table-scroll"><table className="release-table"><thead><tr><th>OBSERVED · UTC</th><th>INSTRUMENT / FILTER</th><th>PROGRAM</th><th>EXPECTED PUBLIC · UTC</th><th>STATUS</th></tr></thead><tbody>{group(rows).map(group=>{
  const r=group[0],past=r.release!==null&&(r.release-40587)*86400000<Date.now();
  return <tr key={r.id}><td className="mono">{day(r.start)}{r.end!==null&&day(r.end)!==day(r.start)&&<small>through {day(r.end)}</small>}</td><td>{r.instrument.split('/')[0]} · <b>{r.filter}</b><small>{group.length} archive record{group.length===1?'':'s'} · level {[...new Set(group.map(x=>x.calibLevel))].join(', ')}</small></td><td><a href={`https://www.stsci.edu/jwst-program-info/program/?program=${encodeURIComponent(r.proposal)}`} target="_blank" rel="noreferrer">{r.proposal} ↗</a></td><td className="mono">{day(r.release)}</td><td><span className={'release-status '+r.status}>{r.status==='exclusive'?'Not yet public':r.status==='public'?'Now public':'Status unconfirmed'}</span><small>{r.status==='exclusive'&&past?'Expected date passed; MAST still reports exclusive access':r.status==='public'?`Release confirmed ${r.releasedAt?.slice(0,10)||r.lastSeen.slice(0,10)}`:r.status==='unconfirmed'?'Previously matched record; no current matching confirmation':''}</small></td></tr>
 })}</tbody></table></div>}
 return <section className="release-panel"><div className="section-head"><div><h2><Clock3 size={17}/> Not yet public <span className="count-badge">{waiting.length}</span></h2><p>Archive metadata at this position. Protected image pixels have not been downloaded.</p></div><a className="text-button" href={mastUrl(sn)} target="_blank" rel="noreferrer">Check MAST <ArrowUpRight size={14}/></a></div>
 {waiting.length>0?table(waiting):<p className="release-note">No observations on this watch list are currently confirmed as exclusive access.</p>}
 {history.length>0&&<details className="release-history"><summary>Previously watched observations ({history.length})</summary>{table(history)}</details>}
 <p className="release-note">Checked daily{checkedAt?` · last metadata check ${checkedAt.slice(0,10)} UTC`:''}. Release dates can change. Images are added after MAST confirms public access and a usable cutout is obtained. Footprint coverage does not confirm an SN detection.</p>
 </section>
}
