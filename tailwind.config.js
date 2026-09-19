/**
 * Tailwind config — implements docs/UI.md's "Visual direction" and
 * "Typography" sections as design tokens. See docs/UI.md for the source
 * language each token maps to; do not add a color/font here without a
 * line in that doc to point back to (docs/DECISIONS.md: the design
 * tokens are a decision, not a developer's personal taste).
 */
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/web/templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        // docs/UI.md "Visual direction": "Warm white background, deep
        // charcoal text, one deep-blue accent, teal/green for positive
        // states ..., amber with explanation for caution, red sparingly."
        "warm-white": "#FAF7F2",
        charcoal: "#2A2A28",
        accent: {
          DEFAULT: "#1E4B8C",
          dark: "#153762",
        },
        positive: {
          DEFAULT: "#0F7B6C",
          bg: "#E6F4F1",
        },
        caution: {
          DEFAULT: "#B45309",
          bg: "#FEF3C7",
        },
        danger: {
          DEFAULT: "#B91C1C",
          bg: "#FEE2E2",
        },
        neutral: {
          // ux-qa-reviewer finding, 2026-09-19: #6B7280 on the badge
          // background (#F3F4F6) measured ~4.4:1, just under WCAG AA's
          // 4.5:1 for normal-weight text -- worse on the italicised
          // "Estimate" badge. Darkened to clear AA with margin.
          DEFAULT: "#4B5563",
          bg: "#F3F4F6",
        },
      },
      fontFamily: {
        // docs/UI.md "Typography": "Noto Sans family with system-font
        // fallback (Devanagari + Latin; Gujarati if the pilot state
        // needs it). No web-font download in the text-only / 2G mode" --
        // system-ui first on purpose: Noto Sans is requested from the
        // OS/browser's own installed fonts, never fetched over the
        // network, so the "no web-font download" constraint holds
        // without any special-casing for a slow connection.
        sans: [
          "Noto Sans",
          "Noto Sans Gujarati",
          "Noto Sans Devanagari",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
