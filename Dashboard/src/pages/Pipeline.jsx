import React from 'react'
import { Layout } from "@/components/layout/Layout"

export function Pipeline() {
  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">My Pipeline</h1>
          <p className="text-muted-foreground">Manage your actively tracked and bidded opportunities.</p>
        </div>
        <div className="bg-card rounded-xl border p-12 flex flex-col items-center justify-center min-h-[400px]">
          <div className="rounded-full bg-primary/10 p-6 mb-4">
             <span className="text-4xl">💼</span>
          </div>
          <h3 className="text-xl font-semibold mb-2">Kanban Board</h3>
          <p className="text-muted-foreground text-center max-w-sm">
            Visual pipeline management with drag-and-drop coming in the next update.
          </p>
        </div>
      </div>
    </Layout>
  )
}
