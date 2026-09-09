"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [mode, setMode] = useState("review");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  async function analyze() {
    if (!title.trim() || !content.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(`${API}/api/v1/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, content, mode, spoiler: false }),
      });
      if (!res.ok) throw new Error("API request failed");
      const data = await res.json();
      setResult(data.result);
    } catch (error) {
      setResult({ review: `Không thể kết nối API: ${error.message}` });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: 32, fontFamily: "Arial, sans-serif" }}>
      <header style={{ marginBottom: 28 }}>
        <p style={{ margin: 0, color: "#666" }}>AI CONTENT REVIEW</p>
        <h1 style={{ fontSize: 42, margin: "8px 0" }}>Đọc nội dung → Tóm tắt → Review</h1>
        <p style={{ color: "#555" }}>V1: nhập nội dung và tạo bản tóm tắt/review bằng bộ phân tích local.</p>
      </header>
      <section style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div>
          <label>Tiêu đề</label>
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Tên chương / video" style={input} />
          <label>Nội dung</label>
          <textarea value={content} onChange={e => setContent(e.target.value)} placeholder="Dán nội dung cần phân tích..." rows={18} style={textarea} />
          <label>Chế độ</label>
          <select value={mode} onChange={e => setMode(e.target.value)} style={input}>
            <option value="summary">Tóm tắt</option>
            <option value="review">Review</option>
            <option value="script">Kịch bản</option>
          </select>
          <button onClick={analyze} disabled={loading} style={button}>{loading ? "Đang phân tích..." : "Phân tích nội dung"}</button>
        </div>
        <div style={{ border: "1px solid #ddd", borderRadius: 12, padding: 24, minHeight: 500, background: "#fafafa" }}>
          <h2>Kết quả</h2>
          {result ? <>
            <h3>Tóm tắt</h3><p>{result.summary}</p>
            <h3>Review / Kịch bản</h3><pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit" }}>{result.review}</pre>
            <h3>Từ khóa</h3><p>{(result.keywords || []).join(", ")}</p>
          </> : <p style={{ color: "#777" }}>Kết quả sẽ xuất hiện tại đây.</p>}
        </div>
      </section>
    </main>
  );
}

const input = { width: "100%", boxSizing: "border-box", padding: 12, margin: "8px 0 18px", border: "1px solid #ccc", borderRadius: 8 };
const textarea = { ...input, resize: "vertical" };
const button = { padding: "12px 18px", border: 0, borderRadius: 8, cursor: "pointer" };
