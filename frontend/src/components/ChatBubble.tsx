import { useState } from 'react'
import { MessageCircleIcon, SendIcon } from 'lucide-react'
import { usePaperChat } from '@/hooks/usePaperChat'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Spinner } from '@/components/ui/spinner'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  SheetFooter,
} from '@/components/ui/sheet'
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from '@/components/ui/message-scroller'

/* Floating chat trigger + panel for a paper. Mounted at the root layout (not
 * a per-page component) so it persists across every /papers/$paperId/* page
 * -- today that's just the patients page, but it requires no changes when
 * occurrences/variants get their own React routes later. */
export function ChatBubble({ paperId }: { paperId: number }) {
  const { messages, isLoading, sendMessage } = usePaperChat(paperId)
  const [draft, setDraft] = useState('')

  const handleSend = () => {
    const message = draft.trim()
    if (!message || sendMessage.isPending) return
    setDraft('')
    sendMessage.mutate(message)
  }

  return (
    <Sheet>
      <SheetTrigger
        render={
          <Button
            size="icon"
            className="fixed bottom-6 right-6 z-40 h-12 w-12 rounded-full shadow-lg"
          />
        }
      >
        <MessageCircleIcon />
        <span className="sr-only">Open chat</span>
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Paper Chat</SheetTitle>
        </SheetHeader>

        <MessageScrollerProvider>
          <MessageScroller className="flex-1 px-4">
            <MessageScrollerViewport>
              <MessageScrollerContent>
                {isLoading && (
                  <div className="flex justify-center py-8">
                    <Spinner />
                  </div>
                )}
                {messages.map((message) => (
                  <MessageScrollerItem key={message.id}>
                    <div
                      className={cn(
                        'flex',
                        message.role === 'user' ? 'justify-end' : 'justify-start',
                      )}
                    >
                      <div
                        className={cn(
                          'max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap',
                          message.role === 'user'
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-foreground',
                        )}
                      >
                        {message.content}
                      </div>
                    </div>
                  </MessageScrollerItem>
                ))}
                {sendMessage.isPending && (
                  <MessageScrollerItem>
                    <div className="flex justify-start">
                      <div className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                        <Spinner className="size-4" />
                      </div>
                    </div>
                  </MessageScrollerItem>
                )}
              </MessageScrollerContent>
            </MessageScrollerViewport>
            <MessageScrollerButton />
          </MessageScroller>
        </MessageScrollerProvider>

        <SheetFooter>
          <div className="flex gap-2">
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder="Ask a question, or ask to re-run an extraction step..."
              className="min-h-10"
            />
            <Button
              size="icon"
              onClick={handleSend}
              disabled={!draft.trim() || sendMessage.isPending}
            >
              <SendIcon />
              <span className="sr-only">Send</span>
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
