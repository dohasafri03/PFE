import React from "react"
import { Sidebar } from "./Sidebar"
import { Header } from "./Header"

export function Layout({ children }) {
  return (
    <div className="alexsys-app-bg flex min-h-screen w-full min-w-0">
      {/* Sidebar hidden on desktop; menu lives in Header */}
      <div className="hidden">
        <Sidebar />
      </div>
      <div className="flex min-w-0 flex-1 flex-col sm:gap-4 sm:py-4 sm:pl-4">
        <div className="alexsys-surface flex min-h-0 min-w-0 flex-1 flex-col bg-background/80 rounded-l-none sm:rounded-tl-3xl border-t border-l overflow-hidden backdrop-blur">
          <Header />
          <main className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-3 md:px-4 md:py-4 lg:px-5 lg:py-5">
            <div className="mx-auto w-full min-w-0 max-w-[1800px]">{children}</div>
          </main>
        </div>
      </div>
    </div>
  )
}
