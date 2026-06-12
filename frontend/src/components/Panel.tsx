import type { ReactNode } from 'react'

export function Panel({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="rounded-panel border border-panel-border bg-panel p-5 shadow-lg shadow-black/30 backdrop-blur">
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between">
          {title && <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}
