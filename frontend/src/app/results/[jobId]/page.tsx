"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Concept {
  title: string;
  description: string;
  start_time: number;
  end_time: number;
  infographic_urls: string[];
}

interface Result {
  youtube_url: string;
  concepts: Concept[];
  slideshow_url: string | null;
}

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function youtubeTimestampUrl(youtubeUrl: string, seconds: number): string {
  const url = new URL(youtubeUrl);
  url.searchParams.set("t", String(Math.floor(seconds)));
  return url.toString();
}

export default function ResultsPage() {
  const params = useParams();
  const jobId = params.jobId as string;
  const router = useRouter();
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;

    async function fetchResult() {
      try {
        const res = await apiFetch(`${API_URL}/api/result/${jobId}`);
        if (!res.ok) {
          setError("Could not load results. The job may still be processing.");
          return;
        }
        const data = await res.json();
        setResult(data);
      } catch {
        setError("Failed to connect to the server.");
      }
    }

    fetchResult();
  }, [jobId]);

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-950 text-white flex flex-col items-center justify-center px-4">
        <p className="text-red-400 mb-4">{error}</p>
        <button
          onClick={() => router.push("/")}
          className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm"
        >
          Go back
        </button>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="min-h-screen bg-zinc-950 text-white flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      {/* Image lightbox */}
      {selectedImage && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 cursor-pointer"
          onClick={() => setSelectedImage(null)}
        >
          <img
            src={selectedImage}
            alt="Infographic"
            className="max-w-full max-h-full object-contain rounded-lg"
          />
        </div>
      )}

      <div className="max-w-4xl mx-auto px-4 py-12">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold">
            YT<span className="text-blue-500">Sage</span>
            <span className="text-zinc-500 text-lg font-normal ml-3">Results</span>
          </h1>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors"
          >
            New video
          </button>
        </div>

        {/* Slideshow video */}
        {result.slideshow_url && (
          <div className="mb-10">
            <h2 className="text-lg font-semibold mb-3 text-zinc-300">Infographic Slideshow</h2>
            <div className="rounded-xl overflow-hidden bg-zinc-900 border border-zinc-800">
              <video
                controls
                className="w-full max-h-[500px]"
                src={`${API_URL}${result.slideshow_url}`}
              >
                Your browser does not support the video tag.
              </video>
            </div>
          </div>
        )}

        {/* Concepts */}
        <h2 className="text-lg font-semibold mb-4 text-zinc-300">Key Concepts</h2>
        <div className="flex flex-col gap-6">
          {result.concepts.map((concept, i) => (
            <div
              key={i}
              className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6"
            >
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-medium">
                      {i + 1}
                    </span>
                    <h3 className="text-xl font-semibold">{concept.title}</h3>
                  </div>
                  <p className="text-zinc-400 text-sm mt-1">{concept.description}</p>
                </div>
                <a
                  href={youtubeTimestampUrl(result.youtube_url, concept.start_time)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs text-blue-400 transition-colors"
                >
                  {formatTimestamp(concept.start_time)} - {formatTimestamp(concept.end_time)}
                </a>
              </div>

              {/* Infographic images */}
              {concept.infographic_urls.length > 0 && (
                <div className="grid grid-cols-2 gap-3 mt-4">
                  {concept.infographic_urls.map((url, j) => (
                    <div
                      key={j}
                      className="rounded-lg overflow-hidden border border-zinc-800 cursor-pointer hover:border-blue-500 transition-colors"
                      onClick={() => setSelectedImage(url)}
                    >
                      <img
                        src={url}
                        alt={`${concept.title} - Slide ${j + 1}`}
                        className="w-full h-auto"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Footer */}
        <p className="text-xs text-zinc-600 text-center mt-12">
          This product is entirely derived from work conducted as part of the NUS CS5260 course.
        </p>
      </div>
    </div>
  );
}
