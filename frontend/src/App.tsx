import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ChangeEvent, KeyboardEvent, ReactNode } from "react";
import "./App.css";
import {
  ApiError,
  AuthError,
  clearSession,
  createConversation,
  createKnowledgeBase,
  deleteConversation,
  deleteDocument,
  deleteKnowledgeBase,
  getConversations,
  getDocuments,
  getIndexStatus,
  getKnowledgeBases,
  getMe,
  getMessages,
  login,
  register,
  runCodingAgent,
  streamChat,
  uploadDocument,
} from "./api";
import type {
  ChatMessage,
  CodingStep,
  ConversationItem,
  DocumentItem,
  KnowledgeBase,
  StreamEvent,
} from "./api";

// =========================
// 轻量 Markdown 渲染（无第三方依赖）
// =========================

function MarkdownLite({ text }: { text: string }) {
  const html = useMemoMarkdown(text);
  return <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function useMemoMarkdown(text: string): string {
  return useMemo(() => renderMarkdown(text), [text]);
}

function renderMarkdown(text: string): string {
  const codeBlocks: string[] = [];
  let source = text.replace(/```([\s\S]*?)```/g, (_match, code: string) => {
    codeBlocks.push(escapeHtml(code.replace(/^\n/, "")));
    return `§§CODE${codeBlocks.length - 1}§§`;
  });

  source = escapeHtml(source);

  source = source
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^### (.*)$/gm, "<h4>$1</h4>")
    .replace(/^## (.*)$/gm, "<h3>$1</h3>")
    .replace(/^# (.*)$/gm, "<h2>$1</h2>")
    .replace(/^[-*] (.*)$/gm, "<li>$1</li>")
    .replace(/^\d+\. (.*)$/gm, "<li>$1</li>")
    .replace(/\n/g, "<br/>");

  source = source.replace(/§§CODE(\d+)§§/g, (_match, index: string) => {
    const code = codeBlocks[Number(index)] ?? "";
    return `<pre class="code-block"><code>${code}</code></pre>`;
  });

  return source;
}

// =========================
// 通用弹窗
// =========================

function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">{title}</div>
        {children}
      </div>
    </div>
  );
}

function Toast({
  message,
  kind,
  onClose,
}: {
  message: string;
  kind: "success" | "error";
  onClose: () => void;
}) {
  useEffect(() => {
    const timer = window.setTimeout(onClose, 3500);
    return () => window.clearTimeout(timer);
  }, [message, onClose]);

  return <div className={`toast toast-${kind}`}>{message}</div>;
}

// =========================
// 登录 / 注册页
// =========================

function AuthPage({
  onSuccess,
}: {
  onSuccess: (username: string) => void;
}) {
  const [username, setUsername] = useState(
    localStorage.getItem("username") || ""
  );
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!username.trim() || !password) {
      setError("请输入用户名和密码");
      return;
    }

    setSubmitting(true);
    setError("");

    try {
      if (isRegisterMode) {
        if (password !== confirmPassword) {
          setError("两次输入的密码不一致");
          return;
        }
        await register(username.trim(), password);
        setIsRegisterMode(false);
        setPassword("");
        setConfirmPassword("");
        setError("注册成功，请使用新账号登录");
      } else {
        const data = await login(username.trim(), password);
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("refresh_token", data.refresh_token);
        localStorage.setItem("username", data.user.username);
        localStorage.setItem("is_admin", String(data.user.is_admin));
        onSuccess(data.user.username);
      }
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "请求失败，请检查后端服务"
      );
    } finally {
      setSubmitting(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter") {
      submit();
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-decoration auth-decoration-one" />
      <div className="auth-decoration auth-decoration-two" />

      <div className="auth-card">
        <div className="auth-brand">
          <div className="brand-mark">N</div>
          <div>
            <div className="brand-name">Nova Agent</div>
            <div className="brand-caption">Enterprise AI Workspace</div>
          </div>
        </div>

        <div className="auth-heading">
          <h1>{isRegisterMode ? "创建账号" : "欢迎回来"}</h1>
          <p>
            {isRegisterMode
              ? "创建你的 AI Agent 工作空间"
              : "登录你的 AI Agent 工作空间"}
          </p>
        </div>

        <div className="auth-form">
          <label>用户名</label>
          <input
            type="text"
            placeholder="请输入用户名"
            value={username}
            onChange={(e) => {
              setUsername(e.target.value);
              setError("");
            }}
            onKeyDown={onKeyDown}
          />

          <label>密码</label>
          <input
            type="password"
            placeholder={isRegisterMode ? "至少 6 位密码" : "请输入密码"}
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setError("");
            }}
            onKeyDown={onKeyDown}
          />

          {isRegisterMode && (
            <>
              <label>确认密码</label>
              <input
                type="password"
                placeholder="再次输入密码"
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  setError("");
                }}
                onKeyDown={onKeyDown}
              />
            </>
          )}

          {error && <div className="auth-message">{error}</div>}

          <button
            className="auth-submit"
            onClick={submit}
            disabled={submitting}
          >
            {submitting
              ? "处理中..."
              : isRegisterMode
                ? "创建账号"
                : "登录"}
          </button>
        </div>

        <div className="auth-switch">
          {isRegisterMode ? "已经有账号？" : "还没有账号？"}
          <button
            type="button"
            onClick={() => {
              setIsRegisterMode(!isRegisterMode);
              setPassword("");
              setConfirmPassword("");
              setError("");
            }}
          >
            {isRegisterMode ? "返回登录" : "立即注册"}
          </button>
        </div>

        <div className="auth-footer">RAG · Tool Calling · AI Agent</div>
      </div>
    </div>
  );
}

