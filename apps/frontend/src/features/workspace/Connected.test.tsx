import {it,expect,vi,afterEach} from 'vitest'
import {renderHook,waitFor,act,cleanup} from '@testing-library/react'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import type {ReactNode} from 'react'
import {useCommunityId} from './Connected'
vi.mock('./api',()=>({workspaceApi:{communities:vi.fn().mockResolvedValue([{id:'a',name:'A'},{id:'b',name:'B'}])}}))
afterEach(()=>{cleanup();sessionStorage.clear()})
it('selects the first authorized community and responds to user selection',async()=>{const client=new QueryClient({defaultOptions:{queries:{retry:false}}});const wrapper=({children}:{children:ReactNode})=><QueryClientProvider client={client}>{children}</QueryClientProvider>;const {result}=renderHook(useCommunityId,{wrapper});await waitFor(()=>expect(result.current.id).toBe('a'));act(()=>{sessionStorage.setItem('community','b');window.dispatchEvent(new Event('community-change'))});expect(result.current.id).toBe('b');client.clear()})
it('ignores an inaccessible community retained from a previous session',async()=>{sessionStorage.setItem('community','unauthorized');const client=new QueryClient();const {result}=renderHook(useCommunityId,{wrapper:({children})=><QueryClientProvider client={client}>{children}</QueryClientProvider>});await waitFor(()=>expect(result.current.id).toBe('a'));client.clear()})
