import type {SpectralPoint, SpectrumProduct} from './spectra';

export type Epoch = {key:string; index:number; start:number|null; end:number|null; productIds:string[]};
export type ProcessedPoint = {wave:number; flux:number; error:number|null; dq:number; samples:number; low:number; high:number};
export type Processing = {bin:'none'|'samples'|'wavelength'; size:number; smooth:number; factor:number; flagged:boolean};

/** Epoch boundaries use consecutive observation START times, in MJD days. */
export function groupEpochs(products:Pick<SpectrumProduct,'id'|'start'>[]):Epoch[] {
  const dated=products.filter(p=>p.start!==null).sort((a,b)=>a.start!-b.start!||a.id.localeCompare(b.id));
  const epochs:Epoch[]=[];
  for(const p of dated){
    let epoch=epochs.at(-1);
    if(!epoch||p.start!-epoch.end!>1){epoch={key:p.id,index:epochs.length,start:p.start,end:p.start,productIds:[]};epochs.push(epoch)}
    epoch.end=p.start;epoch.productIds.push(p.id);
  }
  const unknown=products.filter(p=>p.start===null);
  if(unknown.length)epochs.push({key:'undated',index:epochs.length,start:null,end:null,productIds:unknown.map(p=>p.id)});
  return epochs;
}

export function median(values:number[]):number {
  if(!values.length)return 0;
  const s=values.slice().sort((a,b)=>a-b),mid=Math.floor(s.length/2);
  return s.length%2?s[mid]:(s[mid-1]+s[mid])/2;
}

function mean(points:ProcessedPoint[]):ProcessedPoint {
  const n=points.length;
  return {wave:points.reduce((s,p)=>s+p.wave,0)/n,flux:points.reduce((s,p)=>s+p.flux,0)/n,
    error:points.every(p=>p.error!==null)?Math.sqrt(points.reduce((s,p)=>s+p.error!**2,0))/n:null,
    dq:points.reduce((d,p)=>(d|p.dq)>>>0,0),samples:points.reduce((n,p)=>n+p.samples,0),low:points[0].low,high:points[n-1].high};
}

/** Sample means, not integrated-flux rebinning. Never cross a mask, gap, or segment. */
export function processSegment(points:SpectralPoint[],options:Processing):ProcessedPoint[][] {
  const factor=options.factor>0?options.factor:1;
  const steps=points.slice(1).map((p,i)=>p[0]-points[i][0]).filter(d=>d>0&&Number.isFinite(d));
  const typical=median(steps);
  const runs:ProcessedPoint[][]=[];let run:ProcessedPoint[]=[];
  const flush=()=>{if(run.length)runs.push(run);run=[]};
  for(let i=0;i<points.length;i++){
    const [w,f,e,d]=points[i];
    if(!Number.isFinite(w)||w<=0||f===null||!Number.isFinite(f)||(!options.flagged&&d!==0)){flush();continue}
    if(i>0){
      const delta=w-points[i-1][0],before=i>1?points[i-1][0]-points[i-2][0]:typical,after=i+1<points.length?points[i+1][0]-w:typical;
      if(delta<=0||(Math.max(before,after)>0&&delta>5*Math.max(before,after)))flush();
    }
    run.push({wave:w/factor,flux:f,error:e!==null&&Number.isFinite(e)&&e>=0?e:null,dq:d,samples:1,low:w/factor,high:w/factor});
  }
  flush();
  const size=Number.isFinite(options.size)&&options.size>0?options.size:1;
  return runs.map(source=>{
    let binned=source;
    if(options.bin!=='none'){
      binned=[];let bucket:ProcessedPoint[]=[];let prior=-Infinity;
      for(let i=0;i<source.length;i++){
        const key=options.bin==='samples'?Math.floor(i/Math.max(1,Math.floor(size))):Math.floor(source[i].wave/size+1e-10);
        if(bucket.length&&key!==prior){binned.push(mean(bucket));bucket=[]}
        bucket.push(source[i]);prior=key;
      }
      if(bucket.length)binned.push(mean(bucket));
    }
    const half=Math.floor(Math.max(1,Math.min(101,options.smooth))/2);
    if(!half)return binned;
    return binned.map((p,i)=>({...mean(binned.slice(Math.max(0,i-half),i+half+1)),wave:p.wave}));
  });
}

export function csvText(rows:unknown[][]):string {
  return rows.map(row=>row.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\n');
}
