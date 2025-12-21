import asyncio
import os
from datetime import datetime
from typing import List, Dict, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    openpyxl = None

try:
    import json
    from pathlib import Path
except ImportError:
    json = None
    Path = None

def get_weather(city:str) ->str:
    """get the weather for a city"""
    return f"{city}.今天是晴天，温度为25度."

def get_zhipu_search_mcp_tools():
    client = MultiServerMCPClient(
        {
            "search": {
                "transport": "sse",  # HTTP-based remote server
                # Ensure you start your weather server on port 8000
                "url": "https://open.bigmodel.cn/api/mcp/web_search/sse?Authorization=dfccd65ce1c9466690f465304cb6ae09.KzH9GpjmAVgN4Jhr",
            }
        }
    )
    tools = asyncio.run(client.get_tools())
    return tools
def get_tavily_search_mcp_tools():
    client = MultiServerMCPClient(
        {
            "search": {
                "transport": "streamable_http",  # HTTP-based remote server
                # Ensure you start your weather server on port 8000
                "url": "https://mcp.tavily.com/mcp/?tavilyApiKey=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",
            }
        }
    )
    tools = asyncio.run(client.get_tools())
    return tools
def get_chrome_mcp_tools():
    client = MultiServerMCPClient(
        {
            "chrome_mcp": {
                "transport": "streamable_http",  # HTTP-based remote server
                # Ensure you start your weather server on port 8000
                "url": "http://127.0.0.1:12306/mcp",
            }
        }
    )
    tools = asyncio.run(client.get_tools())
    return tools
def get_mcp_server_chart_tools():
    client = MultiServerMCPClient(
        {
            "mcp_chart_server": {
                "command":"cmd",
                "args": ["/c", "npx", "-y", "@antv/mcp-server-chart"],
                "transport": "stdio",  # HTTP-based remote server
            }
        }
    )
    tools = asyncio.run(client.get_tools())
    return tools
# tools = get_zhipu_search_mcp_tools()
# print(tools)
# os.environ["TAVILY_API_KEY"] = "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"
# from langchain_tavily import TavilySearch
# toolSearch = TavilySearch(max_results=2)


def save_test_cases_to_excel(
    test_cases: List[Dict],
    file_path: str = "test_cases.xlsx",
    sheet_name: str = "测试用例"
) -> str:
    """
    将测试用例保存到 Excel 文件中

    Args:
        test_cases: 测试用例列表，每个测试用例是一个字典
                   示例: [
                       {
                           "case_id": "TC001",
                           "title": "登录功能测试",
                           "precondition": "用户未登录",
                           "steps": "1. 打开登录页\n2. 输入用户名密码\n3. 点击登录",
                           "expected": "登录成功",
                           "priority": "高",
                           "status": "通过"
                       }
                   ]
        file_path: Excel 文件保存路径，默认为 "test_cases.xlsx"
        sheet_name: 工作表名称，默认为 "测试用例"

    Returns:
        str: 保存结果信息
    """
    # 检查是否安装了 openpyxl 库
    if openpyxl is None:
        return "错误: 未安装 openpyxl 库，请运行: pip install openpyxl"

    # 检查测试用例列表是否为空
    if not test_cases:
        return "错误: 测试用例列表为空"

    try:
        # 创建新的工作簿
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = sheet_name

        # 定义表头（根据测试用例字典的键自动生成）
        headers = list(test_cases[0].keys())

        # 设置表头样式
        header_font = Font(bold=True, color="FFFFFF", size=12)
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # 写入表头
        for col_idx, header in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = border

        # 写入测试用例数据
        for row_idx, test_case in enumerate(test_cases, start=2):
            for col_idx, header in enumerate(headers, start=1):
                # 获取对应字段的值
                value = test_case.get(header, "")
                cell = sheet.cell(row=row_idx, column=col_idx, value=value)

                # 设置单元格样式
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = border

                # 根据状态设置不同颜色（如果有 status 字段）
                if header.lower() in ["status", "状态"]:
                    if value in ["通过", "Pass", "PASS"]:
                        cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                    elif value in ["失败", "Fail", "FAIL"]:
                        cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                    elif value in ["阻塞", "Blocked", "BLOCKED"]:
                        cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")

        # 自动调整列宽
        for col_idx, header in enumerate(headers, start=1):
            # 计算该列的最大内容长度
            max_length = len(str(header))
            for row_idx in range(2, len(test_cases) + 2):
                cell_value = str(sheet.cell(row=row_idx, column=col_idx).value)
                # 考虑换行符，取最长的一行
                max_line_length = max(len(line) for line in cell_value.split('\n')) if cell_value else 0
                max_length = max(max_length, max_line_length)

            # 设置列宽（限制最大宽度为50）
            adjusted_width = min(max_length + 2, 50)
            sheet.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = adjusted_width

        # 冻结首行（表头）
        sheet.freeze_panes = "A2"

        # 保存文件
        workbook.save(file_path)

        # 返回成功信息
        return f"成功: 已将 {len(test_cases)} 条测试用例保存到 {os.path.abspath(file_path)}"

    except Exception as e:
        return f"错误: 保存失败 - {str(e)}"


