import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  listChatMessagesPapersPaperIdChatMessagesGet,
  sendChatMessagePapersPaperIdChatMessagesPost,
} from '@/api/generated'
import type { ChatMessageResp } from '@/api/generated/types.gen'

export type { ChatMessageResp }

export function usePaperChat(paperId: number) {
  const queryClient = useQueryClient()
  const queryKey = ['paper-chat', paperId]

  const messagesQuery = useQuery({
    queryKey,
    queryFn: () =>
      listChatMessagesPapersPaperIdChatMessagesGet({ path: { paper_id: paperId } }),
  })

  const sendMessage = useMutation({
    mutationFn: (message: string) =>
      sendChatMessagePapersPaperIdChatMessagesPost({
        path: { paper_id: paperId },
        body: { message },
      }),
    // Optimistically show the user's own message right away -- the assistant's
    // reply can take a few seconds (a real model call), and this is a chat
    // panel, not a form. Replaced by the real rows once the request settles.
    onMutate: async (message) => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<ChatMessageResp[]>(queryKey)
      const optimistic: ChatMessageResp = {
        id: -Date.now(),
        paper_id: paperId,
        role: 'user',
        content: message,
        created_at: new Date().toISOString(),
      }
      queryClient.setQueryData<ChatMessageResp[]>(queryKey, (old) => [
        ...(old ?? []),
        optimistic,
      ])
      return { previous }
    },
    onError: (err, _message, context) => {
      queryClient.setQueryData(queryKey, context?.previous)
      toast.error(`Message failed: ${err.message}`)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey })
    },
  })

  return {
    messages: messagesQuery.data ?? [],
    isLoading: messagesQuery.isPending,
    isError: messagesQuery.isError,
    sendMessage,
  }
}
