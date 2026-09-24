# Simple RAG Agent

> 基于 FastAPI + React + FAISS + DeepSeek 实现的轻量级 RAG Agent 智能问答系统

## 项目简介

Simple RAG 是一个前后端分离的 AI Agent 应用项目，主要用于实践 **RAG（检索增强生成）、Agent、Tool Calling、多轮对话以及 JWT 用户认证**等 AI 应用开发技术。

项目实现了从**用户登录 → 知识库管理 → 文档上传 → 文本切分 → Embedding → FAISS 向量检索 → Agent 工具调用 → LLM 生成回答**的完整流程。

前端使用 React + TypeScript，后端使用 FastAPI，通过 HTTP API 完成前后端通信。

### 项目核心流程

```text
用户登录
   ↓
JWT 身份认证
   ↓
创建 / 选择知识库
   ↓
上传知识文档
   ↓
文本切分
   ↓
Embedding 向量化
   ↓
FAISS 建立索引
   ↓
用户提问
   ↓
Agent 判断问题类型
   ├── 知识库问题 → search_knowledge
   ├── 计算问题   → calculator
   └── 普通问题   → LLM
   ↓
工具结果 / 检索结果
   ↓
DeepSeek
   ↓
生成最终回答
```

---

## 核心功能

### 1. RAG 知识库问答

实现完整的文档检索增强生成流程：

```text
文档
 ↓
文本切分
 ↓
Sentence Embedding
 ↓
FAISS 向量索引
 ↓
相似度检索
 ↓
Top-K 相关文本
 ↓
LLM 生成回答
```

针对知识库问题，Agent 会优先调用 `search_knowledge` 获取相关内容，并根据检索结果生成回答。

当知识库中没有足够的信息时，系统会明确提示：

```text
知识库中没有相关信息
```

避免直接使用模型自身知识回答知识库相关问题。

---

### 2. Agent + Tool Calling

项目不是简单地将所有问题直接发送给大语言模型，而是增加了 Agent 决策层。

目前实现的工具：

| 工具                 | 功能      |
| ------------------ | ------- |
| `search_knowledge` | 检索指定知识库 |
| `calculator`       | 执行数学计算  |

Agent 会根据用户问题选择是否调用工具，并支持连续进行多轮工具调用。

例如：

```text
用户问题
   ↓
Agent 分析
   ↓
判断是否需要工具
   ↓
调用 Tool
   ↓
获取 Tool 返回结果
   ↓
继续分析
   ↓
生成最终回答
```

同时记录工具调用过程，方便开发阶段进行调试和问题定位。

---

### 3. 多轮对话与会话记忆

系统使用数据库保存用户、会话以及消息数据。

核心关系：

```text
User
 │
 ├── KnowledgeBase
 │       └── Document
 │
 └── Conversation
         └── Message
```

用户可以创建多个会话，Agent 可以读取历史消息，并将对话上下文用于后续回答。

---

### 4. JWT 用户认证

后端使用 JWT 实现用户身份认证。

主要包括：

* 用户登录
* Access Token
* Refresh Token
* Token 有效期管理
* API 身份验证
* 用户资源隔离

通过认证机制保证不同用户只能访问自己的知识库及相关数据。

---

### 5. 知识库与文档管理

支持用户管理自己的知识库和文档。

目前实现：

* 创建知识库
* 查询知识库
* 删除知识库
* 上传 TXT 文档
* 查询文档
* 删除文档

