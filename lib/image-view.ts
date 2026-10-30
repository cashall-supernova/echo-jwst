export type ImageView={scale:number;x:number;y:number};
export const FIT_IMAGE:ImageView={scale:1,x:0,y:0};
export const MAX_IMAGE_ZOOM=16;

// Offsets are fractions of the viewport, so resizing preserves the viewed region.
export function clampImageView(view:ImageView):ImageView{
 const scale=Math.min(MAX_IMAGE_ZOOM,Math.max(1,view.scale));
 if(scale===1)return FIT_IMAGE;
 const limit=(scale-1)/2;
 const clamp=(value:number)=>Math.max(-limit,Math.min(limit,value));
 return {scale,x:clamp(view.x),y:clamp(view.y)};
}

export function zoomImageAt(view:ImageView,factor:number,anchor={x:0,y:0}):ImageView{
 const scale=Math.min(MAX_IMAGE_ZOOM,Math.max(1,view.scale*factor));
 const ratio=scale/view.scale;
 return clampImageView({scale,x:anchor.x-(anchor.x-view.x)*ratio,y:anchor.y-(anchor.y-view.y)*ratio});
}