// =========================
// 主应用
// =========================

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(
    Boolean(localStorage.getItem("token"))
  );
  const [username, setUsername] = useState(
    localStorage.getItem("username") || ""
  );
  const [isAdmin, setIsAdmin] = useState(
    localStorage.getItem("is_admin") === "true"
  );

  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<
    number | null
  >(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);

  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<
    number | null
  >(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [messageInput, setMessageInput] = useState("");
  const [streaming, setStreaming] = useState(false);

  const [kbModalOpen, setKbModalOpen] = useState(false);
  const [conversationModalOpen, setConversationModalOpen] = useState(false);
  const [kbName, setKbName] = useState("");
  const [kbDescription, setKbDescription] = useState("");
  const [conversationTitle, setConversationTitle] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<
    { kind: "kb" | "conversation" | "document"; id: number; name: string } | null
  >(null);
  const [toast, setToast] = useState<{
    message: string;
    kind: "success" | "error";
  } | null>(null);
  const [uploading, setUploading] = useState(false);

  // Coding Agent
  const [codingTask, setCodingTask] = useState("");
  const [codingLoading, setCodingLoading] = useState(false);
  const [codingSteps, setCodingSteps] = useState<CodingStep[]>([]);
  const [codingResult, setCodingResult] = useState("");
  const [codingDiffs, setCodingDiffs] = useState<
    { path: string; diff: string }[]
  >([]);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const pollingRef = useRef<number | null>(null);

  const showToast = useCallback(
    (message: string, kind: "success" | "error" = "error") => {
      setToast({ message, kind });
    },
    []
  );

  const handleAuthError = useCallback(() => {
    clearSession();
    setIsLoggedIn(false);
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 登录后：获取用户信息 + 知识库列表
  useEffect(() => {
    if (!isLoggedIn) {
      return;
    }
    (async () => {
      try {
        const me = await getMe();
        setUsername(me.username);
        setIsAdmin(me.is_admin);
        localStorage.setItem("is_admin", String(me.is_admin));

        const data = await getKnowledgeBases();
        setKnowledgeBases(data);
      } catch (error) {
        if (error instanceof AuthError) {
          handleAuthError();
        } else {
          showToast(
            error instanceof ApiError ? error.message : "加载数据失败"
          );
        }
      }
    })();
  }, [isLoggedIn, handleAuthError, showToast]);

  // 轮询索引状态
  const pollIndexStatus = useCallback(
    async (knowledgeBaseId: number) => {
      const poll = async () => {
        try {
          const status = await getIndexStatus(knowledgeBaseId);
          setDocuments(status.documents);
          if (status.ready) {
            if (pollingRef.current) {
              window.clearInterval(pollingRef.current);
              pollingRef.current = null;
            }
          }
        } catch {
          // 轮询失败不打断用户
        }
      };

      if (pollingRef.current) {
        window.clearInterval(pollingRef.current);
      }
      pollingRef.current = window.setInterval(poll, 2000);
      await poll();
    },
    []
  );

  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        window.clearInterval(pollingRef.current);
      }
    };
  }, []);

  const selectKnowledgeBase = async (knowledgeBaseId: number) => {
    setSelectedKnowledgeBaseId(knowledgeBaseId);
    setSelectedConversationId(null);
    setMessages([]);

    try {
      const [conversationData, documentData] = await Promise.all([
        getConversations(knowledgeBaseId),
        getDocuments(knowledgeBaseId),
      ]);
      setConversations(conversationData);
      setDocuments(documentData);
      await pollIndexStatus(knowledgeBaseId);
    } catch (error) {
      setConversations([]);
      setDocuments([]);
      showToast(error instanceof ApiError ? error.message : "加载知识库失败");
    }
  };

  const selectConversation = async (conversationId: number) => {
    setSelectedConversationId(conversationId);
    try {
      const data = await getMessages(conversationId);
      setMessages(data.messages);
    } catch (error) {
      setMessages([]);
      showToast(error instanceof ApiError ? error.message : "加载消息失败");
    }
  };

  const refreshKnowledgeBases = async () => {
    try {
      setKnowledgeBases(await getKnowledgeBases());
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "刷新知识库失败");
    }
  };

  const submitCreateKnowledgeBase = async () => {
    if (!kbName.trim()) {
      return;
    }
    try {
      const kb = await createKnowledgeBase(kbName.trim(), kbDescription.trim());
      setKbModalOpen(false);
      setKbName("");
      setKbDescription("");
      await refreshKnowledgeBases();
      setSelectedKnowledgeBaseId(kb.id);
      setConversations([]);
      setDocuments([]);
      setSelectedConversationId(null);
      setMessages([]);
      showToast("知识库创建成功", "success");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "创建知识库失败");
    }
  };

  const submitCreateConversation = async () => {
    if (!selectedKnowledgeBaseId || !conversationTitle.trim()) {
      return;
    }
    try {
      const conversation = await createConversation(
        conversationTitle.trim(),
        selectedKnowledgeBaseId
      );
      setConversationModalOpen(false);
      setConversationTitle("");
      setConversations(
        await getConversations(selectedKnowledgeBaseId)
      );
      setSelectedConversationId(conversation.id);
      setMessages([]);
      showToast("会话创建成功", "success");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "创建会话失败");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    try {
      if (deleteTarget.kind === "kb") {
        await deleteKnowledgeBase(deleteTarget.id);
        if (selectedKnowledgeBaseId === deleteTarget.id) {
          setSelectedKnowledgeBaseId(null);
          setConversations([]);
          setSelectedConversationId(null);
          setMessages([]);
          setDocuments([]);
        }
        await refreshKnowledgeBases();
      } else if (deleteTarget.kind === "conversation") {
        await deleteConversation(deleteTarget.id);
        if (selectedConversationId === deleteTarget.id) {
          setSelectedConversationId(null);
          setMessages([]);
        }
        if (selectedKnowledgeBaseId) {
          setConversations(await getConversations(selectedKnowledgeBaseId));
        }
      } else if (deleteTarget.kind === "document" && selectedKnowledgeBaseId) {
        await deleteDocument(selectedKnowledgeBaseId, deleteTarget.id);
        setDocuments(await getDocuments(selectedKnowledgeBaseId));
        await pollIndexStatus(selectedKnowledgeBaseId);
      }
      setDeleteTarget(null);
      showToast("删除成功", "success");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "删除失败");
    }
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selectedKnowledgeBaseId) {
      return;
    }

    setUploading(true);
    try {
      await uploadDocument(selectedKnowledgeBaseId, file);
      showToast("上传成功，正在后台建立索引", "success");
      setDocuments(await getDocuments(selectedKnowledgeBaseId));
      await pollIndexStatus(selectedKnowledgeBaseId);
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "上传文档失败");
    } finally {
      setUploading(false);
    }
  };

  const sendMessage = async () => {
    const content = messageInput.trim();
    if (!content || !selectedKnowledgeBaseId || !selectedConversationId) {
      return;
    }

    setMessageInput("");
    setStreaming(true);

    const clientId = `client-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const userMessage: ChatMessage = {
      clientId,
      role: "user",
      content,
    };
    const assistantMessage: ChatMessage = {
      clientId: `${clientId}-assistant`,
      role: "assistant",
      content: "",
      streaming: true,
      sources: [],
      tool_calls: [],
    };
    setMessages((prev) => [...prev, userMessage, assistantMessage]);

    const updateAssistant = (
      updater: (message: ChatMessage) => ChatMessage
    ) => {
      setMessages((prev) =>
        prev.map((item) =>
          item.clientId === assistantMessage.clientId ? updater(item) : item
        )
      );
    };

    try {
      await streamChat(
        content,
        selectedConversationId,
        selectedKnowledgeBaseId,
        (event: StreamEvent) => {
          if (event.type === "delta") {
            updateAssistant((item) => ({
              ...item,
              content: item.content + (event.content ?? ""),
            }));
          } else if (event.type === "tool_call") {
            updateAssistant((item) => ({
              ...item,
              tool_calls: [
                ...(item.tool_calls ?? []),
                {
                  tool: event.tool ?? "unknown",
                  arguments: event.arguments,
                },
              ],
            }));
          } else if (event.type === "done") {
            updateAssistant((item) => ({
              ...item,
              content: event.answer || item.content,
              sources: event.sources ?? [],
              streaming: false,
            }));
          } else if (event.type === "error") {
            updateAssistant((item) => ({
              ...item,
              content: event.message || "请求失败，请稍后重试",
              streaming: false,
            }));
          }
        }
      );
    } catch (error) {
      if (error instanceof AuthError) {
        handleAuthError();
      } else {
        updateAssistant((item) => ({
          ...item,
          content: error instanceof ApiError ? error.message : "请求失败，请检查后端服务",
          streaming: false,
        }));
      }
    } finally {
      setStreaming(false);
    }
  };

  const runCodingTask = async () => {
    if (!codingTask.trim()) {
      return;
    }
    setCodingLoading(true);
    setCodingSteps([]);
    setCodingResult("");
    setCodingDiffs([]);
    try {
      const data = await runCodingAgent(codingTask.trim());
      setCodingSteps(data.steps);
      setCodingResult(data.answer || "");
      setCodingDiffs(data.diffs || []);
    } catch (error) {
      setCodingResult(
        error instanceof ApiError
          ? error.message
          : "Coding Agent 执行失败，请检查后端服务。"
      );
    } finally {
      setCodingLoading(false);
    }
  };

  const logout = () => {
    clearSession();
    setIsLoggedIn(false);
    setKnowledgeBases([]);
    setSelectedKnowledgeBaseId(null);
    setConversations([]);
    setSelectedConversationId(null);
    setMessages([]);
    setDocuments([]);
  };

  if (!isLoggedIn) {
    return (
      <AuthPage
        onSuccess={(name) => {
          setUsername(name);
          setIsLoggedIn(true);
        }}
      />
    );
  }

  const docStatusLabel: Record<DocumentItem["status"], string> = {
    pending: "排队中",
    indexing: "索引中",
    ready: "就绪",
    failed: "失败",
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-mark">N</div>
          <div>
            <div className="logo-title">Nova Agent</div>
            <div className="logo-subtitle">AI Workspace</div>
          </div>
        </div>

        <div className="sidebar-section">
          <div className="section-title">知识库</div>
          <button className="new-button" onClick={() => setKbModalOpen(true)}>
            + 新建知识库
          </button>

          {knowledgeBases.map((kb) => (
            <div
              key={kb.id}
              className={
                selectedKnowledgeBaseId === kb.id
                  ? "knowledge-base-item active"
                  : "knowledge-base-item"
              }
              onClick={() => selectKnowledgeBase(kb.id)}
            >
              <span>{kb.name}</span>
              <button
                className="delete-button"
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteTarget({ kind: "kb", id: kb.id, name: kb.name });
                }}
              >
                删除
              </button>
            </div>
          ))}
        </div>

        <div className="sidebar-section">
          <div className="section-title">会话</div>
          <button
            className="new-button"
            onClick={() => setConversationModalOpen(true)}
          >
            + 新建会话
          </button>

          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={
                selectedConversationId === conversation.id
                  ? "conversation-item active"
                  : "conversation-item"
              }
              onClick={() => selectConversation(conversation.id)}
            >
              <span>{conversation.title}</span>
              <button
                className="delete-button"
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteTarget({
                    kind: "conversation",
                    id: conversation.id,
                    name: conversation.title,
                  });
                }}
              >
                删除
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className="chat-area">
        <header className="chat-header">
          <div className="document-panel">
            <div className="document-title">当前知识库文档</div>
            <div className="document-upload">
              <label className="upload-button">
                {uploading ? "上传中..." : "上传文档"}
                <input
                  type="file"
                  accept=".txt,.md,.csv"
                  disabled={!selectedKnowledgeBaseId || uploading}
                  onChange={handleUpload}
                  style={{ display: "none" }}
                />
              </label>
            </div>

            {documents.length === 0 ? (
              <div className="document-empty">
                当前知识库暂无文档（支持 TXT / MD / CSV）
              </div>
            ) : (
              <div className="document-list">
                {documents.map((document) => (
                  <div key={document.id} className="document-item">
                    <span className="document-name">📄 {document.filename}</span>
                    <span
                      className={`doc-status doc-status-${document.status}`}
                      title={document.error_message || ""}
                    >
                      {docStatusLabel[document.status]}
                    </span>
                    <button
                      className="delete-document-button"
                      onClick={() =>
                        setDeleteTarget({
                          kind: "document",
                          id: document.id,
                          name: document.filename,
                        })
                      }
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <h1>AI Agent</h1>
            <span className="header-context">
              <span className="status-dot" />
              {selectedKnowledgeBaseId ? "知识库已连接" : "请选择一个知识库"}
            </span>
          </div>

          <div className="header-right">
            <span className="username">
              {username}
              {isAdmin && <span className="admin-badge">管理员</span>}
            </span>
            <button className="logout-button" onClick={logout}>
              退出登录
            </button>
          </div>
        </header>

        {isAdmin && (
          <section className="coding-agent-panel">
            <div className="coding-agent-header">
              <h2>AI Coding Agent</h2>
              <span>自动分析 / 修改 / 测试 / 修复（仅管理员）</span>
            </div>

            <div className="coding-agent-input">
              <textarea
                placeholder="例如：检查 /chat 接口，如果有问题就修复并测试。"
                value={codingTask}
                onChange={(e) => setCodingTask(e.target.value)}
              />
              <button
                onClick={runCodingTask}
                disabled={codingLoading || !codingTask.trim()}
              >
                {codingLoading ? "执行中..." : "开始执行"}
              </button>
            </div>

            {codingSteps.length > 0 && (
              <div className="coding-steps">
                <div className="coding-steps-title">Agent 执行过程</div>
                {codingSteps.map((step, index) => (
                  <div key={index} className="coding-step">
                    <div className="coding-step-tool">✓ {step.tool}</div>
                    {step.arguments && (
                      <pre>{JSON.stringify(step.arguments, null, 2)}</pre>
                    )}
                    {step.result != null ? (
                      <div className="coding-step-result">
                        {String(step.result).slice(0, 600)}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}

            {codingDiffs.length > 0 && (
              <div className="coding-diffs">
                <div className="coding-steps-title">Diff</div>
                {codingDiffs.map((item, index) => (
                  <div key={index}>
                    <div className="coding-file">{item.path}</div>
                    <pre className="coding-diff">{item.diff}</pre>
                  </div>
                ))}
              </div>
            )}

            {codingResult && (
              <div className="coding-result">
                <div className="coding-steps-title">最终结果</div>
                <div>
                  <MarkdownLite text={codingResult} />
                </div>
              </div>
            )}
          </section>
        )}

        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome-message">
              <h2>你好，我是 Nova Agent</h2>
              <p>选择一个知识库和会话，开始基于知识库的智能问答。</p>
              <div className="welcome-hints">
                <span>⌘ RAG 检索</span>
                <span>⌘ Tool Calling</span>
                <span>⌘ 流式回答</span>
              </div>
            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={message.clientId ?? message.id ?? index}
              className={
                message.role === "user"
                  ? "message user-message"
                  : "message assistant-message"
              }
            >
              {message.tool_calls && message.tool_calls.length > 0 && (
                <div className="tool-trace">
                  {message.tool_calls.map((call, callIndex) => (
                    <span key={callIndex} className="tool-trace-chip">
                      🔧 {call.tool}
                    </span>
                  ))}
                </div>
              )}
              <MarkdownLite text={message.content} />
              {message.streaming && (
                <span className="typing-dots">
                  <span />
                  <span />
                  <span />
                </span>
              )}
              {message.sources && message.sources.length > 0 && (
                <div className="sources-row">
                  <span className="sources-label">来源：</span>
                  {message.sources.map((source, sourceIndex) => (
                    <span key={sourceIndex} className="source-chip">
                      📄 {source}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          <div className="input-box">
            <textarea
              placeholder="输入消息，Enter 发送，Shift+Enter 换行"
              value={messageInput}
              disabled={streaming}
              onChange={(e) => setMessageInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
            />
            <button
              className="send-button"
              onClick={sendMessage}
              disabled={streaming || !messageInput.trim()}
            >
              {streaming ? "回答中..." : "发送"}
            </button>
          </div>
        </div>
      </main>

      {kbModalOpen && (
        <Modal
          title="新建知识库"
          onClose={() => setKbModalOpen(false)}
        >
          <label className="modal-label">名称</label>
          <input
            className="modal-input"
            value={kbName}
            onChange={(e) => setKbName(e.target.value)}
            placeholder="例如：产品文档"
          />
          <label className="modal-label">描述（可选）</label>
          <input
            className="modal-input"
            value={kbDescription}
            onChange={(e) => setKbDescription(e.target.value)}
            placeholder="简要描述知识库用途"
          />
          <div className="modal-actions">
            <button
              className="button-secondary"
              onClick={() => setKbModalOpen(false)}
            >
              取消
            </button>
            <button
              className="button-primary"
              onClick={submitCreateKnowledgeBase}
              disabled={!kbName.trim()}
            >
              创建
            </button>
          </div>
        </Modal>
      )}

      {conversationModalOpen && (
        <Modal
          title="新建会话"
          onClose={() => setConversationModalOpen(false)}
        >
          <label className="modal-label">会话名称</label>
          <input
            className="modal-input"
            value={conversationTitle}
            onChange={(e) => setConversationTitle(e.target.value)}
            placeholder="例如：关于部署方案的问题"
          />
          <div className="modal-actions">
            <button
              className="button-secondary"
              onClick={() => setConversationModalOpen(false)}
            >
              取消
            </button>
            <button
              className="button-primary"
              onClick={submitCreateConversation}
              disabled={!conversationTitle.trim()}
            >
              创建
            </button>
          </div>
        </Modal>
      )}

      {deleteTarget && (
        <Modal
          title="确认删除"
          onClose={() => setDeleteTarget(null)}
        >
          <p className="modal-text">
            确定要删除「{deleteTarget.name}」吗？此操作不可恢复。
            {deleteTarget.kind === "kb" && (
              <> 知识库下的文档、会话和消息都会被删除。</>
            )}
          </p>
          <div className="modal-actions">
            <button
              className="button-secondary"
              onClick={() => setDeleteTarget(null)}
            >
              取消
            </button>
            <button className="button-danger" onClick={confirmDelete}>
              删除
            </button>
          </div>
        </Modal>
      )}

      {toast && (
        <Toast
          message={toast.message}
          kind={toast.kind}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}

export default App;
