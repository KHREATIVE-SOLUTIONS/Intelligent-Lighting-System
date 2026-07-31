import { authApi } from './api';
import { useAuthStore } from '../stores/authStore';

type MessageHandler = (data: unknown) => void;

// The server closes an unauthenticated socket with the policy-violation code,
// but it does so before the HTTP upgrade completes: a browser reports that as
// 1006 and never surfaces the code the server sent. So the code is checked for
// completeness and "never opened" is what actually catches a rejection.
const CLOSE_POLICY_VIOLATION = 1008;

class WebSocketService {
  private socket: WebSocket | null = null;
  private path: string;
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private isConnecting = false;
  private closedByClient = false;

  constructor(path: string) {
    this.path = path;
  }

  private buildUrl(token: string): string {
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${scheme}//${window.location.host}${this.path}?token=${encodeURIComponent(token)}`;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      if (this.isConnecting) {
        reject(new Error('Already connecting'));
        return;
      }

      const token = useAuthStore.getState().token;
      if (!token) {
        reject(new Error('Not signed in'));
        return;
      }

      this.isConnecting = true;
      this.closedByClient = false;

      try {
        let everOpened = false;
        this.socket = new WebSocket(this.buildUrl(token));

        this.socket.onopen = () => {
          console.log('WebSocket connected');
          everOpened = true;
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          resolve();
        };

        this.socket.onclose = (event) => {
          console.log('WebSocket disconnected');
          this.isConnecting = false;

          if (this.closedByClient) {
            return;
          }

          if (event.code === CLOSE_POLICY_VIOLATION || !everOpened) {
            void this.handleSocketRefused();
            return;
          }

          this.attemptReconnect();
        };

        this.socket.onerror = (error) => {
          console.error('WebSocket error:', error);
          this.isConnecting = false;
          reject(error);
        };

        this.socket.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            const type = message.type;

            if (this.handlers.has(type)) {
              this.handlers.get(type)?.forEach((handler) => {
                handler(message.data || message);
              });
            }

            // Also emit to 'message' handlers for all messages
            if (this.handlers.has('message')) {
              this.handlers.get('message')?.forEach((handler) => {
                handler(message);
              });
            }
          } catch (e) {
            console.error('Error parsing WebSocket message:', e);
          }
        };
      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  disconnect(): void {
    this.closedByClient = true;
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  private async handleSocketRefused(): Promise<void> {
    // A socket that never opened may have been refused for the session, or the
    // box may simply be restarting. Asking is the only way to tell them apart -
    // and burning five reconnects against a token the box will never accept
    // leaves the operator on a silent dashboard with no way back to the login.
    try {
      const status = await authApi.getStatus();
      if (!status.authenticated) {
        console.error('WebSocket rejected: not signed in');
        useAuthStore.getState().clearSession();
        return;
      }
    } catch {
      // The box did not answer at all; that is a transport problem, not a
      // rejected session.
    }
    this.attemptReconnect();
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`Attempting to reconnect in ${delay}ms...`);

    setTimeout(() => {
      this.connect().catch(console.error);
    }, delay);
  }

  on(event: string, handler: MessageHandler): void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)?.add(handler);
  }

  off(event: string, handler: MessageHandler): void {
    this.handlers.get(event)?.delete(handler);
  }

  send(data: unknown): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(data));
    } else {
      console.warn('WebSocket not connected');
    }
  }

  sendBinary(data: ArrayBuffer): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(data);
    } else {
      console.warn('WebSocket not connected');
    }
  }

  get isConnected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }
}

// Audio WebSocket for streaming audio data and receiving analysis
export const audioWebSocket = new WebSocketService('/ws/audio');

// DMX WebSocket for real-time DMX updates
export const dmxWebSocket = new WebSocketService('/ws/dmx');

// Show WebSocket for playback state
export const showWebSocket = new WebSocketService('/ws/show');

export const disconnectAllWebSockets = (): void => {
  audioWebSocket.disconnect();
  dmxWebSocket.disconnect();
  showWebSocket.disconnect();
};

// Audio streaming helper
export class AudioStreamer {
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private processor: ScriptProcessorNode | null = null;
  private isStreaming = false;

  async start(): Promise<void> {
    if (this.isStreaming) return;

    try {
      await audioWebSocket.connect();

      this.audioContext = new AudioContext({ sampleRate: 44100 });
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });

      const source = this.audioContext.createMediaStreamSource(this.mediaStream);

      // Using ScriptProcessorNode (deprecated but widely supported)
      // For production, use AudioWorklet instead
      this.processor = this.audioContext.createScriptProcessor(2048, 1, 1);

      this.processor.onaudioprocess = (event) => {
        if (!this.isStreaming) return;

        const inputData = event.inputBuffer.getChannelData(0);

        // Convert float32 to int16 for transmission
        const int16Data = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          int16Data[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
        }

        audioWebSocket.sendBinary(int16Data.buffer);
      };

      source.connect(this.processor);
      this.processor.connect(this.audioContext.destination);

      this.isStreaming = true;

      // Send start message
      audioWebSocket.send({ type: 'start' });
    } catch (error) {
      console.error('Error starting audio stream:', error);
      throw error;
    }
  }

  stop(): void {
    this.isStreaming = false;

    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    audioWebSocket.send({ type: 'stop' });
  }

  get streaming(): boolean {
    return this.isStreaming;
  }
}

export const audioStreamer = new AudioStreamer();
