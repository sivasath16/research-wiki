import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded bg-zinc-200 dark:bg-zinc-800",
        className
      )}
    />
  );
}

export function WikiPageSkeleton() {
  return (
    <div className="p-8 space-y-6">
      <Skeleton className="h-7 w-64" />
      <div className="flex gap-3">
        <Skeleton className="h-5 w-20 rounded-full" />
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-5 w-24" />
      </div>
      <div className="space-y-3 pt-4">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
      </div>
      <Skeleton className="h-48 w-full rounded-md" />
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    </div>
  );
}

export function RepoCardSkeleton() {
  return (
    <div className="border border-zinc-200 dark:border-zinc-800 rounded-md p-4 space-y-3">
      <div className="flex justify-between">
        <Skeleton className="h-5 w-36" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
      <div className="flex gap-2 pt-1">
        <Skeleton className="h-4 w-16 rounded-full" />
        <Skeleton className="h-4 w-24" />
      </div>
    </div>
  );
}
