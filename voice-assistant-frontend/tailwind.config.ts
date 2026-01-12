import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "accent-gold": "#B9965B",
      },
      fontFamily: {
        heading: ["Frastha", "serif"],
        body: ["Lato", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
