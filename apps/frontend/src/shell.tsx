import {lazy,Suspense} from 'react'
const LiveHomes=lazy(()=>import('./features/workspace/Pages').then(m=>({default:m.Homes})))
const LiveEnergy=lazy(()=>import('./features/workspace/Pages').then(m=>({default:m.Energy})))
const LiveCredits=lazy(()=>import('./features/workspace/Pages').then(m=>({default:m.Credits})))
import {CommunitySelect,ConnectedOverview,ConnectedSettlement,ConnectedHistory} from './features/workspace/Connected'
import { useState } from 'react'
import CommunityPage from './CommunityPage'
import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes, useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, BarChart3, Blocks, CreditCard, Home, LogOut, Menu, RefreshCw, Settings, ShoppingCart, Sun, WalletCards, X, Zap } from 'lucide-react'
import { apiClient, authTokens } from './lib/api'

const errorMessage = (error: unknown) => {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response
    return response?.data?.detail ?? 'The request could not be completed.'
  }
  return 'Unable to reach the Solar Energy Market API.'
}

function useAuth() {
  const query = useQuery({ queryKey: ['me'], queryFn: apiClient.me, retry: false, enabled: Boolean(authTokens.access) })
  return { user: query.data, loading: query.isLoading, error: query.error }
}

function AppLayout() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [dark,setDark]=useState(()=>localStorage.getItem("theme")==="dark")
  const navigate = useNavigate()
  const links = [
    ['Dashboard', '/dashboard', BarChart3], ['My Homes', '/homes', Home], ['Energy Monitoring', '/energy', Zap],
    ['Community Settlement', '/community', Blocks], ['Energy Credits', '/credits', CreditCard], ['Marketplace', '/marketplace', ShoppingCart],
    ['My Orders', '/orders', Activity], ['My Trades', '/trades', ArrowRight], ['Wallet', '/wallet', WalletCards],
    ['Compensation & settlement', '/redemptions', RefreshCw], ['Blockchain', '/blockchain', Blocks], ['Settings', '/settings', Settings],
  ] as const
  const logout = async () => { await apiClient.logout().catch(() => undefined); authTokens.clear(); navigate('/login') }
  return <div className="shell">
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
      <div className="brand"><span className="brand-mark"><Sun size={20} /></span><span>Solar<span>Market</span></span><button className="icon-btn mobile-only" onClick={() => setOpen(false)} aria-label="Close menu"><X size={20} /></button></div>
      <nav>{links.map(([label, path, Icon]) => <NavLink key={path} to={path} end={path === '/dashboard'} onClick={() => setOpen(false)} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}><Icon size={18} /><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="user-chip"><div className="avatar">{user?.full_name?.slice(0, 1).toUpperCase() ?? '?'}</div><div><strong>{user?.full_name ?? 'Account'}</strong><small>{user?.email ?? ''}</small></div></div><button className="nav-item logout" onClick={logout}><LogOut size={18} />Sign out</button></div>
    </aside>
    <main className="main"><header className="topbar"><button className="icon-btn mobile-only" onClick={() => setOpen(true)} aria-label="Open menu"><Menu size={22} /></button><div className="topbar-spacer" /><CommunitySelect/><button className="icon-btn" aria-label="Toggle dark theme" onClick={()=>{document.body.classList.toggle("dark",!dark);localStorage.setItem("theme",dark?"light":"dark");setDark(!dark)}}>Theme</button><span className="status-dot" />Local development prototype</header><div className="page"><Outlet /></div></main>
  </div>
}

function AuthLayout() { return <div className="auth-shell"><div className="auth-brand"><span className="brand-mark"><Sun size={22} /></span>Solar<span>Market</span></div><Outlet /></div> }

function Protected() { const { user, loading } = useAuth(); if (loading) return <div className="loading-screen"><Sun className="spin" />Loading your energy workspace…</div>; return user ? <Outlet /> : <Navigate to="/login" replace /> }

function Login() {
  const navigate = useNavigate(); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState('')
  const mutation = useMutation({ mutationFn: () => apiClient.login({ email, password }), onSuccess: (data) => { authTokens.set(data); navigate('/community') }, onError: (e) => setError(errorMessage(e)) })
  return <AuthCard title="Welcome back" subtitle="Sign in to monitor, trade, and manage your solar assets."><form onSubmit={(e) => { e.preventDefault(); setError(''); mutation.mutate() }}><Field label="Email" type="email" value={email} onChange={setEmail} required /><Field label="Password" type="password" value={password} onChange={setPassword} required /><div className="form-row end"><a href="/forgot-password">Forgot password?</a></div>{error && <Notice tone="error">{error}</Notice>}<button className="primary full" disabled={mutation.isPending}>{mutation.isPending ? 'Signing in…' : 'Sign in'} <ArrowRight size={17} /></button></form><p className="auth-switch">New to SolarMarket? <a href="/register">Create an account</a></p></AuthCard>
}

