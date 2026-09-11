/* The signed-in user's avatar.
 *
 * Initials only, for now. There is no image to show: users have no avatar
 * column, and the object storage that would hold one was deliberately removed
 * (#138/#139). AvatarImage is wired anyway so adding an `avatar_url` later is a
 * one-line change here rather than a rewrite -- with no src it renders nothing
 * and the fallback shows through.
 */
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import type { UserResp } from '@/api/generated/types.gen'

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
  user: Pick<UserResp, 'first_name' | 'last_name' | 'email'>
  size?: 'sm' | 'default' | 'lg'
  className?: string
}) {
  const fullName = `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim()
  return (
    <Avatar size={size} className={className}>
      <AvatarImage alt={fullName || user.email} />
      <AvatarFallback>{initialsFor(user)}</AvatarFallback>
    </Avatar>
  )
}
