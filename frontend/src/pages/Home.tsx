import React from 'react'
import { CONFIG } from '../config'
import { Link } from 'react-router-dom'

export default function Home(){
  return (
    <div className="max-w-2xl mx-auto">
      <div className="backdrop-blur-sm bg-white/5 rounded-2xl p-6 shadow-lg">
        <h2 className="text-4xl font-bold mb-2">{CONFIG.game_name}</h2>
        <p className="mb-4">{CONFIG.description}</p>
        <Link to="/join" className="inline-block bg-primary px-6 py-3 rounded-full font-semibold">Meedoen</Link>
      </div>
    </div>
  )
}
