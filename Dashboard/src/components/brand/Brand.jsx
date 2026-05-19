import React from "react"
import logo from "@/assets/alexsys-logo.png"

export function Brand({ compact = false, className = "", titleClassName = "", subtitleClassName = "" }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div className="relative">
        <div className="absolute -inset-2 rounded-2xl bg-gradient-to-br from-[#6C63FF]/25 via-transparent to-[#F97316]/20 blur-lg" />
        <img
          src={logo}
          alt="Alexsys Solutions"
          className={`relative ${compact ? "h-12 w-12" : "h-10 w-10"} rounded-xl bg-white/5 ring-1 ring-white/10`}
        />
      </div>
      <div className="leading-tight">
        <div className={`font-semibold tracking-tight ${compact ? "text-base" : "text-base"} ${titleClassName}`}>
          Alexsys Solutions
        </div>
        {!compact ? (
          <div className={`text-xs text-muted-foreground ${subtitleClassName}`}>
            AI Procurement
          </div>
        ) : null}
      </div>
    </div>
  )
}

