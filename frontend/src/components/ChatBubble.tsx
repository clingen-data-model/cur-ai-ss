import { useState } from 'react'
import { MessageCircleIcon, SendIcon, XIcon } from 'lucide-react'
import { usePaperChat } from '@/hooks/usePaperChat'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Spinner } from '@/components/ui/spinner'
import {
  Card,
  CardAction,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from '@/components/ui/message-scroller'

/* Floating chat trigger + card for a paper. Mounted at the root layout (not
 * a per-page component) so it persists across every /papers/$paperId/* page
 * -- today that's just the patients page, but it requires no changes when
 * occurrences/variants get their own React routes later. */
export function ChatBubble({ paperId }: { paperId: number }) {
  const { messages, isLoading, sendMessage } = usePaperChat(paperId)
  const [draft, setDraft] = useState('')
  const [open, setOpen] = useState(false)

  const handleSend = () => {
    const message = draft.trim()
    if (!message || sendMessage.isPending) return
    setDraft('')
    sendMessage.mutate(message)
  }

  return (
    <Popover
      open={open}
      onOpenChange={(nextOpen, eventDetails) => {
        // Chat is a persistent side task, not a transient menu -- clicking
        // elsewhere on the page to read something shouldn't lose it. Still
        // closes on Escape, the X button, and re-clicking the trigger.
        if (!nextOpen && eventDetails.reason === 'outside-press') return
        setOpen(nextOpen)
      }}
    >
      <PopoverTrigger
        render={
          <Button
            size="icon"
            className="fixed bottom-6 right-6 z-40 h-12 w-12 rounded-full shadow-lg"
          />
        }
      >
        <MessageCircleIcon />
        <span className="sr-only">Open chat</span>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="end"
        sideOffset={12}
        className="w-96 max-w-[calc(100vw-3rem)] rounded-none bg-transparent p-0 shadow-none ring-0"
      >
        <Card className="h-[32rem] max-h-[70vh] gap-0 py-0 shadow-xl">
          <CardHeader className="border-b py-3">
            <CardTitle>Paper Chat</CardTitle>
            <CardAction>
              <PopoverClose
                render={<Button variant="ghost" size="icon-sm" />}
              >
                <XIcon />
                <span className="sr-only">Close</span>
              </PopoverClose>
            </CardAction>
          </CardHeader>

          <CardContent className="min-h-0 flex-1 p-0">
            <MessageScrollerProvider>
              <MessageScroller className="h-full px-4 py-2">
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
          </CardContent>

          <CardFooter className="border-t py-3">
            <div className="flex w-full items-end gap-2">
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                placeholder="Ask a question, or request a rerun..."
                className="min-h-14"
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
          </CardFooter>
        </Card>
      </PopoverContent>
    </Popover>
  )
}
