import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { copyToClipboard, cn } from "@/lib/utils";

interface CodeBlockProps {
  language?: string;
  children: string;
}

export function CodeBlock({ language, children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    copyToClipboard(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="relative rounded-md overflow-hidden my-2 border border-zinc-700">
      <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-900 border-b border-zinc-700">
        {language && (
          <span className="font-mono text-[10px] text-zinc-500">{language}</span>
        )}
        <button
          onClick={handleCopy}
          className={cn(
            "ml-auto flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded",
            "text-zinc-500 hover:text-zinc-300 transition-colors"
          )}
        >
          {copied ? <Check size={10} /> : <Copy size={10} />}
        </button>
      </div>
      <pre className="p-3 bg-zinc-950 overflow-x-auto">
        <code className="font-mono text-[11px] text-zinc-200 leading-relaxed whitespace-pre">
          {children}
        </code>
      </pre>
    </div>
  );
}