def save_and_generate_report(
    test_cases: List[Dict],
    chart_html: str = "",
    file_path: str = "test_report.html",
    report_title: str = "UI自动化测试报告"
) -> str:
    """
    生成包含图表的HTML测试报告并保存到指定路径

    Args:
        test_cases: 测试用例列表
        chart_html: 图表的HTML代码（从mcp-server-chart生成）
        file_path: 报告保存路径
        report_title: 报告标题

    Returns:
        str: 保存结果信息
    """
    if not test_cases:
        return "错误: 测试用例列表为空"

    try:
        # 统计数据
        total = len(test_cases)
        passed = sum(1 for tc in test_cases if tc.get("状态") in ["通过", "Pass", "PASS"] or tc.get("status") in ["通过", "Pass", "PASS"])
        failed = sum(1 for tc in test_cases if tc.get("状态") in ["失败", "Fail", "FAIL"] or tc.get("status") in ["失败", "Fail", "FAIL"])
        blocked = sum(1 for tc in test_cases if tc.get("状态") in ["阻塞", "Blocked", "BLOCKED"] or tc.get("status") in ["阻塞", "Blocked", "BLOCKED"])
        pass_rate = (passed / total * 100) if total > 0 else 0

        # 生成测试用例表格HTML
        table_rows = ""
        for tc in test_cases:
            status = tc.get("状态") or tc.get("status", "")
            status_class = "pass" if status in ["通过", "Pass", "PASS"] else "fail" if status in ["失败", "Fail", "FAIL"] else "blocked"
            table_rows += f"""
            <tr>
                <td>{tc.get("用例ID") or tc.get("case_id", "")}</td>
                <td>{tc.get("用例标题") or tc.get("title", "")}</td>
                <td>{tc.get("测试步骤") or tc.get("steps", "")}</td>
                <td>{tc.get("预期结果") or tc.get("expected", "")}</td>
                <td>{tc.get("实际结果") or tc.get("actual", "")}</td>
                <td class="{status_class}">{status}</td>
            </tr>
            """

        # HTML模板
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report_title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #4472C4; padding-bottom: 10px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat-card {{ flex: 1; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-card h3 {{ margin: 0; font-size: 32px; }}
        .stat-card p {{ margin: 5px 0 0 0; color: #666; }}
        .total {{ background: #E7F3FF; color: #0066CC; }}
        .pass {{ background: #E8F5E9; color: #2E7D32; }}
        .fail {{ background: #FFEBEE; color: #C62828; }}
        .blocked {{ background: #FFF9E6; color: #F57C00; }}
        .chart-section {{ margin: 30px 0; padding: 20px; background: #fafafa; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border: 1px solid #ddd; }}
        th {{ background: #4472C4; color: white; font-weight: bold; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
        .timestamp {{ color: #666; font-size: 14px; margin-top: 20px; text-align: right; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{report_title}</h1>

        <div class="summary">
            <div class="stat-card total">
                <h3>{total}</h3>
                <p>总用例数</p>
            </div>
            <div class="stat-card pass">
                <h3>{passed}</h3>
                <p>通过</p>
            </div>
            <div class="stat-card fail">
                <h3>{failed}</h3>
                <p>失败</p>
            </div>
            <div class="stat-card blocked">
                <h3>{blocked}</h3>
                <p>阻塞</p>
            </div>
        </div>

        <div class="stat-card" style="background: #F0F4FF; margin: 20px 0;">
            <h3>{pass_rate:.1f}%</h3>
            <p>通过率</p>
        </div>

        {f'<div class="chart-section"><h2>测试统计图表</h2>{chart_html}</div>' if chart_html else ''}

        <h2>测试用例详情</h2>
        <table>
            <thead>
                <tr>
                    <th>用例ID</th>
                    <th>用例标题</th>
                    <th>测试步骤</th>
                    <th>预期结果</th>
                    <th>实际结果</th>
                    <th>状态</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>

        <div class="timestamp">生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
    </div>
</body>
</html>"""

        # 保存文件
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return f"成功: 测试报告已保存到 {os.path.abspath(file_path)}"

    except Exception as e:
        return f"错误: 生成报告失败 - {str(e)}"


# =====================================================================
# PDF 附件解析工具（供 src/file_rag/main.py 的 before_model 中间件调用）
# =====================================================================
#
# 背景说明（新手友好版）：
# - 前端上传 PDF 时，messages 里会带一个 {"type": "file", "source_type": "base64", ...} 的块
# - 如果把 base64 直接塞给模型，通常会出现：
#   1) 请求体太大（卡顿/超时/400）
#   2) 模型不认识 "file" block（400 unknown variant file）
#
# 所以这里做“预处理”：
# 1) base64 -> 真正的 PDF bytes
# 2) 用 langchain-pymupdf4llm 抽取 PDF 文本
# 3) 在需要时，调用多模态模型把 PDF 图片转成文本（可检索、可问答）
# 4) 最终把解析出来的文本回写到 HumanMessage.content（让模型看到“文本”而不是 base64）
#
# 注意：
# - 多模态解析图片开销很大，这里默认“按需启用” + “预算限制”，避免前端看起来卡住
#

import base64
import gc
import hashlib
import json
import re
import time
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from langchain_core.documents import Document
from langchain_core.document_loaders import BaseBlobParser, Blob
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_pymupdf4llm import PyMuPDF4LLMLoader, PyMuPDF4LLMParser

from langchain.tools import tool

from file_rag.core.llms import get_default_model, get_doubao_seed_model


def _env_int(name: str, default: int) -> int:
    """读取 int 环境变量，失败则返回 default。"""
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    """读取 float 环境变量，失败则返回 default。"""
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


# ==========================
# 可调参数（性能/体验相关）
# ==========================
# 你可以通过环境变量调整（不需要改代码）：
# - PDF_FORCE_EXTRACT_IMAGES=1  强制开启图片多模态解析（无论用户问题是否提到图片）
# - PDF_IMAGE_MAX_PAGES=5       最多解析前 N 页的图片（默认 5）
# - PDF_IMAGE_MAX_IMAGES=10     最多解析前 N 张图片（默认 10）
# - PDF_IMAGE_MAX_SECONDS=20    图片解析总耗时上限（秒，默认 20s）
# - PDF_IMAGE_MAX_BYTES=2500000 单张图片最大 bytes（默认 2.5MB）
# - PDF_TEXT_MAX_CHARS=30000    注入到对话的文本最大字符数（默认 30000）
# - PDF_TEXT_MAX_PAGES=20       文本最多解析前 N 页（默认 20）
#
# 建议：
# - 如果你前端经常“转圈很久”，先把 PDF_TEXT_MAX_CHARS/页数上限调小，保证交互先跑通
#
_PDF_FORCE_EXTRACT_IMAGES: bool = os.getenv("PDF_FORCE_EXTRACT_IMAGES", "0").lower() in {
    "1",
    "true",
    "yes",
    "y",
}
_PDF_IMAGE_MAX_PAGES: int = _env_int("PDF_IMAGE_MAX_PAGES", 5)
_PDF_IMAGE_MAX_IMAGES: int = _env_int("PDF_IMAGE_MAX_IMAGES", 10)
_PDF_IMAGE_MAX_SECONDS: float = _env_float("PDF_IMAGE_MAX_SECONDS", 20.0)
_PDF_IMAGE_MAX_BYTES: int = _env_int("PDF_IMAGE_MAX_BYTES", 2_500_000)
_PDF_TEXT_MAX_CHARS: int = _env_int("PDF_TEXT_MAX_CHARS", 30000)
_PDF_TEXT_MAX_PAGES: int = _env_int("PDF_TEXT_MAX_PAGES", 20)

# 图片解析模式：
# - always：总是尝试解析图片（仍受 PDF_IMAGE_MAX_* 预算限制）
# - auto：根据用户问题是否提到“图片/图表/流程图”等再决定
# - never：从不解析图片
_PDF_IMAGES_MODE: str = (os.getenv("PDF_IMAGES_MODE", "always") or "always").strip().lower()

# 是否把“原始 PDF 文件”持久化保存到本地（默认开启，避免信息丢失）
_PDF_PERSIST_UPLOADS: bool = os.getenv("PDF_PERSIST_UPLOADS", "1").lower() in {
    "1",
    "true",
    "yes",
    "y",
}

# 是否把“解析结果”按页分片保存（jsonl）（默认开启，便于后续做检索/RAG）
_PDF_STORE_CHUNKS: bool = os.getenv("PDF_STORE_CHUNKS", "1").lower() in {
    "1",
    "true",
    "yes",
    "y",
}

# 是否覆盖已有的分片文件（同一份 PDF 重复上传时可能命中同一个 doc_id）
_PDF_OVERWRITE_EXTRACTED: bool = os.getenv("PDF_OVERWRITE_EXTRACTED", "0").lower() in {
    "1",
    "true",
    "yes",
    "y",
}

_PDF_UPLOAD_DIR = os.getenv("PDF_UPLOAD_DIR", "storage/pdf_uploads")
_PDF_EXTRACT_DIR = os.getenv("PDF_EXTRACT_DIR", "storage/pdf_extracted")

# 是否复用已落盘的抽取结果（chunks/meta）（默认开启，避免重复解析/重复写入导致“从头再来”）
_PDF_REUSE_EXTRACTED: bool = os.getenv("PDF_REUSE_EXTRACTED", "1").lower() in {
    "1",
    "true",
    "yes",
    "y",
}

# 读取分片时是否去重（防止历史重复写入导致“看起来又从头解析一遍”）
_PDF_DEDUP_CHUNKS: bool = os.getenv("PDF_DEDUP_CHUNKS", "1").lower() in {
    "1",
    "true",
    "yes",
    "y",
}

# “注入到对话上下文”的预算（为了不卡住、避免上下文爆炸）
_PDF_CONTEXT_MAX_PAGES: int = _env_int("PDF_CONTEXT_MAX_PAGES", _PDF_TEXT_MAX_PAGES)
_PDF_CONTEXT_MAX_CHARS: int = _env_int("PDF_CONTEXT_MAX_CHARS", _PDF_TEXT_MAX_CHARS)

# “落盘分片抽取”的预算（用于存储原始解析结果，默认不限制，避免信息丢失）
_PDF_EXTRACT_MAX_PAGES: int = _env_int("PDF_EXTRACT_MAX_PAGES", 0)
_PDF_EXTRACT_MAX_CHARS: int = _env_int("PDF_EXTRACT_MAX_CHARS", 0)

# 落盘 jsonl 的单条最大字符数（把“按页”再切小一点，便于断点续跑）
_PDF_CHUNK_MAX_CHARS: int = _env_int("PDF_CHUNK_MAX_CHARS", 4000)


def _should_extract_images(user_text: str) -> bool:
    """根据配置决定是否解析图片（多模态）。"""
    mode = (_PDF_IMAGES_MODE or "always").lower()
    if mode == "never":
        return False
    if mode == "always":
        return True
    if mode != "auto":
        # 配置写错时，保守起见按 always 处理（避免“用户以为能解析图片，实际没解析”）
        return True

    # auto：只有用户明确提到图片/图表等关键词才触发
    return any(
        kw in (user_text or "")
        for kw in (
            "图片",
            "图中",
            "图里",
            "截图",
            "流程图",
            "示意图",
            "图表",
            "表格",
        )
    )


def _compute_pdf_id(pdf_bytes: bytes) -> str:
    """为一份 PDF 生成稳定的 id（用于去重、持久化目录命名）。"""
    return hashlib.sha256(pdf_bytes).hexdigest()


def _persist_pdf_upload(pdf_bytes: bytes, filename: str) -> tuple[str | None, Path | None]:
    """把原始 PDF bytes 落盘保存，避免“预算限制”导致信息不可恢复。

    返回：
    - (doc_id, pdf_path)
      - doc_id: sha256(pdf_bytes)
      - pdf_path: 保存后的真实路径

    说明：
    - 如果关闭了 PDF_PERSIST_UPLOADS，则返回 (None, None)
    """
    if not _PDF_PERSIST_UPLOADS:
        return None, None

    doc_id = _compute_pdf_id(pdf_bytes)
    base_dir = Path(_PDF_UPLOAD_DIR) / doc_id
    base_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = base_dir / _safe_pdf_filename(filename)
    if not pdf_path.exists():
        pdf_path.write_bytes(pdf_bytes)

    meta_path = base_dir / "meta.json"
    if _PDF_OVERWRITE_EXTRACTED or not meta_path.exists():
        meta = {
            "doc_id": doc_id,
            "filename": _safe_pdf_filename(filename),
            "bytes": len(pdf_bytes),
            "pdf_path": pdf_path.as_posix(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return doc_id, pdf_path


def _open_chunks_writer(doc_id: str, *, filename: str, pdf_path: Path) -> tuple[Path, Any] | tuple[None, None]:
    """打开 jsonl 分片写入器：每行一个 chunk（按页/按阶段）。"""
    if not _PDF_STORE_CHUNKS:
        return None, None

    base_dir = Path(_PDF_EXTRACT_DIR) / doc_id
    base_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = base_dir / "chunks.jsonl"
    if _PDF_OVERWRITE_EXTRACTED and chunks_path.exists():
        chunks_path.write_text("", encoding="utf-8")
    elif chunks_path.exists() and _PDF_REUSE_EXTRACTED:
        # 关键：如果已经存在抽取结果，默认不再“追加写入”，避免：
        # - chunks.jsonl 被重复写入同样内容（导致分析阶段看起来“反复从头解析”）
        # - 文件越来越大，后续分析耗时越来越长
        return chunks_path, None

    meta_path = base_dir / "meta.json"
    if _PDF_OVERWRITE_EXTRACTED or not meta_path.exists():
        meta = {
            "doc_id": doc_id,
            "filename": _safe_pdf_filename(filename),
            "pdf_path": pdf_path.as_posix(),
            "budgets": {
                "PDF_CONTEXT_MAX_PAGES": _PDF_CONTEXT_MAX_PAGES,
                "PDF_CONTEXT_MAX_CHARS": _PDF_CONTEXT_MAX_CHARS,
                "PDF_EXTRACT_MAX_PAGES": _PDF_EXTRACT_MAX_PAGES,
                "PDF_EXTRACT_MAX_CHARS": _PDF_EXTRACT_MAX_CHARS,
                "PDF_IMAGE_MAX_PAGES": _PDF_IMAGE_MAX_PAGES,
                "PDF_IMAGE_MAX_IMAGES": _PDF_IMAGE_MAX_IMAGES,
                "PDF_IMAGE_MAX_SECONDS": _PDF_IMAGE_MAX_SECONDS,
                "PDF_IMAGE_MAX_BYTES": _PDF_IMAGE_MAX_BYTES,
                "PDF_IMAGES_MODE": _PDF_IMAGES_MODE,
            },
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 新文件：写入分片（默认只写一次；后续命中同 doc_id 则复用，不再追加）
    fp = open(chunks_path, "a", encoding="utf-8")
    return chunks_path, fp


def _extracted_ready(doc_id: str) -> bool:
    """判断 doc_id 是否已经有可复用的落盘抽取结果。"""
    base_dir = Path(_PDF_EXTRACT_DIR) / doc_id
    return (base_dir / "chunks.jsonl").exists() and (base_dir / "meta.json").exists()


def _split_text(text: str, max_chars: int) -> list[str]:
    """把长文本切成多个小块（用于 jsonl 分片与断点续跑）。"""
    if not isinstance(text, str) or not text:
        return [""]
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        parts.append(text[start:end])
        start = end
    return parts


def _build_context_excerpt_from_chunks(doc_id: str) -> str:
    """从已落盘的 chunks.jsonl 构造“注入上下文”的节选，避免重复解析 PDF。"""
    chunks_path = Path(_PDF_EXTRACT_DIR) / doc_id / "chunks.jsonl"
    if not chunks_path.exists():
        return ""

    pages_seen: set[int] = set()
    pages_count = 0
    chars = 0
    out_parts: list[str] = []

    with open(chunks_path, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue

            content = obj.get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue

            page = obj.get("page")
            if isinstance(page, int):
                if page not in pages_seen:
                    pages_seen.add(page)
                    pages_count += 1
                if _PDF_CONTEXT_MAX_PAGES > 0 and pages_count > _PDF_CONTEXT_MAX_PAGES:
                    break

            if _PDF_CONTEXT_MAX_CHARS > 0 and chars >= _PDF_CONTEXT_MAX_CHARS:
                break

            remaining = _PDF_CONTEXT_MAX_CHARS - chars if _PDF_CONTEXT_MAX_CHARS > 0 else None
            if remaining is not None and remaining <= 0:
                break

            text_to_add = content if remaining is None else content[:remaining]
            out_parts.append(text_to_add)
            chars += len(text_to_add)

    excerpt = "\n\n".join([p for p in out_parts if p.strip()]).strip()
    if excerpt:
        excerpt += (
            f"\n\n[提示：以上为落盘分片的节选（DOC_ID: {doc_id}）。"
            f"需要“完整不漏”的分析请使用 pdf_analyze_doc(DOC_ID, question)。]"
        )
    return excerpt


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    """把超长文本截断到 max_chars，返回 (截断后的文本, 是否截断过)。"""
    if max_chars <= 0:
        return text, False
    if len(text) <= max_chars:
        return text, False
    return (
        text[:max_chars].rstrip()
        + f"\n\n[内容过长已截断：仅保留前 {max_chars} / {len(text)} 字符，可通过 PDF_TEXT_MAX_CHARS 调整上限]",
        True,
    )


_IMAGE_TO_TEXT_PROMPT: str = (
    "你是一个用于PDF内容解析的助手，任务是把图片内容转成可检索的文本。\n"
    "1) 用尽可能精炼、信息密度高的方式描述图片（便于检索）。\n"
    "2) 提取图片里的全部文字（不要遗漏任何内容）。\n"
    "3) 以Markdown输出，不要包含解释性文字，也不要在开头输出```。\n"
)


def _try_get_image_size(raw: bytes, mimetype: str) -> tuple[int | None, int | None]:
    """尽量从图片 bytes 中解析出宽高（不依赖 Pillow）。"""
    try:
        mt = (mimetype or "").lower()

        # ---- PNG ----
        if mt == "image/png":
            if len(raw) < 24:
                return None, None
            if raw[:8] != b"\x89PNG\r\n\x1a\n":
                return None, None
            if raw[12:16] != b"IHDR":
                return None, None
            w = int.from_bytes(raw[16:20], "big")
            h = int.from_bytes(raw[20:24], "big")
            return (w, h) if w > 0 and h > 0 else (None, None)

        # ---- JPEG ----
        if mt in {"image/jpeg", "image/jpg"}:
            if len(raw) < 4 or raw[0:2] != b"\xFF\xD8":
                return None, None
            i = 2
            n = len(raw)
            while i + 9 < n:
                if raw[i] != 0xFF:
                    i += 1
                    continue
                marker = raw[i + 1]
                i += 2
                if marker in {0xC0, 0xC2}:
                    if i + 7 >= n:
                        break
                    seg_len = int.from_bytes(raw[i : i + 2], "big")
                    if seg_len < 7:
                        break
                    h = int.from_bytes(raw[i + 3 : i + 5], "big")
                    w = int.from_bytes(raw[i + 5 : i + 7], "big")
                    return (w, h) if w > 0 and h > 0 else (None, None)
                if i + 1 >= n:
                    break
                seg_len = int.from_bytes(raw[i : i + 2], "big")
                i += seg_len
            return None, None

        # ---- WEBP ----
        if mt == "image/webp":
            if len(raw) < 30:
                return None, None
            if not (raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"):
                return None, None
            i = 12
            n = len(raw)
            while i + 8 <= n:
                tag = raw[i : i + 4]
                size = int.from_bytes(raw[i + 4 : i + 8], "little")
                i += 8
                if i + size > n:
                    break
                if tag == b"VP8X" and size >= 10 and i + 10 <= n:
                    w = int.from_bytes(raw[i + 4 : i + 7], "little") + 1
                    h = int.from_bytes(raw[i + 7 : i + 10], "little") + 1
                    return (w, h) if w > 0 and h > 0 else (None, None)
                i += size + (size % 2)
            return None, None

        return None, None
    except Exception:
        return None, None


class _BudgetedImageBlobParser(BaseBlobParser):
    """给图片多模态解析加“预算限制”，避免图片太多导致长时间阻塞。"""

    def __init__(self, inner: BaseBlobParser, *, max_images: int) -> None:
        super().__init__()
        self._inner = inner
        self._max_images = max_images
        self.parsed_images = 0
        self.skipped_images = 0

    def lazy_parse(self, blob: Blob):
        if self._max_images >= 0 and self.parsed_images >= self._max_images:
            self.skipped_images += 1
            yield Document(
                page_content=f"[图片过多，已跳过多模态解析：max_images={self._max_images}]",
                metadata={**blob.metadata, **{"source": blob.source}},
            )
            return

        self.parsed_images += 1
        yield from self._inner.lazy_parse(blob)


class _MultimodalImageBlobParser(BaseBlobParser):
    """把图片 Blob 交给多模态模型，输出图片描述/图片文字。"""

    def __init__(self, *, model, prompt: str = _IMAGE_TO_TEXT_PROMPT) -> None:
        super().__init__()
        self._model = model
        self._prompt = prompt
        # doubao 触发 429 时，后续图片不再继续打请求（避免刷屏 + 避免前端看起来“卡住”）
        self._rate_limited = False
        self._rate_limit_notice_emitted = False

    def lazy_parse(self, blob: Blob):
        with blob.as_bytes_io() as buf:
            raw = buf.read()

        if _PDF_IMAGE_MAX_BYTES > 0 and len(raw) > _PDF_IMAGE_MAX_BYTES:
            mb = len(raw) / (1024 * 1024)
            content = (
                f"[图片过大（{mb:.2f}MB），已跳过多模态解析："
                f"PDF_IMAGE_MAX_BYTES={_PDF_IMAGE_MAX_BYTES}]"
            )
            yield Document(
                page_content=content,
                metadata={**blob.metadata, **{"source": blob.source}},
            )
            return

        mimetype = blob.mimetype or "image/png"
        if mimetype == "application/octet-stream" and blob.source:
            suffix = Path(str(blob.source)).suffix.lower()
            mimetype = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(suffix, "image/png")

        width, height = _try_get_image_size(raw, mimetype)
        if width is not None and height is not None and min(width, height) < 14:
            content = f"[图片尺寸过小（{width}x{height}），已跳过多模态解析]"
            yield Document(
                page_content=content,
                metadata={**blob.metadata, **{"source": blob.source}},
            )
            return

        img_base64 = base64.b64encode(raw).decode("utf-8")

        # 如果已经确认模型被限流/暂停，后续图片直接跳过（不再发请求）
        if self._rate_limited:
            if not self._rate_limit_notice_emitted:
                self._rate_limit_notice_emitted = True
                yield Document(
                    page_content=(
                        "[图片多模态解析已暂停：doubao 模型触发 429（Safe Experience Mode / SetLimitExceeded）。"
                        "请在火山引擎模型控制台调整/关闭 Safe Experience Mode 或提升额度后重试。]"
                    ),
                    metadata={**blob.metadata, **{"source": blob.source}},
                )
            else:
                # 返回空内容，避免把“重复提示”写进分片/上下文导致膨胀
                yield Document(
                    page_content="",
                    metadata={**blob.metadata, **{"source": blob.source}},
                )
            return

        try:
            msg = self._model.invoke(
                [
                    HumanMessage(
                        content=[
                            {"type": "text", "text": self._prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mimetype};base64,{img_base64}"
                                },
                            },
                        ]
                    )
                ]
            )
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
        except Exception as exc:
            err = str(exc)
            # 识别“账号推理额度被暂停/限流”的典型报错，后续直接熔断，避免每张图片都打一遍 429。
            if any(
                k in err
                for k in (
                    "SetLimitExceeded",
                    "Safe Experience Mode",
                    "TooManyRequests",
                    "RateLimitError",
                    "429",
                )
            ):
                self._rate_limited = True
            if len(err) > 300:
                err = err[:300] + "…"
            content = f"[图片解析失败（已跳过该图片）：{err}]"

        yield Document(
            page_content=content,
            metadata={**blob.metadata, **{"source": blob.source}},
        )


_pdf_images_parser: BaseBlobParser | None = None
_pdf_images_parser_init_error: Exception | None = None


def _get_pdf_images_parser() -> BaseBlobParser | None:
    """懒加载 + 缓存图片解析器（失败后不反复重试）。"""
    global _pdf_images_parser, _pdf_images_parser_init_error

    if _pdf_images_parser is not None:
        return _pdf_images_parser
    if _pdf_images_parser_init_error is not None:
        return None

    try:
        _pdf_images_parser = _MultimodalImageBlobParser(model=get_doubao_seed_model())
        return _pdf_images_parser
    except Exception as exc:
        _pdf_images_parser_init_error = exc
        return None


def _decode_base64(data: str) -> bytes:
    """把 base64 字符串解码为 bytes（兼容 data URL）。"""
    raw = data.strip()
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    raw = re.sub(r"\s+", "", raw)

    missing_padding = len(raw) % 4
    if missing_padding:
        raw += "=" * (4 - missing_padding)

    return base64.b64decode(raw)


def _safe_pdf_filename(filename: str | None) -> str:
    """生成安全文件名（避免路径穿越，缺省补 .pdf）。"""
    if not filename:
        return "upload.pdf"
    name = Path(filename).name
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


def _extract_pdf_markdown(
    pdf_bytes: bytes,
    filename: str,
    *,
    enable_images: bool,
    doc_id: str | None = None,
    persisted_pdf_path: Path | None = None,
) -> str:
    """PDF bytes -> Markdown（必要时包含图片多模态文本）。"""
    images_parser = _get_pdf_images_parser()

    # 说明：
    # - 如果调用方已经把 PDF 落盘（persisted_pdf_path），这里就复用该路径；
    # - 否则走临时目录（仅用于当前解析）。
    temp_dir_ctx = None
    if persisted_pdf_path is None:
        temp_dir_ctx = TemporaryDirectory(prefix="lc_pdf_", ignore_cleanup_errors=True)
        tmp_dir = temp_dir_ctx.__enter__()
        pdf_path = Path(tmp_dir) / _safe_pdf_filename(filename)
        pdf_path.write_bytes(pdf_bytes)
    else:
        pdf_path = persisted_pdf_path

    chunks_path: Path | None = None
    chunks_fp = None
    if doc_id is not None:
        chunks_path, chunks_fp = _open_chunks_writer(
            doc_id,
            filename=filename,
            pdf_path=pdf_path,
        )

    try:
        # 用文件路径打开：更稳定，也避免某些库在 stream 模式下 doc.name=None 的坑
        blob = Blob.from_path(
            str(pdf_path),
            mime_type="application/pdf",
            metadata={"filename": _safe_pdf_filename(filename)},
        )

        # 注意：这里把“落盘分片”和“注入上下文”分开控制：
        # - 分片落盘：尽量全量（默认不限制），避免信息丢失
        # - 注入上下文：严格预算（默认 20 页 / 30000 字符），避免一次请求把模型撑爆
        text_parts: list[str] = []
        context_text_len = 0
        context_text_pages = 0
        extracted_text_len = 0
        extracted_text_pages = 0
        total_text_pages: int | None = None

        for doc in PyMuPDF4LLMParser(mode="page").lazy_parse(blob):
            if total_text_pages is None and isinstance(doc.metadata, dict):
                total_text_pages = doc.metadata.get("total_pages")

            # 按页分片写入（用于后续检索/RAG）
            if chunks_fp is not None:
                parts = _split_text(doc.page_content, _PDF_CHUNK_MAX_CHARS)
                for part_index, part_text in enumerate(parts):
                    chunk = {
                        "doc_id": doc_id,
                        "kind": "text",
                        "page": doc.metadata.get("page")
                        if isinstance(doc.metadata, dict)
                        else None,
                        "part_index": part_index,
                        "part_total": len(parts),
                        "content": part_text,
                        "metadata": doc.metadata,
                    }
                    chunks_fp.write(json.dumps(chunk, ensure_ascii=False) + "\n")

            # 注入上下文的预算：只把“前面的一部分”拼到 text_md 里
            if _PDF_CONTEXT_MAX_PAGES <= 0 or context_text_pages < _PDF_CONTEXT_MAX_PAGES:
                if _PDF_CONTEXT_MAX_CHARS <= 0 or context_text_len < _PDF_CONTEXT_MAX_CHARS:
                    text_parts.append(doc.page_content)
                    context_text_pages += 1
                    context_text_len += len(doc.page_content)

            # 落盘抽取的预算：默认不限制（<=0 表示不限制）
            extracted_text_pages += 1
            extracted_text_len += len(doc.page_content)
            if _PDF_EXTRACT_MAX_PAGES > 0 and extracted_text_pages >= _PDF_EXTRACT_MAX_PAGES:
                break
            if _PDF_EXTRACT_MAX_CHARS > 0 and extracted_text_len >= _PDF_EXTRACT_MAX_CHARS:
                break

        text_md = "\n\n".join(text_parts).strip()
        if total_text_pages and extracted_text_pages < total_text_pages:
            text_md += (
                f"\n\n[提示：文本分片仅落盘解析前 {extracted_text_pages}/{total_text_pages} 页"
                f"（PDF_EXTRACT_MAX_PAGES={_PDF_EXTRACT_MAX_PAGES}，PDF_EXTRACT_MAX_CHARS={_PDF_EXTRACT_MAX_CHARS}）]"
            )
        if total_text_pages and context_text_pages < total_text_pages:
            text_md += (
                f"\n\n[提示：注入到对话上下文的正文为节选：{context_text_pages}/{total_text_pages} 页"
                f"（PDF_CONTEXT_MAX_PAGES={_PDF_CONTEXT_MAX_PAGES}，PDF_CONTEXT_MAX_CHARS={_PDF_CONTEXT_MAX_CHARS}）]"
            )

        if not enable_images and not _PDF_FORCE_EXTRACT_IMAGES:
            final_text, _ = _truncate_text(text_md, _PDF_CONTEXT_MAX_CHARS)
            return (
                final_text
                + "\n\n[提示：如需解析PDF中的图片/流程图/图表，请在问题中说明“解析图片”，或设置环境变量 PDF_FORCE_EXTRACT_IMAGES=1]"
            )

        if images_parser is not None:
            try:
                budgeted_parser = _BudgetedImageBlobParser(
                    images_parser,
                    max_images=_PDF_IMAGE_MAX_IMAGES,
                )
                loader = PyMuPDF4LLMLoader(
                    str(pdf_path),
                    mode="page",
                    extract_images=True,
                    images_parser=budgeted_parser,
                )

                start = time.monotonic()
                page_contents: list[str] = []
                processed_pages = 0
                total_pages: int | None = None
                timed_out = False

                for doc in loader.lazy_load():
                    if total_pages is None and isinstance(doc.metadata, dict):
                        total_pages = doc.metadata.get("total_pages")
                    page_contents.append(doc.page_content)
                    processed_pages += 1

                    if chunks_fp is not None:
                        parts = _split_text(doc.page_content, _PDF_CHUNK_MAX_CHARS)
                        for part_index, part_text in enumerate(parts):
                            chunk = {
                                "doc_id": doc_id,
                                "kind": "images",
                                "page": doc.metadata.get("page")
                                if isinstance(doc.metadata, dict)
                                else None,
                                "part_index": part_index,
                                "part_total": len(parts),
                                "content": part_text,
                                "metadata": doc.metadata,
                            }
                            chunks_fp.write(json.dumps(chunk, ensure_ascii=False) + "\n")

                    # 约定：<= 0 表示“不限制”
                    if _PDF_IMAGE_MAX_PAGES > 0 and processed_pages >= _PDF_IMAGE_MAX_PAGES:
                        break
                    if _PDF_IMAGE_MAX_SECONDS > 0 and time.monotonic() - start >= _PDF_IMAGE_MAX_SECONDS:
                        timed_out = True
                        break

                images_md = "\n\n".join(page_contents).strip()
                combined = text_md

                has_images = "![" in images_md
                if has_images:
                    notes: list[str] = []
                    if total_pages and processed_pages < total_pages:
                        notes.append(
                            f"仅处理前 {processed_pages}/{total_pages} 页图片（PDF_IMAGE_MAX_PAGES={_PDF_IMAGE_MAX_PAGES}）"
                        )
                    if budgeted_parser.skipped_images:
                        notes.append(
                            f"图片超过上限，已跳过 {budgeted_parser.skipped_images} 张（PDF_IMAGE_MAX_IMAGES={_PDF_IMAGE_MAX_IMAGES}）"
                        )
                    if timed_out:
                        notes.append(
                            f"达到耗时上限 {int(_PDF_IMAGE_MAX_SECONDS)}s（PDF_IMAGE_MAX_SECONDS={_PDF_IMAGE_MAX_SECONDS}）"
                        )

                    combined = (
                        f"{text_md}\n\n---\n\n[图片多模态解析（节选）]\n{images_md}"
                    )
                    if notes:
                        combined += "\n\n[" + "；".join(notes) + "]"

                final_text, _ = _truncate_text(combined, _PDF_CONTEXT_MAX_CHARS)
                return final_text
            except Exception as exc:
                final_text, _ = _truncate_text(text_md, _PDF_CONTEXT_MAX_CHARS)
                return f"{final_text}\n\n[图片解析失败，已降级为仅文本提取：{exc}]"
            finally:
                gc.collect()

        final_text, _ = _truncate_text(text_md, _PDF_CONTEXT_MAX_CHARS)
        return final_text
    finally:
        if chunks_fp is not None:
            chunks_fp.close()
        if temp_dir_ctx is not None:
            temp_dir_ctx.__exit__(None, None, None)


def _replace_pdf_file_blocks_with_text(content: Any) -> tuple[str | None, bool]:
    """把 HumanMessage.content 中的 PDF file 块替换成可读文本。"""
    if not isinstance(content, list):
        return None, False

    user_text_parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if isinstance(text, str) and text.strip():
                user_text_parts.append(text.strip())
    user_text = "\n".join(user_text_parts)

    enable_images = _should_extract_images(user_text)

    text_chunks: list[str] = []
    replaced_any = False

    for block in content:
        if isinstance(block, str):
            if block.strip():
                text_chunks.append(block)
            continue

        if not isinstance(block, dict):
            continue

        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text", "")
            if isinstance(text, str) and text.strip():
                text_chunks.append(text)
            continue

        if block_type != "file":
            continue

        if (block.get("source_type") or "").lower() != "base64":
            continue
        if (block.get("mime_type") or "").lower() != "application/pdf":
            continue

        filename = (block.get("metadata") or {}).get("filename") or "upload.pdf"
        data = block.get("data") or ""
        if not isinstance(data, str) or not data.strip():
            replaced_any = True
            text_chunks.append(f"[附件 {filename}：未提供可用的base64数据]")
            continue

        replaced_any = True
        try:
            pdf_bytes = _decode_base64(data)
            doc_id, persisted_pdf_path = _persist_pdf_upload(pdf_bytes, filename)

            if doc_id is not None and _PDF_REUSE_EXTRACTED and not _PDF_OVERWRITE_EXTRACTED and _extracted_ready(doc_id):
                # 已经抽取过：直接复用落盘分片，避免重复解析导致“从头再来”
                md = _build_context_excerpt_from_chunks(doc_id)
                if not md:
                    md = "[已存在落盘分片，但未能生成节选，请使用 pdf_analyze_doc(DOC_ID, question)]"
            else:
                md = _extract_pdf_markdown(
                    pdf_bytes,
                    filename,
                    enable_images=enable_images,
                    doc_id=doc_id,
                    persisted_pdf_path=persisted_pdf_path,
                )

            # 给用户一个“可追溯 id”：后续要做分片检索/RAG 时，可以用 DOC_ID 定位。
            #
            # 注意：这里不要输出 "doc_id=..."（带等号），否则 system_prompt 可能把它当作“触发条件”，
            # 导致模型在同一轮里反复调用工具，看起来像“一直重复从头解析”。
            if doc_id is not None:
                saved_tip = (
                    f"\n\n[PDF已落盘；DOC_ID: {doc_id}；"
                    f"原始文件目录={Path(_PDF_UPLOAD_DIR).joinpath(doc_id).as_posix()}]"
                )
            else:
                saved_tip = ""

            text_chunks.append(f"[附件 {filename} 解析结果]\n{md}{saved_tip}")
        except Exception as exc:
            text_chunks.append(f"[附件 {filename} 解析失败：{exc}]")

    if not replaced_any:
        return None, False

    return "\n\n".join(text_chunks).strip(), True


def build_pdf_message_updates(messages: list[Any]) -> list[Any]:
    """扫描 messages，把含 PDF 附件的 HumanMessage 更新为“文本版”。"""
    updated_messages: list[Any] = []

    for msg in messages:
        content = getattr(msg, "content", None)
        new_content, replaced = _replace_pdf_file_blocks_with_text(content)
        if replaced and new_content is not None:
            if getattr(msg, "id", None) is None:
                msg.id = str(uuid4())
            updated_messages.append(msg.model_copy(update={"content": new_content}))

    return updated_messages


def _read_pdf_chunks_jsonl(doc_id: str) -> list[dict[str, Any]]:
    """读取落盘的 chunks.jsonl 并返回 chunks 列表（按写入顺序）。"""
    doc_id = _normalize_doc_id(doc_id)
    chunks_path = Path(_PDF_EXTRACT_DIR) / doc_id / "chunks.jsonl"
    if not chunks_path.exists():
        raise FileNotFoundError(f"未找到分片文件：{chunks_path.as_posix()}")

    chunks: list[dict[str, Any]] = []
    seen: set[str] = set()
    with open(chunks_path, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            if _PDF_DEDUP_CHUNKS:
                sig = hashlib.sha1(line.encode("utf-8")).hexdigest()
                if sig in seen:
                    continue
                seen.add(sig)
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                chunks.append(obj)
    return chunks


_DOC_ID_HEX_RE = re.compile(r"[0-9a-fA-F]{64}")


def _normalize_doc_id(value: Any) -> str:
    """把多种“doc_id 传参形式”统一成 64 位 hex（小写）。

    兼容以下输入：
    - 纯哈希：ed8c...（64位）
    - 带前缀：DOC_ID: ed8c...
    - 老格式：doc_id=ed8c...

    这样可以避免：
    - 模型/前端把 DOC_ID 连同前缀一起传进来，导致找不到落盘目录；
    - 用户复制粘贴时带上多余字符，导致“看起来像从头开始”。
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("DOC_ID 不能为空，请传入 64 位十六进制哈希。")

    m = _DOC_ID_HEX_RE.search(value.strip())
    if not m:
        raise ValueError(
            "无效 DOC_ID：未在入参中找到 64 位十六进制哈希。"
            "示例：DOC_ID: ed8c506c...（共 64 位）"
        )
    return m.group(0).lower()


@tool
def pdf_analyze_doc(doc_id: str, question: str) -> str:
    """对指定 doc_id 的 PDF 分片做“逐片完整阅读 + 汇总回答”。

    设计目标：
    - 解决“单次上下文塞不下整份 PDF”导致的信息遗漏
    - 用“多次调用模型”逐片处理（每片可控），最后输出尽量完整的解读报告

    关键点：
    - 断点续跑：中途被打断不会从头来（状态落盘在 analysis_state.json）
    - 追加拼接：每次只生成“本分片增量笔记”，直接追加到 notes.md（避免把整份笔记反复塞进模型导致 400）
    - 产物落盘：storage/pdf_extracted/<DOC_ID>/notes.md 与 answer.md
    """
    doc_id = _normalize_doc_id(doc_id)
    model = get_default_model()

    max_steps = _env_int("PDF_ANALYZE_MAX_STEPS", 5000)
    max_seconds = _env_float("PDF_ANALYZE_MAX_SECONDS", 90.0)
    flush_every_steps = _env_int("PDF_ANALYZE_FLUSH_EVERY", 5)
    preview_chars = _env_int("PDF_ANALYZE_NOTES_PREVIEW_CHARS", 1500)
    notes_tail_chars = _env_int("PDF_ANALYZE_NOTES_TAIL_CHARS", 2000)
    # 防御性上限：避免极端情况下写爆磁盘；需要“尽量不漏”可以调大，或设为 0 代表不限。
    notes_max_chars = _env_int("PDF_ANALYZE_NOTES_MAX_CHARS", 300000)

    final_sections_max_chars = _env_int("PDF_ANALYZE_FINAL_MAX_CHARS", 20000)
    final_input_max_chars = _env_int("PDF_ANALYZE_FINAL_INPUT_MAX_CHARS", 90000)
    chat_return_max_chars = _env_int("PDF_CHAT_RETURN_MAX_CHARS", 6000)

    chunks_path = Path(_PDF_EXTRACT_DIR) / doc_id / "chunks.jsonl"
    if not chunks_path.exists():
        raise FileNotFoundError(f"未找到分片文件：{chunks_path.as_posix()}")

    out_dir = Path(_PDF_EXTRACT_DIR) / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    notes_path = out_dir / "notes.md"
    answer_path = out_dir / "answer.md"
    state_path = out_dir / "analysis_state.json"

    def wants_reset(text: str) -> bool:
        """判断用户是否明确想“重新从头分析”。"""
        t = (text or "").strip()
        return any(k in t for k in ("从头", "重来", "重新", "清空", "reset"))

    def _read_tail(path: Path, max_chars: int) -> str:
        """只读文件尾部，避免大文件把内存/上下文撑爆。"""
        if max_chars <= 0 or not path.exists():
            return ""
        try:
            with open(path, "rb") as fp:
                fp.seek(0, os.SEEK_END)
                size = fp.tell()
                fp.seek(max(0, size - 64 * 1024))
                tail_bytes = fp.read()
            tail_text = tail_bytes.decode("utf-8", errors="ignore")
            if len(tail_text) <= max_chars:
                return tail_text.strip()
            return tail_text[-max_chars:].lstrip().strip()
        except Exception:
            return ""

    analysis_goal = (question or "").strip()
    line_offset = 0
    steps = 0
    done = False
    start_ts = time.monotonic()

    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = None
        if isinstance(state, dict):
            line_offset = int(state.get("line_offset", 0) or 0)
            steps = int(state.get("steps", 0) or 0)
            done = bool(state.get("done", False))

            prev_goal = state.get("analysis_goal", "")
            if isinstance(prev_goal, str) and prev_goal.strip() and not done and not wants_reset(question):
                analysis_goal = prev_goal

            # 兼容旧版：旧版把 notes 塞进 state.json，升级后先迁移到 notes.md，避免丢失。
            legacy_notes = state.get("notes")
            if isinstance(legacy_notes, str) and legacy_notes.strip() and not notes_path.exists():
                notes_path.write_text(legacy_notes, encoding="utf-8")

    def flush_state(*, done_flag: bool) -> None:
        payload = {
            "doc_id": doc_id,
            "analysis_goal": analysis_goal,
            "line_offset": line_offset,
            "steps": steps,
            "done": done_flag,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "notes_path": notes_path.as_posix(),
            "answer_path": answer_path.as_posix(),
        }
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 用户明确要求“重新/从头”：清空 notes + 进度
    if wants_reset(question):
        line_offset = 0
        steps = 0
        done = False
        if notes_path.exists():
            notes_path.write_text("", encoding="utf-8")
        flush_state(done_flag=False)

    system = SystemMessage(
        content=(
            "你是一个严谨的文档分析助手，你将按顺序阅读 PDF 的分片内容。\n"
            "要求：\n"
            "1) 你只输出【本分片新增的关键信息】（增量），不要复述已有内容。\n"
            "2) 增量必须结构化（Markdown 小标题/列表/表格），信息密度高。\n"
            "3) 对规则/优先级/数量限制/字段/埋点/看板等细节要逐条记录。\n"
            "4) 不要照抄原文，要提炼为可用的事实/规则/结论。\n"
        )
    )

    if not done:
        try:
            total_lines = sum(1 for _ in open(chunks_path, "r", encoding="utf-8"))
        except Exception:
            total_lines = None

        seen: set[str] = set()
        with open(chunks_path, "r", encoding="utf-8") as fp:
            for idx, line in enumerate(fp):
                if idx < line_offset:
                    continue
                if max_steps > 0 and steps >= max_steps:
                    break
                if max_seconds > 0 and (time.monotonic() - start_ts) >= max_seconds:
                    break

                line = line.strip()
                if not line:
                    line_offset = idx + 1
                    continue

                if _PDF_DEDUP_CHUNKS:
                    sig = hashlib.sha1(line.encode("utf-8")).hexdigest()
                    if sig in seen:
                        line_offset = idx + 1
                        continue
                    seen.add(sig)

                try:
                    chunk = json.loads(line)
                except Exception:
                    line_offset = idx + 1
                    continue
                if not isinstance(chunk, dict):
                    line_offset = idx + 1
                    continue

                content = chunk.get("content", "")
                if not isinstance(content, str) or not content.strip():
                    line_offset = idx + 1
                    continue

                kind = chunk.get("kind", "text")
                page = chunk.get("page")
                part_index = chunk.get("part_index")
                part_total = chunk.get("part_total")

                steps += 1
                notes_tail = _read_tail(notes_path, notes_tail_chars)

                prompt = HumanMessage(
                    content=(
                        f"分析目标：\n{analysis_goal}\n\n"
                        f"当前分片：kind={kind} page={page} part={part_index}/{part_total}\n"
                        f"{content}\n\n"
                        "已记录的累计笔记（末尾节选，仅用于去重，不代表全部）：\n"
                        f"{notes_tail}\n\n"
                        "请输出：只写【本分片新增的关键信息】（增量），不要复述上面的节选。"
                    )
                )

                try:
                    result = model.invoke([system, prompt])
                except Exception as exc:
                    flush_state(done_flag=False)
                    preview = _read_tail(notes_path, preview_chars)
                    progress = str(line_offset)
                    if total_lines:
                        pct = (line_offset / total_lines) * 100
                        progress = f"{line_offset}/{total_lines}（{pct:.1f}%）"
                    return (
                        f"[已断点保存] DOC_ID: {doc_id}\n"
                        f"- 已处理到分片行号：{progress}\n"
                        f"- 本轮累计 steps：{steps}\n"
                        f"- 当前进度已落盘：{state_path.as_posix()}\n\n"
                        f"[本次调用遇到错误]\n{exc}\n\n"
                        f"[累计笔记预览]\n{preview}\n\n"
                        f"如需继续，请发送：继续解析 DOC_ID: {doc_id}"
                    )

                delta = result.content if isinstance(result.content, str) else str(result.content)
                delta = (delta or "").strip()
                if delta:
                    header = (
                        f"\n\n## 分片 {idx + 1}\n"
                        f"- kind: {kind}\n"
                        f"- page: {page}\n"
                        f"- part: {part_index}/{part_total}\n\n"
                    )
                    to_write = header + delta + "\n"

                    if notes_max_chars > 0 and notes_path.exists():
                        try:
                            if notes_path.stat().st_size > notes_max_chars:
                                to_write = (
                                    "\n\n[警告] notes.md 已超过上限，后续增量将不再写入。"
                                    "如需继续写入，请调大 PDF_ANALYZE_NOTES_MAX_CHARS 或设置为 0。\n"
                                )
                        except Exception:
                            pass

                    with open(notes_path, "a", encoding="utf-8") as out_fp:
                        out_fp.write(to_write)

                line_offset = idx + 1
                if flush_every_steps > 0 and steps % flush_every_steps == 0:
                    flush_state(done_flag=False)

            else:
                done = True

        if not done:
            try:
                total_lines = sum(1 for _ in open(chunks_path, "r", encoding="utf-8"))
            except Exception:
                total_lines = None
            if total_lines is not None and line_offset >= total_lines:
                done = True

        flush_state(done_flag=done)

        if not done:
            preview = _read_tail(notes_path, preview_chars)
            progress = str(line_offset)
            if total_lines:
                pct = (line_offset / total_lines) * 100
                progress = f"{line_offset}/{total_lines}（{pct:.1f}%）"
            return (
                f"[已断点保存] DOC_ID: {doc_id}\n"
                f"- 已处理到分片行号：{progress}\n"
                f"- 本轮累计 steps：{steps}\n"
                f"- 当前进度已落盘：{state_path.as_posix()}\n\n"
                f"[累计笔记预览]\n{preview}\n\n"
                f"如需继续，请发送：继续解析 DOC_ID: {doc_id}\n"
                f"（提示：可调 PDF_ANALYZE_MAX_SECONDS / PDF_ANALYZE_MAX_STEPS 让单次跑更久）"
            )

    # 已完成：生成最终报告（尽量长，但避免一次输出把前端卡死）
    flush_state(done_flag=True)
    notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""

    final_system = SystemMessage(
        content=(
            "你是一个严谨的PRD/需求文档解读专家。\n"
            "你会收到一份对 PDF 全文逐片阅读后形成的【累计笔记】或其节选。\n"
            "要求：\n"
            "1) 输出要尽可能完整，不要只写一段很短的概括；宁可稍微冗长也不要遗漏。\n"
            "2) 必须结构化：使用 Markdown 标题/表格/列表。\n"
            "3) 对“规则/优先级/数量限制/字段校验/埋点/看板维度”等细节要逐条列出。\n"
            "4) 只基于笔记；如果笔记没有信息，要明确写“笔记未包含该信息”。\n"
        )
    )

    def clamp(text: str) -> str:
        if final_sections_max_chars <= 0:
            return text
        return text[:final_sections_max_chars].rstrip()

    def select_notes_excerpt(all_notes: str, keywords: set[str]) -> str:
        if not all_notes.strip():
            return ""

        paras = [p.strip() for p in all_notes.split("\n\n") if p.strip()]
        head = paras[:40]

        picked: list[str] = []
        for p in paras:
            if any(k in p for k in keywords):
                picked.append(p)

        text = "\n\n".join(head + picked).strip()
        if final_input_max_chars <= 0 or len(text) <= final_input_max_chars:
            return text
        return text[:final_input_max_chars].rstrip()

    section_specs: list[dict[str, Any]] = [
        {
            "task": "请输出【一页纸总览】：需求背景、目标、里程碑、核心方案一句话、范围边界、关键风险。",
            "keywords": {"背景", "目标", "里程碑", "范围", "边界", "风险", "结论"},
        },
        {
            "task": "请输出【竞品分析与结论】：逐个竞品的标签策略、优劣势、对拼拼的启示。",
            "keywords": {"竞品", "叮咚", "盒马", "美团", "拼多多", "对标", "启示", "优劣"},
        },
        {
            "task": "请输出【标签方案（全量细节）】：标签分组、组内/组间优先级、数量限制、标签类型、去掉/新增的标签。",
            "keywords": {"标签", "分组", "优先级", "组内", "组间", "数量", "限制", "规则生产", "手动", "新增", "去掉"},
        },
        {
            "task": "请输出【C端展示规则（必须详细表格）】：商卡页/商详页各位置：位置、标签组、最大数量、优先级、示例；并写变化点。",
            "keywords": {"C端", "商卡", "商详", "腰带", "标题", "位置", "展示", "温层", "促销"},
        },
        {
            "task": "请输出【后台/CMS功能清单】：新增/调整点、审批逻辑、标签管理、优先级(P0)等。",
            "keywords": {"CMS", "后台", "审批", "标签管理", "商卡商详", "P0", "体验优化"},
        },
        {
            "task": "请输出【数据埋点与看板】：埋点列表（页面/位/eid/参数/事件类型）、看板新增维度、数据源、是否实验。",
            "keywords": {"埋点", "曝光", "点击", "eid", "参数", "看板", "维度", "数据源", "实验"},
        },
        {
            "task": "请输出【约束/边界/待确认】：时间约束、范围边界、依赖项、待确认问题。",
            "keywords": {"约束", "依赖", "边界", "待确认", "时间", "风险"},
        },
    ]

    parts: list[str] = []
    for idx, spec in enumerate(section_specs, start=1):
        section_notes = select_notes_excerpt(notes, set(spec.get("keywords") or set()))
        user = HumanMessage(
            content=(
                f"用户问题：\n{question}\n\n"
                f"本章任务（第{idx}章）：\n{spec.get('task')}\n\n"
                f"累计笔记节选（来自 DOC_ID: {doc_id}）：\n{section_notes}"
            )
        )
        resp = model.invoke([final_system, user])
        part_text = resp.content if isinstance(resp.content, str) else str(resp.content)
        parts.append(clamp(part_text))

    answer_text = "\n\n---\n\n".join([p for p in parts if p.strip()]).strip()
    if not answer_text:
        answer_text = "未能生成报告（模型未返回内容），请重试。"

    answer_path.write_text(answer_text, encoding="utf-8")

    chat_text = answer_text
    if chat_return_max_chars > 0 and len(chat_text) > chat_return_max_chars:
        chat_text = (
            chat_text[:chat_return_max_chars].rstrip()
            + "\n\n[提示] 聊天窗口已截断输出，完整报告已落盘，请查看："
            f"{answer_path.as_posix()}"
        )

    return f"{chat_text}\n\n[已落盘：笔记={notes_path.as_posix()}；回答={answer_path.as_posix()}]"


@tool
def pdf_read_report(
    doc_id: str,
    kind: str = "answer",
    offset: int = -1,
    max_chars: int = 6000,
) -> str:
    """分段读取 PDF 的落盘产物（answer.md / notes.md），用于“把完整内容发到聊天里”。

    为什么需要这个工具？
    - answer.md / notes.md 可能很长；一次性把全文塞进聊天返回，容易导致前端卡住、或被网关截断。
    - 这个工具允许你按 offset 分段读取，每次读一段，直到读完。
    - 默认返回“纯内容”，不带状态头/尾，确保前端界面看到的就是报告正文。

    参数说明：
    - doc_id：
      - 支持 `DOC_ID: <hash>` / 纯 hash / 老格式 `doc_id=<hash>`（会自动归一化）
      - 也支持 `auto` / `latest` 或空字符串：自动选择最近一次落盘的 DOC_ID（最省事，但可能选错文档）
    - kind：`answer`（默认）读取最终报告；`notes` 读取累计笔记。
    - offset：从第 offset 个字符开始读取。
      - `-1`（默认）：自动从“上次输出位置”继续（无需用户自己传 offset）。
      - `0`：从头开始输出（重置）。
    - max_chars：本次最多返回多少字符；<=0 表示“尽量全读”（不推荐，容易卡）。
    """
    def auto_pick_latest_doc_id() -> str:
        """自动选择最近一次落盘的 DOC_ID（按文件修改时间）。"""
        base = Path(_PDF_EXTRACT_DIR)
        if not base.exists():
            raise FileNotFoundError(f"未找到目录：{base.as_posix()}")

        best_doc_id: str | None = None
        best_ts: float = -1.0

        for child in base.iterdir():
            if not child.is_dir():
                continue
            name = child.name
            if not _DOC_ID_HEX_RE.fullmatch(name):
                continue

            candidates = [
                child / "answer.md",
                child / "notes.md",
                child / "analysis_state.json",
                child / "report_read_state.json",
            ]
            ts = -1.0
            for p in candidates:
                if p.exists():
                    try:
                        ts = max(ts, p.stat().st_mtime)
                    except Exception:
                        continue
            if ts > best_ts:
                best_ts = ts
                best_doc_id = name

        if best_doc_id is None:
            raise FileNotFoundError(
                f"未发现任何可用的 DOC_ID（{base.as_posix()} 下没有落盘产物）。"
            )
        return best_doc_id

    raw_doc_id = (doc_id or "").strip()
    if not raw_doc_id or raw_doc_id.lower() in {"auto", "latest"}:
        normalized = auto_pick_latest_doc_id()
    else:
        normalized = _normalize_doc_id(raw_doc_id)

    safe_kind = (kind or "").strip().lower()
    if safe_kind not in {"answer", "notes"}:
        return (
            f"kind 参数无效：{kind!r}，仅支持 'answer' 或 'notes'。\n"
            f"示例：pdf_read_report('DOC_ID: {normalized}', kind='answer', offset=0, max_chars=6000)"
        )

    out_dir = Path(_PDF_EXTRACT_DIR) / normalized
    path = out_dir / ("answer.md" if safe_kind == "answer" else "notes.md")
    progress_path = out_dir / "report_read_state.json"
    if not path.exists():
        return (
            f"未找到落盘文件：{path.as_posix()}\n"
            f"请先运行 pdf_analyze_doc('DOC_ID: {normalized}', question) 生成产物。"
        )

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return f"读取失败：{path.as_posix()}：{exc}"

    total = len(text)

    def load_resume_state() -> tuple[int, bool]:
        if not progress_path.exists():
            return 0, False
        try:
            obj = json.loads(progress_path.read_text(encoding="utf-8"))
        except Exception:
            return 0, False
        if not isinstance(obj, dict):
            return 0, False
        by_kind = obj.get(safe_kind)
        if not isinstance(by_kind, dict):
            return 0, False
        v = by_kind.get("offset", 0)
        done = bool(by_kind.get("done", False))
        try:
            return int(v or 0), done
        except Exception:
            return 0, done

    def save_resume_offset(new_offset: int, *, done: bool) -> None:
        payload: dict[str, Any] = {}
        if progress_path.exists():
            try:
                payload = json.loads(progress_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload[safe_kind] = {
            "offset": int(new_offset),
            "done": bool(done),
            "total": int(total),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        progress_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    try:
        requested_offset = int(offset)
    except Exception:
        requested_offset = -1

    if requested_offset < 0:
        resume_offset, resume_done = load_resume_state()
        # 已经读完且用户没有显式指定 offset：返回空字符串，避免“继续”导致又从头开始。
        if resume_done and resume_offset >= total:
            return ""
        start = resume_offset
    else:
        start = requested_offset

    start = max(0, min(start, total))

    if max_chars is None:
        max_chars = 6000
    try:
        limit = int(max_chars)
    except Exception:
        limit = 6000

    if limit <= 0:
        chunk = text[start:]
        next_offset = total
    else:
        chunk = text[start : start + limit]
        next_offset = start + len(chunk)

    done = next_offset >= total
    save_resume_offset(next_offset, done=done)

    # 只返回“正文内容”，不输出额外状态信息（用户要在前端界面直接看到正文）。
    return chunk
