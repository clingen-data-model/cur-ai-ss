/* The signed-in user's avatar.
 *
 * Renders the uploaded image when there is one and initials otherwise. Object
 * storage was removed in #138/#139, so the image is served off the VM disk by
 * the same static mount that serves PDF thumbnails -- which is why the src is
 * built from API_BASE_URL rather than being a bare path.
 *
 * avatar_url already carries a ?v= cache-buster from the server; the file path
 * itself never changes, and the static mount sends a 24-hour Cache-Control.
 */
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import type { UserResp } from '@/api/generated/types.gen'
import { API_BASE_URL } from '@/lib/api'

/** First letters of the user's names; the email's first letter if they have none. */
export function initialsFor(user: Pick<UserResp, 'first_name' | 'last_name' | 'email'>): string {
  const letters = [user.first_name, user.last_name]
    .map((n) => n?.trim()?.[0] ?? '')
    .join('')
  return (letters || user.email?.[0] || '?').toUpperCase()
}

export function UserAvatar({
  user,
  size,
  className,
}: {
  user: Pick<UserResp, 'first_name' | 'last_name' | 'email'> & {
    avatar_url?: string | null
  }
  size?: 'sm' | 'default' | 'lg'
  className?: string
}) {
  const fullName = `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim()
  const src = user.avatar_url ? `${API_BASE_URL}${user.avatar_url}` : undefined
  return (
    <Avatar size={size} className={className}>
      <AvatarImage src={src} alt={fullName || user.email} />
      <AvatarFallback>{initialsFor(user)}</AvatarFallback>
    </Avatar>
  )
}
