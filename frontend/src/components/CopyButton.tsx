/* Small icon button that copies a value to the clipboard, flipping to a
 * checkmark briefly to confirm -- for identifiers a curator needs to paste
 * elsewhere (e.g. an HPO id) rather than just read. */
import { useState } from 'react'
import { Check, Copy } from 'lucide-react'

export function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard access can be denied (permissions, insecure context) -- no
      // confirmation is the only feedback needed; nothing else to recover.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      title="Copy"
      className="inline-flex items-center justify-center size-5 shrink-0 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </button>
  )
}
