"use client";
import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/appStore";

interface MermaidDiagramProps {
  diagram: string;
  className?: string;
}

let _initialized = false;

export function MermaidDiagram({ diagram, className }: MermaidDiagramProps) {
  const { darkMode } = useAppStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const idRef = useRef(`mermaid-${crypto.randomUUID().slice(0, 8)}`);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: darkMode ? "dark" : "neutral",
      themeVariables: darkMode
        ? {
            background: "#09090b",
            primaryColor: "#1D9E75",
            primaryTextColor: "#e4e4e7",
            lineColor: "#3f3f46",
            edgeLabelBackground: "#18181b",
            clusterBkg: "#18181b",
          }
        : {
            primaryColor: "#1D9E75",
            primaryTextColor: "#18181b",
            lineColor: "#a1a1aa",
          },
      fontFamily: "JetBrains Mono, monospace",
    });
    _initialized = true;
  }, [darkMode]);

  useEffect(() => {
    if (!containerRef.current || !diagram) return;
    setError(null);

    const id = idRef.current;
    mermaid
      .render(id, diagram)
      .then(({ svg }) => {
        if (containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      })
      .catch((e) => {
        setError("Failed to render diagram");
      });
  }, [diagram, darkMode]);

  if (error) {
    return (
      <div className="border border-zinc-200 dark:border-zinc-800 rounded-md p-3">
        <pre className="font-mono text-xs text-zinc-500 whitespace-pre-wrap">{diagram}</pre>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={cn(
        "overflow-x-auto border border-zinc-200 dark:border-zinc-800 rounded-md p-4 bg-zinc-50 dark:bg-zinc-900",
        className
      )}
    />
  );
}
