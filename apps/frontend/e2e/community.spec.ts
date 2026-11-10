import {test,expect} from '@playwright/test'
test('protected routes require a session',async({page})=>{await page.goto('/homes');await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible()})
test('authenticated community creation and mobile navigation use the real API',async({page,request})=>{
 const suffix=Date.now().toString().slice(-8);const email=`ui${suffix}@example.com`;const password='frontend-test-password'
 const created=await request.post('http://127.0.0.1:8000/api/v1/auth/signup',{data:{username:suffix,email,password,first_name:'Frontend',last_name:'Test'}});expect(created.status()).toBe(201)
 const login=await request.post('http://127.0.0.1:8000/api/v1/auth/login',{data:{email,password}});expect(login.ok()).toBeTruthy();const tokens=await login.json()
 await page.addInitScript(tokens=>{localStorage.setItem('solar_access_token',tokens.access_token);localStorage.setItem('solar_refresh_token',tokens.refresh_token)},tokens)
 await page.goto('/community');await page.getByLabel('Community name',{exact:true}).fill(`Test community ${suffix}`);await page.getByRole('button',{name:'Create community',exact:true}).click();await expect(page.getByLabel('Active community')).toContainText(`Test community ${suffix}`)
 await page.getByRole('link',{name:'Dashboard',exact:true}).click();await expect(page.getByRole('heading',{name:'Community overview'})).toBeVisible();await expect(page.getByText('Verified injection',{exact:true})).toBeVisible()
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Open menu'}).click();await page.getByRole('link',{name:'My Homes',exact:true}).click();await expect(page.getByRole('heading',{name:'Homes & sensors'})).toBeVisible()
})
