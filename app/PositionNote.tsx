import type {Supernova} from '@/lib/catalog';

export default function PositionNote({sn}:{sn:Supernova}){
 const position=sn.astrometry;
 if(!position)return <p className="position-note">Pointers use the catalogue position. Its uncertainty and the image’s absolute alignment may both contribute to an apparent offset.</p>;
 if(position.status==='needs-review')return <p className="position-note">Pointers use the current catalogue position. {position.note}</p>;
 return <details className="position-note refined-position">
  <summary><strong>Refined optical position</strong><span>Gaia reference · {position.offsetArcsec.toFixed(2)}″ from {position.catalogue.source}</span></summary>
  <div className="position-evidence">
   <p>The coordinates above and all image pointers use {position.label}. {position.method}</p>
   <p>Original {position.catalogue.source}: <span className="mono">{position.catalogue.ra.toFixed(7)}°, {position.catalogue.dec.toFixed(7)}°</span>.
    {position.catalogue.raErrorArcsec!==undefined&&position.catalogue.decErrorArcsec!==undefined&&<> Reported coordinate errors: RA {position.catalogue.raErrorArcsec.toFixed(2)}″, Dec {position.catalogue.decErrorArcsec.toFixed(2)}″.</>}</p>
   <p>{position.uncertaintyNote} The archive image WCS is unchanged. Reviewed {position.reviewedAt.slice(0,10)}; a catalogue-position change suspends this refinement until it is checked again.</p>
   <div className="position-references">{position.references.map(ref=><a key={ref.url} href={ref.url} target="_blank" rel="noreferrer">{ref.label} ↗</a>)}</div>
  </div>
 </details>;
}
