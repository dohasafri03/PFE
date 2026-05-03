import React from 'react'
import { Layout } from "@/components/layout/Layout"

export function Opportunities() {
  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Opportunities</h1>
          <p className="text-muted-foreground">Browse and explore public IT procurement computing opportunities.</p>
        </div>
        <div className="bg-card rounded-xl border p-12 flex flex-col items-center justify-center min-h-[400px]">
          <div className="rounded-full bg-primary/10 p-6 mb-4">
             <span className="text-4xl">🎯</span>
          </div>
          <h3 className="text-xl font-semibold mb-2">Opportunities Engine</h3>
          <p className="text-muted-foreground text-center max-w-sm">
            Advanced search, filtering, and deep dive module coming soon. 
          </p>
        </div>
      </div>
    </Layout>
  )
}
