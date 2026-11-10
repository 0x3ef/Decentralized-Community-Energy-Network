import {parseUnits} from 'viem'
export function tokenUnits(value:string,decimals:number):bigint {
 if(!/^\d+(\.\d+)?$/.test(value)|| (value.split('.')[1]?.length||0)>decimals)throw new Error('Enter a positive amount within token precision.')
 const result=parseUnits(value,decimals);if(result<=0n)throw new Error('Amount must be greater than zero.');return result
}
export function quote(quantity:string,price:string):bigint{return (tokenUnits(quantity,18)*tokenUnits(price,6)+10n**18n-1n)/10n**18n}
export function checkPurchase(balance:bigint,allowance:bigint,cost:bigint){if(balance<cost)throw new Error('Insufficient USDx balance.');if(allowance<cost)throw new Error('Approve the required USDx allowance first.')}
