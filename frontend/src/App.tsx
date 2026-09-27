
import { useEffect, useState } from "react";
import "./App.css";
import {
  login,
  register,
  getKnowledgeBases,
  getConversations,
  getMessages,
  getDocuments,
  deleteDocument,
  createConversation,
  createKnowledgeBase,
  sendMessage,
  uploadDocument,
  deleteKnowledgeBase,
} from "./api";

function App() {
  // =========================
  // 登录状态
  // =========================

  const [isLoggedIn, setIsLoggedIn] = useState(
    Boolean(localStorage.getItem("token"))
  );

  const [username, setUsername] = useState(
  localStorage.getItem("username") || ""
);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [isSubmittingAuth, setIsSubmittingAuth] = useState(false);

  // =========================
  // 知识库
  // =========================

  const [knowledgeBases, setKnowledgeBases] = useState<any[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] =
    useState<number | null>(null);
  const [documents, setDocuments] = useState<any[]>([]);
  // =========================
  // 会话
  // =========================

  const [conversations, setConversations] = useState<any[]>([]);
  const [selectedConversationId, setSelectedConversationId] =
    useState<number | null>(null);

  // =========================
  // 聊天消息
  // =========================

  const [messages, setMessages] = useState<any[]>([]);
  const [messageInput, setMessageInput] = useState("");

  // =========================
  // 登录
  // =========================

  const handleLogin = async () => {
    try {
      setLoginError("");

      const data = await login(username, password);

      localStorage.setItem("token", data.access_token);
      localStorage.setItem(
        "refresh_token",
        data.refresh_token
      );
      localStorage.setItem("username", username);
      setIsLoggedIn(true);
    } catch (error) {
      console.error(error);

      setLoginError("用户名或密码错误");
    }
  };

  // =========================
  // 注册
  // =========================

  const handleRegister = async () => {
    const trimmedUsername = username.trim();

    if (!trimmedUsername || !password) {
      setLoginError("请输入用户名和密码");
      return;
    }

    if (trimmedUsername.length < 3) {
      setLoginError("用户名至少需要 3 个字符");
      return;
    }

    if (password.length < 6) {
      setLoginError("密码至少需要 6 个字符");
      return;
    }

    if (password !== confirmPassword) {
      setLoginError("两次输入的密码不一致");
      return;
    }

    try {
      setLoginError("");
      setIsSubmittingAuth(true);

      await register(trimmedUsername, password);

      setIsRegisterMode(false);
      setConfirmPassword("");
      setPassword("");
      setLoginError("注册成功，请使用新账号登录");
    } catch (error) {
      console.error("注册失败：", error);
      setLoginError(
        error instanceof Error ? error.message : "注册失败，请检查后端服务"
      );
    } finally {
      setIsSubmittingAuth(false);
    }
  };

  // =========================
  // 登录后加载知识库
  // =========================

  useEffect(() => {
    if (!isLoggedIn) {
      return;
    }

    getKnowledgeBases()
  .then((data) => {
    console.log("知识库数据：", data);
    setKnowledgeBases(data);
  })
  .catch((error) => {
    console.error("获取知识库失败：", error);
  });
  }, [isLoggedIn]);

  // =========================
  // 点击知识库
  // =========================

  const handleSelectKnowledgeBase = async (
  knowledgeBaseId: number
) => {

  console.log("点击了知识库，ID =", knowledgeBaseId);

  setSelectedKnowledgeBaseId(knowledgeBaseId);

  setSelectedConversationId(null);
  setMessages([]);

  try {
    const data = await getConversations(knowledgeBaseId);

    console.log("获取到的会话：", data);

    setConversations(data);
  } catch (error) {
    console.error("获取会话失败：", error);

    setConversations([]);
  } 

   try {
    const documentData = await getDocuments(
      knowledgeBaseId
    );

    console.log(
      "获取到的文档：",
      documentData
    );

    setDocuments(documentData);
  } catch (error) {
    console.error(
      "获取文档失败：",
      error
    );

    setDocuments([]);
  }
};

// =========================
  // 删除知识库
  // =========================
const handleDeleteKnowledgeBase = async (
  knowledgeBaseId: number
) => {
  const knowledgeBase = knowledgeBases.find(
    (kb) => kb.id === knowledgeBaseId
  );

  if (!knowledgeBase) {
    return;
  }

  const confirmed = window.confirm(
    `确定要删除知识库「${knowledgeBase.name}」吗？`
  );

  if (!confirmed) {
    return;
  }

  try {
    await deleteKnowledgeBase(knowledgeBaseId);

    console.log(
      "删除知识库成功：",
      knowledgeBaseId
    );

    const data = await getKnowledgeBases();

    setKnowledgeBases(data);

    if (
      selectedKnowledgeBaseId === knowledgeBaseId
    ) {
      setSelectedKnowledgeBaseId(null);
      setConversations([]);
      setSelectedConversationId(null);
      setMessages([]);
    }

  } catch (error) {
    console.error(
      "删除知识库失败：",
      error
    );

    alert("删除知识库失败，请检查后端服务");
  }
};
// =========================
  // 增加上传函数
  // =========================
const handleUploadDocument = async (
  event: React.ChangeEvent<HTMLInputElement>
) => {
  const file = event.target.files?.[0];

  if (!file) {
    return;
  }

  if (selectedKnowledgeBaseId === null) {
    alert("请先选择一个知识库");
    return;
  }

  try {
    await uploadDocument(
      selectedKnowledgeBaseId,
      file
    );

    alert("文档上传成功");

    const data = await getDocuments(
      selectedKnowledgeBaseId
    );

    setDocuments(data);
  } catch (error) {
    console.error(
      "上传文档失败：",
      error
    );

    alert("文档上传失败");
  }

  event.target.value = "";
};
// =========================
  // 文档删除
  // =========================
const handleDeleteDocument = async (
  documentId: number
) => {
  if (selectedKnowledgeBaseId === null) {
    return;
  }

  const confirmed = window.confirm(
    "确定要删除这个文档吗？"
  );

  if (!confirmed) {
    return;
  }

  try {
    await deleteDocument(
      selectedKnowledgeBaseId,
      documentId
    );

    alert("文档删除成功");

    const data = await getDocuments(
      selectedKnowledgeBaseId
    );

    setDocuments(data);
  } catch (error) {
    console.error(
      "删除文档失败：",
      error
    );

    alert("文档删除失败");
  }
};

 // =========================
  // 创建会话
  // =========================
const handleCreateConversation = async () => {
  if (!selectedKnowledgeBaseId) {
    alert("请先选择知识库");
    return;
  }

  const title = window.prompt("请输入会话名称");

  if (!title || !title.trim()) {
    return;
  }

  try {
    const conversation = await createConversation(
      title.trim(),
      selectedKnowledgeBaseId
    );

    console.log("创建会话成功：", conversation);

    // 重新获取当前知识库的会话
    const data = await getConversations(
      selectedKnowledgeBaseId
    );

    setConversations(data);

    // 自动进入刚刚创建的会话
    setSelectedConversationId(conversation.id);
    setMessages([]);
  } catch (error) {
    console.error("创建会话失败：", error);
    alert("创建会话失败，请检查后端服务");
  }
};

const handleCreateKnowledgeBase = async () => {
  const name = window.prompt("请输入知识库名称");

  if (!name || !name.trim()) {
    return;
  }

  const description = window.prompt("请输入知识库描述") || "";

  try {
    const knowledgeBase = await createKnowledgeBase(
      name.trim(),
      description.trim()
    );

    console.log(
      "创建知识库成功：",
      knowledgeBase
    );



    // 重新获取知识库列表
    const data = await getKnowledgeBases();

    setKnowledgeBases(data);

    // 自动选中新创建的知识库
    setSelectedKnowledgeBaseId(
      knowledgeBase.id
    );

    // 清空当前会话
    setConversations([]);
    setSelectedConversationId(null);
    setMessages([]);

  } catch (error) {
    console.error(
      "创建知识库失败：",
      error
    );

    alert("创建知识库失败，请检查后端服务");
  }
};


  // =========================
  // 点击会话
  // =========================

  const handleSelectConversation = async (
  conversationId: number
) => {
  console.log("点击了会话，ID =", conversationId);

  setSelectedConversationId(conversationId);
  setMessages([]);

  try {
    const data = await getMessages(conversationId);

    console.log("获取到的历史消息：", data);

    setMessages(data);
  } catch (error) {
    console.error("获取历史消息失败：", error);

    setMessages([]);
  }
};

const handleLogout = () => {
  // 清除登录凭证
  localStorage.removeItem("token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("username");

  // 修改登录状态
  setIsLoggedIn(false);

  // 清空当前页面的数据
  setKnowledgeBases([]);
  setSelectedKnowledgeBaseId(null);

  setConversations([]);
  setSelectedConversationId(null);

  setMessages([]);

  // 清空登录表单
  setUsername("");
  setPassword("");
  setConfirmPassword("");
  setLoginError("");
  setIsRegisterMode(false);
};

  // =========================
  // 发送消息
  // =========================

  const handleSendMessage = async () => {
    if (!messageInput.trim()) {
      return;
    }

    if (!selectedKnowledgeBaseId) {
      alert("请先选择知识库");
      return;
    }

    if (!selectedConversationId) {
      alert("请先选择会话");
      return;
    }

    const userMessage = messageInput;

    // 清空输入框
    setMessageInput("");

    // 立即显示用户消息
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: userMessage,
      },
    ]);

    try {
      const data = await sendMessage(
        userMessage,
        selectedConversationId,
        selectedKnowledgeBaseId
      );

      // 显示 Agent 回复
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
        },
      ]);
    } catch (error) {
      console.error("聊天请求失败：", error);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "请求失败，请检查后端服务。",
        },
      ]);
    }
  };

  // =========================
  // 未登录页面
  // =========================

  if (!isLoggedIn) {
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
                setLoginError("");
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isRegisterMode) {
                  handleLogin();
                }
              }}
            />

            <label>密码</label>
            <input
              type="password"
              placeholder={isRegisterMode ? "至少 6 位密码" : "请输入密码"}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setLoginError("");
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isRegisterMode) {
                  handleLogin();
                }
              }}
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
                    setLoginError("");
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      handleRegister();
                    }
                  }}
                />
              </>
            )}

            {loginError && (
              <div className="auth-message">
                {loginError}
              </div>
            )}

            <button
              className="auth-submit"
              onClick={isRegisterMode ? handleRegister : handleLogin}
              disabled={isSubmittingAuth}
            >
              {isSubmittingAuth
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
                setLoginError("");
              }}
            >
              {isRegisterMode ? "返回登录" : "立即注册"}
            </button>
          </div>

          <div className="auth-footer">
            RAG · Tool Calling · AI Agent
          </div>
        </div>
      </div>
    );
  }

  // =========================
  // 登录后的主页面
  // =========================

  return (
    <div className="app">

      {/* =========================
          左侧边栏
          ========================= */}

      <aside className="sidebar">

        <div className="logo">
          <div className="logo-mark">N</div>
          <div>
            <div className="logo-title">Nova Agent</div>
            <div className="logo-subtitle">AI Workspace</div>
          </div>
        </div>

        {/* 知识库区域 */}

        <div className="sidebar-section">

          <div className="section-title">
            知识库
          </div>

          <button
  className="new-button"
  onClick={handleCreateKnowledgeBase}
>
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
      onClick={() =>
        handleSelectKnowledgeBase(kb.id)
      }
    >
      <span>
        {kb.name}
      </span>

      <button
        className="delete-button"
        onClick={(e) => {
          e.stopPropagation();
          handleDeleteKnowledgeBase(
            kb.id
          );
        }}
    >
      删除
    </button>
  </div>
))}

        </div>

        {/* 会话区域 */}

        <div className="sidebar-section">

  <div className="section-title">
    会话
  </div>

  <button
    className="new-button"
    onClick={handleCreateConversation}
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
              onClick={() =>
                handleSelectConversation(
                  conversation.id
                )
              }
            >
              {conversation.title}
            </div>
          ))}

        </div>

      </aside>

      {/* =========================
          右侧聊天区域
          ========================= */}

      <main className="chat-area">

        {/* 顶部 */}

        <header className="chat-header">