function Register() {
  const navigate = useNavigate(); const [form, setForm] = useState({ full_name: '', email: '', password: '', confirm: '' }); const [error, setError] = useState('')
  const mutation = useMutation({ mutationFn: () => apiClient.register({ full_name: form.full_name, email: form.email, password: form.password }), onSuccess: (data) => { authTokens.set(data); navigate('/community') }, onError: (e) => setError(errorMessage(e)) })
  return <AuthCard title="Create your account" subtitle="Start turning clean energy into measurable value."><form onSubmit={(e) => { e.preventDefault(); if (form.password !== form.confirm) return setError('Passwords do not match.'); setError(''); mutation.mutate() }}><Field label="Full name" value={form.full_name} onChange={(v) => setForm({ ...form, full_name: v })} required /><Field label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} required /><Field label="Password" type="password" value={form.password} onChange={(v) => setForm({ ...form, password: v })} required /><Field label="Confirm password" type="password" value={form.confirm} onChange={(v) => setForm({ ...form, confirm: v })} required />{error && <Notice tone="error">{error}</Notice>}<button className="primary full" disabled={mutation.isPending}>{mutation.isPending ? 'Creating…' : 'Create account'} <ArrowRight size={17} /></button></form><p className="auth-switch">Already registered? <a href="/login">Sign in</a></p></AuthCard>
}

function ForgotPassword() {
  const [email, setEmail] = useState(''); const [sent, setSent] = useState(false); const [error, setError] = useState('')
  const mutation = useMutation({ mutationFn: () => apiClient.forgotPassword(email), onSuccess: () => setSent(true), onError: (e) => setError(errorMessage(e)) })
  return <AuthCard title="Reset your password" subtitle="We will create reset instructions for the account if it exists."><form onSubmit={(e) => { e.preventDefault(); mutation.mutate() }}><Field label="Email" type="email" value={email} onChange={setEmail} required />{sent && <Notice tone="success">If the account exists, reset instructions were created.</Notice>}{error && <Notice tone="error">{error}</Notice>}<button className="primary full" disabled={mutation.isPending}>{mutation.isPending ? 'Sending…' : 'Send instructions'}</button></form><p className="auth-switch"><a href="/login">Back to sign in</a></p></AuthCard>
}

function ResetPassword() {
  const params = new URLSearchParams(window.location.search); const [password, setPassword] = useState(''); const [message, setMessage] = useState('')
  const mutation = useMutation({ mutationFn: () => apiClient.resetPassword(params.get('token') ?? '', password), onSuccess: () => setMessage('Password updated. You can sign in now.'), onError: (e) => setMessage(errorMessage(e)) })
  return <AuthCard title="Choose a new password" subtitle="Use the secure reset token from your email."><form onSubmit={(e) => { e.preventDefault(); mutation.mutate() }}><Field label="New password" type="password" value={password} onChange={setPassword} required />{message && <Notice tone={message.includes('updated') ? 'success' : 'error'}>{message}</Notice>}<button className="primary full" disabled={mutation.isPending || !params.get('token')}>{mutation.isPending ? 'Saving…' : 'Update password'}</button></form><p className="auth-switch"><a href="/login">Back to sign in</a></p></AuthCard>
}

function AuthCard({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) { return <div className="auth-card"><div className="eyebrow">SOLAR ENERGY MARKET</div><h1>{title}</h1><p className="muted">{subtitle}</p>{children}</div> }
function Field({ label, type = 'text', value, onChange, required }: { label: string; type?: string; value: string; onChange: (value: string) => void; required?: boolean }) { return <label className="field"><span>{label}</span><input type={type} value={value} onChange={(e) => onChange(e.target.value)} required={required} /></label> }
function Notice({ tone = 'info', children }: { tone?: 'info' | 'error' | 'success'; children: ReactNode }) { return <div className={`notice ${tone}`}>{children}</div> }
function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: React.ReactNode }) { return <div className="page-header"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1>{description && <p className="muted">{description}</p>}</div>{action}</div> }
function SettingsPage() { const { user } = useAuth(); return <><PageHeader eyebrow="ACCOUNT" title="Settings" description="Your account identity and session information." /><section className="panel settings-card"><div className="avatar large">{user?.full_name?.slice(0, 1).toUpperCase()}</div><div><h2>{user?.full_name}</h2><p className="muted">{user?.email}</p><span className="pill success">{user?.status}</span></div></section></> }
export default function App() { return <BrowserRouter><Suspense fallback={<p role="status">Loading view…</p>}><Routes><Route element={<AuthLayout />}><Route path="/login" element={<Login />} /><Route path="/register" element={<Register />} /><Route path="/forgot-password" element={<ForgotPassword />} /><Route path="/reset-password" element={<ResetPassword />} /></Route><Route element={<Protected />}><Route element={<AppLayout />}><Route index element={<Navigate to="/community" replace />} /><Route path="/dashboard" element={<ConnectedOverview />} /><Route path="/community" element={<CommunityPage />} /><Route path="/homes" element={<LiveHomes />} /><Route path="/energy" element={<LiveEnergy />} /><Route path="/credits" element={<LiveCredits />} /><Route path="/marketplace" element={<CommunityPage />} /><Route path="/orders" element={<ConnectedHistory />} /><Route path="/trades" element={<ConnectedSettlement />} /><Route path="/wallet" element={<CommunityPage />} /><Route path="/redemptions" element={<ConnectedSettlement />} /><Route path="/blockchain" element={<ConnectedHistory />} /><Route path="/settings" element={<SettingsPage />} /></Route></Route><Route path="*" element={<Navigate to="/" replace />} /></Routes></Suspense></BrowserRouter> }
