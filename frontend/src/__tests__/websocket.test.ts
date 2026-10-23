import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// A socket that never opens: what a browser reports while the box reboots.
class DeadSocket {
  static OPEN = 1;
  static instances: DeadSocket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  constructor(public url: string) {
    DeadSocket.instances.push(this);
    setTimeout(() => {
      this.onerror?.(new Event('error'));
      this.onclose?.({ code: 1006 });
    }, 0);
  }
  close() {}
  send() {}
}

vi.mock('../services/api', () => ({
  // The box is down: asking for auth status fails at the network.
  authApi: { getStatus: vi.fn().mockRejectedValue(new Error('offline')) },
}));

describe('live socket reconnect', () => {
  beforeEach(async () => {
    vi.useFakeTimers();
    DeadSocket.instances = [];
    vi.stubGlobal('WebSocket', DeadSocket);
    const { useAuthStore } = await import('../stores/authStore');
    useAuthStore.getState().setSession('test-token');
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('keeps retrying after the quick attempts and reports the link as lost', async () => {
    const { audioWebSocket } = await import('../services/websocket');
    const states: string[] = [];
    const stop = audioWebSocket.onStateChange((s) => states.push(s));

    audioWebSocket.connect().catch(() => {});
    // Well past the old five-attempt limit.
    for (let i = 0; i < 12; i++) {
      await vi.advanceTimersByTimeAsync(10_000);
    }

    expect(DeadSocket.instances.length).toBeGreaterThan(8);
    expect(states).toContain('reconnecting');
    expect(audioWebSocket.linkState).toBe('lost');

    stop();
    audioWebSocket.disconnect();
  });

  it('stops retrying once the operator logs out', async () => {
    const { audioWebSocket } = await import('../services/websocket');
    audioWebSocket.connect().catch(() => {});
    await vi.advanceTimersByTimeAsync(10);
    audioWebSocket.disconnect();
    const before = DeadSocket.instances.length;

    await vi.advanceTimersByTimeAsync(60_000);

    expect(DeadSocket.instances.length).toBe(before);
    expect(audioWebSocket.linkState).toBe('idle');
  });
});
