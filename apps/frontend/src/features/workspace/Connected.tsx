import {lazy,useSyncExternalStore} from 'react'
import {useQuery} from '@tanstack/react-query'
import {workspaceApi} from './api'
const Overview=lazy(()=>import('./Pages').then(m=>({default:m.Overview})))
const Settlement=lazy(()=>import('./Pages').then(m=>({default:m.Settlement})))
const History=lazy(()=>import('./Pages').then(m=>({default:m.History})))
const subscribe=(notify:()=>void)=>{window.addEventListener('community-change',notify);return()=>window.removeEventListener('community-change',notify)}
export function useCommunityId(){const stored=useSyncExternalStore(subscribe,()=>sessionStorage.getItem('community')||'');const q=useQuery({queryKey:['communities'],queryFn:({signal})=>workspaceApi.communities(signal)});return {id:q.data?.some(c=>c.id===stored)?stored:q.data?.[0]?.id||'',query:q}}
export function CommunitySelect(){const {id,query}=useCommunityId();return <label>Active community<select aria-label="Active community" value={id} onChange={e=>{sessionStorage.setItem('community',e.target.value);window.dispatchEvent(new Event('community-change'))}}><option value="">Select community</option>{query.data?.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}
export function ConnectedOverview(){const {id}=useCommunityId();return <Overview community={id}/>}
export function ConnectedSettlement(){const {id}=useCommunityId();return <Settlement community={id}/>}
export function ConnectedHistory(){const {id}=useCommunityId();return <History key={id} community={id}/>}
