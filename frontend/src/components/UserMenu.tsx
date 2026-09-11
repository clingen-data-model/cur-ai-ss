/* Signed-in user controls in the header.
 *
 * The avatar, the upload allowance, and sign-out. Change password used to live
 * here behind a dialog; it moved to /settings, which the avatar links to.
 *
 * The name and email are deliberately not printed. The avatar stands in for
 * them -- it carries the initials, names the user in its tooltip and aria-label,
 * and /settings shows the full identity. A header should be the smallest thing
 * that gets you where you are going.
 */
import { Link } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { UserAvatar } from '@/components/UserAvatar'
import { useAuth } from '@/lib/auth'

export function UserMenu() {
  const { user, signOut } = useAuth()
  if (!user) return null

  // The only place the user is named now that the header prints no text, so it
  // feeds both the tooltip and the avatar's accessible name.
  const fullName = `${user.first_name} ${user.last_name}`.trim()
  const displayName = fullName ? `${fullName} (${user.email})` : user.email

  return (
    <div className="flex items-center gap-3 text-white">
      {user.max_papers !== null && user.max_papers !== undefined && (
        <p className="text-xs opacity-80 leading-tight">
          {user.max_papers} paper upload{user.max_papers !== 1 ? 's' : ''} remaining
        </p>
      )}
      <Tooltip>
        <TooltipTrigger
          render={
            <Link
              to="/settings"
              aria-label={`Account settings for ${displayName}`}
              className="rounded-full ring-offset-2 ring-offset-transparent transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            />
          }
        >
          <UserAvatar user={user} />
        </TooltipTrigger>
        <TooltipContent>{displayName}</TooltipContent>
      </Tooltip>
      <Button variant="ghost" size="sm" className="text-white hover:bg-white/10" onClick={signOut}>
        Log out
      </Button>
    </div>
  )
}
