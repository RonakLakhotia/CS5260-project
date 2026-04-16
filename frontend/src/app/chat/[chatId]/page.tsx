"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Markdown from "react-markdown";
import { apiFetch } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Msg { role: "user" | "assistant"; content: string; sources?: Src[]; webSources?: WebSrc[]; }
interface Src { text: string; start_time: number; end_time: number; }
interface WebSrc { title: string; url: string; snippet: string; }


function SourcesDropdown({ sources, onSeek }: { sources: Src[]; onSeek: (t: number) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 6, paddingLeft: 28 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          fontSize: 12, color: "#52525b", background: "none", border: "none",
          cursor: "pointer", padding: 0,
        }}
      >
        <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5"/>
        </svg>
        Video references ({sources.length})
      </button>
      {open && (
        <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 6 }}>
          {sources.map((s, i) => {
            const startM = Math.floor(s.start_time / 60);
            const startS = Math.floor(s.start_time % 60);
            const endM = Math.floor(s.end_time / 60);
            const endS = Math.floor(s.end_time % 60);
            const label = `${startM}:${String(startS).padStart(2,"0")} - ${endM}:${String(endS).padStart(2,"0")}`;
            return (
              <div key={i} style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, padding: "8px 10px", fontSize: 12 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ color: "#71717a", fontWeight: 500 }}>{label}</span>
                  <button
                    onClick={() => onSeek(Math.floor(s.start_time))}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "#60a5fa", fontSize: 11, padding: 0, display: "flex", alignItems: "center", gap: 3 }}
                  >
                    <svg width="10" height="10" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                    Play
                  </button>
                </div>
                <div style={{ color: "#a1a1aa", lineHeight: 1.5 }}>{s.text}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WebSourcesDropdown({ sources }: { sources: WebSrc[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 6, paddingLeft: 28 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          fontSize: 12, color: "#52525b", background: "none", border: "none",
          cursor: "pointer", padding: 0,
        }}
      >
        <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5"/>
        </svg>
        Web sources ({sources.length})
      </button>
      {open && (
        <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 6 }}>
          {sources.map((s, i) => (
            <a key={i} href={s.url} target="_blank" rel="noopener noreferrer"
              style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, padding: "8px 10px", textDecoration: "none", display: "block" }}>
              <div style={{ fontSize: 12, color: "#60a5fa", marginBottom: 2, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</div>
              <div style={{ fontSize: 10, color: "#52525b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.url}</div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatPage() {
  const { chatId } = useParams() as { chatId: string };
  const videoId = useSearchParams().get("video_id") || "";

  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState("");
  const [err, setErr] = useState("");
  const [webSearch, setWebSearch] = useState(false);

  const [ssState, setSsState] = useState<"idle"|"processing"|"complete"|"error">("idle");
  const [ssJob, setSsJob] = useState("");
  const [ssProg, setSsProg] = useState("");
  const [ssUrl, setSsUrl] = useState("");
  const [ssSteps, setSsSteps] = useState<string[]>([]);
  const [ssDropdown, setSsDropdown] = useState(false);
  const [ssOverlay, setSsOverlay] = useState(false);
  const ytRef = useRef<HTMLIFrameElement>(null);

  const bottom = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, status]);
  useEffect(() => { taRef.current?.focus(); }, []);

  useEffect(() => {
    if (!chatId) return;
    apiFetch(`${API}/api/chat/sessions/${chatId}/messages`).then(r=>r.json()).then(d => {
      if (Array.isArray(d) && d.length) setMsgs(d.map((m:{role:string;content:string}) => ({ role: m.role as "user"|"assistant", content: m.content })));
    }).catch(()=>{});
  }, [chatId]);

  // Restore slideshow state - ask backend for video info (works across browsers)
  useEffect(() => {
    if (!videoId || ssState !== "idle") return;

    // Restore saved steps from sessionStorage
    const savedSteps = sessionStorage.getItem(`slideshow_steps_${videoId}`);
    if (savedSteps) { try { setSsSteps(JSON.parse(savedSteps)); } catch {} }

    // Ask backend for authoritative video status
    apiFetch(`${API}/api/videos/${videoId}`).then(r => r.ok ? r.json() : null).then(d => {
      if (!d) return;

      if (d.has_slideshow) {
        // Slideshow exists on disk
        setSsState("complete");
        setSsUrl(`${API}${d.slideshow_url}`);
      } else if (d.pipeline_status === "processing") {
        // Pipeline is running - start polling
        setSsJob(d.pipeline_job_id);
        setSsState("processing");
        setSsProg(d.pipeline_progress || "Generating...");
      } else if (d.pipeline_status === "error") {
        setSsState("error");
      } else if (d.pipeline_job_id) {
        // Job exists but backend restarted (status unknown) - try polling anyway
        setSsJob(d.pipeline_job_id);
        setSsState("processing");
      }
      // else: no pipeline started yet, stay idle
    }).catch(() => {});
  }, [videoId, ssState]);

  // Poll slideshow status
  useEffect(() => {
    if (!ssJob || ssState !== "processing") return;
    const iv = setInterval(async () => {
      try {
        const r = await apiFetch(`${API}/api/status/${ssJob}`);
        if (!r.ok) return;
        const d = await r.json();
        const prog = d.progress as string;
        setSsProg(prog);
        setSsSteps(prev => {
          const updated = (prev.length === 0 || prev[prev.length - 1] !== prog) ? [...prev, prog] : prev;
          sessionStorage.setItem(`slideshow_steps_${videoId}`, JSON.stringify(updated));
          return updated;
        });
        if (d.status === "complete") { setSsState("complete"); setSsUrl(`${API}/api/slideshow/video/${videoId}`); clearInterval(iv); }
        else if (d.status === "error") { setSsState("error"); clearInterval(iv); }
      } catch {}
    }, 5000);
    return () => clearInterval(iv);
  }, [ssJob, ssState, videoId]);

  const send = useCallback(async () => {
    const q = input.trim();
    if (!q || streaming) return;
    setInput(""); setErr(""); setStreaming(true);
    setStatus(webSearch ? "searching_web" : "searching_transcript");
    if (taRef.current) taRef.current.style.height = "20px";
    setMsgs(p => [...p, { role: "user", content: q }, { role: "assistant", content: "" }]);
    try {
      const res = await apiFetch(`${API}/api/chat/sessions/${chatId}/messages`, {
        method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ question: q, web_search: webSearch }),
      });
      if (!res.ok) throw 0;
      const rdr = res.body!.getReader(), dec = new TextDecoder();
      let buf = "", ev = "", srcs: Src[] = [], webSrcs: WebSrc[] = [];
      while (true) {
        const { done, value } = await rdr.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n"); buf = lines.pop()!;
        for (const l of lines) {
          if (l.startsWith("event: ")) ev = l.slice(7).trim();
          else if (l.startsWith("data: ") && ev) {
            try {
              const d = JSON.parse(l.slice(6));
              if (ev==="status") setStatus(d.step);
              else if (ev==="sources") srcs = d.chunks||[];
              else if (ev==="web_sources") webSrcs = d.results||[];
              else if (ev==="token") setMsgs(p => { const u=[...p],last=u[u.length-1]; if(last?.role==="assistant") u[u.length-1]={...last,content:last.content+d.text}; return u; });
              else if (ev==="done") { setMsgs(p => { const u=[...p],last=u[u.length-1]; if(last?.role==="assistant") u[u.length-1]={...last,sources:srcs,webSources:webSrcs}; return u; }); setStreaming(false); setStatus(""); }
              else if (ev==="error") { setErr(d.message||"Error"); setStreaming(false); setStatus(""); }
            } catch{}
            ev = "";
          }
        }
      }
    } catch {
      setErr("Failed to get response."); setStreaming(false); setStatus("");
      setMsgs(p => (p.at(-1)?.role==="assistant"&&!p.at(-1)?.content) ? p.slice(0,-1) : p);
    }
  }, [input, streaming, chatId, webSearch]);

  const onKey = (e: React.KeyboardEvent) => { if (e.key==="Enter"&&!e.shiftKey) { e.preventDefault(); send(); } };
  const stLabel = status==="searching_transcript"?"Searching transcript...":status==="searching_web"?"Searching the web...":status==="reviewing_history"?"Reviewing history...":status==="generating"?"Thinking...":"";
  const empty = msgs.length === 0 && !streaming;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: "#09090b", color: "#e4e4e7" }}>

      {/* Slideshow overlay */}
      {ssOverlay && ssUrl && (
        <div
          onClick={() => setSsOverlay(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 100,
            background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div onClick={e => e.stopPropagation()} style={{
            background: "#18181b", border: "1px solid #27272a", borderRadius: 16,
            padding: 16, width: 340, boxShadow: "0 24px 48px rgba(0,0,0,0.6)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "#e4e4e7" }}>Infographic Slideshow</span>
              <button onClick={() => setSsOverlay(false)}
                style={{ background: "#27272a", border: "none", color: "#a1a1aa", cursor: "pointer", width: 24, height: 24, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>
                &times;
              </button>
            </div>
            <div style={{ borderRadius: 10, overflow: "hidden", background: "#000" }}>
              <video
                controls
                autoPlay
                src={ssUrl}
                style={{ width: "100%", display: "block", borderRadius: 10 }}
              />
            </div>
            <p style={{ fontSize: 11, color: "#52525b", textAlign: "center", marginTop: 10 }}>
              6 infographic slides - 5s each
            </p>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ height: 52, borderBottom: "1px solid #27272a", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px", flexShrink: 0 }}>
        <a href="/" style={{ color: "#52525b", textDecoration: "none", fontSize: 13, display: "flex", alignItems: "center", gap: 5 }}>
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
          New chat
        </a>
        <a href="/" style={{ display: "flex", alignItems: "center", gap: 7, textDecoration: "none", color: "white" }}>
          <span style={{ fontSize: 15, fontWeight: 600 }}>YT<span style={{ color: "#60a5fa" }}>Sage</span></span>
          <div style={{ width: 24, height: 24, borderRadius: 6, background: "#2563eb", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="12" height="12" fill="white" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
          </div>
        </a>
      </div>

      {/* Video - sticky below header */}
      {videoId && (
        <div style={{ position: "relative", flexShrink: 0 }}>
          <div style={{ background: "#09090b", padding: "12px 0 20px" }}>
            <div style={{ display: "flex", justifyContent: "center" }}>
              <div style={{ borderRadius: 10, overflow: "hidden", background: "#000", width: 300, maxWidth: "90%", boxShadow: "0 4px 24px rgba(0,0,0,0.4)" }}>
                <div style={{ position: "relative", paddingBottom: "56.25%", height: 0 }}>
                  <iframe
                    ref={ytRef}
                    src={`https://www.youtube.com/embed/${videoId}?enablejsapi=1`}
                    title="YouTube video"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
                    style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%" }}
                  />
                </div>
              </div>
            </div>
          </div>
          {/* Fade out into chat */}
          <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 20, background: "linear-gradient(to bottom, transparent, #09090b)", pointerEvents: "none" }} />
        </div>
      )}

      {/* Chat area - scrollable */}
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        <div style={{ maxWidth: 720, margin: "0 auto", padding: "16px 16px 0" }}>

          {/* Empty state suggestions */}
          {empty && (
            <div style={{ textAlign: "center", paddingBottom: 16 }}>
              <p style={{ color: "#71717a", fontSize: 14, marginBottom: 12 }}>What would you like to know about this video?</p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
                {["Summarize the key points", "What are the main topics?", "Explain the most important idea"].map(q => (
                  <button key={q} onClick={() => { setInput(q); taRef.current?.focus(); }}
                    style={{ fontSize: 12, color: "#71717a", border: "1px solid #27272a", borderRadius: 999, padding: "6px 14px", background: "transparent", cursor: "pointer" }}
                    onMouseEnter={e => { (e.target as HTMLElement).style.borderColor = "#52525b"; (e.target as HTMLElement).style.color = "#d4d4d8"; }}
                    onMouseLeave={e => { (e.target as HTMLElement).style.borderColor = "#27272a"; (e.target as HTMLElement).style.color = "#71717a"; }}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          {!empty && (
            <div style={{ paddingBottom: 8 }}>
              {msgs.map((m, i) => (
                <div key={i} style={{ marginBottom: 16 }}>
                  {m.role === "user" ? (
                    /* User - right aligned bubble */
                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                      <div style={{
                        background: "#27272a", borderRadius: "18px 18px 4px 18px",
                        padding: "10px 16px", maxWidth: "75%",
                        fontSize: 14, lineHeight: 1.7, color: "#e4e4e7",
                      }}>
                        {m.content}
                      </div>
                    </div>
                  ) : (
                    /* Assistant - left aligned */
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                        <div style={{ width: 22, height: 22, borderRadius: "50%", background: "#2563eb", display: "flex", alignItems: "center", justifyContent: "center" }}>
                          <svg width="10" height="10" fill="white" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#71717a" }}>YTSage</span>
                      </div>
                      <div style={{ paddingLeft: 28 }} className="chat-md">
                        <Markdown>{m.content}</Markdown>
                        {i === msgs.length - 1 && streaming && status === "generating" && (
                          <span style={{ display: "inline-block", width: 2, height: 16, background: "#60a5fa", marginLeft: 2, marginBottom: -3, borderRadius: 1, animation: "pulse 1s infinite" }}/>
                        )}
                      </div>
                      {m.sources && m.sources.length > 0 && (
                        <SourcesDropdown sources={m.sources.slice(0, 3)} onSeek={t => {
                          if (ytRef.current) {
                            ytRef.current.contentWindow?.postMessage(JSON.stringify({
                              event: "command", func: "seekTo", args: [t, true]
                            }), "*");
                            ytRef.current.contentWindow?.postMessage(JSON.stringify({
                              event: "command", func: "playVideo", args: []
                            }), "*");
                          }
                        }} />
                      )}
                      {m.webSources && m.webSources.length > 0 && (
                        <WebSourcesDropdown sources={m.webSources} />
                      )}
                    </div>
                  )}
                </div>
              ))}

              {streaming && stLabel && status !== "generating" && (
                <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 28, marginBottom: 12 }}>
                  <span style={{ fontSize: 12, color: "#52525b" }}>{stLabel}</span>
                </div>
              )}

              {err && <p style={{ fontSize: 13, color: "#f87171", paddingLeft: 28 }}>{err}</p>}
            </div>
          )}

          <div ref={bottom}/>
        </div>
      </div>

      {/* Infographic banner + Input bar - always at bottom */}
      <div style={{ flexShrink: 0 }}>

        {/* Infographic status - floating banner */}
        {(ssState === "processing" || ssState === "complete" || ssState === "error") && (
          <div style={{ display: "flex", justifyContent: "center", padding: "8px 12px" }}>
            {ssState === "processing" && (
              <div style={{ position: "relative" }}>
                <button onClick={() => setSsDropdown(o => !o)}
                  style={{
                    background: "#14141f", border: "1px solid #1e1e3a", borderRadius: 999,
                    padding: "8px 16px", cursor: "pointer",
                    display: "flex", alignItems: "center", gap: 8,
                    boxShadow: "0 2px 12px rgba(37,99,235,0.08)",
                  }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#3b82f6", animation: "pulse 2s infinite", flexShrink: 0 }}/>
                  <span style={{ fontSize: 12, color: "#a1a1aa" }}>{ssProg || "Generating infographics..."}</span>
                  <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="#52525b" strokeWidth={2} style={{ transform: ssDropdown ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5"/>
                  </svg>
                </button>
                {ssDropdown && (
                  <div style={{
                    position: "absolute", bottom: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)",
                    background: "#141418", border: "1px solid #27272a", borderRadius: 12,
                    padding: "10px 14px", minWidth: 240, zIndex: 50,
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                  }}>
                    <div style={{ fontSize: 10, color: "#3f3f46", marginBottom: 8, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>Pipeline</div>
                    {ssSteps.map((step, i) => {
                      const isLast = i === ssSteps.length - 1;
                      return (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: i < ssSteps.length - 1 ? 5 : 0 }}>
                          {isLast
                            ? <span style={{ width: 12, height: 12, borderRadius: "50%", border: "2px solid #3b82f6", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                <span style={{ width: 4, height: 4, borderRadius: "50%", background: "#3b82f6" }}/>
                              </span>
                            : <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#22c55e", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                <svg width="7" height="7" fill="none" viewBox="0 0 24 24" stroke="white" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5"/></svg>
                              </span>
                          }
                          <span style={{ fontSize: 12, color: isLast ? "#d4d4d8" : "#71717a" }}>{step}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {ssState === "complete" && (
              <button onClick={() => setSsOverlay(true)}
                style={{
                  background: "#0f1f15", border: "1px solid #14532d", borderRadius: 999,
                  padding: "8px 16px", cursor: "pointer",
                  display: "flex", alignItems: "center", gap: 8,
                  boxShadow: "0 2px 12px rgba(34,197,94,0.08)",
                }}>
                <svg width="12" height="12" fill="#34d399" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                <span style={{ fontSize: 12, color: "#34d399" }}>Infographic slideshow ready</span>
              </button>
            )}

            {ssState === "error" && (
              <div style={{
                background: "#1a0f0f", border: "1px solid #7f1d1d", borderRadius: 999,
                padding: "8px 16px",
                display: "flex", alignItems: "center", gap: 8,
              }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#ef4444", flexShrink: 0 }}/>
                <span style={{ fontSize: 12, color: "#f87171" }}>Infographic generation failed</span>
              </div>
            )}
          </div>
        )}

        {/* Input bar */}
        <div style={{ borderTop: "1px solid #27272a", padding: 12 }}>
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          {/* Web search toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
            <button
              onClick={() => setWebSearch(w => !w)}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                background: webSearch ? "#1e3a5f" : "transparent",
                border: webSearch ? "1px solid #2563eb" : "1px solid #27272a",
                borderRadius: 999, padding: "4px 10px", cursor: "pointer",
                transition: "all 0.15s",
              }}>
              <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke={webSearch ? "#60a5fa" : "#52525b"} strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418"/>
              </svg>
              <span style={{ fontSize: 11, color: webSearch ? "#60a5fa" : "#52525b" }}>Web search</span>
            </button>
            {webSearch && <span style={{ fontSize: 10, color: "#3f3f46" }}>Answers from the web instead of transcript</span>}
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
          <div style={{ flex: 1, background: "#18181b", border: "1px solid #27272a", borderRadius: 12, padding: "10px 12px" }}>
            <textarea
              ref={taRef}
              value={input}
              onChange={e => { setInput(e.target.value); e.target.style.height = "20px"; e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px"; }}
              onKeyDown={onKey}
              placeholder={webSearch ? "Search the web..." : "Message YTSage..."}
              disabled={streaming}
              rows={1}
              style={{ width: "100%", background: "transparent", border: "none", outline: "none", color: "#d4d4d8", fontSize: 14, resize: "none", lineHeight: "20px", minHeight: 20, maxHeight: 120, fontFamily: "inherit" }}
            />
          </div>
          <button onClick={send} disabled={streaming || !input.trim()}
            style={{
              width: 38, height: 38, borderRadius: 10, border: "none", cursor: "pointer",
              background: (!streaming && input.trim()) ? "#2563eb" : "#27272a",
              color: (!streaming && input.trim()) ? "white" : "#52525b",
              display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
            }}>
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18"/></svg>
          </button>
        </div>
        </div>
        </div>
      </div>

      <style>{`@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: 0.4 } }`}</style>
    </div>
  );
}
