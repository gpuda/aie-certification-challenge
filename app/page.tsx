"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Tv } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

type Message = {
  role: "user" | "assistant";
  content: string;
  isPlaceholder?: boolean;
};

const QUICK_QUESTIONS = [
  "Top 5 channels by AVG viewing minutes (last 3 months)",
  "Top 5 channels by AVG unique viewers (last 3 months)",
  "AVG viewing minutes by content_playback_type (last 3 months)",
  "What does nr_unique_viewers represent in this dataset?",
];

export default function Home() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const typingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const typingFullTextRef = useRef<string>("");

  async function sendMessage(textOverride?: string) {
    const textSafe = (textOverride ?? input ?? "").trim();
    if (!textSafe || isLoading) return;

    const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    console.log("NEXT_PUBLIC_API_URL (compiled):", API);

    const userMsgObj: Message = { role: "user", content: textSafe };

    if (!textOverride) setInput("");
    setIsLoading(true);

    if (typingIntervalRef.current) {
      clearInterval(typingIntervalRef.current);
      typingIntervalRef.current = null;
    }
    typingFullTextRef.current = "";

    const history = messages ?? [];
    const messagesForBackend = [...history, userMsgObj];

    const placeholder: Message = {
      role: "assistant",
      content: "BroadcastIQ is analysing the data...",
      isPlaceholder: true,
    };

    setMessages([...messagesForBackend, placeholder]);

    try {
      const controller = new AbortController();
      const timeoutMs = 30_000;
      const t = setTimeout(() => controller.abort(), timeoutMs);

      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: messagesForBackend }),
        signal: controller.signal,
      });

      clearTimeout(t);

      if (!res.ok) {
        const errText = await res.text();

        let friendlyDetail = "";
        try {
          const maybeJson = JSON.parse(errText);
          if (
            maybeJson &&
            typeof maybeJson === "object" &&
            typeof (maybeJson as any).detail === "string"
          ) {
            friendlyDetail = (maybeJson as any).detail;
          }
        } catch {
          // not JSON
        }

        const message =
          friendlyDetail && friendlyDetail !== errText
            ? `HTTP ${res.status}: ${friendlyDetail}`
            : `HTTP ${res.status}: ${errText}`;

        throw new Error(message);
      }

      const data = await res.json();

      const raw =
        typeof data?.content === "string"
          ? data.content
          : JSON.stringify(data?.content ?? "");

      const clean = raw.trim();
      const finalText = clean.length > 0 ? clean : "No response content";

      typingFullTextRef.current = finalText;

      setMessages((prev) => {
        const safe = [...(prev ?? [])];
        const lastIndex = safe.length - 1;

        if (lastIndex >= 0 && safe[lastIndex].role === "assistant") {
          safe[lastIndex] = {
            ...safe[lastIndex],
            isPlaceholder: false,
            content: "",
          };
        } else {
          safe.push({
            role: "assistant",
            content: "",
            isPlaceholder: false,
          });
        }

        return safe;
      });

      let currentIndex = 0;
      const step = 3;

      typingIntervalRef.current = setInterval(() => {
        currentIndex += step;
        const next = typingFullTextRef.current.slice(0, currentIndex);

        setMessages((prev) => {
          const safe = [...(prev ?? [])];
          const lastIndex = safe.length - 1;

          if (lastIndex >= 0 && safe[lastIndex].role === "assistant") {
            safe[lastIndex] = {
              ...safe[lastIndex],
              content: next,
            };
          }

          return safe;
        });

        if (currentIndex >= typingFullTextRef.current.length) {
          if (typingIntervalRef.current) {
            clearInterval(typingIntervalRef.current);
            typingIntervalRef.current = null;
          }
        }
      }, 18);
    } catch (e: any) {
      console.error("CHAT error:", e);

      if (typingIntervalRef.current) {
        clearInterval(typingIntervalRef.current);
        typingIntervalRef.current = null;
      }
      typingFullTextRef.current = "";

      const isAbort = typeof e?.name === "string" && e.name === "AbortError";

      const errorText = isAbort
        ? "Error: request timeout (backend nije vratio odgovor). Provjeri backend /health i log."
        : `Error: ${String(e?.message ?? "backend unavailable or invalid response")}`;

      setMessages((prev) => {
        const safe = [...(prev ?? [])];
        const lastIndex = safe.length - 1;

        if (
          lastIndex >= 0 &&
          safe[lastIndex].role === "assistant" &&
          safe[lastIndex].isPlaceholder
        ) {
          safe[lastIndex] = {
            ...safe[lastIndex],
            isPlaceholder: false,
            content: errorText,
          };
        } else {
          safe.push({
            role: "assistant",
            content: errorText,
          });
        }

        return safe;
      });
    } finally {
      setIsLoading(false);
    }
  }

  function clearChat() {
    setMessages([]);
  }

  async function handleQuickQuestion(q: string) {
    if (isLoading) return;
    setInput(q);
    await sendMessage(q);
    setInput("");
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    return () => {
      if (typingIntervalRef.current) {
        clearInterval(typingIntervalRef.current);
      }
    };
  }, []);

  return (
    <main className="relative min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-slate-100 flex flex-col items-center justify-center gap-6 p-6 overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-28 left-1/2 h-[560px] w-[560px] -translate-x-1/2 rounded-full bg-[hsl(var(--primary)/0.14)] blur-[120px]" />
        <div className="absolute top-[120px] left-[8%] h-[320px] w-[320px] rounded-full bg-[hsl(var(--primary)/0.10)] blur-[110px]" />
        <div className="absolute top-[80px] right-[6%] h-[300px] w-[300px] rounded-full bg-white/5 blur-[110px]" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-slate-950/60" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55 }}
        className="text-center z-10"
      >
        <div className="mx-auto mb-4 h-16 w-16 rounded-3xl border border-white/10 bg-gradient-to-br from-[hsl(var(--primary)/0.55)] via-fuchsia-500/40 to-transparent backdrop-blur flex items-center justify-center shadow-[0_24px_80px_-32px_rgba(236,72,153,0.75)] scale-110">
          <Tv className="h-8 w-8 text-fuchsia-200" />
        </div>

        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">
          <span className="bg-gradient-to-r from-white via-white to-white/70 bg-clip-text text-transparent">
            BroadcastIQ
          </span>
        </h1>

        <p className="mt-2 text-sm sm:text-base text-slate-300">
          Smart diagnostics • Instant answers • Clear next steps
        </p>

        <div className="mt-5 flex flex-wrap gap-2 justify-center">
          {QUICK_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => handleQuickQuestion(q)}
              className="rounded-full border border-white/12 bg-white/5 px-3 py-1 text-sm text-white/90 hover:bg-[hsl(var(--primary)/0.10)] hover:border-[hsl(var(--primary)/0.25)] transition disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary)/0.5)]"
              type="button"
              disabled={isLoading}
            >
              {q}
            </button>
          ))}
        </div>
      </motion.div>

      <Card className="w-full max-w-xl bg-slate-900/55 backdrop-blur border-white/10 shadow-[0_18px_60px_-36px_rgba(0,0,0,0.6)]">
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="text-sm text-slate-300">Chat</div>

          <Button
            variant="secondary"
            size="sm"
            onClick={clearChat}
            className="bg-white/5 text-slate-100 hover:bg-white/10 border border-white/10"
            disabled={isLoading}
          >
            Clear
          </Button>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="space-y-3 max-h-80 overflow-y-auto pr-1 scroll-smooth">
            {messages.map((m, i) => {
              const isUser = m.role === "user";
              return (
                <div
                  key={i}
                  className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={[
                      "max-w-[80%] rounded-2xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap",
                      isUser
                        ? "bg-[hsl(var(--primary))] text-white shadow-[0_10px_34px_-22px_hsl(var(--primary)/0.75)]"
                        : "bg-white/5 text-slate-100 border border-white/10",
                      !isUser && m.isPlaceholder ? "opacity-75 animate-pulse" : "",
                    ].join(" ")}
                  >
                    {m.content}
                  </div>
                </div>
              );
            })}

            <div ref={bottomRef} />
          </div>

          <div className="flex gap-2">
            <input
              className="flex-1 px-3 py-2 rounded-md bg-white/5 text-slate-100 border border-white/10 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary)/0.55)] focus:border-[hsl(var(--primary)/0.35)]"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={isLoading ? "Thinking..." : "Type something..."}
              onKeyDown={(e) => {
                if (e.key === "Enter") sendMessage();
              }}
              disabled={isLoading}
            />
            <Button
              onClick={() => sendMessage()}
              disabled={isLoading}
              className="shadow-[0_16px_46px_-28px_hsl(var(--primary)/0.75)]"
            >
              {isLoading ? "..." : "Send"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}