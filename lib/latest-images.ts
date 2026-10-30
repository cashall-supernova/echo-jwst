import type {Supernova,Stamp} from './catalog';
const mjdDate=(mjd:number)=>Number.isFinite(mjd)?new Date((mjd-40587)*86400000).toISOString().slice(0,10):'Unknown';
export type LatestImageGroup={key:string;sn:Supernova;instrument:string;program:string;observed:string;available:string|null;source:'release'|'confirmed'|'indexed'|'unknown';images:Stamp[]};
export function imageAvailability(sn:Supernova,image:Stamp):{date:string|null;source:LatestImageGroup['source']}{
 if(typeof image.publicReleaseMjd==='number'&&Number.isFinite(image.publicReleaseMjd)&&image.publicReleaseMjd>0)return {date:mjdDate(image.publicReleaseMjd),source:'release'};
 const watched=sn.releaseWatch?.find(w=>w.obsId===image.obsId&&w.status==='public');
 if(watched?.releasedAt&&Number.isFinite(Date.parse(watched.releasedAt)))return {date:watched.releasedAt.slice(0,10),source:'confirmed'};
 if(image.firstIndexedAt&&Number.isFinite(Date.parse(image.firstIndexedAt)))return {date:image.firstIndexedAt.slice(0,10),source:'indexed'};
 return {date:null,source:'unknown'};
}
export function latestObservation(sn:Supernova):number{
 return Math.max(0,...[...sn.observations,...(sn.releaseWatch||[]).filter(o=>o.status==='exclusive')].map(o=>o.start??0));
}
export function latestPublicRelease(sn:Supernova):ReturnType<typeof imageAvailability>{
 return sn.observations.map(image=>imageAvailability(sn,image)).sort((a,b)=>(b.date||'').localeCompare(a.date||''))[0]||{date:null,source:'unknown'};
}
export function compareImageDates(a:Supernova,b:Supernova,sort:'released'|'observed'):number{
 return (sort==='released'?(latestPublicRelease(b).date||'').localeCompare(latestPublicRelease(a).date||''):0)||latestObservation(b)-latestObservation(a)||a.name.localeCompare(b.name);
}
export function latestImageGroups(objects:Supernova[]):LatestImageGroup[]{
 const groups=new Map<string,LatestImageGroup>();
 for(const sn of objects)for(const image of sn.observations){
  const {date,source}=imageAvailability(sn,image),observed=mjdDate(image.start),instrument=image.instrument.split('/')[0];
  const key=[sn.name,date,source,observed,instrument,image.proposal].join('|');
  const group=groups.get(key)||{key,sn,instrument,program:image.proposal,observed,available:date,source,images:[]};
  group.images.push(image);groups.set(key,group);
 }
 return [...groups.values()].sort((a,b)=>(b.available||'').localeCompare(a.available||'')||b.observed.localeCompare(a.observed)||a.sn.name.localeCompare(b.sn.name));
}
