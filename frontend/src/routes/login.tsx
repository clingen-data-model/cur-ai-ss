/* Login screen.
 *
 * Mirrors lib/ui/auth.py: a sign-in form plus a collapsible "request access"
 * form. Registration deliberately does not sign anyone in — /auth/register
 * creates an inactive account, and an admin has to run lib.bin.activate_user
 * before the credentials work.
 */
import React, { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { ChevronDownIcon, ChevronRightIcon } from 'lucide-react'
import { registerUserAuthRegisterPost } from '@/api/generated'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { EMAIL_RE, errorDetail, useAuth } from '@/lib/auth'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </label>
  )
}

function ErrorText({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-destructive">{children}</p>
}

function SignInForm() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      await signIn(email, password)
      navigate({ to: '/' })
    } catch {
      // The API returns 'Incorrect email or password' for unknown, inactive, and
      // wrong-password alike; don't leak which one it was.
      setError('Email/password is incorrect.')
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Field label="Email">
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
        />
      </Field>
      <Field label="Password">
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
      </Field>
      {error && <ErrorText>{error}</ErrorText>}
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  )
}

function RequestAccessForm() {
  const [open, setOpen] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [useCase, setUseCase] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!(firstName && lastName && email && useCase)) {
      setError('All fields are required.')
      return
    }
    if (!EMAIL_RE.test(email.trim())) {
      setError('Please enter a valid email address.')
      return
    }
    setPending(true)
    try {
      await registerUserAuthRegisterPost({
        body: {
          email: email.trim(),
          first_name: firstName,
          last_name: lastName,
          description_of_use_case: useCase,
        },
      })
      setSubmitted(true)
    } catch (err) {
      setError(errorDetail(err, 'Could not submit request.'))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="mt-4 border-t border-border pt-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-sm font-medium hover:opacity-80"
      >
        {open ? <ChevronDownIcon className="size-4" /> : <ChevronRightIcon className="size-4" />}
        Need access? Request it here!
      </button>

      {open &&
        (submitted ? (
          <p className="mt-3 text-sm text-green-700">
            Request submitted — an admin will review your request.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="mt-3 space-y-3">
            <Field label="First name">
              <Input value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            </Field>
            <Field label="Last name">
              <Input value={lastName} onChange={(e) => setLastName(e.target.value)} />
            </Field>
            <Field label="Email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Describe your use case">
              <Textarea value={useCase} onChange={(e) => setUseCase(e.target.value)} rows={3} />
            </Field>
            {error && <ErrorText>{error}</ErrorText>}
            <Button type="submit" variant="secondary" className="w-full" disabled={pending}>
              {pending ? 'Submitting…' : 'Request access'}
            </Button>
          </form>
        ))}
    </div>
  )
}

export function LoginPage() {
  return (
    <div className="flex justify-center">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
        </CardHeader>
        <CardContent>
          <SignInForm />
          <RequestAccessForm />
        </CardContent>
      </Card>
    </div>
  )
}
