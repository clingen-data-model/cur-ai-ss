import type { Config } from 'tailwindcss'

/* Tailwind CSS configuration
 * - content: tells Tailwind which files to scan for class names
 *   This prevents unused styles in production
 * - theme.extend: customize or extend Tailwind's default design tokens
 *   (colors, spacing, fonts, etc.)
 * - plugins: add Tailwind plugins (e.g., shadcn/ui components will register here)
 */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
} satisfies Config
