"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { CSSProperties, ReactNode } from "react";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export function Skeleton({ className, style }: { className?: string; style?: CSSProperties }) {
  return <div aria-hidden className={cn("skeleton", className)} style={style} />;
}

export function SkeletonLines({ rows = 4, height = 44 }: { rows?: number; height?: number }) {
  return (
    <div className="flex flex-col gap-3" role="status" aria-label="Yuklanmoqda">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} style={{ height }} />
      ))}
    </div>
  );
}

export function EmptyState({ text, action }: { text: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 py-4">
      <p className="text-[14px] text-muted">{text}</p>
      {action}
    </div>
  );
}

export function ErrorState({ onRetry, message }: { onRetry: () => void; message?: string }) {
  const t = useT();
  return (
    <div role="alert" className="flex flex-col items-start gap-2 py-4">
      <p className="text-[14px] text-text-2">{message ?? t.shell.loadError}</p>
      <button type="button" className="btn btn-plain -ml-2" onClick={onRetry}>
        {t.shell.retry}
      </button>
    </div>
  );
}

export function Async<T>({
  query,
  skeleton,
  isEmpty,
  empty,
  children,
}: {
  query: UseQueryResult<T>;
  skeleton: ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <>{skeleton}</>;
  if (query.isError) return <ErrorState onRetry={() => void query.refetch()} message={query.error instanceof Error && query.error.name === "ApiError" ? query.error.message : undefined} />;
  if (isEmpty?.(query.data)) return <>{empty}</>;
  return <>{children(query.data)}</>;
}
