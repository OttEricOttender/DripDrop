/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        waterDrop: {
          '0%':   { transform: 'translateY(-6px) scale(0.8)', opacity: '0' },
          '40%':  { opacity: '1' },
          '80%':  { transform: 'translateY(6px) scale(1.1)', opacity: '0.6' },
          '100%': { transform: 'translateY(10px) scale(0.9)', opacity: '0' },
        },
        waveFlow: {
          '0%, 100%': { transform: 'scaleX(1)',   opacity: '0.6' },
          '50%':      { transform: 'scaleX(1.18)', opacity: '1'   },
        },
      },
      animation: {
        'water-drop':  'waterDrop 1.4s ease-in-out infinite',
        'wave-flow':   'waveFlow 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
