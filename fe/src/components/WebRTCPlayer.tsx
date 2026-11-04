import { useEffect, useRef } from "react";

interface Props {
  whepUrl: string;
  onConnected?: () => void;
  onError?: (error: Error) => void;
  playbackTimeoutMs?: number;
}

const WebRTCPlayer = ({
  whepUrl,
  onConnected,
  onError,
  playbackTimeoutMs = 15_000,
}: Props) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);

  useEffect(() => {
    if (!whepUrl || !videoRef.current) return;

    const video = videoRef.current;
    const pc = new RTCPeerConnection({ iceServers: [] });
    const abortController = new AbortController();
    let cancelled = false;
    let failed = false;
    let sessionUrl: string | null = null;
    let disconnectTimer: ReturnType<typeof setTimeout> | null = null;
    pcRef.current = pc;

    const fail = (reason: unknown) => {
      if (cancelled || failed) return;
      failed = true;
      const error = reason instanceof Error ? reason : new Error(String(reason));
      console.error("[WebRTCPlayer] failed:", error);
      onError?.(error);
    };

    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });

    pc.ontrack = (e) => {
      video.srcObject = e.streams[0] ?? new MediaStream([e.track]);
    };

    pc.onconnectionstatechange = () => {
      if (disconnectTimer) {
        clearTimeout(disconnectTimer);
        disconnectTimer = null;
      }

      if (pc.connectionState === "failed") {
        fail(new Error("WebRTC connection failed"));
      } else if (pc.connectionState === "disconnected") {
        disconnectTimer = setTimeout(() => {
          if (pc.connectionState === "disconnected") {
            fail(new Error("WebRTC connection remained disconnected"));
          }
        }, 3_000);
      }
    };

    const waitForIceGathering = () => new Promise<void>((resolve, reject) => {
      if (pc.iceGatheringState === "complete") {
        resolve();
        return;
      }

      const timeout = setTimeout(() => {
        pc.removeEventListener("icegatheringstatechange", handleChange);
        reject(new Error("ICE gathering timed out"));
      }, 5_000);
      const handleChange = () => {
        if (pc.iceGatheringState === "complete") {
          clearTimeout(timeout);
          pc.removeEventListener("icegatheringstatechange", handleChange);
          resolve();
        }
      };
      pc.addEventListener("icegatheringstatechange", handleChange);
    });

    const waitForPlayback = () => new Promise<void>((resolve, reject) => {
      if (!video.paused && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        resolve();
        return;
      }

      const timeout = setTimeout(() => {
        video.removeEventListener("playing", handlePlaying);
        reject(new Error("WebRTC playback timed out"));
      }, playbackTimeoutMs);
      const handlePlaying = () => {
        clearTimeout(timeout);
        video.removeEventListener("playing", handlePlaying);
        resolve();
      };
      video.addEventListener("playing", handlePlaying);
    });

    (async () => {
      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        await waitForIceGathering();

        const res = await fetch(whepUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/sdp",
            Accept: "application/sdp",
          },
          body: pc.localDescription?.sdp,
          signal: abortController.signal,
        });
        if (!res.ok) throw new Error(`WHEP ${res.status}`);
        const location = res.headers.get("Location");
        if (location) sessionUrl = new URL(location, whepUrl).toString();
        const sdp = await res.text();
        await pc.setRemoteDescription({ type: "answer", sdp });
        const playback = waitForPlayback();
        await video.play();
        await playback;
        if (!cancelled) onConnected?.();
      } catch (err) {
        if (!abortController.signal.aborted) fail(err);
      }
    })();

    return () => {
      cancelled = true;
      abortController.abort();
      if (disconnectTimer) clearTimeout(disconnectTimer);
      const stream = video.srcObject;
      if (stream instanceof MediaStream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      video.srcObject = null;
      pc.close();
      pcRef.current = null;
      if (sessionUrl) {
        fetch(sessionUrl, { method: "DELETE", keepalive: true }).catch(() => {});
      }
    };
  }, [onConnected, onError, playbackTimeoutMs, whepUrl]);

  return (
    <video
      ref={videoRef}
      style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }}
      autoPlay
      muted
      playsInline
    />
  );
};

export default WebRTCPlayer;
