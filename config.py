"""RAG 参数配置。"""

# 文本切分参数
CHUNK_SIZE = 200
CHUNK_OVERLAP = 40

# 检索参数
TOP_K = 2

# Embedding 模型
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# DeepSeek
LLM_MODEL = "deepseek-v4-flash"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
