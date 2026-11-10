import axios from 'axios'

export type User = {
  id: string
  email: string
  full_name: string
  status: string
}

export type TokenResponse = {
  access_token: string
  refresh_token: string
  token_type?: string
  user: User
}

export type Home = {
  id: string
  owner_id: string
  name: string
  address?: string | null
  city?: string | null
  country: string
  latitude?: number | null
  longitude?: number | null
  timezone: string
  installed_capacity_w: number
  has_battery: boolean
  status: string
  created_at: string
}

export type Device = {
  id: string
  home_id: string
  device_code: string
  device_type: string
  manufacturer?: string | null
  model?: string | null
  serial_number?: string | null
  firmware_version?: string | null
  installation_date?: string | null
  status: string
  last_seen_at?: string | null
  created_at: string
}

export type EnergyInterval = {
  id: string
  home_id: string
  interval_start: string
  interval_end: string
  generation_wh: number
  consumption_wh: number
  grid_import_wh: number
  grid_export_wh: number
  battery_charge_wh: number
  battery_discharge_wh: number
  eligible_export_wh: number
  calculation_version: string
  quality_status: string
  created_at: string
}

export type EnergySummary = {
  home_id: string
  window_hours: number
  generation_wh: number
  consumption_wh: number
  grid_import_wh: number
  grid_export_wh: number
  eligible_export_wh: number
}

export type Credit = {
  id: string
  interval_id: string
  owner_id: string
  energy_wh: number
  token_amount: string
  status: string
  created_at: string
}

export type Issuance = {
  id: string
  credit_id: string
  wallet_id: string
  chain_id: number
  transaction_hash?: string | null
  block_number?: number | null
  token_amount: string
  status: string
  created_at: string
  confirmed_at?: string | null
}

export type Order = {
  id: string
  seller_id: string
  order_type: string
  token_amount: string
  price_per_token: string
  remaining_amount: string
  status: string
  created_at: string
  updated_at: string
}

export type Trade = {
  id: string
  order_id: string
  buyer_id: string
  seller_id: string
  token_amount: string
  execution_price: string
  transaction_hash?: string | null
  status: string
  created_at: string
}

export type Wallet = {
  id: string
  user_id: string
  address: string
  chain_id: number
  is_verified: boolean
  created_at: string
}

export type Redemption = {
  id: string
  user_id: string
  wallet_id: string
  token_amount: string
  compensation_amount?: string | null
  compensation_currency?: string | null
  transaction_hash?: string | null
  status: string
  created_at: string
  completed_at?: string | null
}

