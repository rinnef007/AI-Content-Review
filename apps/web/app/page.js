"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [project, setProject] = useState(null);
  const [relationships, setRelationships] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [episodeTitle, setEpisodeTitle] = useState("");
  const [episodeContent, setEpisodeContent] = useState("");
  const [tab, setTab] = useState("overview");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function request(path, options = {}) {
    const res = await fetch(`${API}${path}`, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "API request failed");
    return data;
  }

  async function loadProjects() {
    try {
      const data = await request("/api/v1/projects");
      setProjects(data);
      if (!projectId && data[0]) setProjectId(data[0].id);
    } catch (err) { setError(err.message); }
  }

  async function loadProject(id = projectId) {
    if (!id) return;
    try {
      const [data, rels, time] = await Promise.all([
        request(`/api/v1/projects/${id}`),
        request(`/api/v1/projects/${id}/relationships`),
        request(`/api/v1/projects/${id}/timeline`),
      ]);
      setProject(data); setRelationships(rels); setTimeline(time);
    } catch (err) { setError(err.message); }
  }

  useEffect(() => { loadProjects(); }, []);
  useEffect(() => { loadProject(); }, [projectId]);

  async function createProject() {
    if (!name.trim()) return;
    setLoading(true); setError("");
    try {
      const created = await request("/api/v1/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description }) });
      setName(""); setDescription(""); setProjectId(created.id); await loadProjects(); await loadProject(created.id); setMessage("Đã tạo project.");
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }

  async function createEpisode() {
    if (!projectId || !episodeTitle.trim()) return;
    setLoading(true); setError("");
    try {
      await request(`/api/v1/projects/${projectId}/episodes`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: episodeTitle, content: episodeContent, source_type: "text" }) });
      setEpisodeTitle(""); setEpisodeContent(""); await loadProject(); setMessage("Đã tạo episode.");
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }

  async function analyzeEpisode(id) {
    setLoading(true); setError("");
    try {
      const data = await request(`/api/v1/projects/${projectId}/episodes/${id}/analyze`, { method: "POST" });
      await loadProject(); setTab("characters"); setMessage(`Đã phân tích: ${data.persisted.characters_created || 0} nhân vật mới, ${data.persisted.events_created || 0} sự kiện, ${data.persisted.relationships_created || 0} quan hệ.`);
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }

  const characters = project?.characters || [];
  const events = project?.events || [];
  const episodes = project?.episodes || [];
  const tabs = [["overview","Tổng quan"],["episodes","Episodes"],["characters","Nhân vật"],["events","Sự kiện"],["relationships","Quan hệ"],["timeline","Timeline"]];

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <div><p style={styles.eyebrow}>AI CONTENT REVIEW</p><h1 style={styles.h1}>Project Knowledge</h1><p style={styles.subtitle}>Quản lý project, episode và knowledge nhân vật/sự kiện sau phân tích AI.</p></div>
        <button onClick={() => loadProject()} style={styles.refresh}>↻ Làm mới</button>
      </header>

      <section style={styles.topGrid}>
        <div style={styles.card}><label style={styles.label}>Project</label><select value={projectId} onChange={e => setProjectId(e.target.value)} style={styles.input}><option value="">Chọn project</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
        <div style={styles.card}><strong>{project?.name || "Chưa chọn project"}</strong><p style={styles.muted}>{project?.description || "Tạo project để bắt đầu quản lý series."}</p><div style={styles.stats}><span>{episodes.length} Episodes</span><span>{characters.length} Characters</span><span>{events.length} Events</span><span>{relationships.length} Relations</span></div></div>
      </section>

      <section style={styles.tabs}>{tabs.map(([key, label]) => <button key={key} onClick={() => setTab(key)} style={tab === key ? styles.activeTab : styles.tab}>{label}</button>)}</section>
      {message && <div style={styles.success}>{message}</div>}
      {error && <div style={styles.error}>{error}</div>}

      {tab === "overview" && <section style={styles.grid}>
        <div style={styles.card}><h2>Tạo project</h2><input value={name} onChange={e => setName(e.target.value)} placeholder="Tên bộ truyện / series / nội dung" style={styles.input}/><textarea value={description} onChange={e => setDescription(e.target.value)} placeholder="Mô tả" rows={4} style={styles.textarea}/><button disabled={loading} onClick={createProject} style={styles.button}>Tạo project</button></div>
        <div style={styles.card}><h2>Thêm episode</h2><input value={episodeTitle} onChange={e => setEpisodeTitle(e.target.value)} placeholder="Tên chương / tập" style={styles.input}/><textarea value={episodeContent} onChange={e => setEpisodeContent(e.target.value)} placeholder="Nội dung episode để AI phân tích..." rows={7} style={styles.textarea}/><button disabled={loading || !projectId} onClick={createEpisode} style={styles.button}>Thêm episode</button></div>
      </section>}

      {tab === "episodes" && <section style={styles.card}><h2>Episodes</h2>{!episodes.length ? <p style={styles.muted}>Chưa có episode.</p> : episodes.map((e, i) => <div key={e.id} style={styles.row}><div><strong>#{i + 1} · {e.title}</strong><p style={styles.muted}>{e.source_type}</p></div><button onClick={() => analyzeEpisode(e.id)} disabled={loading} style={styles.smallButton}>Phân tích AI</button></div>)}</section>}

      {tab === "characters" && <section style={styles.card}><h2>Characters</h2>{!characters.length ? <p style={styles.muted}>Chưa có nhân vật. Hãy phân tích episode.</p> : <div style={styles.list}>{characters.map(c => <div key={c.id} style={styles.knowledge}><strong>{c.name}</strong><span>{c.role || "Chưa xác định vai trò"}</span>{c.aliases?.length > 0 && <small>Alias: {c.aliases.join(", ")}</small>}</div>)}</div>}</section>}

      {tab === "events" && <section style={styles.card}><h2>Events</h2>{!events.length ? <p style={styles.muted}>Chưa có sự kiện.</p> : <div style={styles.list}>{events.map(e => <div key={e.id} style={styles.knowledge}><strong>{e.title}</strong><span>Episode: {episodes.find(x => x.id === e.episode_id)?.title || "Không xác định"}</span>{e.evidence && <small>Evidence: {e.evidence}</small>}</div>)}</div>}</section>}

      {tab === "relationships" && <section style={styles.card}><h2>Character Relationships</h2>{!relationships.length ? <p style={styles.muted}>Chưa có quan hệ. Hãy phân tích episode bằng AI.</p> : <div style={styles.list}>{relationships.map(r => <div key={r.id} style={styles.knowledge}><strong>{r.from} → {r.to}</strong><span>{r.relation}</span>{r.evidence && <small>Evidence: {r.evidence}</small>}</div>)}</div>}</section>}

      {tab === "timeline" && <section style={styles.card}><h2>Series Timeline</h2>{!timeline.length ? <p style={styles.muted}>Chưa có timeline.</p> : <div style={styles.timeline}>{timeline.map((item, index) => <div key={item.episode_id} style={styles.timelineItem}><div style={styles.timelineMarker}>{index + 1}</div><div><strong>{item.episode_title}</strong>{!item.events?.length ? <p style={styles.muted}>Chưa có event.</p> : item.events.map(event => <div key={event.id} style={styles.eventLine}><b>{event.title}</b>{event.characters?.length > 0 && <span> · {event.characters.join(", ")}</span>}{event.evidence && <small>{event.evidence}</small>}</div>)}</div></div>)}</div>}</section>}

      <footer style={styles.footer}>API: {API} · Knowledge Base · PostgreSQL</footer>
    </main>
  );
}

const styles = {
  page: { maxWidth: 1240, margin: "0 auto", padding: 32, fontFamily: "Arial, sans-serif", color: "#171717" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24 },
  eyebrow: { margin: 0, fontSize: 12, fontWeight: 700, letterSpacing: 2, color: "#666" },
  h1: { fontSize: 38, margin: "8px 0" },
  subtitle: { color: "#666", margin: 0 },
  topGrid: { display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr)", gap: 16, marginBottom: 18 },
  grid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 },
  card: { border: "1px solid #ddd", borderRadius: 14, padding: 22, background: "#fff" },
  tabs: { display: "flex", flexWrap: "wrap", gap: 8, margin: "18px 0", borderBottom: "1px solid #ddd", paddingBottom: 8 },
  tab: { border: 0, background: "transparent", padding: "10px 14px", cursor: "pointer", color: "#666" },
  activeTab: { border: 0, borderBottom: "2px solid #111", background: "transparent", padding: "10px 14px", cursor: "pointer", fontWeight: 700 },
  label: { display: "block", fontWeight: 700, marginBottom: 8 },
  input: { width: "100%", boxSizing: "border-box", padding: 12, border: "1px solid #ccc", borderRadius: 8, background: "#fff", marginBottom: 12 },
  textarea: { width: "100%", boxSizing: "border-box", padding: 12, border: "1px solid #ccc", borderRadius: 8, resize: "vertical", fontFamily: "inherit", marginBottom: 12 },
  button: { padding: "11px 16px", border: 0, borderRadius: 8, cursor: "pointer", fontWeight: 700 },
  smallButton: { padding: "9px 12px", border: "1px solid #ccc", borderRadius: 8, background: "#fff", cursor: "pointer" },
  refresh: { padding: "9px 12px", border: "1px solid #ccc", borderRadius: 8, background: "#fff", cursor: "pointer" },
  stats: { display: "flex", flexWrap: "wrap", gap: 18, color: "#555", fontSize: 14 },
  row: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 0", borderBottom: "1px solid #eee" },
  list: { display: "grid", gap: 10 },
  knowledge: { display: "grid", gap: 5, padding: 15, border: "1px solid #eee", borderRadius: 10, background: "#fafafa" },
  timeline: { display: "grid", gap: 20 },
  timelineItem: { display: "grid", gridTemplateColumns: "36px 1fr", gap: 14, paddingBottom: 18, borderBottom: "1px solid #eee" },
  timelineMarker: { width: 32, height: 32, borderRadius: 16, display: "grid", placeItems: "center", background: "#eee", fontWeight: 700 },
  eventLine: { marginTop: 9, padding: 10, borderLeft: "3px solid #ddd", background: "#fafafa" },
  muted: { color: "#777" },
  success: { padding: 12, borderRadius: 8, background: "#eef8f0", marginBottom: 16 },
  error: { padding: 12, borderRadius: 8, background: "#fff0f0", color: "#a00", marginBottom: 16 },
  footer: { marginTop: 30, color: "#999", fontSize: 12 },
};
