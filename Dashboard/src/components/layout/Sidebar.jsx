import React from "react"
import { useLocation, Link } from "react-router-dom"
import { LayoutDashboard, FileText } from "lucide-react"
import { cn } from "@/lib/utils"
import { Brand } from "@/components/brand/Brand"

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", href: "/" },
  { icon: FileText, label: "Reports", href: "/reports" },
]

export function Sidebar() {
  const location = useLocation()
  const pathname = location.pathname

  return (
    <aside className="hidden w-72 shrink-0 flex-col border-r border-border bg-background/50 backdrop-blur md:flex">
      <div className="flex h-16 items-center flex-shrink-0 px-5 border-b border-border">
        <Brand compact />
      </div>
      <div className="flex-1 overflow-auto py-4">
        <nav className="grid items-start px-4 text-sm font-medium gap-2">
          {navItems.map((item, index) => {
            const isActive = pathname === item.href
            return (
              <Link
                key={index}
                to={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors",
                  isActive
                    ? "bg-gradient-to-r from-primary/15 to-accent/10 text-foreground ring-1 ring-primary/20"
                    : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            )
          })}
        </nav>
      </div>
      {/* Bloc 'Upgrade to Pro' supprimé */}
    </aside>
  )
}
