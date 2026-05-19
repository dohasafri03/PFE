import { useEffect, useState } from "react"

/** Affiche le texte lettre par lettre au montage. */
export function useTypingEffect(text, speedMs = 32, active = true) {
  const [display, setDisplay] = useState("")

  useEffect(() => {
    if (!active) {
      setDisplay(text)
      return undefined
    }
    setDisplay("")
    let index = 0
    const timer = window.setInterval(() => {
      index += 1
      setDisplay(text.slice(0, index))
      if (index >= text.length) window.clearInterval(timer)
    }, speedMs)
    return () => window.clearInterval(timer)
  }, [text, speedMs, active])

  return display
}
