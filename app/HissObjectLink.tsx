'use client';
import {archiveFetch,sitePath} from '@/lib/archive-client';
import {useEffect,useState} from 'react';
import {ArrowUpRight} from 'lucide-react';
type Link={hissId:string;imagesName?:string;spectraName?:string};
export default function HissObjectLink({name,kind,hasData}:{name:string;kind:'imagesName'|'spectraName';hasData:boolean}){
 const [links,setLinks]=useState<Link[]>([]);
 useEffect(()=>{const controller=new AbortController();archiveFetch('/api/cross-links',{cache:'no-store',signal:controller.signal}).then(r=>r.ok?r.json() as Promise<{links:Link[]}>:null).then(data=>{if(data&&Array.isArray(data.links))setLinks(data.links)}).catch(()=>{});return()=>controller.abort()},[]);
 const link=hasData?links.find(row=>row[kind]===name):null;
 if(!link)return null;
 return <a className="btn" href={'https://cashall-supernova.github.io/hiss-spectra/#'+encodeURIComponent(link.hissId)} target="_blank" rel="noopener noreferrer" title={`Open ${name} spectra and light curves in HISS`}>This SN in HISS <ArrowUpRight size={16}/></a>;
}