const api = axios.create({
  baseURL: `${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
})

let accessToken = localStorage.getItem('solar_access_token')
let refreshToken = localStorage.getItem('solar_refresh_token')

export const authTokens = {
  set(tokens: Pick<TokenResponse, 'access_token' | 'refresh_token'>) {
    accessToken = tokens.access_token
    refreshToken = tokens.refresh_token
    localStorage.setItem('solar_access_token', accessToken)
    localStorage.setItem('solar_refresh_token', refreshToken)
  },
  clear() {
    accessToken = null
    refreshToken = null
    localStorage.removeItem('solar_access_token')
    localStorage.removeItem('solar_refresh_token')
  },
  get access() {
    return accessToken
  },
}

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

let refreshPromise: Promise<string | null> | null = null
api.interceptors.response.use(undefined, async (error) => {
  const original = error.config
  if (error.response?.status !== 401 || original?._retry || !refreshToken) {
    return Promise.reject(error)
  }
  original._retry = true
  refreshPromise ??= axios
    .get<TokenResponse>(`${api.defaults.baseURL}/auth/refresh_token`, {headers: {Authorization: `Bearer ${refreshToken}`}})
    .then(({ data }) => {
      authTokens.set(data)
      return data.access_token
    })
    .catch(() => {
      authTokens.clear()
      return null
    })
    .finally(() => {
      refreshPromise = null
    })
  const token = await refreshPromise
  if (!token) return Promise.reject(error)
  original.headers.Authorization = `Bearer ${token}`
  return api(original)
})

export const apiClient = {
  login: (body: { email: string; password: string }) =>
    api.post<TokenResponse>('/auth/login', body).then((r) => r.data),
  register: async (body: { email: string; full_name: string; password: string }) => {
    const [first_name, ...last] = body.full_name.trim().split(/\s+/)
    await api.post('/auth/signup', {email:body.email,password:body.password,first_name,last_name:last.join(' ') || first_name,username:crypto.randomUUID().slice(0,8)})
    return (await api.post<TokenResponse>('/auth/login',{email:body.email,password:body.password})).data
  },
  forgotPassword: (email: string) => api.post('/auth/password/forgot', { email }).then((r) => r.data),
  resetPassword: (token: string, password: string) =>
    api.post('/auth/password/reset', { token, password }).then((r) => r.data),
  me: () => api.get('/auth/me').then(({data}) => ({...data,id:data.uid,full_name:`${data.first_name} ${data.last_name}`} as User)),
  logout: () => api.get('/auth/logout'),
  portfolio: () => api.get<Record<string, unknown>>('/users/me/portfolio').then((r) => r.data),
  homes: () => api.get('/home/').then(({data}) => (data.homes as Home[]).map((home) => ({...home,name:home.name || home.address || home.id}))),
  home: (id: string) => api.get(`/home/${id}`).then(({data}) => ({...data.home,name:data.home.name || data.home.address} as Home)),
  createHome: (body: Omit<Home, 'id' | 'owner_id' | 'status' | 'created_at'>) =>
    api.post('/home/', body).then(({data}) => ({...data.home,name:data.home.name || data.home.address} as Home)),
  devices: (homeId: string) => api.get<Device[]>(`/homes/${homeId}/devices`).then((r) => r.data),
  credits: () => api.get<Credit[]>('/energy/credits').then((r) => r.data),
  credit: (id: string) => api.get<Credit>(`/energy/credits/${id}`).then((r) => r.data),
  issuance: (id: string) => api.get<Issuance>(`/credits/${id}/issuance`).then((r) => r.data),
  intervals: (homeId: string) =>
    api.get<EnergyInterval[]>(`/energy/homes/${homeId}/energy/intervals?start=${new Date(Date.now()-86400000).toISOString()}&end=${new Date().toISOString()}`).then((r) => r.data),
  summary: (homeId: string) =>
    api.get<EnergySummary>(`/energy/homes/${homeId}/energy/summary?start=${new Date(Date.now()-86400000).toISOString()}&end=${new Date().toISOString()}`).then((r) => r.data),
  orders: () => api.get<Order[]>('/marketplace/orders').then((r) => r.data),
  myOrders: () => api.get<Order[]>('/marketplace/orders/me').then((r) => r.data),
  trades: () => api.get<Trade[]>('/marketplace/trades/me').then((r) => r.data),
  stats: () => api.get<Record<string, number>>('/marketplace/stats').then((r) => r.data),
  createOrder: (body: { order_type: string; token_amount: string; price_per_token: string }) =>
    api.post<Order>('/marketplace/orders', body).then((r) => r.data),
  fill: (token_amount: string) =>
    api.post<Trade[]>('/marketplace/fill', { token_amount }).then((r) => r.data),
  cancelOrder: (id: string) => api.post<Order>(`/marketplace/orders/${id}/cancel`).then((r) => r.data),
  wallets: () => api.get('/wallet/').then(({data}) => data.wallets as Wallet[]),
  addWallet: (body: { address: string; chain_id: number }) =>
    api.post<Wallet>('/users/me/wallets', body).then((r) => r.data),
  redemptions: (userId: string) =>
    api.get<Redemption[]>(`/users/${userId}/redemptions`).then((r) => r.data),
  createRedemption: (body: { wallet_id: string; token_amount: string }) =>
    api.post<Redemption>('/redemptions', body).then((r) => r.data),
  blockchainStatus: () => api.get<Record<string, unknown>>('/blockchain/status').then((r) => r.data),
  blockchainNetworks: () => api.get<unknown[]>('/blockchain/networks').then((r) => r.data),
}

export default api
