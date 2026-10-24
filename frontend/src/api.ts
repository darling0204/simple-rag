// API 基础地址：
// - 开发环境可在 frontend/.env 中配置 VITE_API_BASE_URL
// - 生产环境默认同源（由 Nginx 反代 /api 到后端）
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL as string | undefined
) ?? "";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export class AuthError extends ApiError {
  constructor() {
    super(401, "登录状态已失效，请重新登录");
  }
}

async function parseError(response: Response, fallback: string): Promise<never> {
  let message = fallback;
  try {
    const data = await response.json();
    if (data && typeof data.detail === "string") {
      message = data.detail;
    } else if (data && typeof data.message === "string") {
      message = data.message;
    }
  } catch {
    // 保留默认错误信息
  }
  throw new ApiError(response.status, message);
}

function getToken(): string | null {
  return localStorage.getItem("token");
}

export function clearSession(): void {
  localStorage.removeItem("token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("username");
}

export async function refreshAccessToken(): Promise<string> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) {
    clearSession();
    throw new AuthError();
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    throw new ApiError(0, "无法连接服务器，请检查网络");
  }

  if (!response.ok) {
    clearSession();
    throw new AuthError();
  }

  const data = await response.json();
  localStorage.setItem("token", data.access_token);
  return data.access_token;
}

async function requestWithAuth(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  let token = getToken();

  const doFetch = (accessToken: string | null) =>
    fetch(url, {
      ...options,
      headers: {
        ...(options.headers ?? {}),
        ...(accessToken
          ? { Authorization: `Bearer ${accessToken}` }
          : {}),
      },
    });

  let response: Response;
  try {
    response = await doFetch(token);
  } catch {
    throw new ApiError(0, "无法连接服务器，请检查网络");
  }

  if (response.status === 401 && token) {
    try {
      token = await refreshAccessToken();
      response = await doFetch(token);
    } catch (error) {
      if (error instanceof AuthError) {
        throw error;
      }
      throw error;
    }
  }

  return response;
}

// =========================
// 类型定义
// =========================

export interface UserInfo {
  id: number;
  username: string;
  is_admin: boolean;
  created_at?: string;
}

export interface LoginResult {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: UserInfo;
}

export interface KnowledgeBase {
  id: number;
  name: string;
  description: string;
  user_id: number;
  created_at?: string;
}

export interface DocumentItem {
  id: number;
  filename: string;
  size: number;
  chunk_count: number;
  status: "pending" | "indexing" | "ready" | "failed";
  error_message: string;
}

export interface ConversationItem {
  id: number;
  title: string;
  knowledge_base_id: number;
  updated_at?: string;
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  tool_calls?: ToolCallTrace[];
  streaming?: boolean;
}

export interface ToolCallTrace {
  round?: number;
  tool: string;
  arguments?: Record<string, unknown>;
  result?: string;
}

export interface StreamEvent {
  type: "tool_call" | "tool_result" | "delta" | "done" | "error";
  content?: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  result?: string;
  answer?: string;
  sources?: string[];
  message?: string;
}

export interface CodingStep {
  round?: number;
  tool: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
  path?: string;
  diff?: string;
}

// =========================
// 认证
// =========================

