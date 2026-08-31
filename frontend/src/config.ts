export type GamePreset = {
  id: string
  label: string
  type: string
  roles: string[]
  theme: {
    primary: string
    accent: string
    surface: string
    text: string
  }
}

export const GAME_PRESETS: GamePreset[] = [
  {
    id: 'murder_mystery',
    label: 'Murder Mystery',
    type: 'murder_mystery',
    roles: ['Murderer', 'Detective', 'Citizen'],
    theme: {
      primary: '#7f1d1d',
      accent: '#fbbf24',
      surface: '#111827',
      text: '#f8fafc'
    }
  },
  {
    id: 'the_heist',
    label: 'The Heist',
    type: 'the_heist',
    roles: ['Boss', 'Inside Man', 'Banker', 'Operative'],
    theme: {
      primary: '#2563eb',
      accent: '#f59e0b',
      surface: '#0f172a',
      text: '#e2e8f0'
    }
  },
  {
    id: 'the_investigation',
    label: 'The Investigation',
    type: 'the_investigation',
    roles: ['Detective', 'Witness', 'Archivist', 'Suspect'],
    theme: {
      primary: '#0f766e',
      accent: '#cbd5e1',
      surface: '#111827',
      text: '#f8fafc'
    }
  }
]

export const CONFIG = {
  game_name: 'Secret Game',
  description: 'Wat staat er vandaag te gebeuren?',
  primary_color: '#7c3aed',
  logo: ''
}

export const API_BASE_URL = '/api'
  .replace(/\/$/, '')
  .replace(/\/api$/, '')
