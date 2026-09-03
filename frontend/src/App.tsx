import React from 'react'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import Home from './pages/Home'
import Join from './pages/Join'
import Admin from './pages/Admin'
import Game from './pages/Game'
import Test from './pages/Test'
import './styles/index.css'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-950 text-slate-100">
        <header className="border-b border-white/10 bg-slate-950/80 backdrop-blur-sm">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
            <Link to="/" className="text-xl font-bold tracking-[0.22em] text-white uppercase">
              Secret Game
            </Link>
            <nav className="flex items-center gap-4 text-sm text-slate-300">
              <Link to="/" className="transition hover:text-white">Home</Link>
              <Link to="/join" className="transition hover:text-white">Meedoen</Link>
              <Link to="/admin" className="transition hover:text-white">Admin</Link>
            </nav>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/join" element={<Join />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/game" element={<Game />} />
            <Route path="/admin/test" element={<Test />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
