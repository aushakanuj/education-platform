import { apiRequest } from "./client";

export type ChatCitation = {
  id: string;
  label: string;
  excerpt: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  citations?: ChatCitation[] | null;
  created_at: string;
};

export type ContextUsage = {
  used_tokens: number;
  limit_tokens: number;
  used_percent: number;
};

export type ConversationSummary = {
  id: string;
  title: string;
  updated_at: string;
  context: ContextUsage;
};

export type ConversationDetail = ConversationSummary & {
  messages: ChatMessage[];
};

export type PostMessageResult = {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  context: ContextUsage;
};

export function listChats(): Promise<ConversationSummary[]> {
  return apiRequest<ConversationSummary[]>("/chats", { auth: true });
}

export function createChat(title?: string): Promise<ConversationSummary> {
  return apiRequest<ConversationSummary>("/chats", {
    method: "POST",
    auth: true,
    body: title ? { title } : {},
  });
}

export function getChat(conversationId: string): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`/chats/${encodeURIComponent(conversationId)}`, {
    auth: true,
  });
}

export function deleteChat(conversationId: string): Promise<void> {
  return apiRequest<void>(`/chats/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
    auth: true,
  });
}

export function postChatMessage(
  conversationId: string,
  content: string,
): Promise<PostMessageResult> {
  return apiRequest<PostMessageResult>(
    `/chats/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "POST",
      auth: true,
      body: { content },
    },
  );
}
