import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f5f5f7",
          200: "#c9c9d1",
          300: "#a5a5b2",
          400: "#7c7c8a",
          500: "#666676",
          600: "#393945",
          700: "#24242d",
          800: "#17171e",
          900: "#0d0d12",
          950: "#08080c",
        },
        accent: {
          DEFAULT: "#7c5cff",
          soft: "#b9a7ff",
        },
      },
      fontFamily: {
        serif: ["ui-serif", "Georgia", "Cambria", "serif"],
        sans: ["ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
