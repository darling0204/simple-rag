"""Agent 可用的工具实现。

所有文件类工具都做严格的安全检查：
- 路径必须位于项目目录内（commonpath 校验，防止前缀绕过）；
- 禁止访问敏感文件（.env、数据库、密钥等）。
"""

import os
import subprocess
import sys

from safe_calc import CalculationError, safe_calculate


PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

SENSITIVE_PATH_PARTS = {
    ".env",
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
}

SENSITIVE_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}


def _resolve_in_project(path):
    """把用户传入的相对路径解析到项目内，越界返回 None。"""
    target_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
    try:
        if os.path.commonpath([PROJECT_ROOT, target_path]) != PROJECT_ROOT:
            return None
    except ValueError:
        return None
    return target_path


def _is_sensitive(target_path):
    relative = os.path.relpath(target_path, PROJECT_ROOT).lower()
    parts = set(relative.split(os.sep))
    if parts & SENSITIVE_PATH_PARTS:
        return True
    if any(relative.endswith(suffix) for suffix in SENSITIVE_SUFFIXES):
        return True
    if os.path.basename(target_path).lower().startswith(".env"):
        return True
    return False


def search_knowledge_structured(
    query, model, index, chunks, top_k=None, sources=None
):
    """执行检索，返回结构化结果列表（供 Agent 内部使用）。"""
    from rag import retrieve

    return retrieve(
        query,
        model,
        index,
        chunks,
        top_k,
        sources,
    )


def _format_retrieval_results(results):
    """把结构化检索结果格式化为给模型看的文本。"""
    if not results:
        return ["知识库为空或没有检索到相关内容。"]

    formatted = []
    for result in results:
        source = result.get("source") or "未知文档"
        formatted.append(
            f"[文档: {source}] (相关度距离 {result['distance']:.4f})\n"
            f"{result['chunk']}"
        )

    return formatted


def search_knowledge(query, model, index, chunks, top_k=None, sources=None):
    """搜索本地知识库，返回带来源标记的文本块列表。"""
    results = search_knowledge_structured(
        query, model, index, chunks, top_k, sources
    )
    return _format_retrieval_results(results)


def calculator(expression):
    """安全地计算数学表达式。"""
    try:
        return safe_calculate(expression)
    except CalculationError as exc:
        return f"计算失败：{exc}"


def read_file(path):
    """读取项目内的文件内容。"""
    try:
        target_path = _resolve_in_project(path)
        if target_path is None:
            return "读取失败：不允许访问项目目录之外的文件。"
        if _is_sensitive(target_path):
            return "读取失败：该文件属于敏感文件，不允许读取。"
        if not os.path.isfile(target_path):
            return f"读取失败：文件不存在：{path}"

        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        if len(content) > 20000:
            content = content[:20000] + "\n...(内容过长，已截断)"
        return content

    except UnicodeDecodeError:
        return f"读取失败：{path} 不是文本文件。"
    except Exception as exc:
        return f"读取文件失败：{exc}"


def search_code(keyword):
    """在项目代码文件中搜索关键词。"""
    if not keyword or len(keyword) > 200:
        return "搜索失败：关键词为空或过长。"

    allowed_extensions = {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".md",
    }

    results = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [
            d
            for d in dirs
            if d
            not in {
                ".git", ".venv", "node_modules", "__pycache__", "dist",
                "indexes", "uploads", "logs",
            }
        ]

        for filename in files:
            _, ext = os.path.splitext(filename)
            if ext not in allowed_extensions:
                continue

            file_path = os.path.join(root, filename)
            if _is_sensitive(file_path):
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line_number, line in enumerate(f, start=1):
                        if keyword.lower() in line.lower():
                            relative_path = os.path.relpath(
                                file_path, PROJECT_ROOT
                            )
                            results.append(
                                f"{relative_path}:{line_number}: {line.strip()}"
                            )
                        if len(results) >= 50:
                            break
            except Exception:
                continue

            if len(results) >= 50:
                break

    if not results:
        return f"没有找到关键词：{keyword}"

    return "\n".join(results)


def write_file(path, content):
    """创建或覆盖项目内的文件。"""
    try:
        target_path = _resolve_in_project(path)
        if target_path is None:
            return "修改失败：不允许访问项目目录之外的文件。"
        if _is_sensitive(target_path):
            return "修改失败：不允许修改敏感文件。"

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"文件修改成功：{path}"

    except Exception as exc:
        return f"修改文件失败：{exc}"


def edit_file(path, old_text, new_text):
    """局部替换项目内文件的内容。"""
    try:
        target_path = _resolve_in_project(path)
        if target_path is None:
            return "修改失败：不允许访问项目目录之外的文件。"
        if _is_sensitive(target_path):
            return "修改失败：不允许修改敏感文件。"
        if not os.path.isfile(target_path):
            return f"修改失败：文件不存在：{path}"

        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        if old_text not in content:
            return "修改失败：没有找到需要替换的原代码。"

        count = content.count(old_text)
        if count > 1:
            return (
                f"修改失败：原代码出现了 {count} 次，"
                "无法确定应该修改哪一处。"
            )

        new_content = content.replace(old_text, new_text, 1)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"文件修改成功：{path}"

    except Exception as exc:
        return f"修改文件失败：{exc}"


def run_test(test_file="agent_test.py", timeout=30):
    """运行项目内的 Python 测试文件。"""
    target_path = _resolve_in_project(test_file)
    if target_path is None:
        return "测试失败：不允许访问项目目录之外的文件。"
    if not os.path.isfile(target_path):
        return f"测试失败：文件不存在：{test_file}"
    if not test_file.lower().endswith(".py"):
        return "测试失败：只能运行 Python 测试文件。"

    try:
        result = subprocess.run(
            [sys.executable, target_path],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = (result.stdout + "\n" + result.stderr).strip()
        return f"退出码：{result.returncode}\n{output}"

    except subprocess.TimeoutExpired:
        return f"测试失败：执行超过 {timeout} 秒，已终止。"
    except Exception as exc:
        return f"测试失败：{exc}"
