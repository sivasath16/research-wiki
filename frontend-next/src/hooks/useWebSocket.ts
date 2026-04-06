"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { WS_BASE } from "@/lib/api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  streaming?: boolean;
  type?: "normal" | "dependency_suggestion";
  depRepos?: DepRepo[];
  originalQuery?: string;
}

export interface SourceRef {
  file_path: string;
  name: string | null;
  start_line: number | null;
  end_line: number | null;
  language: string | null;
  repo_id?: number;
}

export interface DepRepo {
  id: number;
  owner: string;
  name: string;
}

interface RateLimit {
  remaining: number;
  limit: number;
}

type WsStatus = "disconnected" | "connecting" | "connected" | "error";

export function useWebSocket(repoId: number | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<WsStatus>("disconnected");
  const [rateLimit, setRateLimit] = useState<RateLimit>({ remaining: 20, limit: 20 });
  const wsRef = useRef<WebSocket | null>(null);
  const streamingIdRef = useRef<string | null>(null);

  const connect = useCallback(() => {
    if (!repoId || wsRef.current?.readyState === WebSocket.OPEN) return;
    setStatus("connecting");
    const ws = new WebSocket(`${WS_BASE}/ws/chat/${repoId}`);
    wsRef.current = ws;

    ws.onopen = () => setStatus("connected");

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case "connected":
          if (msg.rate_limit) setRateLimit(msg.rate_limit);
          break;

        case "stream_start": {
          const id = crypto.randomUUID();
          streamingIdRef.current = id;
          setMessages((prev) => [...prev, { id, role: "assistant", content: "", streaming: true }]);
          break;
        }

        case "token": {
          const sid = streamingIdRef.current;
          if (!sid) break;
          setMessages((prev) =>
            prev.map((m) => m.id === sid ? { ...m, content: m.content + msg.content } : m)
          );
          break;
        }

        case "stream_end": {
          const sid = streamingIdRef.current;
          if (sid) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === sid ? { ...m, streaming: false, sources: msg.sources || [] } : m
              )
            );
            streamingIdRef.current = null;
          }
          if (msg.rate_limit) setRateLimit(msg.rate_limit);
          break;
        }

        case "dependency_suggestion":
          // Show inline prompt asking user if they want to include dependent repos
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: msg.message,
              type: "dependency_suggestion",
              depRepos: msg.dep_repos,
              originalQuery: msg.original_query,
            },
          ]);
          break;

        case "retrieving":
          // No-op — could add a "thinking" indicator here
          break;

        case "rate_limited":
          if (msg.rate_limit) setRateLimit(msg.rate_limit);
          setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: "assistant", content: msg.message },
          ]);
          break;

        case "error":
          setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: "assistant", content: `Error: ${msg.message}` },
          ]);
          break;
      }
    };

    ws.onclose = () => { setStatus("disconnected"); wsRef.current = null; };
    ws.onerror = () => setStatus("error");
  }, [repoId]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("disconnected");
  }, []);

  useEffect(() => {
    if (repoId) connect();
    return () => disconnect();
  }, [repoId, connect, disconnect]);

  const sendMessage = useCallback(
    (content: string, extraRepoIds?: number[]) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) { connect(); return; }
      const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content };
      setMessages((prev) => [...prev, userMsg]);
      wsRef.current.send(JSON.stringify({
        type: "message",
        content,
        ...(extraRepoIds?.length ? { extra_repo_ids: extraRepoIds } : {}),
      }));
    },
    [connect]
  );

  const clearMessages = useCallback(() => setMessages([]), []);

  return { messages, status, rateLimit, sendMessage, clearMessages, reconnect: connect };
}
