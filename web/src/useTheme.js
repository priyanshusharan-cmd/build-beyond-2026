import { useEffect, useState } from 'react'

const KEY = 'ba-theme'
const mq = () => window.matchMedia('(prefers-color-scheme: dark)')
const read = () => { try { return localStorage.getItem(KEY) } catch { return null } }

/** 'light' | 'dark', resolved from an explicit choice or the OS setting. Sets data-theme on <html>. */
export function useTheme() {
  const [choice, setChoice] = useState(read)
  const [os, setOs] = useState(() => (mq().matches ? 'dark' : 'light'))
  useEffect(() => {
    const m = mq(), f = () => setOs(m.matches ? 'dark' : 'light')
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [])
  const theme = choice ?? os
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#0E131B' : '#F4F6FA')
  }, [theme])
  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setChoice(next)
    try { localStorage.setItem(KEY, next) } catch { /* private mode */ }
  }
  return [theme, toggle]
}

export const CHART_THEME = {
  light: { axis: '#8A94A3', grid: '#E9ECF1', ink: '#1F2733', heatBg: '#F1F3F6', price: '#C4622D', shock: '#C62F3B', chaos: '#C4622D' },
  dark: { axis: '#7D8A9C', grid: '#232C3A', ink: '#E7ECF3', heatBg: '#1C2431', price: '#F0956A', shock: '#FF7B84', chaos: '#F0956A' },
}