<div className="document-panel">

  <div className="document-title">
    当前知识库文档
  </div>
  <div className="document-upload">

  <label className="upload-button">
    上传 TXT 文档

    <input
      type="file"
      accept=".txt"
      onChange={handleUploadDocument}
      style={{ display: "none" }}
    />
  </label>

</div>

  {documents.length === 0 ? (
    <div className="document-empty">
      当前知识库暂无文档
    </div>
  ) : (
    <div className="document-list">

     {documents.map((document) => (
  <div
    key={document.id}
    className="document-item"
  >
    <span>
      📄 {document.filename}
    </span>

    <button
      className="delete-document-button"
      onClick={() =>
        handleDeleteDocument(document.id)
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
      {selectedKnowledgeBaseId
        ? "知识库已连接"
        : "请选择一个知识库"} 
    </span>

  </div>

  <div className="header-right">

    <span className="username">
      {username || "用户"}
    </span>

    <button
      className="logout-button"
      onClick={handleLogout}
    >
      退出登录
    </button>

  </div>

</header>

        {/* 消息区域 */}

        <div className="messages">

          {messages.length === 0 && (
            <div className="welcome-message">

              <h2>
                你好，我是 Nova Agent
              </h2>

              <p>
                选择一个知识库并开始对话。
                Agent 会根据知识库内容进行检索和回答。
              </p>

              <div className="welcome-hints">
                <span>⌘ RAG 检索</span>
                <span>⌘ Tool Calling</span>
                <span>⌘ 多轮对话</span>
              </div>

            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              className={
                message.role === "user"
                  ? "message user-message"
                  : "message assistant-message"
              }
            >
              {message.content}
            </div>
          ))}

        </div>

        {/* 输入区域 */}

        <div className="input-area">

          <div className="input-box">

            <textarea
              placeholder="输入消息..."
              value={messageInput}
              onChange={(e) =>
                setMessageInput(e.target.value)
              }
            />

            <button
              className="send-button"
              onClick={handleSendMessage}
              disabled={!messageInput.trim()}
            >
              发送
            </button>

          </div>

        </div>

      </main>

    </div>
  );
}

export default App;
