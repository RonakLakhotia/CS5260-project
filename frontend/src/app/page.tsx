"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type IngestionStep =
  | "idle"
  | "fetching_metadata"
  | "fetching_transcript"
  | "generating_summary"
  | "embedding"
  | "done"
  | "error";

const STEP_LABELS: Record<IngestionStep, string> = {
  idle: "",
  fetching_metadata: "Fetching video info",
  fetching_transcript: "Extracting transcript",
  generating_summary: "Generating summary",
  embedding: "Embedding into vector store",
  done: "Ready - opening chat",
  error: "Something went wrong",
};

export default function Home() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState<IngestionStep>("idle");
  const [videoTitle, setVideoTitle] = useState("");
  const [videoThumbnail, setVideoThumbnail] = useState("");
  const [videoChannel, setVideoChannel] = useState("");
  const router = useRouter();
  const abortRef = useRef<AbortController | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    setStep("idle");
    setVideoTitle("");
    setVideoThumbnail("");
    setVideoChannel("");

    abortRef.current = new AbortController();

    try {
      const res = await fetch(`${API_URL}/api/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: url }),
        signal: abortRef.current.signal,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Server error");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ") && currentEvent) {
            try {
              const data = JSON.parse(line.slice(6));
              handleSSEEvent(currentEvent, data);
            } catch {
              // skip
            }
            currentEvent = "";
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Failed to connect to the server. Please try again.");
      setStep("error");
      setLoading(false);
    }
  };

  const handleSSEEvent = (event: string, data: Record<string, unknown>) => {
    switch (event) {
      case "status":
        setStep(data.step as IngestionStep);
        break;
      case "metadata":
        if (data.title) setVideoTitle(data.title as string);
        if (data.thumbnail) setVideoThumbnail(data.thumbnail as string);
        if (data.channel) setVideoChannel(data.channel as string);
        break;
      case "done": {
        setStep("done");
        const chatId = data.chat_id as string;
        const videoId = data.video_id as string;
        fetch(`${API_URL}/api/process`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ youtube_url: url }),
        })
          .then((r) => r.json())
          .then((d) => {
            if (d.job_id) sessionStorage.setItem(`slideshow_${videoId}`, d.job_id);
          })
          .catch(() => {})
          .finally(() => {
            router.push(`/chat/${chatId}?video_id=${videoId}`);
          });
        break;
      }
      case "error":
        setError((data.message as string) || "Ingestion failed");
        setStep("error");
        setLoading(false);
        break;
    }
  };

  const completedSteps = ["fetching_metadata", "fetching_transcript", "generating_summary", "embedding", "done"];
  const currentIdx = completedSteps.indexOf(step);

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Background glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-500/[0.03] rounded-full blur-[120px] pointer-events-none" />

      <main className="w-full max-w-lg flex flex-col items-center gap-8 text-center relative z-10">
        {/* Logo */}
        <div className="flex flex-col items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-2xl shadow-blue-500/30">
            <svg className="w-7 h-7 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          </div>
          <div>
            <h1 className="text-4xl font-bold tracking-tight">
              YT<span className="text-blue-400">Sage</span>
            </h1>
            <p className="text-sm text-white/30 mt-2 max-w-xs leading-relaxed">
              Chat with any YouTube video. AI infographic summaries generated in the background.
            </p>
          </div>
        </div>

        {/* Input */}
        <form onSubmit={handleSubmit} className="w-full">
          <div className="relative flex items-center bg-white/[0.04] border border-white/[0.08] rounded-2xl pl-4 pr-2 py-2 focus-within:border-blue-500/30 focus-within:bg-white/[0.06] focus-within:shadow-xl focus-within:shadow-blue-500/[0.05] transition-all duration-300">
            <svg className="w-4 h-4 text-white/20 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
            </svg>
            <input
              type="text"
              placeholder="Paste a YouTube URL..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={loading}
              className="flex-1 bg-transparent text-sm text-white/90 placeholder-white/20 focus:outline-none disabled:opacity-40"
              required
            />
            <button
              type="submit"
              disabled={loading}
              className="h-9 px-5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-white/[0.06] disabled:text-white/20 text-white text-sm font-medium transition-all duration-200 shadow-lg shadow-blue-500/20 disabled:shadow-none flex-shrink-0"
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <div className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  <span>Processing</span>
                </div>
              ) : (
                "Start"
              )}
            </button>
          </div>

          {error && !loading && (
            <p className="text-red-400/80 text-sm mt-3">{error}</p>
          )}
        </form>

        {/* Progress card */}
        {loading && step !== "idle" && step !== "error" && (
          <div className="w-full rounded-2xl border border-white/[0.06] bg-white/[0.02] backdrop-blur-sm overflow-hidden">
            {/* Video preview */}
            {(videoTitle || videoThumbnail) && (
              <div className="flex items-center gap-3 p-4 border-b border-white/[0.04]">
                {videoThumbnail && (
                  <img
                    src={videoThumbnail}
                    alt=""
                    className="w-20 h-12 rounded-lg object-cover flex-shrink-0 ring-1 ring-white/[0.06]"
                  />
                )}
                <div className="min-w-0 text-left">
                  {videoTitle && (
                    <p className="text-sm text-white/80 font-medium truncate">{videoTitle}</p>
                  )}
                  {videoChannel && (
                    <p className="text-xs text-white/30 mt-0.5">{videoChannel}</p>
                  )}
                </div>
              </div>
            )}

            {/* Steps */}
            <div className="p-4 flex flex-col gap-2.5">
              {completedSteps.slice(0, -1).map((s, i) => {
                const isDone = i < currentIdx;
                const isCurrent = i === currentIdx;
                return (
                  <div key={s} className="flex items-center gap-3">
                    {isDone ? (
                      <div className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center flex-shrink-0">
                        <svg className="w-3 h-3 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                        </svg>
                      </div>
                    ) : isCurrent ? (
                      <div className="w-5 h-5 flex items-center justify-center flex-shrink-0">
                        <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                      </div>
                    ) : (
                      <div className="w-5 h-5 rounded-full border border-white/[0.08] flex-shrink-0" />
                    )}
                    <span
                      className={`text-sm transition-colors duration-300 ${
                        isDone
                          ? "text-white/30"
                          : isCurrent
                            ? "text-white/80"
                            : "text-white/15"
                      }`}
                    >
                      {STEP_LABELS[s as IngestionStep]}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <p className="text-[11px] text-white/10 mt-8 select-none">
          NUS CS5260 Course Project
        </p>
      </main>
    </div>
  );
}
