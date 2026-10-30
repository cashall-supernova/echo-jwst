'use client';
import {useEffect,useState} from 'react';
import {ArrowUpRight} from 'lucide-react';
import {archiveFetch,sitePath} from '@/lib/archive-client';
import type {SpectraCatalog,SpectralSN} from '@/lib/spectra';

export default function JwstSpectraLink({name}:{name:string}){
 const [objects,setObjects]=useState<SpectralSN[]>([]);
 useEffect(()=>{
  const controller=new AbortController();
  archiveFetch('/api/spectra',{cache:'no-store',signal:controller.signal})
   .then(r=>r.ok?r.json() as Promise<SpectraCatalog>:null)
   .then(data=>{if(data&&Array.isArray(data.objects))setObjects(data.objects)})
   .catch(()=>{});
  return()=>controller.abort();
 },[]);
 const target=objects.find(object=>object.name===name&&object.spectra.some(product=>product.status==='ready'));
 if(!target)return null;
 return <a className="btn" href={sitePath('/spectra')+'#'+encodeURIComponent(target.name)} title={`Open ${name} JWST spectra`}>JWST spectra <ArrowUpRight size={16}/></a>;
}
