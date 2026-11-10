import {useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {createWalletClient,createPublicClient,custom,formatEther,parseEther,formatUnits} from 'viem'
import type {Address,Hex,EIP1193Provider} from 'viem'
import api from '../../lib/api'
import {useCommunityId} from './Connected'
import {Feedback,Metric} from '../../components/ui/Feedback'
import {errorMessage} from './api'
import {tokenUnits} from '../../lib/blockchain/amounts'
type NativeWallet={address:Address;chain_id:number;asset:string;wallet_wei:string;available_wei:string;reserved_wei:string;earnings_wei:string;sun_units:string;escrow_sun_units:string;reserved_sun_units:string;price_wei_per_kwh:string}
type Action='deposit'|'withdraw'|'withdraw_earnings'|'approve_sun'|'approve_retirement'|'escrow_sun'|'withdraw_sun'|'execute'|'retire'
export default function NativeSettlement(){
 const {id}=useCommunityId();const cache=useQueryClient();const [amount,setAmount]=useState('0.01');const [sun,setSun]=useState('3');const [phase,setPhase]=useState('IDLE');const [error,setError]=useState('');const [hash,setHash]=useState<Hex>();const [busy,setBusy]=useState(false)
 const [batch,setBatch]=useState('');const [claim,setClaim]=useState('');const [node,setNode]=useState('');const [meter,setMeter]=useState('');const [proof,setProof]=useState('[]');const [wh,setWh]=useState('3000')
 const q=useQuery({queryKey:['native-wallet',id],queryFn:({signal})=>api.get<NativeWallet>(`/communities/${id}/native-wallet`,{signal}).then(r=>r.data),enabled:!!id,refetchInterval:15000,retry:false})
 const provider=()=>{const p=(window as unknown as {ethereum?:EIP1193Provider}).ethereum;if(!p)throw new Error('Connect an Ethereum browser wallet. Never enter a private key.');return p}
 const connect=async()=>{setBusy(true);setError('');try{const wallet=createWalletClient({transport:custom(provider())});const [address]=await wallet.requestAddresses();const challenge=(await api.post('/communities/wallet/challenge',{address})).data;const signature=await wallet.signMessage({account:address,message:challenge.message});await api.post('/communities/wallet/verify',{address,nonce:challenge.nonce,signature});await cache.invalidateQueries({queryKey:['native-wallet']})}catch(e){setError(errorMessage(e))}finally{setBusy(false)}}
 const transact=async(action:Action)=>{
  let submitted=false;setBusy(true);setError('');setHash(undefined);setPhase('AWAITING_WALLET')
  try{
   if(!q.data)throw new Error('A linked wallet and governed native deployment are required.')
   const transport=custom(provider());const wallet=createWalletClient({transport});const [account]=await wallet.requestAddresses()
   if(account.toLowerCase()!==q.data.address.toLowerCase())throw new Error('Select your verified wallet account.')
   if(await wallet.getChainId()!==q.data.chain_id){await wallet.switchChain({id:q.data.chain_id});if(await wallet.getChainId()!==q.data.chain_id)throw new Error('Network switch was not completed.')}
   const amount_base_units=action==='retire'?BigInt(wh).toString():(action.includes('sun')||action==='approve_retirement')?tokenUnits(sun,18).toString():action==='execute'?'0':parseEther(amount).toString()
   const body:Record<string,unknown>={action,amount_base_units}
   if(action==='execute')body.claim_id=claim
   if(action==='retire'){body.batch_id=batch;body.claim_id=claim;body.node_id=node;body.meter_id=meter;body.proof=JSON.parse(proof)}
   const prepared=(await api.post<{to:Address;data:Hex;value:string;chain_id:number}>(`/communities/${id}/native/prepare`,body)).data
   if(prepared.chain_id!==q.data.chain_id)throw new Error('Deployment chain changed; reload before signing.')
   setPhase('AWAITING_SIGNATURE');const tx=await wallet.sendTransaction({account,chain:null,to:prepared.to,data:prepared.data,value:BigInt(prepared.value)})
   submitted=true;setHash(tx);setPhase('CONFIRMING')
   const receipt=await createPublicClient({transport}).waitForTransactionReceipt({hash:tx,confirmations:q.data.chain_id===11155111?3:1})
   if(receipt.status!=='success')throw new Error('Transaction reverted. No settlement is confirmed.')
   setPhase('CONFIRMED');await cache.invalidateQueries({queryKey:['native-wallet']})
  }catch(e){setPhase(submitted?'RECONCILIATION_REQUIRED':'FAILED');setError(errorMessage(e))}finally{setBusy(false)}
 }
 return <section><h1>Community ETH settlement</h1><p>Approved energy allocations are funded by explicit test ETH deposits. SUN delivery, producer earnings and consumption retirement are distinct operations. No USDx, COP or fiat conversion is used.</p><button disabled={busy} onClick={connect}>Connect and verify wallet</button><Feedback loading={q.isLoading} error={q.error} empty={!id}>{q.data&&<><p>Network: {q.data.asset} · {q.data.address}</p><div className="my-6 grid gap-4 md:grid-cols-3">{[['Available deposit',q.data.available_wei],['Reserved funds',q.data.reserved_wei],['Producer earnings',q.data.earnings_wei]].map(([label,value])=><Metric key={label} label={label} value={`${formatEther(BigInt(value))} test ETH`}/>)}<Metric label="SUN held" value={formatUnits(BigInt(q.data.sun_units),18)}/><Metric label="SUN escrow available" value={formatUnits(BigInt(q.data.escrow_sun_units),18)}/><Metric label="SUN escrow reserved" value={formatUnits(BigInt(q.data.reserved_sun_units),18)}/></div><p>Governance price: {q.data.price_wei_per_kwh} wei per kWh. Consumer deposits authorize this price limit. Underfunded allocations remain unsettled.</p></>}</Feedback>
 <fieldset disabled={busy||!q.data}><legend>Native deposits and safe withdrawals</legend><label>Amount in test ETH<input inputMode="decimal" value={amount} onChange={e=>setAmount(e.target.value)}/></label><button onClick={()=>transact('deposit')}>Deposit ETH</button><button onClick={()=>transact('withdraw')}>Withdraw unreserved ETH</button><button onClick={()=>transact('withdraw_earnings')}>Claim producer earnings</button></fieldset>
 <fieldset disabled={busy||!q.data}><legend>Producer SUN escrow</legend><label>SUN quantity<input inputMode="decimal" value={sun} onChange={e=>setSun(e.target.value)}/></label><button onClick={()=>transact('approve_sun')}>Approve SUN escrow allowance</button><button onClick={()=>transact('escrow_sun')}>Escrow SUN for approved allocations</button><button onClick={()=>transact('withdraw_sun')}>Withdraw unreserved SUN</button></fieldset>
 <fieldset disabled={busy||!q.data}><legend>Approved allocation and consumption claims</legend><label>Allocation or retirement claim ID (bytes32)<input value={claim} onChange={e=>setClaim(e.target.value)}/></label><button onClick={()=>transact('execute')}>Execute funded reservation</button><label>Finalized batch ID<input value={batch} onChange={e=>setBatch(e.target.value)}/></label><label>Consumer node ID<input value={node} onChange={e=>setNode(e.target.value)}/></label><label>Approved meter ID<input value={meter} onChange={e=>setMeter(e.target.value)}/></label><label>Approved Wh<input value={wh} onChange={e=>setWh(e.target.value)}/></label><label>Merkle proof JSON<input value={proof} onChange={e=>setProof(e.target.value)}/></label><p>Retirement requires a separately approved SUN allowance to the settlement contract. It burns credits and never makes a second ETH payment.</p><button onClick={()=>transact('approve_retirement')}>Approve retirement SUN allowance</button><button onClick={()=>transact('retire')}>Retire approved, delivered energy credits</button></fieldset>
 <p role="status">{phase}</p>{hash&&<code className="break-all">{hash}</code>}{error&&<p role="alert">{error}</p>}
 </section>
}
