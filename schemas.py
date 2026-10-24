"""API 请求/响应模型，统一参数校验规则。"""

from pydantic import BaseModel, Field, field_validator

from config import settings


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def username_allowed(cls, value: str) -> str:
        value = value.strip()
        if not all(ch.isalnum() or ch in "_-" for ch in value):
            raise ValueError("用户名只能包含字母、数字、下划线和连字符")
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("知识库名称不能为空")
        return value


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    knowledge_base_id: int = Field(gt=0)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("会话名称不能为空")
        return value


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=settings.MAX_MESSAGE_LENGTH)
    conversation_id: int = Field(gt=0)
    knowledge_base_id: int = Field(gt=0)


class CodingAgentRequest(BaseModel):
    task: str = Field(min_length=1, max_length=settings.MAX_MESSAGE_LENGTH)
