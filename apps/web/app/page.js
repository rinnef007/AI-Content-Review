"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState("review");
  const [spoiler, setSpoiler] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function analyze() {
    if (!title.trim() && !file && !content.trim()) return;
    setLoading(true);
    setResult(null);
    setError("");
    try {
      let res;
      if (file) {
        const form = new FormData();
        form.append("file", file);
        form.append("title", title.trim() || file.name);
        form.append("mode", mode);
        form.append("spoiler", String(spoiler));
        res = await fetch(`${API}/api/v1/analyze/upload`, { method: "POST", body: form });
      } else {
        res = await fetch(`${API}/api/v1/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, content, mode, spoiler }),
        });
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "API request failed");
      setResult(data.result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <p style={styles.eyebrow}>AI CONTENT REVIEW</p>
        <h1 style={styles.h1}>Đọc nội dung → OCR → Phân tích → Review</h1>
        <p style={styles.subtitle}>Tải PDF/ảnh hoặc dán văn bản. V1 hỗ trợ OCR tiếng Việt + English và tạo tóm tắt, review hoặc kịch bản.</p>
      </header>
      <section style={styles.grid}>
        <div style={styles.card}>
          <label style={styles.label}>Tiêu đề</label>
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Tên chương / video / tài liệu" style={styles.input} />
          <label style={styles.label}>File PDF / ảnh</label>
          <input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tiff" onChange={e => setFile(e.target.files?.[0] || null)} style={styles.input} />
          {file && <p style={styles.file}>Đã chọn: {file.name}</p>}
          <label style={styles.label}>Hoặc nhập văn bản</label>
          <textarea value={content} onChange={e => setContent(e.target.value)} placeholder="Dán nội dung cần phân tích..." rows={10} style={styles.textarea} />
          <label style={styles.label}>Chế độ</label>
          <select value={mode} onChange={e => setMode(e.target.value)} style={styles.input}>
            <option value="summary">Tóm tắt</option>
            <option value="review">Review</option>
            <option value="script">Kịch bản</option>
          </select>
          <label style={styles.check}><input type="checkbox" checked={spoiler} onChange={e => setSpoiler(e.target.checked)} /> Cho phép spoiler</label>
          <button onClick={analyze} disabled={loading} style={styles.button}>{loading ? "Đang xử lý..." : file ? "OCR & phân tích" : "Phân tích nội dung"}</button>
          {error && <div style={styles.error}>{error}</div>}
        </div>
        <div style={styles.resultCard}>
          <h2 style={styles.h2}>Kết quả</h2>
          {!result && <p style={styles.muted}>Kết quả OCR và phân tích sẽ xuất hiện tại đây.</p>}
          {result && <>
            <div style={styles.meta}>
              <span>Provider: {result.provider || "local"}</span>
              {result.source && <span>Nguồn: {result.source.type}{result.source.pages ? ` · ${result.source.pages} trang` : ""}</span>}
              {result.source?.ocr_used && <span>OCR: đã dùng</span>}
            </div>
            <h3>Tóm tắt</h3><p>{result.summary}</p>
            <h3>Review / Kịch bản</h3><pre style={styles.pre}>{result.review}</pre>
            <h3>Từ khóa</h3><p>{(result.keywords || []).join(", ") || "Chưa xác định"}</p>
            {result.stats && <p style={styles.muted}>Thống kê: {result.stats.words} từ · {result.stats.sentences} câu</p>}
            {result.extracted_text && <details style={styles.details}><summary>Xem văn bản OCR đã trích xuất</summary><pre style={styles.ocr}>{result.extracted_text}</pre></details>}
          </>}
        </div>
      </section>
    </main>
  );
}

const styles = {
  page: { maxWidth: 1180, margin: "0 auto", padding: 32, fontFamily: "Arial, sans-serif", color: "#171717" },
  header: { marginBottom: 28 },
  eyebrow: { margin: 0, fontSize: 13, fontWeight: 700, letterSpacing: 2, color: "#666" },
  h1: { fontSize: 40, lineHeight: 1.1, margin: "8px 0 12px" },
  subtitle: { color: "#555", maxWidth: 850 },
  grid: { display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 24 },
  card: { border: "1px solid #ddd", borderRadius: 14, padding: 24, background: "#fff" },
  resultCard: { border: "1px solid #ddd", borderRadius: 14, padding: 24, minHeight: 520, background: "#fafafa" },
  h2: { marginTop: 0 },
  label: { display: "block", fontWeight: 600, marginTop: 8 },
  input: { width: "100%", boxSizing: "border-box", padding: 12, margin: "8px 0 18px", border: "1px solid #ccc", borderRadius: 8, background: "#fff" },
  textarea: { width: "100%", boxSizing: "border-box", padding: 12, margin: "8px 0 18px", border: "1px solid #ccc", borderRadius: 8, resize: "vertical", fontFamily: "inherit" },
  file: { margin: "-10px 0 16px", color: "#555", fontSize: 13 },
  check: { display: "flex", gap: 8, alignItems: "center", margin: "4px 0 18px", color: "#444" },
  button: { padding: "12px 18px", border: 0, borderRadius: 8, cursor: "pointer", fontWeight: 700 },
  error: { marginTop: 16, padding: 12, borderRadius: 8, background: "#fff0f0", color: "#a00" },
  muted: { color: "#777" },
  meta: { display: "flex", flexWrap: "wrap", gap: 8, fontSize: 13, color: "#666", marginBottom: 20 },
  pre: { whiteSpace: "pre-wrap", fontFamily: "inherit", lineHeight: 1.5 },
  details: { marginTop: 24 },
  ocr: { whiteSpace: "pre-wrap", maxHeight: 360, overflow: "auto", background: "#fff", padding: 12, borderRadius: 8, fontSize: 13 },
};
