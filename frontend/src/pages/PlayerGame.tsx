import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../config'

type Player = { id: number; name: string }
type Progression = { current_phase: number; phases: { phase_number: number; name: string; purpose: string; open_question: string }[]; events: { title: string; description: string; delivery: string }[]; voting_moments: { id: string; question: string; open: boolean }[]; players?: Player[]; player?: { name: string; role: string; role_description: string; objective: string; secret_information: string; clues: string[]; relationships: string[]; instructions: string } }

export default function PlayerGame() {
  const [data, setData] = useState<Progression | null>(null)
  const [candidate, setCandidate] = useState<number>()
  const [message, setMessage] = useState('')
  const token = new URLSearchParams(window.location.search).get('token') || localStorage.getItem('player_token') || ''

  useEffect(() => {
    if (token) localStorage.setItem('player_token', token)
    fetch(`${API_BASE_URL}/game/progression?token=${encodeURIComponent(token)}`, { headers: { 'X-Player-Token': token } })
      .then((response) => response.json())
      .then(setData)
      .catch(() => setMessage('De geheime spelpagina kan niet worden geladen.'))
  }, [token])

  async function vote() {
    if (!candidate) return
    const response = await fetch(`${API_BASE_URL}/game/vote`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Player-Token': token }, body: JSON.stringify({ candidate_player_id: candidate }) })
    const result = await response.json().catch(() => ({}))
    setMessage(result.message || result.detail || 'Stem ontvangen.')
  }

  if (!data?.player) return <p className="py-20 text-center text-slate-400">{message || 'Geheime spelpagina laden...'}</p>
  const openVote = data.voting_moments.find((moment) => moment.open)
  return <div className="space-y-8">
    <header className="border-b border-white/10 pb-7"><p className="text-xs uppercase tracking-[0.25em] text-amber-400">Fase {data.current_phase}</p><h1 className="mt-2 text-4xl font-black text-white">{data.player.name}, jouw briefing</h1><p className="mt-3 text-xl text-amber-300">{data.player.role}</p><p className="mt-2 text-slate-300">{data.player.role_description}</p></header>
    <section className="grid gap-6 md:grid-cols-2"><div className="panel space-y-4"><h2 className="panel-title">Jouw informatie</h2><p className="text-slate-300"><b>Doel:</b> {data.player.objective}</p><p className="text-slate-300"><b>Geheim:</b> {data.player.secret_information}</p><ul className="list-disc space-y-2 pl-5 text-slate-300">{data.player.clues.map((clue) => <li key={clue}>{clue}</li>)}</ul></div><div className="panel"><h2 className="panel-title">Actieve fase</h2>{data.phases.filter((phase) => phase.phase_number <= data.current_phase).slice(-1).map((phase) => <div key={phase.phase_number}><p className="text-xl text-white">{phase.name}</p><p className="mt-2 text-slate-300">{phase.purpose}</p><p className="mt-4 text-sm text-amber-300">Open vraag: {phase.open_question}</p></div>)}<p className="mt-6 text-slate-300">{data.player.instructions}</p></div></section>
    {data.events.length > 0 && <section className="panel"><h2 className="panel-title">Nieuwe informatie</h2><div className="mt-4 space-y-4">{data.events.map((event) => <article key={event.title} className="border-l-2 border-amber-400 pl-4"><p className="font-bold text-white">{event.title}</p><p className="mt-1 text-slate-300">{event.description}</p></article>)}</div></section>}
    {openVote && <section className="panel border-emerald-400/40"><h2 className="panel-title">Geheime verdenking</h2><p className="mt-2 text-slate-300">{openVote.question}</p><div className="mt-4 grid gap-2">{data.players?.filter((player) => player.name !== data.player?.name).map((player) => <label key={player.id} className="flex items-center gap-3 border border-white/10 p-3 text-white"><input type="radio" name="suspect" onChange={() => setCandidate(player.id)} />{player.name}</label>)}</div><button onClick={vote} disabled={!candidate} className="mt-4 bg-emerald-400 px-4 py-3 font-bold text-slate-950 disabled:opacity-40">Geheim indienen</button>{message && <p className="mt-3 text-sm text-emerald-300">{message}</p>}</section>}
  </div>
}
