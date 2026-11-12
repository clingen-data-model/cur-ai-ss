import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  applyChatProposalPapersPaperIdChatMessagesMessageIdApplyPost,
  cancelChatProposalPapersPaperIdChatMessagesMessageIdCancelPost,
  clearChatMessagesPapersPaperIdChatMessagesDelete,
  listChatMessagesPapersPaperIdChatMessagesGet,
  sendChatMessagePapersPaperIdChatMessagesPost,
} from '@/api/generated'
import type { ChatMessageResp } from '@/api/generated/types.gen'
import { apiErrorMessage } from '@/lib/apiError'

export type { ChatMessageResp }

/** Apply or cancel the direct edits a chat reply proposed. Applying changes
 * the paper's data, so every view of it refetches; the chat refetches either
 * way to show the card resolved. */
const APPLIED_EDIT_QUERIES = [
  'families',
  'patients',
  'variants',
  'occurrences',
  'phenotypes',
  'flags',
  'review-cases',
  'segregation-analysis',
]

function useResolveProposal(paperId: number, outcome: 'apply' | 'cancel') {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (messageId: number) => {
      const options = {
        path: { paper_id: paperId, message_id: messageId },
        throwOnError: true as const,
      }
      return outcome === 'apply'
        ? applyChatProposalPapersPaperIdChatMessagesMessageIdApplyPost(options)
        : cancelChatProposalPapersPaperIdChatMessagesMessageIdCancelPost(options)
    },
    onSuccess: () => {
      if (outcome === 'apply') {
        // A proposal can touch any of the paper's tables (a deleted
        // individual takes their occurrences and phenotypes with them).
        for (const key of APPLIED_EDIT_QUERIES) {
          queryClient.invalidateQueries({ queryKey: [key, paperId] })
        }
        queryClient.invalidateQueries({ queryKey: ['papers'] })
        toast.success('Changes applied')
      }
    },
    onError: (err) =>
      toast.error(
        apiErrorMessage(err, outcome === 'apply' ? 'Could not apply the changes' : 'Could not cancel'),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['paper-chat', paperId] }),
  })
}

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

  const clearChat = useMutation({
    mutationFn: () =>
      clearChatMessagesPapersPaperIdChatMessagesDelete({ path: { paper_id: paperId } }),
    onSuccess: () => {
      queryClient.setQueryData<ChatMessageResp[]>(queryKey, [])
      toast.success('Chat cleared')
    },
    onError: (err) => {
      toast.error(`Failed to clear chat: ${err.message}`)
    },
  })

  const applyProposal = useResolveProposal(paperId, 'apply')
  const cancelProposal = useResolveProposal(paperId, 'cancel')

  return {
    messages: messagesQuery.data ?? [],
    isLoading: messagesQuery.isPending,
    isError: messagesQuery.isError,
    sendMessage,
    clearChat,
    applyProposal,
    cancelProposal,
  }
}
