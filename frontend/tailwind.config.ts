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
        warning: 'var(--warning)',
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
          'PingFang SC',
          'Hiragino Sans GB',
          'Microsoft YaHei',
          'Noto Sans SC',
          'sans-serif',
        ],
      },
      fontSize: {
        'xs': ['0.75rem', { lineHeight: '1.125rem', letterSpacing: '0.01em' }],
        'sm': ['0.875rem', { lineHeight: '1.3125rem', letterSpacing: '0' }],
        'base': ['1rem', { lineHeight: '1.5rem', letterSpacing: '0' }],
        'lg': ['1.125rem', { lineHeight: '1.6875rem', letterSpacing: '-0.01em' }],
        'xl': ['1.25rem', { lineHeight: '1.875rem', letterSpacing: '-0.02em' }],
      },
      letterSpacing: {
        tightest: '-0.03em',
      },
      lineHeight: {
        relaxed: '1.625',
      },
      borderRadius: {
        card: '10px',
        btn: '8px',
        dialog: '14px',
      },
      boxShadow: {
        soft: '0 2px 8px -2px rgba(0, 0, 0, 0.12)',
        elevated: '0 8px 24px -8px rgba(0, 0, 0, 0.2)',
        glow: '0 0 20px -4px var(--glow-color, rgba(255,255,255,0.35))',
      },
      transitionDuration: {
        DEFAULT: '200ms',
      },
      transitionTimingFunction: {
        DEFAULT: 'cubic-bezier(0.4, 0, 0.2, 1)',
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
