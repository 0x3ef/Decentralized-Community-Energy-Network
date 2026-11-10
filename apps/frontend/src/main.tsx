import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

document.body.classList.toggle('dark',localStorage.getItem('theme')==='dark')
const queryClient = new QueryClient({defaultOptions:{mutations:{retry:false},queries:{retry:(count,error)=>{
 const status=(error as {response?:{status:number}}).response?.status
 return ![401,403,404].includes(status||0)&&count<2
}}}})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
