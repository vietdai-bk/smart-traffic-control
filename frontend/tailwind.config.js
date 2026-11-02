/** @type {import('tailwindcss').Config} */
const v = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Token ngữ nghĩa — tự động đổi theo theme (:root = light, [data-theme=dark] / .dark)
        carbon: v("carbon"),
        surface: v("surface"),
        panel: v("panel"),
        line: v("line"),
        ink: { DEFAULT: v("ink"), dim: v("ink-dim"), mute: v("ink-mute") },
        go: { DEFAULT: v("go"), ink: v("go-ink") },
        warn: { DEFAULT: v("warn"), ink: v("warn-ink") },
        stop: { DEFAULT: v("stop"), ink: v("stop-ink") },
        auto: { DEFAULT: v("auto"), ink: v("auto-ink") },
        manual: { DEFAULT: v("manual"), ink: v("manual-ink") },
      },
      fontFamily: {
        sans: ['"Be Vietnam Pro"', '"Plus Jakarta Sans"', "system-ui", "-apple-system", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        "xs": ["0.75rem", { lineHeight: "1.125rem" }],
        "sm": ["0.8125rem", { lineHeight: "1.25rem" }],
      },
      borderRadius: {
        panel: "10px",
        card: "12px",
        ctl: "7px",
        tag: "4px",
      },
      boxShadow: {
        panel: "var(--shadow-panel)",
        pop: "var(--shadow-pop)",
        "glow-go": "0 0 16px -2px rgba(16, 185, 129, 0.45)",
        "glow-warn": "0 0 16px -2px rgba(245, 158, 11, 0.45)",
        "glow-stop": "0 0 16px -2px rgba(239, 68, 68, 0.45)",
        "glow-auto": "0 0 16px -2px rgba(59, 130, 246, 0.4)",
      },
      keyframes: {
        pulseRing: { "0%,100%": { boxShadow: "0 0 0 0 rgba(239,68,68,0.55)" }, "50%": { boxShadow: "0 0 0 6px rgba(239,68,68,0)" } },
        blink: { "0%,49%": { opacity: "1" }, "50%,100%": { opacity: "0.2" } },
        slideIn: { from: { transform: "translateX(100%)" }, to: { transform: "translateX(0)" } },
        beacon: { "0%,100%": { opacity: "1", transform: "scale(1)" }, "50%": { opacity: "0.4", transform: "scale(0.92)" } },
      },
      animation: {
        pulseRing: "pulseRing 1.4s ease-in-out infinite",
        blink: "blink 1s steps(1) infinite",
        slideIn: "slideIn 180ms cubic-bezier(0.16, 1, 0.3, 1)",
        beacon: "beacon 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
