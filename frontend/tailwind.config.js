/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#070A10',
          900: '#0B0F17',
          800: '#121826',
          700: '#1A2233',
          600: '#242E44',
          500: '#37435E',
        },
        gold: {
          400: '#E8C077',
          500: '#DDAA4E',
          600: '#C08F35',
        },
        teal: {
          300: '#7FE0D3',
          400: '#4FD1C5',
          500: '#2FB6AA',
        },
        ledger: {
          up: '#4FD1C5',
          down: '#E8846B',
        },
      },
      fontFamily: {
        display: ['"Fraunces"', 'ui-serif', 'Georgia', 'serif'],
        sans: ['"Inter"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      backgroundImage: {
        'grain': "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.035) 1px, transparent 0)",
      },
    },
  },
  plugins: [],
}
