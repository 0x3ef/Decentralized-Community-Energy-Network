import api from '../../lib/api'
export type Community = {id:string;name:string;sun_per_kwh:string;loss_factor:string;temporal_policy:string}
export type Home = {id:string;name:string;address:string;city:string}
export type Interval = {id:string;interval_start:string;generation_wh:number;consumption_wh:number;grid_import_wh:number;grid_export_wh:number;eligible_export_wh:number;quality_status:string}
export type Credit = {id:string;interval_id:string;energy_wh:number;token_amount:string;status:string}
export type Retirement = {id:string;energy_wh:number;status:string;transaction_hash:string|null}
export type Payment = {id:string;buyer:string;seller:string;sun_units:string;payment_units:string;status:string;transaction_hash:string}
export type Statement = {verified_injection_wh:number;verified_withdrawal_wh:number;allocated_wh:number;compensated_wh:number;unallocated_injection_wh:number;uncompensated_withdrawal_wh:number;retirements:Retirement[];simulated_payments:Payment[]}
export type Ledger = {id:string;operation:string;source_id:string;energy_wh:number;created_at:string;blockchain_hash:string|null}
export type Device = {id:string;device_type:string;status:string;last_seen_at:string|null}
export const workspaceApi = {
 communities: (signal?:AbortSignal)=>api.get<Community[]>('/communities',{signal}).then(r=>r.data),
 homes: (signal?:AbortSignal)=>api.get<{homes:Home[]}>('/home/',{signal}).then(r=>r.data.homes),
 statement:(id:string,signal?:AbortSignal)=>api.get<Statement>(`/communities/${id}/statement`,{signal}).then(r=>r.data),
 nodes:(id:string,signal?:AbortSignal)=>api.get<{id:string;home_id:string;authorized:boolean}[]>(`/communities/${id}/nodes`,{signal}).then(r=>r.data),
 credits:(signal?:AbortSignal)=>api.get<Credit[]>('/energy/credits',{signal}).then(r=>r.data),
 intervals:(home:string,start:string,end:string,signal?:AbortSignal)=>api.get<Interval[]>(`/energy/homes/${home}/energy/intervals`,{params:{start,end},signal}).then(r=>r.data),
 devices:(home:string,signal?:AbortSignal)=>api.get<{devices:Device[]}>('/device/device/',{params:{home_id:home},signal}).then(r=>r.data.devices),
 ledger:(community:string,offset:number,signal?:AbortSignal)=>api.get<Ledger[]>(`/communities/${community}/ledger`,{params:{offset,limit:20},signal}).then(r=>r.data),
 issuance:(id:string)=>api.get<{status:string;operations:{id:string;status:string;transaction_hash:string|null}[]}>(`/communities/credits/${id}/issuance`).then(r=>r.data),
}
export function errorMessage(error:unknown):string {
 if(typeof error==='object' && error!==null && 'response' in error){const response=error.response as {status?:number;data?:{detail?:unknown}};if(response.status===403)return 'Your account does not have permission for this action.';if(typeof response.data?.detail==='string')return response.data.detail}
 return error instanceof Error?error.message:'The request could not be completed.'
}
