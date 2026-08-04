import React from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Home from './pages/Home'
import Join from './pages/Join'
import Admin from './pages/Admin'
import './styles/index.css'

export default function App(){
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[radial-gradient(ellipse_at_bottom_right,_var(--tw-gradient-stops))] from-gray-900 via-gray-900 to-black text-white">
        <header className="p-6 flex justify-between items-center">
          <h1 className="text-2xl font-bold">Secret Game</h1>
          <nav className="space-x-4">
            <Link to="/" className="hover:underline">Home</Link>
            <Link to="/join" className="hover:underline">Meedoen</Link>
            <Link to="/admin" className="hover:underline">Admin</Link>
          </nav>
        </header>
        <main className="p-4">
          <Routes>
            <Route path="/" element={<Home/>} />
            <Route path="/join" element={<Join/>} />
            <Route path="/admin" element={<Admin/>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
