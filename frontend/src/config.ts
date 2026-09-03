export type RoleSummary = { name: string; description: string }
export type GamePreset = {
  id: string
  name: string
  type: string
  description: string
  goal: string
  rules: string[]
  steps: string[]
  roles: RoleSummary[]
  theme: {
    primary: string
    accent: string
    surface?: string
    text?: string
  }
}

export const CONFIG = {
  game_name: 'Secret Game',
  description: 'Wat staat er vandaag te gebeuren?',
  primary_color: '#7c3aed',
  logo: ''
}

export const API_BASE_URL = '/api'