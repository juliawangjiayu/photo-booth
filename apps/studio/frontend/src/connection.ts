type Refresh = (quiet: boolean) => Promise<void>;
type Clock = {
  setInterval(callback: () => void, delay: number): number;
  clearInterval(timer: number): void;
};

export function startConnectionMonitor(refresh: Refresh, intervalMs = 5000, clock: Clock = window) {
  void refresh(false);
  const timer = clock.setInterval(() => { void refresh(true); }, intervalMs);
  return () => clock.clearInterval(timer);
}
