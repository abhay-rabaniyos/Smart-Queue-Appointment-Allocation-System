import { useState, useEffect } from "react";
import { api, type Board } from "../api";
export default function useBoard() {
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
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws/board`,
      );
      socket.onmessage = (e) => {
        if (!stopped) {
          setBoard(JSON.parse(e.data));
          setLive(true);
        }
      };
      socket.onclose = () => {
        setLive(false);
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
  }, []);
  return { board, live };
}
