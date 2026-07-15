/** Pagination utilities for variable-size pages (larger first page). */

export function getOffset(page: number, firstPageSize: number, subsequentPageSize: number): number {
  if (page <= 1) return 0;
  return firstPageSize + (page - 2) * subsequentPageSize;
}

export function computeTotalPages(count: number, firstPageSize: number, subsequentPageSize: number): number {
  if (count === 0) return 1;
  const remaining = count - firstPageSize;
  if (remaining <= 0) return 1;
  return 1 + Math.ceil(remaining / subsequentPageSize);
}

export function pageSizeForPage(page: number, firstPageSize: number, subsequentPageSize: number): number {
  return page === 1 ? firstPageSize : subsequentPageSize;
}
