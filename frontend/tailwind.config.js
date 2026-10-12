/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: { colors: { brand: { DEFAULT: "#b3121b", dark: "#7f0d13" } } } },
  plugins: [],
};
