# PDF Watermark Remover

[![CI](https://github.com/QVQZZH/pdf-watermark-remover/actions/workflows/ci.yml/badge.svg)](https://github.com/QVQZZH/pdf-watermark-remover/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white&style=flat-square)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-ready-009688?logo=fastapi&logoColor=white&style=flat-square)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](https://github.com/QVQZZH/pdf-watermark-remover/pulls)

[快速开始](#快速开始) · [功能](#功能) · [命令行](#命令行) · [API](#api) · [限制](#当前限制) · [路线图](#路线图) · [English](README.md) | **中文**

**面向文字版 PDF 的本地水印清理工具，用于移除水印、签名控件、印章式覆盖层和遮挡文字的视觉元素，同时尽量保留原始文本层和版式。**

PDF Watermark Remover 是一个本地优先的 PDF 水印清理工具，适合处理文字版业务文档、流水、表单和记录。它使用 `pypdf` 重写 PDF，清理常见电子签名结构，检测覆盖文字的图片或透明文字层，并提供命令行和 FastAPI 网页界面。

项目默认适配隐私敏感场景：文件在本地处理，仓库不包含真实 PDF 样本，生成结果也会被 Git 忽略。

## 示例文件

仓库内包含一组纯合成、可公开展示的示例，用于演示完整清理流程：

![PDF Watermark Remover 清理前后对比图](docs/examples/demo-comparison.png?raw=1)

- [清理前预览 PNG](docs/examples/demo-before.png)
- [清理后预览 PNG](docs/examples/demo-after.png)
- [带 demo 水印和签名控件的输入 PDF](docs/examples/demo-statement.pdf)
- [清理后的 PDF 输出](docs/examples/demo-statement-clean.pdf)
- [JSON 清理报告](docs/examples/demo-report.json)

示例报告会移除 1 个签名字段、1 个签名控件和 1 个透明文字水印，同时保留文本层：

```json
{
  "signature_fields_removed": 1,
  "signature_widgets_removed": 1,
  "transparent_text_blocks_removed": 1,
  "text_length_before": 581,
  "text_length_after": 566
}
```

重新生成示例文件：

```bash
python scripts/create_demo_examples.py
```

## 关键词

`PDF 签名清理` · `PDF 水印清理` · `文字版 PDF 清理` · `FastAPI PDF 工具` · `pypdf 签名控件移除` · `PDF AcroForm 签名字段清理` · `本地 PDF 处理`

## 功能

- 移除 PDF 签名 Widget 注释。
- 移除 AcroForm 签名字段和签名标记。
- 尽量保留页数、版式和可抽取文本层。
- 检测覆盖文字区域的图片 XObject，并默认移除检测到的图片遮挡。
- 检测低透明度文字水印和透明 Form XObject 水印。
- 可选择强力移除全部图片 XObject。
- 命令行支持手动指定白色遮盖矩形。
- 生成 JSON 报告，包含页面级检测结果、移除数量、警告和遮挡摘要。
- 浏览器界面支持上传分析、清理下载和遮挡图片预览。

## 使用场景

- 内部审核前清理文字版 PDF 流水或表单。
- 移除空白或可见的电子签名控件。
- 识别覆盖文字的图片章、水印、签名或透明文字层。
- 输出一份记录处理变化的 JSON 报告。
- 在本地完成 PDF 处理，不把文档发送到托管服务。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

启动网页应用：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## 命令行

清理 PDF 并生成 JSON 报告：

```bash
python -m app.pdf_tools input.pdf output/clean.pdf --report output/report.json
```

按 PDF 坐标手动添加白色遮盖区域：

```bash
python -m app.pdf_tools input.pdf output/clean.pdf --whiteout 50,680,170,772
```

强力移除全部图片 XObject：

```bash
python -m app.pdf_tools input.pdf output/clean.pdf --remove-images
```

保留自动检测到的图片或透明文字遮挡，仅清理签名结构：

```bash
python -m app.pdf_tools input.pdf output/clean.pdf --keep-detected-obstructions
```

## API

### 分析 PDF

```http
POST /api/analyze
Content-Type: multipart/form-data
```

表单字段：

```text
file=<PDF file>
```

返回 JSON `PdfReport`，包含页数、文本长度、签名字段数量、遮挡候选和摘要信息。

### 清理 PDF

```http
POST /api/clean
Content-Type: multipart/form-data
```

表单字段：

```text
file=<PDF file>
remove_detected_obstructions=true
remove_images=false
```

返回清理后的 PDF。响应头包含：

```text
X-Report-Id
X-Image-Xobjects-Removed
X-Transparent-Text-Blocks-Removed
X-Obstruction-Count
```

## 环境要求

- Python 3.10+
- `pypdf`
- `FastAPI`
- `uvicorn`
- `python-multipart`
- `Pillow` 用于网页分析里的图片预览生成

## 工作原理

```text
PDF 输入
  -> pypdf 读取页面、注释、AcroForm 字段、资源和内容流
  -> 移除签名 Widget 和签名字段
  -> 根据文本框检测疑似图片和透明文字遮挡
  -> 可从页面资源和内容操作中移除检测到的遮挡
  -> 可追加手动白色遮盖矩形
  -> 重写为新的 PDF
  -> 输出 JSON 报告记录变更、警告和页面级检测结果
```

## 项目结构

```text
app/
  main.py        FastAPI 应用和浏览器上传接口
  pdf_tools.py   PDF 分析、清理、报告和 CLI
web/
  index.html     浏览器界面
  script.js      上传、分析、清理和预览交互
  style.css      UI 样式
test/
  test_pdf_tools.py
```

## 当前限制

- 不支持加密 PDF。
- 不对扫描图片型 PDF 做 OCR。
- 移除图片可能同时移除 logo、扫描底图或其他有用图片。
- 自动遮挡检测是启发式规则，重要文档需要人工复核。
- 不修复损坏 PDF，也不绕过文档访问限制。

## 开发

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s test
python -m uvicorn app.main:app --reload
```

## 路线图

- 增加页面处理前后对比预览。
- 在浏览器中增加交互式框选白色遮盖区域。
- 增加批量处理和 ZIP 导出。
- 增加 Docker 打包。
- 增加更多透明文字和图片遮挡的合成测试样本。

## FAQ

### PDF Watermark Remover 会把文件上传到远程服务吗？

不会。应用在本地运行，上传文件只进入本地 FastAPI 进程，生成结果写入本地 `output/`。

### 扫描版 PDF 能处理吗？

可以重写扫描版 PDF，但不会做 OCR。效果最好的对象是带可抽取文本层的文字版 PDF。

### 能移除所有水印吗？

不能。PDF 水印实现方式很多。PDF Watermark Remover 主要处理签名结构、部分图片遮挡、低透明度文字和 Form XObject 水印。无法自动处理时可使用手动 whiteout 作为兜底。

### 会改动原文件吗？

不会。清理器写入新的输出文件，不会修改输入路径。重要文档仍建议保留备份。

## 许可证

MIT
