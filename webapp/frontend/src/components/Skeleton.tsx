// Loading skeletons. Shimmer is CSS-only (see styles.css .skeleton).

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function SidebarListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="sidebar-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="sk-list-item" />
      ))}
    </div>
  );
}

export function WorkspaceSkeleton() {
  return (
    <div className="workspace-skeleton">
      <Skeleton className="sk-header" />
      <div className="sk-band">
        <Skeleton className="sk-line" />
        <Skeleton className="sk-line sk-line--short" />
        <Skeleton className="sk-line sk-line--mid" />
      </div>
      <div className="sk-grid">
        <Skeleton className="sk-card" />
        <Skeleton className="sk-card" />
      </div>
      <Skeleton className="sk-block" />
    </div>
  );
}
