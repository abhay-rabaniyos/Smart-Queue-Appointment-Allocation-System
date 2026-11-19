import { useState, useEffect } from "react";
import { api, type Board } from "../api";
export default function useBoard(
  report: (source: string, message: string) => void,
  resolve: (source: string) => void,
) {
  const [board, setBoard] = useState<Board | null>(null),
    [live, setLive] = useState(false);
  useEffect(() => {
    let stopped = false,
      socket: WebSocket | undefined,
      retry: ReturnType<typeof setTimeout>;
    const poll = () =>
      api<Board>("/board")
        .then((v) => {
          if (!stopped) setBoard(v);
        })
        .catch(() => {});
    void poll();
    const interval = setInterval(poll, 10000);
    function connect() {
      if (stopped) return;
      try {
        socket = new WebSocket(
          `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws/board`,
        );
      } catch {
        report(
          "live-updates",
          "Cannot start live updates. Periodic refresh remains active.",
        );
        retry = setTimeout(connect, 3000);
        return;
      }
      socket.onmessage = (e) => {
        if (!stopped) {
          try {
            setBoard(JSON.parse(e.data));
            setLive(true);
            resolve("live-updates");
          } catch {
            report(
              "live-updates",
              "Live queue data could not be read. Periodic refresh remains active.",
            );
          }
        }
      };
      socket.onclose = () => {
        if (stopped) return;
        setLive(false);
        report(
          "live-updates",
          "Live updates disconnected. Periodic refresh remains active while reconnecting.",
        );
        if (!stopped) retry = setTimeout(connect, 3000);
      };
      socket.onerror = () => socket?.close();
    }
    connect();
    return () => {
      stopped = true;
      clearInterval(interval);
      clearTimeout(retry);
      socket?.close();
    };
  }, [report, resolve]);
  return { board, live };
}
