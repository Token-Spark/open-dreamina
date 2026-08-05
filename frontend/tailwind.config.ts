import type { Config } from 'tailwindcss'

// Black-white-gray tech aesthetic per spec section 10.1.
// 颜色 token 全部引用 CSS 变量，由 globals.css 在 .dark / .light 下切换值，
// 这样无需在组件中写 dark: 前缀即可整页切换深/浅色主题。
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Background layers
        bg: {
          primary: 'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          tertiary: 'var(--bg-tertiary)',
        },
        // Text hierarchy
        fg: {
          primary: 'var(--fg-primary)',
          secondary: 'var(--fg-secondary)',
          muted: 'var(--fg-muted)',
        },
        // Accents / status (status colors used only for indicators)
        accent: 'var(--accent)',
        success: 'var(--success)',
        error: 'var(--error)',
        border: {
          DEFAULT: 'var(--border)',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'SF Pro Display',
          'SF Pro Text',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'sans-serif',
        ],
      },
      borderRadius: {
        card: '8px',
        btn: '6px',
        dialog: '12px',
      },
      transitionDuration: {
        DEFAULT: '200ms',
      },
      transitionTimingFunction: {
        DEFAULT: 'ease',
      },
      keyframes: {
        'breath-glow': {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 8px 0 var(--glow-color, rgba(255,255,255,0.35))' },
          '50%': { opacity: '0.6', boxShadow: '0 0 16px 2px var(--glow-color, rgba(255,255,255,0.6))' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.96)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'breath-glow': 'breath-glow 2s ease-in-out infinite',
        'fade-in': 'fade-in 200ms ease',
        'scale-in': 'scale-in 200ms ease',
        'slide-up': 'slide-up 200ms ease',
      },
    },
  },
  plugins: [],
} satisfies Config
