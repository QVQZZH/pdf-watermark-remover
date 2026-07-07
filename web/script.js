const fileInput = document.querySelector("#fileInput");
const dropzone = document.querySelector("#dropzone");
const analyzeBtn = document.querySelector("#analyzeBtn");
const cleanBtn = document.querySelector("#cleanBtn");
const removeImagesInput = document.querySelector("#removeImagesInput");
const log = document.querySelector("#log");
const previews = document.querySelector("#previews");

let selectedFile = null;

const setLog = (value) => {
  log.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
};

const setPreviews = (report) => {
  previews.replaceChildren();
  const previewMap = new Map();
  for (const page of report.page_reports ?? []) {
    for (const candidate of page.obstruction_candidates ?? []) {
      if (!candidate.preview_url || previewMap.has(candidate.preview_url)) {
        continue;
      }
      previewMap.set(candidate.preview_url, { ...candidate, page: page.page_index + 1 });
    }
  }
  const candidates = [...previewMap.values()];
  if (!candidates.length) {
    previews.hidden = true;
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const candidate of candidates.slice(0, 12)) {
    const item = document.createElement("figure");
    const image = document.createElement("img");
    const caption = document.createElement("figcaption");
    image.src = candidate.preview_url;
    image.alt = `第 ${candidate.page} 页遮挡图片`;
    caption.textContent = `第 ${candidate.page} 页 ${candidate.name}`;
    item.append(image, caption);
    fragment.append(item);
  }
  previews.append(fragment);
  previews.hidden = false;
};

const formatAnalysis = (report) => {
  const summary = report.obstruction_summary ?? {};
  const pages = (report.page_reports ?? []).filter((page) => {
    return (page.obstruction_candidates?.length ?? 0) > 0 || page.signature_widgets_removed > 0;
  });
  const lines = [
    summary.message ?? "分析完成。",
    "",
    `页数：${report.pages}`,
    `文本长度：${report.text_length_before}`,
    `电子签名字段：${summary.signature_field_count ?? report.signature_fields_before ?? 0}`,
    `签名控件：${summary.signature_widget_count ?? report.signature_widgets_removed ?? 0}`,
    `疑似图片遮挡：${summary.image_obstruction_count ?? 0}`,
    `透明文字水印：${summary.transparent_text_obstruction_count ?? 0}`,
    `涉及页数：${summary.pages_with_obstruction ?? pages.length}`,
  ];

  if (pages.length) {
    lines.push("", "检测明细：");
    for (const page of pages.slice(0, 30)) {
      const candidates = page.obstruction_candidates ?? [];
      const imageCount = candidates.filter((candidate) => candidate.kind === "image").length;
      const transparentTextCount = candidates.filter((candidate) => candidate.kind === "transparent_text").length;
      const boxes = candidates
        .slice(0, 6)
        .map((candidate) =>
          candidate.kind === "image"
            ? `${candidate.name} 坐标[${candidate.rect.join(", ")}] 重叠文字${candidate.overlap_text_chars}`
            : `${candidate.name} ${candidate.reason}`
        )
        .join("; ");
      lines.push(
        `第 ${page.page_index + 1} 页：签名控件 ${page.signature_widgets_removed}，图片遮挡 ${imageCount}，透明文字水印 ${transparentTextCount}${boxes ? `，${boxes}` : ""}`
      );
    }
    if (pages.length > 30) {
      lines.push(`还有 ${pages.length - 30} 页未展开。`);
    }
  }

  return lines.join("\n");
};

const setFile = (file) => {
  selectedFile = file;
  previews.hidden = true;
  previews.replaceChildren();
  setLog(file ? `已选择：${file.name}\n大小：${(file.size / 1024).toFixed(1)} KB` : "等待选择文件。");
};

fileInput.addEventListener("change", () => setFile(fileInput.files?.[0] ?? null));

for (const eventName of ["dragenter", "dragover"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragover");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragover");
  });
}

dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer?.files?.[0];
  if (file) setFile(file);
});

const requestPdf = async (endpoint) => {
  if (!selectedFile) {
    setLog("请先选择 PDF 文件。");
    return null;
  }
  const formData = new FormData();
  formData.append("file", selectedFile);
  if (endpoint === "/api/clean") {
    formData.append("remove_detected_obstructions", "true");
    formData.append("remove_images", removeImagesInput.checked ? "true" : "false");
  }
  const response = await fetch(endpoint, { method: "POST", body: formData });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response;
};

analyzeBtn.addEventListener("click", async () => {
  try {
    analyzeBtn.disabled = true;
    setLog("正在分析...");
    const response = await requestPdf("/api/analyze");
    if (!response) return;
    const report = await response.json();
    setLog(formatAnalysis(report));
    setPreviews(report);
  } catch (error) {
    setLog(`分析失败：${error.message}`);
  } finally {
    analyzeBtn.disabled = false;
  }
});

cleanBtn.addEventListener("click", async () => {
  try {
    cleanBtn.disabled = true;
    setLog("正在清理并生成下载...");
    const response = await requestPdf("/api/clean");
    if (!response) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = selectedFile.name.replace(/\\.pdf$/i, "_clean.pdf");
    link.click();
    URL.revokeObjectURL(url);
    setLog(
      `处理完成。\n报告 ID：${response.headers.get("X-Report-Id") ?? "已生成"}\n移除图片对象：${response.headers.get("X-Image-Xobjects-Removed") ?? "0"}\n移除透明文字水印：${response.headers.get("X-Transparent-Text-Blocks-Removed") ?? "0"}`
    );
  } catch (error) {
    setLog(`清理失败：${error.message}`);
  } finally {
    cleanBtn.disabled = false;
  }
});
