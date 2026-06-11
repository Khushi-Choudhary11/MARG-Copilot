/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        rail:   { DEFAULT: '#f97316', dark: '#c2410c' },
        safe:   '#22c55e',
        warn:   '#eab308',
        danger: '#ef4444',
        panel:  '#0f172a',
        card:   '#1e293b',
        border: '#334155',
      },
      animation: {
        'pulse-fast': 'pulse 0.8s cubic-bezier(0.4,0,0.6,1) infinite',
        'count-up':   'countUp 0.4s ease-out',
      },
      keyframes: {
        countUp: { '0%': { transform: 'translateY(8px)', opacity: '0' },
                   '100%': { transform: 'translateY(0)', opacity: '1' } },
      },
    },
  },
  plugins: [],
}
