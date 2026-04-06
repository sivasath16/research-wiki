import { useEffect, useId, useRef, useState } from "react";
import mermaid from "mermaid";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/appStore";

interface MermaidDiagramProps {
  diagram: string;
  className?: string;
}

export function MermaidDiagram({ diagram, className }: MermaidDiagramProps) {
  const { darkMode } = useAppStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reactId = useId().replace(/:/g, "");

  const trimmed = diagram?.trim() ?? "";

  useEffect(() => {
    if (!trimmed) {
      setLoading(false);
      setError(null);
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    seqRef.current += 1;
    const renderId = `m-${reactId}-${seqRef.current}`;

    setError(null);
    setLoading(true);
    container.innerHTML = "";

    const run = async () => {
      try {
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
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
          securityLevel: "strict",
        });

        const { svg, bindFunctions } = await mermaid.render(renderId, trimmed);

        if (cancelled || !containerRef.current) return;

        containerRef.current.innerHTML = svg;
        bindFunctions?.(containerRef.current);
      } catch (e) {
        if (!cancelled) {
          console.warn("Mermaid render failed:", e);
          setError(e instanceof Error ? e.message : "Failed to render diagram");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [trimmed, darkMode, reactId]);

  if (!trimmed) {
    return null;
  }

  if (error) {
    return (
      <div className="border border-amber-200 dark:border-amber-800 rounded-md p-3 bg-amber-50/50 dark:bg-amber-900/10">
        <p className="text-xs text-amber-800 dark:text-amber-200 mb-2">Could not render diagram.</p>
        <pre className="font-mono text-xs text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap overflow-x-auto">
          {trimmed}
        </pre>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "relative overflow-x-auto border border-zinc-200 dark:border-zinc-800 rounded-md bg-zinc-50 dark:bg-zinc-900 min-h-[120px]",
        className
      )}
    >
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 bg-zinc-50/90 dark:bg-zinc-900/90 text-xs text-zinc-500">
          <span className="inline-block w-4 h-4 border-2 border-[#1D9E75] border-t-transparent rounded-full animate-spin" />
          Rendering diagram…
        </div>
      )}
      <div ref={containerRef} className="p-4 [&_svg]:max-w-full" />
    </div>
  );
}
