import type { useQueryClient } from "@tanstack/react-query";

export const invalidate = (qc: ReturnType<typeof useQueryClient>, ...keys: string[]) =>
  Promise.all(keys.map((key) => qc.invalidateQueries({ queryKey: [key] })));
