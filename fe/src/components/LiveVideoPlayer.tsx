import { useCallback, useMemo, useState } from "react";
import VideoPlayer from "./VideoPlayer";
import WebRTCPlayer from "./WebRTCPlayer";

interface Props {
  hlsUrl: string;
  mediaServerUrl: string;
  webrtcBaseUrl?: string;
}

type PlaybackMode = "connecting" | "webrtc" | "hls" | "error";

const getStreamName = (hlsUrl: string) => {
  const match = hlsUrl.match(/\/live\/([^/?#]+)(?:\/|$)/);
  return match?.[1] ?? null;
};

interface PlaybackProps extends Omit<Props, "webrtcBaseUrl"> {
  whepUrl: string | null;
}

const Playback = ({ hlsUrl, mediaServerUrl, whepUrl }: PlaybackProps) => {
  const [mode, setMode] = useState<PlaybackMode>(whepUrl ? "connecting" : "hls");

  const handleWebRTCConnected = useCallback(() => setMode("webrtc"), []);
  const handleWebRTCError = useCallback(() => setMode("hls"), []);
  const handleHLSError = useCallback(() => setMode("error"), []);

  const statusLabel: Record<PlaybackMode, string> = {
    connecting: "WebRTC 연결 중",
    webrtc: "WebRTC",
    hls: whepUrl ? "HLS 전환" : "HLS",
    error: "재생 오류",
  };

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", background: "#000" }}>
      {(mode === "connecting" || mode === "webrtc") && whepUrl ? (
        <WebRTCPlayer
          whepUrl={whepUrl}
          onConnected={handleWebRTCConnected}
          onError={handleWebRTCError}
        />
      ) : (
        <VideoPlayer
          hlsUrl={hlsUrl}
          mediaServerUrl={mediaServerUrl}
          onError={handleHLSError}
        />
      )}
      <span
        style={{
          position: "absolute",
          right: 8,
          bottom: 8,
          padding: "2px 6px",
          borderRadius: 3,
          background: "rgba(0,0,0,.55)",
          color: mode === "error" ? "#fca5a5" : "rgba(255,255,255,.8)",
          fontSize: 10,
          pointerEvents: "none",
        }}
      >
        {statusLabel[mode]}
      </span>
    </div>
  );
};

const LiveVideoPlayer = ({ hlsUrl, mediaServerUrl, webrtcBaseUrl = "" }: Props) => {
  const whepUrl = useMemo(() => {
    const streamName = getStreamName(hlsUrl);
    if (!webrtcBaseUrl || !streamName) return null;
    return `${webrtcBaseUrl.replace(/\/$/, "")}/live/${encodeURIComponent(streamName)}/whep`;
  }, [hlsUrl, webrtcBaseUrl]);

  return (
    <Playback
      key={`${hlsUrl}:${whepUrl ?? "hls"}`}
      hlsUrl={hlsUrl}
      mediaServerUrl={mediaServerUrl}
      whepUrl={whepUrl}
    />
  );
};

export default LiveVideoPlayer;
