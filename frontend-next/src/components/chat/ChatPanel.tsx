"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, RotateCcw, GitBranch, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { useWebSocket } from "@/hooks/useWebSocket";

interface ChatPanelProps {
  repoId: number | null;
  onSourceClick?: (filePath: string) => void;
}

const MIN_WIDTH = 260;
const DEFAULT_WIDTH = 320;
const EXPANDED_WIDTH = 520;
const MAX_WIDTH = 720;

export function ChatPanel({ repoId, onSourceClick }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [isExpanded, setIsExpanded] = useState(false);
  const { messages, status, rateLimit, sendMessage, clearMessages, reconnect } =
    useWebSocket(repoId);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const isConnected = status === "connected";
  const isStreaming = messages.some((m) => m.streaming);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming || !isConnected) return;
    sendMessage(text);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }, [input, isStreaming, isConnected, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  };

  // Drag-to-resize
  const onDragStart = (e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startWidth: width };

    const onMove = (e: MouseEvent) => {
      if (!dragRef.current) return;
      const delta = dragRef.current.startX - e.clientX;
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, dragRef.current.startWidth + delta));
      setWidth(newWidth);
      setIsExpanded(newWidth > DEFAULT_WIDTH + 40);
    };

    const onUp = () => {
      dragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  const toggleExpand = () => {
    if (isExpanded) {
      setWidth(DEFAULT_WIDTH);
      setIsExpanded(false);
    } else {
      setWidth(EXPANDED_WIDTH);
      setIsExpanded(true);
    }
  };

  return (
    <div
      className="flex-shrink-0 border-l border-zinc-200 dark:border-zinc-800 flex bg-white dark:bg-zinc-950"
      style={{ width }}
    >
      {/* Drag handle */}
      <div
        onMouseDown={onDragStart}
        className="w-1 flex-shrink-0 cursor-col-resize hover:bg-[#1D9E75]/40 active:bg-[#1D9E75]/60 transition-colors group relative"
        title="Drag to resize"
      >
        <div className="absolute inset-y-0 -left-1 -right-1" />
      </div>

      {/* Panel body */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">Ask about this repo</span>
            {isConnected && <span className="w-1.5 h-1.5 rounded-full bg-[#1D9E75] animate-pulse" />}
          </div>
          <div className="flex items-center gap-1">
            {(status === "error" || status === "disconnected") && (
              <button onClick={reconnect} className="p-1 rounded text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors" title="Reconnect">
                <RotateCcw size={13} />
              </button>
            )}
            {messages.length > 0 && (
              <button onClick={clearMessages} className="text-[11px] text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors px-1">
                Clear
              </button>
            )}
            <button
              onClick={toggleExpand}
              className="p-1 rounded text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
              title={isExpanded ? "Collapse" : "Expand"}
            >
              {isExpanded ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            </button>
          </div>
        </div>

        {/* Status bar */}
        {status !== "connected" && (
          <div className={cn(
            "px-3 py-1.5 text-[11px] text-center",
            status === "connecting" && "bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400",
            status === "disconnected" && "bg-zinc-50 dark:bg-zinc-900 text-zinc-400",
            status === "error" && "bg-red-50 dark:bg-red-900/20 text-red-500"
          )}>
            {status === "connecting" && "Connecting..."}
            {status === "disconnected" && "Disconnected"}
            {status === "error" && "Connection error — click to retry"}
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center py-8">
              <div className="w-8 h-8 rounded-full bg-teal-50 dark:bg-teal-900/20 flex items-center justify-center mb-3">
                <span className="text-[#1D9E75] text-lg">?</span>
              </div>
              <p className="text-xs text-zinc-400 max-w-[180px] leading-relaxed">
                Ask questions about the codebase — architecture, functions, how things work.
              </p>
            </div>
          )}
          {messages.map((msg) =>
            msg.type === "dependency_suggestion" ? (
              <DependencySuggestion
                key={msg.id}
                message={msg.content}
                depRepos={msg.depRepos || []}
                originalQuery={msg.originalQuery || ""}
                onConfirm={(extraRepoIds) => sendMessage(msg.originalQuery || "", extraRepoIds)}
              />
            ) : (
              <ChatMessage key={msg.id} message={msg} onSourceClick={onSourceClick} />
            )
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Rate limit */}
        <div className="px-3 py-1.5 border-t border-zinc-100 dark:border-zinc-900">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-zinc-400">
              {rateLimit.remaining}/{rateLimit.limit} queries today
            </span>
            <div className="flex gap-0.5">
              {Array.from({ length: Math.min(rateLimit.limit, 10) }).map((_, i) => (
                <div
                  key={i}
                  className={cn(
                    "w-1 h-2 rounded-sm",
                    i < Math.floor((rateLimit.remaining / rateLimit.limit) * 10)
                      ? "bg-[#1D9E75]"
                      : "bg-zinc-200 dark:bg-zinc-800"
                  )}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Input */}
        <div className="p-3 border-t border-zinc-200 dark:border-zinc-800">
          <div className={cn(
            "flex items-end gap-2 rounded border bg-zinc-50 dark:bg-zinc-900 px-3 py-2",
            "border-zinc-200 dark:border-zinc-800 focus-within:border-[#1D9E75] transition-colors"
          )}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder={isConnected ? "Ask anything... (Enter to send)" : "Connecting..."}
              disabled={!isConnected || isStreaming}
              rows={1}
              className="flex-1 bg-transparent text-xs text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 resize-none outline-none min-h-[20px] max-h-[120px] leading-relaxed"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || !isConnected || isStreaming}
              className={cn(
                "p-1 rounded transition-colors flex-shrink-0",
                input.trim() && isConnected && !isStreaming
                  ? "text-[#1D9E75] hover:bg-teal-50 dark:hover:bg-teal-900/20"
                  : "text-zinc-300 dark:text-zinc-700 cursor-not-allowed"
              )}
            >
              <Send size={14} />
            </button>
          </div>
          <p className="text-[10px] text-zinc-400 mt-1.5 text-center">Shift+Enter for new line</p>
        </div>
      </div>
    </div>
  );
}

// ── Dependency suggestion inline card ─────────────────────────────────────────

interface DepRepo { id: number; owner: string; name: string; }

function DependencySuggestion({
  message, depRepos, originalQuery, onConfirm,
}: {
  message: string;
  depRepos: DepRepo[];
  originalQuery: string;
  onConfirm: (repoIds: number[]) => void;
}) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  return (
    <div className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-3 text-xs">
      <div className="flex items-start gap-2 mb-2">
        <GitBranch size={13} className="text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
        <p className="text-zinc-700 dark:text-zinc-300 leading-relaxed">{message}</p>
      </div>
      <div className="flex gap-2 mt-2">
        <button
          onClick={() => {
            onConfirm(depRepos.map((r) => r.id));
            setDismissed(true);
          }}
          className="px-2.5 py-1 rounded bg-[#1D9E75] text-white text-[11px] font-medium hover:bg-[#188f68] transition-colors"
        >
          Yes, include {depRepos.length === 1 ? depRepos[0].name : "them"}
        </button>
        <button
          onClick={() => setDismissed(true)}
          className="px-2.5 py-1 rounded text-zinc-500 dark:text-zinc-400 text-[11px] hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
        >
          No, skip
        </button>
      </div>
    </div>
  );
}
