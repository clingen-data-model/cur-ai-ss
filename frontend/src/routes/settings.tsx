/* Account settings.
 *
 * A route rather than a sheet or dialog: settings are a destination you link to
 * and reload, not a quick edit you make without losing your place. Change
 * password used to live in a dialog behind the header's UserMenu; it moved here
 * so there is one place account state is managed.
 */
import React, { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  changePasswordAuthChangePasswordPost,
  deleteMyAvatarAuthMeAvatarDelete,
  updateMeAuthMePatch,
  uploadMyAvatarAuthMeAvatarPut,
} from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { UserAvatar } from '@/components/UserAvatar'
import { Spinner } from '@/components/ui/spinner'
import { MIN_PASSWORD_LENGTH, errorDetail, useAuth } from '@/lib/auth'

function ProfileCard() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)

  const invalidateMe = () =>
    queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })

  const uploadAvatar = useMutation({
    mutationFn: (image: File) =>
      uploadMyAvatarAuthMeAvatarPut({ body: { image }, throwOnError: true }),
    onSuccess: () => {
      invalidateMe()
      toast.success('Picture updated.')
    },
    // The server decodes the bytes rather than trusting the type, so its message
    // ("Not a readable image.") is more accurate than anything guessable here.
    onError: (err) => toast.error(errorDetail(err, 'Could not update picture.')),
  })

  const removeAvatar = useMutation({
    mutationFn: () => deleteMyAvatarAuthMeAvatarDelete({ throwOnError: true }),
    onSuccess: () => {
      invalidateMe()
      toast.success('Picture removed.')
    },
    onError: (err) => toast.error(errorDetail(err, 'Could not remove picture.')),
  })

  if (!user) return null

  const busy = uploadAvatar.isPending || removeAvatar.isPending
  const fullName = `${user.first_name} ${user.last_name}`.trim()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>How you appear across the app.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-4">
          <UserAvatar user={user} size="lg" />
          <div className="min-w-0">
            {fullName && <p className="font-medium leading-tight">{fullName}</p>}
            <p className="text-sm text-muted-foreground truncate">{user.email}</p>
            {user.max_papers !== null && user.max_papers !== undefined && (
              <p className="text-xs text-muted-foreground mt-1">
                {user.max_papers} paper upload{user.max_papers !== 1 ? 's' : ''} remaining
              </p>
            )}
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              {busy && <Spinner className="mr-2" />}
              {user.avatar_url ? 'Change' : 'Add picture'}
            </Button>
            {user.avatar_url && (
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => removeAvatar.mutate()}
              >
                Remove
              </Button>
            )}
          </div>
          {/* The button is the affordance; this only exists to open the picker.
              Resetting value on change means re-picking the same file after a
              failed upload still fires, which it would not otherwise. */}
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            onChange={(e) => {
              const image = e.target.files?.[0]
              e.target.value = ''
              if (image) uploadAvatar.mutate(image)
            }}
          />
        </div>
      </CardContent>
    </Card>
  )
}

function ChangePasswordCard() {
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
      reset()
    } catch (err) {
      setError(errorDetail(err, 'Could not update password.'))
    } finally {
      setPending(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Change password</CardTitle>
        <CardDescription>
          At least {MIN_PASSWORD_LENGTH} characters. You stay signed in afterwards.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4 max-w-sm">
          <div className="space-y-1.5">
            <Label htmlFor="current-password">Current password</Label>
            <Input
              id="current-password"
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-password">New password</Label>
            <Input
              id="new-password"
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="repeat-password">Repeat new password</Label>
            <Input
              id="repeat-password"
              type="password"
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={pending}>
            {pending ? 'Updating…' : 'Update password'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function NotificationsCard() {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (enabled: boolean) =>
      updateMeAuthMePatch({
        body: { notify_on_paper_complete: enabled },
        throwOnError: true,
      }),
    onSuccess: (_data, enabled) => {
      // /auth/me is keyed by token in useAuth; refetch so the toggle reflects
      // what the server stored rather than optimistic local state.
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      toast.success(enabled ? 'Email notifications on.' : 'Email notifications off.')
    },
    onError: (err) => {
      toast.error(errorDetail(err, 'Could not update notification settings.'))
    },
  })

  if (!user) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Notifications</CardTitle>
        <CardDescription>Email sent to {user.email}.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-start justify-between gap-6">
          <div className="space-y-0.5">
            <Label htmlFor="notify-complete">Paper extraction complete</Label>
            <p className="text-sm text-muted-foreground">
              Email me when a paper I queued finishes its pipeline.
            </p>
          </div>
          <Switch
            id="notify-complete"
            checked={user.notify_on_paper_complete}
            disabled={mutation.isPending}
            onCheckedChange={(checked: boolean) => mutation.mutate(checked)}
          />
        </div>
      </CardContent>
    </Card>
  )
}

export function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your account.</p>
      </div>
      <ProfileCard />
      <NotificationsCard />
      <ChangePasswordCard />
    </div>
  )
}
