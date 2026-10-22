/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}",
    "./*.html",
  ],
  theme: {
    extend: {
      colors: {
        offwhite: {
          50: "#fcfbf9",
          100: "#f8f7f4",
          200: "#f0eee9",
          300: "#e4e1da",
          800: "#292524",
          900: "#1c1917",
        },
      },
    },
  },
  plugins: [],
}
