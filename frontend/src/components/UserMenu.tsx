/* Signed-in user controls in the header.
 *
 * Mirrors the Streamlit sidebar in lib/ui/auth.py: display name, remaining
 * paper uploads, change-password, and log out.
 */
import React, { useState } from 'react'
import { toast } from 'sonner'
import { changePasswordAuthChangePasswordPost } from '@/api/generated'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { MIN_PASSWORD_LENGTH, errorDetail, useAuth } from '@/lib/auth'

function ChangePasswordDialog() {
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const reset = () => {
    setCurrent('')
    setNext('')
    setRepeat('')
    setError(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!(current && next)) {
      setError('All fields are required.')
      return
    }
    if (next !== repeat) {
      setError('New passwords do not match.')
      return
    }
    if (next.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }
    setPending(true)
    try {
      await changePasswordAuthChangePasswordPost({
        body: { current_password: current, new_password: next },
      })
      toast.success('Password updated.')
      setOpen(false)
      reset()
    } catch (err) {
      setError(errorDetail(err, 'Could not update password.'))
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v)
        if (!v) reset()
      }}
    >
      <DialogTrigger
        render={<Button variant="ghost" size="sm" className="text-white hover:bg-white/10" />}
      >
        Change password
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Change password</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input
            type="password"
            placeholder="Current password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
          />
          <Input
            type="password"
            placeholder="New password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
          />
          <Input
            type="password"
            placeholder="Repeat new password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            autoComplete="new-password"
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? 'Updating…' : 'Update password'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function UserMenu() {
  const { user, signOut } = useAuth()
  if (!user) return null

  const fullName = `${user.first_name} ${user.last_name}`.trim()
  const displayName = fullName ? `${fullName} (${user.email})` : user.email

  return (
    <div className="flex items-center gap-3 text-white">
      <div className="text-right leading-tight">
        <p className="text-sm">
          Signed in as <span className="font-semibold">{displayName}</span>
        </p>
        {user.max_papers !== null && user.max_papers !== undefined && (
          <p className="text-xs opacity-80">
            {user.max_papers} paper upload{user.max_papers !== 1 ? 's' : ''} remaining
          </p>
        )}
      </div>
      <ChangePasswordDialog />
      <Button variant="ghost" size="sm" className="text-white hover:bg-white/10" onClick={signOut}>
        Log out
      </Button>
    </div>
  )
}
