import type {ReactNode} from 'react'
import {errorMessage} from '../../features/workspace/api'
export function Feedback({loading,error,empty,children}:{loading?:boolean;error?:unknown;empty?:boolean;children:ReactNode}){
 if(loading)return <p role="status" className="animate-pulse p-6">Loading current records…</p>
 if(error)return <p role="alert" className="rounded-xl border border-red-300 bg-red-50 p-4 text-red-900">{errorMessage(error)}</p>
 if(empty)return <p className="rounded-xl border border-dashed p-8">No records yet. Only verified backend records appear here.</p>
 return children
}
export function Metric({label,value}:{label:string;value:string}){return <article className="rounded-2xl border border-emerald-900/10 bg-white p-5 text-slate-900 shadow-sm"><p className="text-sm text-slate-500">{label}</p><strong className="mt-2 block text-2xl">{value}</strong></article>}
export const energy=(wh:number)=>`${(wh/1000).toLocaleString(undefined,{maximumFractionDigits:3})} kWh`
