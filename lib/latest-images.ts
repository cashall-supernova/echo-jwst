import type {Supernova,Stamp} from './catalog';
const mjdDate=(mjd:number)=>Number.isFinite(mjd)?new Date((mjd-40587)*86400000).toISOString().slice(0,10):'Unknown';
export type Activity={date:string|null;timestamp:number;reason:'SN added'|'New image match'|'JWST release'|'Public confirmed'|'Unknown'};
export type ImageDateSort='recent'|'released'|'observed';
export type LatestImageGroup={key:string;sn:Supernova;instrument:string;program:string;observed:string;available:string|null;source:'release'|'confirmed'|'indexed'|'unknown';images:Stamp[];activity:Activity};
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
export function latestActivity(sn:Supernova):Activity{
 let latest:Activity={date:null,timestamp:0,reason:'Unknown'};
 const add=(timestamp:number,reason:Activity['reason'])=>{if(Number.isFinite(timestamp)&&timestamp>latest.timestamp)latest={date:new Date(timestamp).toISOString().slice(0,10),timestamp,reason}};
 // Keep an SN addition as the explanation when its first images arrive together.
 if(sn.firstIndexedAt)add(Date.parse(sn.firstIndexedAt),'SN added');
 for(const image of sn.observations){
  if(image.firstIndexedAt)add(Date.parse(image.firstIndexedAt),'New image match');
  if(typeof image.publicReleaseMjd==='number'&&Number.isFinite(image.publicReleaseMjd)&&image.publicReleaseMjd>0)add((image.publicReleaseMjd-40587)*86400000,'JWST release');
  else{
   const watched=sn.releaseWatch?.find(w=>w.obsId===image.obsId&&w.status==='public');
   if(watched?.releasedAt)add(Date.parse(watched.releasedAt),'Public confirmed');
  }
 }
 return latest;
}
export function compareImageDates(a:Supernova,b:Supernova,sort:ImageDateSort):number{
 if(sort==='recent')return latestActivity(b).timestamp-latestActivity(a).timestamp||(latestPublicRelease(b).date||'').localeCompare(latestPublicRelease(a).date||'')||a.name.localeCompare(b.name);
 return (sort==='released'?(latestPublicRelease(b).date||'').localeCompare(latestPublicRelease(a).date||''):0)||latestObservation(b)-latestObservation(a)||a.name.localeCompare(b.name);
}
export function latestImageGroups(objects:Supernova[],sort:ImageDateSort='recent'):LatestImageGroup[]{
 const groups=new Map<string,LatestImageGroup>();
 for(const sn of objects)for(const image of sn.observations){
  const {date,source}=imageAvailability(sn,image),observed=mjdDate(image.start),instrument=image.instrument.split('/')[0];
  const key=[sn.name,date,source,observed,instrument,image.proposal].join('|');
  const group:LatestImageGroup=groups.get(key)||{key,sn,instrument,program:image.proposal,observed,available:date,source,images:[],activity:{date:null,timestamp:0,reason:'Unknown'}};
  group.images.push(image);groups.set(key,group);
 }
 for(const group of groups.values())group.activity=latestActivity({...group.sn,observations:group.images});
 return [...groups.values()].sort((a,b)=>(sort==='recent'?b.activity.timestamp-a.activity.timestamp:sort==='observed'?b.observed.localeCompare(a.observed):0)||(b.available||'').localeCompare(a.available||'')||b.observed.localeCompare(a.observed)||a.sn.name.localeCompare(b.sn.name));
}
