export const today = () => new Date().toLocaleDateString("en-CA");
export const formatTime = (v: string) =>
  new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
export const status = (v: string) => v.replaceAll("_", " ");
