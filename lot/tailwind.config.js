/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./core/**/*.{html,py}",
    "./shop/**/*.{html,py}",
    "./blog/**/*.{html,py}",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#0a0a0a",
        bone: "#f4f4f0",
        forest: { DEFAULT: "#2c570e", dark: "#1f3f0a" },
      },
      fontFamily: {
        display: ['"Archivo Black"', "Impact", "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        serif: ['"Source Serif 4"', "Georgia", "Cambria", '"Times New Roman"', "serif"],
      },
      keyframes: {
        marquee: { "0%": { transform: "translateX(0)" }, "100%": { transform: "translateX(-50%)" } },
      },
      animation: { marquee: "marquee 30s linear infinite" },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
