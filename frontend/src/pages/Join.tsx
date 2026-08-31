import React, { FormEvent, useState } from 'react'
import { API_BASE_URL, CONFIG } from '../config'

export default function Join() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setStatus('loading')
    setMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email })
      })

      const data = await response.json().catch(() => ({}))
      if (response.ok) {
        setStatus('success')
        setMessage(data.message || 'Succes! Je bent aangemeld.')
        setName('')
        setEmail('')
      } else {
        setStatus('error')
        setMessage(data.message || 'Er is iets misgegaan. Probeer later opnieuw.')
      }
    } catch (_error) {
      setStatus('error')
      setMessage('Er is iets misgegaan. Probeer later opnieuw.')
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6 shadow-2xl shadow-slate-950/30 sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-violet-300">Aanmelden</p>
        <h2 className="mt-3 text-3xl font-bold text-white">{CONFIG.game_name}</h2>
        <p className="mt-2 text-slate-300">Vul je naam en email in om mee te doen aan het geheimspel.</p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Naam"
            className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none ring-0 placeholder:text-slate-500 focus:border-violet-400"
          />
          <input
            required
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="Email"
            className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none placeholder:text-slate-500 focus:border-violet-400"
          />
          <button
            type="submit"
            disabled={status === 'loading'}
            className="w-full rounded-full bg-violet-500 px-4 py-3 font-semibold text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {status === 'loading' ? 'Versturen…' : 'Verstuur'}
          </button>
        </form>

        {message && (
          <p className={`mt-4 ${status === 'success' ? 'text-emerald-400' : 'text-red-400'}`}>{message}</p>
        )}
      </div>
    </div>
  )
}
