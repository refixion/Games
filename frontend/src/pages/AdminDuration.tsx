import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE_URL } from '../config'

const durations = [['avond', 'Avond'], ['1_week', '1 week'], ['2_weken', '2 weken'], ['3_weken', '3 weken'], ['1_maand', '1 maand']]

export default function AdminDuration() {
  const [duration, setDuration] = useState('avond')
  const [message, setMessage] = useState('')
  const password = sessionStorage.getItem('admin_pw') || ''

  useEffect(() => {
    fetch(`${API_BASE_URL}/game-state`).then((response) => response.json()).then((data) => setDuration(data.state.duration || 'avond'))
  }, [])

  async function save() {
    const response = await fetch(`${API_BASE_URL}/admin/duration`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Admin-Password': password }, body: JSON.stringify({ duration }) })
    const data = await response.json().catch(() => ({}))
    setMessage(response.ok ? 'Speelduur opgeslagen.' : data.detail || 'Opslaan mislukt.')
  }

  return <section className="mx-auto max-w-xl space-y-6"><Link to="/admin" className="text-sm text-amber-300">Terug naar admin</Link><header><p className="text-xs uppercase tracking-[0.25em] text-amber-400">Campaign setup</p><h1 className="mt-2 text-4xl font-black text-white">Speelduur</h1><p className="mt-3 text-slate-400">Deze keuze bepaalt de gegenereerde phases, events, clues en stemmomenten.</p></header><div className="panel space-y-4">{durations.map(([value, label]) => <label key={value} className="flex items-center gap-3 border border-white/10 p-4 text-white"><input type="radio" name="duration" value={value} checked={duration === value} onChange={() => setDuration(value)} />{label}</label>)}<button onClick={save} className="bg-amber-400 px-4 py-3 font-bold text-slate-950">Speelduur opslaan</button>{message && <p className="text-sm text-amber-300">{message}</p>}</div></section>
}
