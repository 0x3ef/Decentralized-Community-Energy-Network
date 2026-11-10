import {describe,it,expect} from 'vitest'
import {tokenUnits,quote,checkPurchase} from './amounts'
describe('precise wallet amounts',()=>{
 it('quotes the mandatory trade with distinct token decimals',()=>expect(quote('3','450')).toBe(1350000000n))
 it('rounds fractional payment up without free dust',()=>expect(quote('0.000000000000000001','1')).toBe(1n))
 it.each(['0','-1','NaN','1e3','1.0000001'])('rejects invalid USDx quantity %s',s=>expect(()=>tokenUnits(s,6)).toThrow())
 it('rejects insufficient balances',()=>expect(()=>checkPurchase(1n,10n,2n)).toThrow('balance'))
 it('rejects insufficient allowance',()=>expect(()=>checkPurchase(10n,1n,2n)).toThrow('allowance'))
})
