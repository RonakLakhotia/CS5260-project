"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { use } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STEPS = [
  "Ingesting transcript",
  "Identifying key concepts",
  "Designing infographics",
  "Generating images",
  "Done",
];

function getStepIndex(progress: string): number {
  const lower = progress.toLowerCase();
  if (lower.includes("done") || lower.includes("finaliz")) return 4;
  if (lower.includes("generat") || lower.includes("video") || lower.includes("stitch")) return 3;
  if (lower.includes("script") || lower.includes("infographic prompt") || lower.includes("design")) return 2;
  if (lower.includes("plan") || lower.includes("concept") || lower.includes("identify")) return 1;
  if (lower.includes("ingest") || lower.includes("transcript")) return 0;
  return 0;
}

export default function ProcessingPage() {
  const params = useParams();
  const jobId = params.jobId as string;
  const router = useRouter();
  const [progress, setProgress] = useState("Starting pipeline");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!jobId) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/api/status/${jobId}`);
        if (!res.ok) {
          setError("Job not found");
          clearInterval(interval);
          return;
        }

        const data = await res.json();
        setProgress(data.progress);

        if (data.status === "complete") {
          clearInterval(interval);
          router.push(`/results/${jobId}`);
        } else if (data.status === "error") {
          clearInterval(interval);
          setError(data.progress);
        }
      } catch {
        setError("Lost connection to server");
        clearInterval(interval);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [jobId, router]);

  const currentStep = getStepIndex(progress);

  return (
    <div className="min-h-screen bg-zinc-950 text-white flex flex-col items-center justify-center px-4">
      <main className="w-full max-w-lg flex flex-col items-center gap-8">
        <h1 className="text-3xl font-bold tracking-tight">
          YT<span className="text-blue-500">Sage</span>
        </h1>

        {error ? (
          <div className="w-full flex flex-col items-center gap-4">
            <div className="w-12 h-12 rounded-full bg-red-500/20 flex items-center justify-center">
              <span className="text-red-400 text-xl">!</span>
            </div>
            <p className="text-red-400 text-center">{error}</p>
            <button
              onClick={() => router.push("/")}
              className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors"
            >
              Try another video
            </button>
          </div>
        ) : (
          <div className="w-full flex flex-col gap-6">
            <p className="text-zinc-400 text-center">Processing your video...</p>

            <div className="flex flex-col gap-3">
              {STEPS.map((step, i) => (
                <div key={step} className="flex items-center gap-3">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium shrink-0 ${
                      i < currentStep
                        ? "bg-blue-600 text-white"
                        : i === currentStep
                        ? "bg-blue-500/20 text-blue-400 ring-2 ring-blue-500"
                        : "bg-zinc-800 text-zinc-600"
                    }`}
                  >
                    {i < currentStep ? "\u2713" : i + 1}
                  </div>
                  <span
                    className={`text-sm ${
                      i < currentStep
                        ? "text-zinc-400"
                        : i === currentStep
                        ? "text-white font-medium"
                        : "text-zinc-600"
                    }`}
                  >
                    {step}
                  </span>
                  {i === currentStep && i < STEPS.length - 1 && (
                    <div className="ml-auto">
                      <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}
                </div>
              ))}
            </div>

            <p className="text-xs text-zinc-600 text-center mt-4">
              This may take a few minutes depending on the video length.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
