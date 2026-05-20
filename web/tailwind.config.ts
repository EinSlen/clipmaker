import type { Config } from 'tailwindcss';

export default {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          50: '#f5f5f7',
          200: '#c9c9d1',
          400: '#7c7c8a',
          700: '#23232b',
          800: '#15151b',
          900: '#0b0b10'
        },
        accent: {
          DEFAULT: '#8b6cff',
          soft: '#b9a7ff'
        }
      },
      fontFamily: {
        serif: ['ui-serif', 'Georgia', 'Cambria', 'serif'],
        sans: ['ui-sans-serif', 'system-ui', 'sans-serif']
      }
    }
  },
  plugins: []
} satisfies Config;
