import client from './client'
export interface LoginRequest { username: string; password: string }
export interface LoginResponse { access_token: string; token_type: string; expires_in: number; user_id: string; tenant_id: string; username: string }
export const authApi = { login: (data: LoginRequest) => client.post<LoginResponse>('/auth/login', data), me: () => client.get('/auth/me') }

