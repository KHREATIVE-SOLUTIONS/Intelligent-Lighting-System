import { useEffect, useRef, useCallback } from 'react';

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  autoConnect?: boolean;
  reconnect?: boolean;
  reconnectInterval?: number;
}

export function useWebSocket({
  url,
  onMessage,
  onOpen,
  onClose,
  onError,
  autoConnect = true,
  reconnect = true,
  reconnectInterval = 3000,
}: UseWebSocketOptions) {
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const socket = new WebSocket(url);

    socket.onopen = () => {
      console.log('WebSocket connected');
      onOpen?.();
    };

    socket.onclose = () => {
      console.log('WebSocket disconnected');
      onClose?.();

      if (reconnect) {
        reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
      }
    };

    socket.onerror = (event) => {
      console.error('WebSocket error:', event);
      onError?.(event);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage?.(data);
      } catch {
        onMessage?.(event.data);
      }
    };

    socketRef.current = socket;
  }, [url, onMessage, onOpen, onClose, onError, reconnect, reconnectInterval]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
  }, []);

  const send = useCallback((data: unknown) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(
        typeof data === 'string' ? data : JSON.stringify(data)
      );
    } else {
      console.warn('WebSocket not connected');
    }
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(data);
    } else {
      console.warn('WebSocket not connected');
    }
  }, []);

  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  return {
    connect,
    disconnect,
    send,
    sendBinary,
    isConnected: socketRef.current?.readyState === WebSocket.OPEN,
  };
}
