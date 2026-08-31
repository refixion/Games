import React, { FormEvent, useEffect, useState } from 'react'
import { API_BASE_URL, GAME_PRESETS } from '../config'

type Player = {
  id: number
  name: string
  email: string
  role: string | null
  status: string | null
  game_preset: string | null
}

type TabKey = 'dashboard' | 'game' | 'players'

export default function Admin() {
  const [pw, setPw] = useState('')
  const [authed, setAuthed] = useState(false)
  const [count, setCount] = useState<number | null>(null)
  const [players, setPlayers] = useState<Player[]>([])
  const [activeTab, setActiveTab] = useState<TabKey>('dashboard')
  const [loading, setLoading] = useState(false)

  const authHeaders = () => ({ 'X-Admin-Password': sessionStorage.getItem('admin_pw') || '' })

  async function fetchStats() {
    setLoading(true)
    try {
      const countRes = await fetch(`${API_BASE_URL}/players/count`, { headers: authHeaders() })
      if (countRes.ok) {
        const countData = await countRes.json()
        setCount(countData.count ?? 0)
      }

      const playersRes = await fetch(`${API_BASE_URL}/players`, { headers: authHeaders() })
      if (playersRes.ok) {
        const playersData = await playersRes.json()
        setPlayers(playersData.players ?? [])
      }
    } catch (_error) {
      setCount(null)
      setPlayers([])
    } finally {
      setLoading(false)
    }
  }

  function login(event: FormEvent) {
    event.preventDefault()
    const trimmed = pw.trim()
    if (!trimmed) return
    sessionStorage.setItem('admin_pw', trimmed)
    setAuthed(true)
    fetchStats()
  }

  async function draw() {
    const password = sessionStorage.getItem('admin_pw') || ''
    if (!password) return
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/draw`, {
        method: 'POST',
        headers: { 'X-Admin-Password': password }
      })

      if (response.ok) {
        alert('De geheime speler is geïnformeerd.')
        await fetchStats()
      } else {
        alert('Fout bij het kiezen van een rol.')
      }
    } catch (_error) {
      alert('Er is iets misgegaan.')
    } finally {
      setLoading(false)
    }
  }

  async function reset() {
    const password = sessionStorage.getItem('admin_pw') || ''
    if (!password) return
    if (!window.confirm('Weet je zeker dat je alle deelnemers wilt verwijderen?')) return
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/reset`, {
        method: 'POST',
        headers: { 'X-Admin-Password': password }
      })

      if (response.ok) {
        alert('Reset uitgevoerd.')
        await fetchStats()
      } else {
        alert('Reset mislukt.')
      }
    } catch (_error) {
      alert('Er is iets misgegaan bij de reset.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const stored = sessionStorage.getItem('admin_pw')
    if (stored) {
      setAuthed(true)
      fetchStats()
    }
  }, [])

  if (!authed) {
    return (
      <div className="mx-auto max-w-md">
        <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6 text-white sm:p-8">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-violet-300">Admin</p>
          <h3 className="mt-3 text-3xl font-bold">Login</h3>
          <form onSubmit={login} className="mt-6 space-y-4">
            <input
              type="password"
              value={pw}
              onChange={(event) => setPw(event.target.value)}
              placeholder="Wachtwoord"
              className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none placeholder:text-slate-500 focus:border-violet-400"
            />
            <button type="submit" className="w-full rounded-full bg-violet-500 px-4 py-3 font-semibold text-white hover:bg-violet-400">
              Login
            </button>
          </form>
        </div>
      </div>
    )
  }

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'dashboard', label: 'Dashboard' },
    { key: 'game', label: 'Game' },
    { key: 'players', label: 'Players' }
  ]

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-violet-300">Admin portal</p>
            <h3 className="mt-2 text-3xl font-bold text-white">Secret Game</h3>
          </div>
          <button className="rounded-full border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-200" onClick={reset}>
            Reset spel
          </button>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`rounded-full px-4 py-2 text-sm font-medium ${activeTab === tab.key ? 'bg-violet-500 text-white' : 'bg-slate-800 text-slate-300'}`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'dashboard' && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-white/10 bg-slate-900/80 p-5">
            <p className="text-sm text-slate-400">Actieve game</p>
            <p className="mt-2 text-2xl font-bold text-white">Murder Mystery</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-slate-900/80 p-5">
            <p className="text-sm text-slate-400">Ingeschreven spelers</p>
            <p className="mt-2 text-2xl font-bold text-white">{loading ? '…' : count ?? 0}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-slate-900/80 p-5">
            <p className="text-sm text-slate-400">Status</p>
            <p className="mt-2 text-2xl font-bold text-emerald-400">Open</p>
          </div>
        </div>
      )}

      {activeTab === 'game' && (
        <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
          <h4 className="text-xl font-bold text-white">Game preset kiezen</h4>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {GAME_PRESETS.map((preset) => (
              <button key={preset.id} className="rounded-2xl border border-white/10 bg-slate-950/70 p-4 text-left">
                <div className="mb-3 h-2 w-20 rounded-full" style={{ background: preset.theme.primary }} />
                <p className="text-lg font-semibold text-white">{preset.label}</p>
                <p className="mt-2 text-sm text-slate-400">{preset.roles.join(', ')}</p>
              </button>
            ))}
          </div>
          <button onClick={draw} className="mt-6 rounded-full bg-violet-500 px-5 py-3 font-semibold text-white hover:bg-violet-400">
            Loting uitvoeren
          </button>
        </div>
      )}

      {activeTab === 'players' && (
        <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h4 className="text-xl font-bold text-white">Spelers</h4>
            <span className="text-sm text-slate-400">{players.length} totaal</span>
          </div>
          <div className="space-y-3">
            {players.length === 0 ? (
              <p className="text-slate-400">Nog geen spelers aangemeld.</p>
            ) : (
              players.map((player) => (
                <div key={player.id} className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-slate-950/70 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="font-semibold text-white">{player.name}</p>
                    <p className="text-sm text-slate-400">{player.email}</p>
                  </div>
                  <div className="text-sm text-slate-300">
                    <span className="mr-2 rounded-full bg-slate-800 px-2 py-1">{player.role ?? 'Geen rol'}</span>
                    <span className="rounded-full bg-slate-800 px-2 py-1">{player.status ?? 'registered'}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