export async function register(
  username: string,
  password: string
): Promise<{ id: number; username: string }> {
  const response = await fetch(`${API_BASE_URL}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    return parseError(response, "注册失败");
  }
  return response.json();
}

export async function login(
  username: string,
  password: string
): Promise<LoginResult> {
  const response = await fetch(`${API_BASE_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    return parseError(response, "登录失败");
  }
  return response.json();
}

export async function getMe(): Promise<UserInfo> {
  const response = await requestWithAuth(`${API_BASE_URL}/users/me`);
  if (!response.ok) {
    return parseError(response, "获取用户信息失败");
  }
  return response.json();
}

// =========================
// 知识库
// =========================

export async function getKnowledgeBases(): Promise<KnowledgeBase[]> {
  const response = await requestWithAuth(`${API_BASE_URL}/knowledge-bases`);
  if (!response.ok) {
    return parseError(response, "获取知识库失败");
  }
  return response.json();
}

export async function createKnowledgeBase(
  name: string,
  description: string
): Promise<KnowledgeBase> {
  const response = await requestWithAuth(`${API_BASE_URL}/knowledge-bases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
  if (!response.ok) {
    return parseError(response, "创建知识库失败");
  }
  return response.json();
}

export async function deleteKnowledgeBase(
  knowledgeBaseId: number
): Promise<void> {
  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    return parseError(response, "删除知识库失败");
  }
}

export async function getIndexStatus(
  knowledgeBaseId: number
): Promise<{
  rebuilding: boolean;
  ready: boolean;
  index_exists: boolean;
  documents: DocumentItem[];
}> {
  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/index-status`
  );
  if (!response.ok) {
    return parseError(response, "获取索引状态失败");
  }
  return response.json();
}

// =========================
// 文档
// =========================

export async function getDocuments(
  knowledgeBaseId: number
): Promise<DocumentItem[]> {
  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents`
  );
  if (!response.ok) {
    return parseError(response, "获取文档失败");
  }
  return response.json();
}

export async function uploadDocument(
  knowledgeBaseId: number,
  file: File
): Promise<DocumentItem> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents`,
    { method: "POST", body: formData }
  );
  if (!response.ok) {
    return parseError(response, "上传文档失败");
  }
  return response.json();
}

export async function deleteDocument(
  knowledgeBaseId: number,
  documentId: number
): Promise<void> {
  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    return parseError(response, "删除文档失败");
  }
}

// =========================
// 会话与消息
// =========================

export async function getConversations(
  knowledgeBaseId: number
): Promise<ConversationItem[]> {
  const response = await requestWithAuth(
    `${API_BASE_URL}/conversations?knowledge_base_id=${knowledgeBaseId}`
  );
  if (!response.ok) {
    return parseError(response, "获取会话失败");
  }
  return response.json();
}

export async function createConversation(
  title: string,
  knowledgeBaseId: number
): Promise<ConversationItem> {
  const response = await requestWithAuth(`${API_BASE_URL}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, knowledge_base_id: knowledgeBaseId }),
  });
  if (!response.ok) {
    return parseError(response, "创建会话失败");
  }
  return response.json();
}

export async function deleteConversation(
  conversationId: number
): Promise<void> {
  const response = await requestWithAuth(
    `${API_BASE_URL}/conversations/${conversationId}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    return parseError(response, "删除会话失败");
  }
}

export async function getMessages(
  conversationId: number
): Promise<{ total: number; messages: ChatMessage[] }> {
  const response = await requestWithAuth(
    `${API_BASE_URL}/conversations/${conversationId}/messages`
  );
  if (!response.ok) {
    return parseError(response, "获取历史消息失败");
  }
  return response.json();
}

export async function sendMessage(
  message: string,
  conversationId: number,
  knowledgeBaseId: number
): Promise<{ answer: string; sources: string[] }> {
  const response = await requestWithAuth(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      knowledge_base_id: knowledgeBaseId,
    }),
  });
  if (!response.ok) {
    return parseError(response, "聊天请求失败");
  }
  return response.json();
}

// =========================
// 流式对话（SSE）
// =========================

export async function streamChat(
  message: string,
  conversationId: number,
  knowledgeBaseId: number,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const doStream = async (accessToken: string | null) => {
    const response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        knowledge_base_id: knowledgeBaseId,
      }),
      signal,
    });

    if (response.status === 401 && accessToken) {
      const newToken = await refreshAccessToken();
      return doStream(newToken);
    }

    if (!response.ok) {
      return parseError(response, "聊天请求失败");
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new ApiError(0, "浏览器不支持流式响应");
    }

    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith("data:")) {
          continue;
        }
        try {
          const event = JSON.parse(line.slice(5).trim()) as StreamEvent;
          onEvent(event);
        } catch {
          // 忽略无法解析的帧
        }
      }
    }
  };

  await doStream(getToken());
}

// =========================
// Coding Agent
// =========================

export async function runCodingAgent(task: string): Promise<{
  answer: string;
  steps: CodingStep[];
  modified_files: string[];
  diffs: { path: string; diff: string }[];
}> {
  const response = await requestWithAuth(`${API_BASE_URL}/coding-agent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task }),
  });
  if (!response.ok) {
    return parseError(response, "Coding Agent 请求失败");
  }
  return response.json();
}
