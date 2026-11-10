import {errorMessage} from './features/workspace/api'
import {useQueryClient} from '@tanstack/react-query'
import {tokenUnits,checkPurchase} from './lib/blockchain/amounts'
import {useCommunityId} from './features/workspace/Connected'
import { useState,useEffect,useRef } from 'react'
import { createWalletClient, createPublicClient, custom, parseAbi, parseUnits, keccak256, stringToHex, formatUnits } from 'viem'
import type { EIP1193Provider, Address, Hex } from 'viem'
import api from './lib/api'

const abi = parseAbi([
  'function approve(address spender,uint256 amount) returns (bool)',
  'function placeSellOrder(uint256 amount,uint256 pricePerToken,uint256 expiresAt) returns (uint256)',
  'function fillBestOrder(uint256 amount,uint256 maxPricePerToken)', 'function fillOrder(uint256 id,uint256 amount)', 'function cancelOrder(uint256 id)',
  'function retire(bytes32 id)',
])
type Balances = { address: Address; sun_base_units: string; usdx_base_units: string; sun_decimals: number; usdx_decimals: number; contracts: {chain_id:number; sun_address:Address; payment_address:Address; marketplace_address:Address; compensation_address:Address} }

export default function CommunityPage() {
  const cache=useQueryClient()
  const {id:activeCommunity}=useCommunityId()
  const [chosenCommunity,setCommunity]=useState('')
  const community=chosenCommunity||activeCommunity
  const [name, setName] = useState('')
  const [quantity, setQuantity] = useState('3')
  const [price, setPrice] = useState('450')
  const [order, setOrder] = useState('0')
  const [retirement, setRetirement] = useState('')
  const [injection, setInjection] = useState('')
  const [withdrawal, setWithdrawal] = useState('')
  const [balances, setBalances] = useState<Balances>()
  const [output, setOutput] = useState('')
  const [busy, setBusy] = useState(false)
  const [phase,setPhase]=useState('IDLE')
  const submitted=useRef(false)
  const [hash,setHash]=useState<Hex>()
  useEffect(()=>{const clear=()=>{setBalances(undefined);setHash(undefined);setPhase('IDLE')};window.addEventListener('community-change',clear);return()=>window.removeEventListener('community-change',clear)},[])
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);submitted.current=false;setHash(undefined);setPhase('AWAITING_WALLET')
    try { setOutput(JSON.stringify(await work(), (_, value) => typeof value === 'bigint' ? value.toString() : value, 2)) }
    catch (error) { setPhase(submitted.current?'RECONCILIATION_REQUIRED':'FAILED');setOutput(errorMessage(error)) }
    finally { setBusy(false);cache.invalidateQueries({queryKey:["communities"]});cache.invalidateQueries({queryKey:["statement"]}) }
  }
  const provider = () => {
    const ethereum = (window as unknown as { ethereum?: EIP1193Provider }).ethereum
    if (!ethereum) throw new Error('Connect a browser EVM wallet to the local development chain.')
    return ethereum
  }
  const load = async () => { const {data} = await api.get<Balances>(`/communities/${community}/wallet`); setBalances(data); return data }
  const connect = async () => {
    const wallet = createWalletClient({transport:custom(provider())})
    const [address] = await wallet.requestAddresses()
    const challenge = (await api.post('/communities/wallet/challenge',{address})).data
    const signature = await wallet.signMessage({account:address,message:challenge.message})
    await api.post('/communities/wallet/verify',{address,nonce:challenge.nonce,signature})
    return load()
  }
  const transact = async (address: Address, functionName: 'approve'|'placeSellOrder'|'fillOrder'|'fillBestOrder'|'cancelOrder'|'retire', args: readonly [bigint] | readonly [Hex] | readonly [bigint,bigint] | readonly [Address,bigint] | readonly [bigint,bigint,bigint]) => {
    if (!balances) throw new Error('Load your linked wallet first.')
    const transport=custom(provider())
    const wallet=createWalletClient({transport})
    const [account]=await wallet.requestAddresses()
    if (account.toLowerCase() !== balances.address.toLowerCase()) throw new Error('Select the linked wallet account.')
    if (await wallet.getChainId() !== balances.contracts.chain_id) throw new Error('Switch your wallet to the registered community chain.')
    setPhase('AWAITING_SIGNATURE')
    const hash=await wallet.writeContract({account,chain:null,address,abi,functionName,args})
    submitted.current=true;setHash(hash);setPhase('CONFIRMING')
    const receipt=await createPublicClient({transport}).waitForTransactionReceipt({hash})
    if (receipt.status !== 'success') throw new Error('Transaction reverted; accounting remains unconfirmed.')
    setPhase('CONFIRMED');await load()
    return hash
  }
  const trade = async () => {
    if (!balances) throw new Error('Load wallet first.')
    const {data}=await api.get<{order:[number,string,string,string]}>(`/communities/${community}/orders/${order}`)
    const cost=(tokenUnits(quantity,18)*BigInt(data.order[3])+10n**18n-1n)/10n**18n
    const current=(await api.get<Balances & {usdx_marketplace_allowance:string}>(`/communities/${community}/wallet`)).data
    checkPurchase(BigInt(current.usdx_base_units),BigInt(current.usdx_marketplace_allowance),cost)
    const hash=await transact(balances.contracts.marketplace_address,'fillOrder',[BigInt(order),tokenUnits(quantity,18)])
    return (await api.post(`/communities/${community}/trades/reconcile`,{transaction_hash:hash})).data
  }
  const burn = async () => {
    if (!balances) throw new Error('Load wallet first.')
    const hash=await transact(balances.contracts.compensation_address,'retire',[keccak256(stringToHex(retirement))])
    return (await api.post(`/communities/compensations/${retirement}/confirm`,{transaction_hash:hash})).data
  }
  return <section>
    <h1>Community energy settlement</h1>
    <p>SUN represents verified energy credits. USDx is unbacked simulated Colombian peso points for local demonstrations. Trading credits does not physically deliver electricity.</p>
    <fieldset disabled={busy}>
      <legend>Community and wallet</legend>
      <label>Community name <input value={name} onChange={e=>setName(e.target.value)} /></label>
      <button onClick={()=>run(async()=>{const {data}=await api.post('/communities',{name});setCommunity(data.id);return data})}>Create community</button>
      <label>Community ID <input value={community} onChange={e=>setCommunity(e.target.value)} /></label>
      <button onClick={()=>run(connect)}>Connect and prove wallet ownership</button>
      <button onClick={()=>run(load)}>Refresh balances</button>
      {balances && <p>{formatUnits(BigInt(balances.sun_base_units),balances.sun_decimals)} SUN · {formatUnits(BigInt(balances.usdx_base_units),balances.usdx_decimals)} USDx</p>}
    </fieldset>
    <fieldset disabled={busy || !balances}>
      <legend>Atomic SUN / USDx trading</legend>
      <label>SUN quantity <input value={quantity} onChange={e=>setQuantity(e.target.value)} /></label>
      <label>USDx per SUN <input value={price} onChange={e=>setPrice(e.target.value)} /></label>
      <label>Order ID <input value={order} onChange={e=>setOrder(e.target.value)} /></label>
      <button onClick={()=>run(()=>transact(balances!.contracts.sun_address,'approve',[balances!.contracts.marketplace_address,tokenUnits(quantity,18)]))}>Approve seller SUN escrow</button>
      <button onClick={()=>run(()=>transact(balances!.contracts.marketplace_address,'placeSellOrder',[tokenUnits(quantity,18),parseUnits(price,6),BigInt(Math.floor(Date.now()/1000)+3600)]))}>List SUN for one hour</button>
      <button onClick={()=>run(async()=>{const {data}=await api.get(`/communities/${community}/orders/${order}`);const units=tokenUnits(quantity,18);const cost=(units*BigInt(data.order[3])+10n**18n-1n)/10n**18n;return transact(balances!.contracts.payment_address,'approve',[balances!.contracts.marketplace_address,cost])})}>Approve quoted USDx payment</button>
      <button onClick={()=>run(trade)}>Purchase and reconcile</button>
      <button onClick={()=>run(async()=>(await api.get(`/communities/${community}/orderbook`)).data)}>View price-time order book</button>
      <button onClick={()=>run(()=>transact(balances!.contracts.payment_address,'approve',[balances!.contracts.marketplace_address,(tokenUnits(quantity,18)*parseUnits(price,6)+10n**18n-1n)/10n**18n]))}>Approve maximum quoted payment</button>
      <button onClick={()=>run(async()=>{const hash=await transact(balances!.contracts.marketplace_address,'fillBestOrder',[tokenUnits(quantity,18),parseUnits(price,6)]);return (await api.post(`/communities/${community}/trades/reconcile`,{transaction_hash:hash})).data})}>Match best order at my price limit</button>
      <button onClick={()=>run(()=>transact(balances!.contracts.marketplace_address,'cancelOrder',[BigInt(order)]))}>Cancel my order</button>
    </fieldset>
    <fieldset disabled={busy || !balances}>
      <legend>Compensate verified consumption</legend>
      <label>Injection interval ID <input value={injection} onChange={e=>setInjection(e.target.value)} /></label>
      <label>Withdrawal interval ID <input value={withdrawal} onChange={e=>setWithdrawal(e.target.value)} /></label>
      <button onClick={()=>run(async()=>{const wh=parseUnits(quantity,3);if(wh>BigInt(Number.MAX_SAFE_INTEGER))throw new Error('Quantity too large');const {data}=await api.post(`/communities/${community}/compensations`,{injection_interval_id:injection,withdrawal_interval_id:withdrawal,energy_wh:Number(wh),idempotency_key:crypto.randomUUID()});setRetirement(data.id);return data})}>Reserve allocation</button>
      <label>Retirement request ID <input value={retirement} onChange={e=>setRetirement(e.target.value)} /></label>
      <button onClick={()=>run(()=>transact(balances!.contracts.sun_address,'approve',[balances!.contracts.compensation_address,tokenUnits(quantity,18)]))}>Approve SUN burn</button>
      <button onClick={()=>run(burn)}>Retire authorized credits</button>
      <button onClick={()=>run(async()=>(await api.get(`/communities/${community}/statement`)).data)}>Community statement</button>
    </fieldset>
    <p role="status">{phase} <code className="break-all">{hash}</code>{busy ? 'Waiting for wallet or network…' : ''}</p>
    <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}} aria-live="polite">{output}</pre>
  </section>
}
