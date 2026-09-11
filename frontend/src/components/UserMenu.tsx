/* Signed-in user controls in the header.
 *
 * Identity and sign-out only. Change password used to live here behind a
 * dialog; it moved to /settings, which the avatar links to -- the header should
 * say who you are and get out of the way, not host account forms.
 */
import { Link } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { UserAvatar } from '@/components/UserAvatar'
import { useAuth } from '@/lib/auth'

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
      <Tooltip>
        <TooltipTrigger
          render={
            <Link
              to="/settings"
              aria-label="Account settings"
              className="rounded-full ring-offset-2 ring-offset-transparent transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            />
          }
        >
          <UserAvatar user={user} />
        </TooltipTrigger>
        <TooltipContent>Settings</TooltipContent>
      </Tooltip>
      <Button variant="ghost" size="sm" className="text-white hover:bg-white/10" onClick={signOut}>
        Log out
      </Button>
    </div>
  )
}
