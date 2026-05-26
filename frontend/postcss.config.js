/* PostCSS configuration for Tailwind CSS
 * Tailwind CSS works as a PostCSS plugin, which transforms @tailwind
 * directives in CSS files into actual Tailwind classes.
 * Autoprefixer adds vendor prefixes for older browser support.
 */
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
