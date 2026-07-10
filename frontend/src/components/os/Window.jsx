import { useRef, useState, useCallback } from "react";
import { useGameStore } from "@/store/useGameStore";

/**
 * Generic chrome for every OS app: draggable header, close button, focus
 * ring. Individual apps (Terminal, Evidence Board, Messenger) just render
 * inside <Window> and never worry about positioning or z-index themselves.
 */
export default function Window({ id, title, initial = { x: 40, y: 40, w: 480, h: 380 }, children }) {
  const focusedWindow = useGameStore((s) => s.focusedWindow);
  const focusWindow = useGameStore((s) => s.focusWindow);
  const closeWindow = useGameStore((s) => s.closeWindow);

  const [pos, setPos] = useState({ x: initial.x, y: initial.y });
  const dragState = useRef(null);

  const isFocused = focusedWindow === id;

  const onHeaderPointerDown = useCallback(
    (e) => {
      focusWindow(id);
      dragState.current = { startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y };
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
    },
    [pos, id, focusWindow]
  );

  const onPointerMove = (e) => {
    if (!dragState.current) return;
    const { startX, startY, origX, origY } = dragState.current;
    setPos({ x: origX + (e.clientX - startX), y: origY + (e.clientY - startY) });
  };

  const onPointerUp = () => {
    dragState.current = null;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
  };

  return (
    <div
      className={`os-window${isFocused ? " focused" : ""}`}
      style={{ left: pos.x, top: pos.y, width: initial.w, height: initial.h, zIndex: isFocused ? 50 : 10 }}
      onMouseDown={() => focusWindow(id)}
    >
      <div className={`os-window-header${isFocused ? " focused" : ""}`} onPointerDown={onHeaderPointerDown}>
        <span>{title}</span>
        <span className="os-window-close" onClick={() => closeWindow(id)}>
          ✕
        </span>
      </div>
      <div className="os-window-body">{children}</div>
    </div>
  );
}
