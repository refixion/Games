import React, { useEffect, useState } from 'react'

export default function Admin(){
  const [pw, setPw] = useState('')
  const [authed, setAuthed] = useState(false)
  const [count, setCount] = useState<number|null>(null)
  const [loading, setLoading] = useState(false)

  function login(e: React.FormEvent){
    e.preventDefault()
    sessionStorage.setItem('admin_pw', pw)
    setAuthed(true)
    fetchCount(pw)
  }

  async function fetchCount(pwHeader?: string){
    setLoading(true)
    try{
      const res = await fetch((import.meta.env.VITE_BACKEND_URL || '') + '/players/count', {
        headers: { 'X-Admin-Password': pwHeader||sessionStorage.getItem('admin_pw')||'' }
      })
      if(res.ok){
        const data = await res.json()
        setCount(data.count)
      }else{
        setCount(null)
      }
    }catch(e){
      setCount(null)
    }finally{setLoading(false)}
  }

  async function draw(){
    const pwStored = sessionStorage.getItem('admin_pw')||''
    setLoading(true)
    try{
      const res = await fetch((import.meta.env.VITE_BACKEND_URL || '') + '/draw', { method: 'POST', headers: { 'X-Admin-Password': pwStored } })
      if(res.ok){
        alert('De geheime speler is geïnformeerd.')
        fetchCount()
      }else{
        alert('Fout bij kiezen')
      }
    }catch(e){ alert('Fout') }
    setLoading(false)
  }

  async function reset(){
    const pwStored = sessionStorage.getItem('admin_pw')||''
    if(!confirm('Weet je zeker dat je alle deelnemers wil verwijderen?')) return
    setLoading(true)
    try{
      const res = await fetch((import.meta.env.VITE_BACKEND_URL || '') + '/reset', { method: 'POST', headers: { 'X-Admin-Password': pwStored } })
      if(res.ok){
        alert('Reset uitgevoerd')
        fetchCount()
      }else{
        alert('Fout bij reset')
      }
    }catch(e){ alert('Fout') }
    setLoading(false)
  }

  useEffect(()=>{
    const stored = sessionStorage.getItem('admin_pw')
    if(stored){ setAuthed(true); fetchCount(stored) }
  },[])

  if(!authed) return (
    <div className="max-w-md mx-auto">
      <div className="backdrop-blur-sm bg-white/5 rounded-2xl p-6">
        <h3 className="text-2xl font-bold mb-4">Admin login</h3>
        <form onSubmit={login} className="space-y-4">
          <input type="password" value={pw} onChange={e=>setPw(e.target.value)} placeholder="Wachtwoord" className="w-full p-3 rounded-full bg-white/5" />
          <button className="w-full bg-primary p-3 rounded-full" type="submit">Login</button>
        </form>
      </div>
    </div>
  )

  return (
    <div className="max-w-md mx-auto">
      <div className="backdrop-blur-sm bg-white/5 rounded-2xl p-6">
        <h3 className="text-2xl font-bold mb-4">Admin</h3>
        <p>Aantal deelnemers: {loading? '...' : (count ?? '—')}</p>
        <div className="space-y-2 mt-4">
          <button className="w-full bg-primary p-3 rounded-full" onClick={draw}>Kies geheime speler</button>
          <button className="w-full bg-red-600 p-3 rounded-full" onClick={reset}>Reset spel</button>
        </div>
      </div>
    </div>
  )
}
