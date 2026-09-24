
const API_BASE_URL = "http://127.0.0.1:8000";

// =========================
// 登录
// =========================

export async function login(
  username: string,
  password: string
) {
  const response = await fetch(
    `${API_BASE_URL}/login`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        username,
        password,
      }),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    console.log("登录失败：", errorText);
    throw new Error("登录失败");
  }

  return response.json();
}


// =========================
// 刷新 Access Token
// =========================

export async function refreshAccessToken() {
  const refreshToken = localStorage.getItem(
    "refresh_token"
  );

  if (!refreshToken) {
    throw new Error("没有 Refresh Token");
  }

  const response = await fetch(
    `${API_BASE_URL}/refresh`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        refresh_token: refreshToken,
      }),
    }
  );

  if (!response.ok) {
    throw new Error("Refresh Token 已失效");
  }

  const data = await response.json();

  // 保存新的 Access Token
  localStorage.setItem(
    "token",
    data.access_token
  );

  return data.access_token;
}


// =========================
// 自动处理身份认证
// =========================

async function requestWithAuth(
  url: string,
  options: RequestInit = {}
) {
  let token = localStorage.getItem("token");

  // 第一次请求
  let response = await fetch(
    url,
    {
      ...options,
      headers: {
        ...options.headers,
        Authorization: `Bearer ${token}`,
      },
    }
  );

  // Access Token 过期
  if (response.status === 401) {
    try {
      console.log("Access Token 已失效，尝试刷新...");

      // 使用 Refresh Token 获取新的 Access Token
      token = await refreshAccessToken();

      console.log("Access Token 刷新成功");

      // 使用新的 Access Token 重新请求
      response = await fetch(
        url,
        {
          ...options,
          headers: {
            ...options.headers,
            Authorization: `Bearer ${token}`,
          },
        }
      );
    } catch (error) {
      console.error("Token 刷新失败：", error);

      // Refresh Token 也失效
      localStorage.removeItem("token");
      localStorage.removeItem("refresh_token");

      throw error;
    }
  }

  return response;
}


// =========================
// 获取知识库
// =========================

export async function getKnowledgeBases() {

  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases`,
    {
      method: "GET",
    }
  );

  if (!response.ok) {
    throw new Error("获取知识库失败");
  }

  return response.json();
}


// =========================
// 获取会话
// =========================

export async function getConversations(
  knowledgeBaseId: number
) {

  const response = await requestWithAuth(
    `${API_BASE_URL}/conversations?knowledge_base_id=${knowledgeBaseId}`,
    {
      method: "GET",
    }
  );

  if (!response.ok) {
    throw new Error("获取会话失败");
  }

  return response.json();
}


// =========================
// 发送消息
// =========================

export async function sendMessage(
  message: string,
  conversationId: number,
  knowledgeBaseId: number
) {

  const response = await requestWithAuth(
    `${API_BASE_URL}/chat`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        knowledge_base_id: knowledgeBaseId,
      }),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();

    console.log(
      "聊天请求失败：",
      errorText
    );

    throw new Error("聊天请求失败");
  }

  return response.json();
}


// =========================
// 获取历史消息
// =========================

export async function getMessages(
  conversationId: number
) {

  const response = await requestWithAuth(
    `${API_BASE_URL}/conversations/${conversationId}/messages`,
    {
      method: "GET",
    }
  );

  if (!response.ok) {
    const errorText = await response.text();

    console.log(
      "获取历史消息失败：",
      errorText
    );

    throw new Error("获取历史消息失败");
  }

  return response.json();
}


// =========================
// 创建会话
// =========================

export async function createConversation(
  title: string,
  knowledgeBaseId: number
) {

  const response = await requestWithAuth(
    `${API_BASE_URL}/conversations`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title,
        knowledge_base_id: knowledgeBaseId,
      }),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();

    console.log(
      "创建会话失败：",
      errorText
    );

    throw new Error("创建会话失败");
  }

  return response.json();
}

// =========================
// 创建知识库
// =========================
export async function createKnowledgeBase(
  name: string,
  description: string
) {
  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name,
        description,
      }),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();

    console.log(
      "创建知识库失败：",
      errorText
    );

    throw new Error("创建知识库失败");
  }

  return response.json();
}

// =========================
// 删除知识库
// =========================
export async function deleteKnowledgeBase(
  knowledgeBaseId: number
) {
  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}`,
    {
      method: "DELETE",
    }
  );

  if (!response.ok) {
    const errorText = await response.text();

    console.log(
      "删除知识库失败：",
      errorText
    );

    throw new Error("删除知识库失败");
  }

  return response.json();
}
// =========================
// 获取知识库文档
// =========================

export async function getDocuments(
  knowledgeBaseId: number
) {
  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents`,
    {
      method: "GET",
    }
  );

  if (!response.ok) {
    const errorText = await response.text();

    console.log(
      "获取文档失败：",
      errorText
    );

    throw new Error("获取文档失败");
  }

  return response.json();
}

// =========================
// 上传知识库文档
// =========================

export async function uploadDocument(
  knowledgeBaseId: number,
  file: File
) {
  const formData = new FormData();

  formData.append("file", file);

  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents`,
    {
      method: "POST",
      body: formData,
    }
  );

  if (!response.ok) {
    const errorText = await response.text();

    console.log(
      "上传文档失败：",
      errorText
    );

    throw new Error("上传文档失败");
  }

  return response.json();
}

// =========================
// 删除知识库文档
// =========================

export async function deleteDocument(
  knowledgeBaseId: number,
  documentId: number
) {
  const response = await requestWithAuth(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`,
    {
      method: "DELETE",
    }
  );

  if (!response.ok) {
    const errorText = await response.text();

    console.log(
      "删除文档失败：",
      errorText
    );

    throw new Error("删除文档失败");
  }

  return response.json();
}

