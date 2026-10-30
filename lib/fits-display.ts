// Reader for the uncompressed float32 primary HDUs written by our cutout
// pipeline. This deliberately rejects other FITS formats, rather than silently
// displaying the wrong array. Downloaded science FITS are never modified.
export type DisplayPixels = {width:number; height:number; channels:Float32Array[]; sorted:number[][]; unit:string};
export function readDisplayFits(buffer:ArrayBuffer):DisplayPixels {
  const view=new DataView(buffer), decoder=new TextDecoder('ascii');
  const header:Record<string,string>={}; let offset=0, ended=false;
  for(;offset+80<=buffer.byteLength;offset+=80){
    const card=decoder.decode(new Uint8Array(buffer,offset,80)),key=card.slice(0,8).trim();
    if(key==='END'){offset+=80;ended=true;break;}
    if(card[8]==='=')header[key]=card.slice(10).split(' / ')[0].trim();
    if(offset>100000)throw Error('FITS header exceeds the display limit.');
  }
  const width=Number(header.NAXIS1),height=Number(header.NAXIS2),axes=Number(header.NAXIS);
  const count=axes===3?Number(header.NAXIS3):1;
  if(!ended||Number(header.BITPIX)!==-32||![2,3].includes(axes)||![1,3].includes(count)||
    !Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width*height*count>4000000)
    throw Error('This FITS format is not supported by the interactive preview.');
  offset=Math.ceil(offset/2880)*2880;
  if(offset+width*height*count*4>buffer.byteLength)throw Error('The FITS download is incomplete.');
  const bscale=Number(header.BSCALE??1),bzero=Number(header.BZERO??0),channels:Float32Array[]=[];
  for(let c=0;c<count;c++){
    const pixels=new Float32Array(width*height);
    for(let i=0;i<pixels.length;i++)pixels[i]=view.getFloat32(offset+4*(c*pixels.length+i),false)*bscale+bzero;
    channels.push(pixels);
  }
  const sorted=channels.map(p=>Array.from(p).filter(Number.isFinite).sort((a,b)=>a-b));
  if(sorted.some(p=>p.length===0))throw Error('No finite pixels are available.');
  return {width,height,channels,sorted,unit:(header.BUNIT||'').replaceAll("'",'').trim()};
}
export function percentile(sorted:number[],percent:number){
  const i=(sorted.length-1)*Math.max(0,Math.min(100,percent))/100,lo=Math.floor(i),hi=Math.ceil(i);
  return sorted[lo]+(sorted[hi]-sorted[lo])*(i-lo);
}
export function renderDisplay(pixels:DisplayPixels,black:number,white:number,strength:number){
  const {width,height,channels,sorted}=pixels;
  const limits=sorted.map(s=>[percentile(s,black),percentile(s,white)]);
  const rgba=new Uint8ClampedArray(width*height*4);
  let clipped=0,validCount=0;
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const i=y*width+x,out=((height-1-y)*width+x)*4;
    const valid=channels.every(c=>Number.isFinite(c[i]));
    rgba[out+3]=255;
    if(!valid)continue;
    validCount++;
    if(channels.some((c,k)=>c[i]>limits[k][1]))clipped++;
    for(let c=0;c<3;c++){
      const k=channels.length===1?0:c,[lo,hi]=limits[k];
      const normalized=Math.max(0,Math.min(1,(channels[k][i]-lo)/Math.max(hi-lo,1e-12)));
      rgba[out+c]=255*(strength>0?Math.asinh(normalized*strength)/Math.asinh(strength):normalized);
    }
  }
  return {rgba,limits,clipped:validCount?clipped/validCount:0};
}
