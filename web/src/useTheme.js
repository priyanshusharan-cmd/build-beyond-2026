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
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#111418' : '#F8F9FF')
  }, [theme])
  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setChoice(next)
    try { localStorage.setItem(KEY, next) } catch { /* private mode */ }
  }
  return [theme, toggle]
}

export const CHART_THEME = {
  light: { axis: '#73777F', grid: '#DCE0E7', ink: '#191C20', heatBg: '#ECEEF4', heatLow: [186, 26, 26], heatMid: [125, 87, 0], heatHigh: [40, 108, 76], price: '#6B5778', shock: '#BA1A1A', chaos: '#6B5778' },
  dark: { axis: '#8D9199', grid: '#2B2F35', ink: '#E1E2E9', heatBg: '#1D2024', heatLow: [147, 0, 10], heatMid: [121, 86, 10], heatHigh: [0, 82, 47], price: '#D7BDE4', shock: '#FFB4AB', chaos: '#D7BDE4' },
}
