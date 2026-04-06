import { useState, useEffect, useRef, useCallback } from "react";
import { WS_BASE } from "@/lib/api";

const HEARTBEAT_INTERVAL = 25_000;
const MAX_RETRY_DELAY = 30_000;

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

export interface UseWebSocketOptions {
  enabled?: boolean;
}

export function useWebSocket(repoId: number | null, options?: UseWebSocketOptions) {
  const enabled = options?.enabled ?? true;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<WsStatus>("disconnected");
  const [rateLimit, setRateLimit] = useState<RateLimit>({ remaining: 20, limit: 20 });
  const wsRef = useRef<WebSocket | null>(null);
  const streamingIdRef = useRef<string | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const intentionalCloseRef = useRef(false);
  const pendingQueueRef = useRef<string[]>([]);
  const connectRef = useRef<() => void>(() => {});

  const connect = useCallback(() => {
    if (!repoId || !enabledRef.current || wsRef.current?.readyState === WebSocket.OPEN) return;
    setStatus("connecting");
    const ws = new WebSocket(`${WS_BASE}/ws/chat/${repoId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("connected");
      retryCountRef.current = 0;

      heartbeatTimerRef.current = setInterval(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "ping" }));
        }
      }, HEARTBEAT_INTERVAL);

      const pending = pendingQueueRef.current.splice(0);
      pending.forEach((msg) => ws.send(msg));
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case "pong":
          break;

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
            prev.map((m) => (m.id === sid ? { ...m, content: m.content + msg.content } : m))
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

    ws.onclose = () => {
      setStatus("disconnected");
      wsRef.current = null;
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = null;
      }
      if (!intentionalCloseRef.current && enabledRef.current) {
        const delay = Math.min(1000 * 2 ** retryCountRef.current, MAX_RETRY_DELAY);
        retryCountRef.current += 1;
        retryTimerRef.current = setTimeout(() => connectRef.current(), delay);
      }
    };

    ws.onerror = () => setStatus("error");
  }, [repoId]);

  connectRef.current = connect;

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("disconnected");
  }, []);

  useEffect(() => {
    if (!repoId || !enabled) {
      intentionalCloseRef.current = true;
      disconnect();
      return;
    }
    intentionalCloseRef.current = false;
    connect();
    return () => {
      intentionalCloseRef.current = true;
      disconnect();
    };
  }, [repoId, enabled, connect, disconnect]);

  const sendMessage = useCallback(
    (content: string, extraRepoIds?: number[]) => {
      const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content };
      setMessages((prev) => [...prev, userMsg]);

      const payload = JSON.stringify({
        type: "message",
        content,
        ...(extraRepoIds?.length ? { extra_repo_ids: extraRepoIds } : {}),
      });

      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(payload);
      } else if (enabledRef.current) {
        pendingQueueRef.current.push(payload);
        connect();
      }
    },
    [connect]
  );

  const clearMessages = useCallback(() => setMessages([]), []);

  return { messages, status, rateLimit, sendMessage, clearMessages, reconnect: connect };
}
