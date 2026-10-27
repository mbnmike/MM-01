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
        coal: "#121212",
        bone: "#f4f4f0",
        // light: the same green lifted for readable text and hovers on dark backgrounds.
        forest: { DEFAULT: "#2c570e", dark: "#1f3f0a", light: "#6f9f45" },
      },
      fontFamily: {
        display: ['"Archivo Black"', "Impact", "system-ui", "sans-serif"],        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        serif: ['"Source Serif 4"', "Georgia", "Cambria", '"Times New Roman"', "serif"],
      },
      keyframes: {
        marquee: { "0%": { transform: "translateX(0)" }, "100%": { transform: "translateX(-50%)" } },
        nudge: { "0%, 100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(6px)" } },
      },
      animation: { marquee: "marquee 30s linear infinite", nudge: "nudge 2.4s ease-in-out infinite" },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
