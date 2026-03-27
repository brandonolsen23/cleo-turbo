/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    fontFamily: {
      sans: [
        '"Untitled Sans"',
        "-apple-system",
        "BlinkMacSystemFont",
        '"Segoe UI"',
        "Helvetica",
        "Arial",
        "sans-serif",
      ],
    },
    fontWeight: {
      light: "300",
      normal: "400",
      medium: "500",
      semibold: "500",
      bold: "500",
    },
  },
  plugins: [],
};
