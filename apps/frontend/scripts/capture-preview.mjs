// Read-only preview capture from the explicit local native test fixture.
import {chromium} from '@playwright/test'
import fs from 'node:fs'
import {fileURLToPath} from 'node:url'
const frontend=fileURLToPath(new URL('../',import.meta.url))
process.chdir(frontend)
const fixture=JSON.parse(fs.readFileSync('e2e/.native-fixture.json','utf8'))
fs.mkdirSync('docs/screenshots',{recursive:true})
const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||'/usr/bin/chromium',args:['--no-sandbox']})
try {
 const page=await browser.newPage({viewport:{width:1440,height:1100}})
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.exposeBinding('readRpc',async(_source,{method,params})=>{
  if(!['eth_call','eth_blockNumber','eth_getBalance','eth_getCode','eth_chainId'].includes(method))throw new Error('Screenshot transport permits read-only RPC')
  const response=await fetch('http://127.0.0.1:8545',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params})})
  const data=await response.json();if(data.error)throw new Error(data.error.message);return data.result
 })
 await page.addInitScript(({producer,community})=>{sessionStorage.setItem('solar.access',producer.access_token);sessionStorage.setItem('solar.community',community);Object.defineProperty(window,'ethereum',{value:{request:async({method,params=[]})=>method==='eth_accounts'?[producer.address]:method==='eth_chainId'?'0x7a69':window.readRpc({method,params}),on:()=>{},removeListener:()=>{}}})},fixture)
 const capture=async name=>page.screenshot({path:`docs/screenshots/${name}.png`,fullPage:true,animations:'disabled'})
 await page.goto('http://127.0.0.1:5173/');await page.getByRole('heading',{name:'Tu energía, Productor'}).waitFor();await page.waitForLoadState('networkidle');await capture('dashboard-desktop')
 await page.getByRole('button',{name:'Activar tema oscuro'}).click();await capture('dashboard-dark');await page.getByRole('button',{name:'Activar tema claro'}).click()
 await page.getByRole('link',{name:'Depósitos y retiros',exact:true}).click();await page.getByRole('heading',{name:'Nueva operación'}).waitFor();await page.waitForLoadState('networkidle');await capture('deposits-desktop')
 for(const route of ['comunidad','hogares','dispositivos','energia','creditos','liquidacion','compensacion','transacciones','gobernanza','configuracion']){await page.goto('http://127.0.0.1:5173/'+route);await page.waitForLoadState('networkidle')}
 await page.goto('http://127.0.0.1:5173/');await page.waitForLoadState('networkidle');await page.setViewportSize({width:390,height:844})
 await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=0)
 await capture('dashboard-mobile')
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Mobile horizontal overflow')
 if(errors.length)throw new Error(errors.join('\n'))
 console.log('All 12 top-level routes rendered without page errors; desktop, dark, mobile and finance screenshots saved.')
} finally {await browser.close()}
