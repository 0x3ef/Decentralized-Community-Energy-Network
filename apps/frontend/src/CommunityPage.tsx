import {useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import api from './lib/api'
import {errorMessage} from './features/workspace/api'
import {useCommunityId} from './features/workspace/Connected'

export default function CommunityPage(){
 const cache=useQueryClient();const {id}=useCommunityId()
 const [name,setName]=useState('');const [boundary,setBoundary]=useState('');const [community,setCommunity]=useState('');const [busy,setBusy]=useState(false);const [output,setOutput]=useState('')
 const run=async(work:()=>Promise<unknown>)=>{setBusy(true);try{setOutput(JSON.stringify(await work(),null,2));await cache.invalidateQueries({queryKey:['communities']})}catch(e){setOutput(errorMessage(e))}finally{setBusy(false)}}
 return <section><h1>Community governance</h1><p>Describe the physical community and submit a proposal for governance review. A draft or proposal grants no operator authority. Activation, membership, nodes and meters require authorized governance.</p><fieldset disabled={busy}><legend>Propose a physical community</legend><label>Name<input value={name} onChange={e=>setName(e.target.value)}/></label><label>Physical boundary description<textarea value={boundary} onChange={e=>setBoundary(e.target.value)}/></label><button onClick={()=>run(async()=>{const {data}=await api.post('/communities',{name,boundary_description:boundary,interval_seconds:900});setCommunity(data.id);return data})}>Create draft</button><label>Community ID<input value={community||id||''} onChange={e=>setCommunity(e.target.value)}/></label><button onClick={()=>run(async()=>(await api.post(`/communities/${community||id}/propose`)).data)}>Prepare governance proposal</button></fieldset><p>Submit the returned unsigned registry transaction with your wallet. Governance reviews the boundary and policy before activation. Open ETH settlement to connect your wallet and manage SUN and test ETH after approval.</p><pre aria-live="polite" style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{output}</pre></section>
}
