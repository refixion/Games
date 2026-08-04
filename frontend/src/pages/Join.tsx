import React, { useState } from 'react'

export default function Join(){
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle'|'loading'|'success'|'error'>('idle')

  async function submit(e: React.FormEvent){
    e.preventDefault()
    setStatus('loading')
    try{
      const res = await fetch((import.meta.env.VITE_BACKEND_URL || '') + '/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email })
      })
      if(res.ok){
        setStatus('success')
        setName('')
        setEmail('')
      }else{
        setStatus('error')
      }
    }catch(err){
      setStatus('error')
    }
  }

  return (
    <div className="max-w-md mx-auto">
      <div className="backdrop-blur-sm bg-white/5 rounded-2xl p-6 shadow-lg">
        <h3 className="text-2xl font-bold mb-4">Meedoen</h3>
        <form onSubmit={submit} className="space-y-4">
          <input required value={name} onChange={e=>setName(e.target.value)} placeholder="Naam" className="w-full p-3 rounded-full bg-white/5" />
          <input required type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="Email" className="w-full p-3 rounded-full bg-white/5" />
          <button className="w-full bg-primary p-3 rounded-full font-semibold" disabled={status==='loading'}>Verstuur</button>
        </form>
        {status==='success' && <p className="mt-4 text-green-400">Succes! Je bent aangemeld.</p>}
        {status==='error' && <p className="mt-4 text-red-400">Er is iets misgegaan. Probeer later opnieuw.</p>}
      </div>
    </div>
  )
}
