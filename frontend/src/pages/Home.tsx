import React from 'react'
import { Link } from 'react-router-dom'
import { CONFIG, GAME_PRESETS } from '../config'

export default function Home() {
  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900 to-slate-800 p-6 shadow-2xl shadow-slate-950/40 sm:p-8">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.28em] text-violet-300">Mysterieuze AVONTUREN</p>
        <h1 className="text-4xl font-black tracking-tight text-white sm:text-5xl">{CONFIG.game_name}</h1>
        <p className="mt-4 max-w-2xl text-lg text-slate-300">{CONFIG.description}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link to="/join" className="rounded-full bg-violet-500 px-5 py-3 font-semibold text-white transition hover:bg-violet-400">Meedoen</Link>
          <Link to="/admin" className="rounded-full border border-white/15 bg-white/5 px-5 py-3 font-semibold text-slate-200 transition hover:bg-white/10">Admin</Link>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {GAME_PRESETS.map((preset) => (
          <div key={preset.id} className="rounded-2xl border border-white/10 bg-slate-900/80 p-5">
            <div className="mb-3 h-2 w-20 rounded-full" style={{ background: preset.theme.primary }} />
            <h2 className="text-xl font-bold text-white">{preset.label}</h2>
            <p className="mt-2 text-sm text-slate-300">Speltype: {preset.type}</p>
            <ul className="mt-4 space-y-2 text-sm text-slate-400">
              {preset.roles.map((role) => (
                <li key={role}>• {role}</li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </div>
  )
}
