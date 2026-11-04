import { useEffect, useRef } from "react";
import Hls from "hls.js";

interface Props {
  hlsUrl: string;
  mediaServerUrl: string;
  onReady?: () => void;
  onError?: (error: Error) => void;
}

const VideoPlayer = ({ hlsUrl, mediaServerUrl, onReady, onError }: Props) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !hlsUrl) return;

    const fullUrl = `${mediaServerUrl}${hlsUrl}`;

    if (Hls.isSupported()) {
      const hls = new Hls({
        lowLatencyMode: true,
        backBufferLength: 0,
        maxBufferLength: 4,
        maxMaxBufferLength: 8,
        liveSyncDurationCount: 2,
        liveMaxLatencyDurationCount: 4,
      });
      hls.loadSource(fullUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (video.duration === Infinity || isNaN(video.duration)) {
          video.currentTime = 1e10;
        }
        video.play().then(() => onReady?.()).catch((error) => onError?.(error));
      });
      hls.on(Hls.Events.LEVEL_LOADED, (_, data) => {
        if (data.details.live) {
          const liveEdge = data.details.totalduration - 2;
          if (video.currentTime < liveEdge) video.currentTime = liveEdge;
        }
      });
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) onError?.(new Error(`HLS ${data.type}: ${data.details}`));
      });
      return () => hls.destroy();
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = fullUrl;
      const handleLoaded = () => {
        video.play().then(() => onReady?.()).catch((error) => onError?.(error));
      };
      const handleError = () => onError?.(new Error("Native HLS playback failed"));
      video.addEventListener("loadedmetadata", handleLoaded);
      video.addEventListener("error", handleError);
      return () => {
        video.removeEventListener("loadedmetadata", handleLoaded);
        video.removeEventListener("error", handleError);
        video.removeAttribute("src");
        video.load();
      };
    }
  }, [hlsUrl, mediaServerUrl, onError, onReady]);

  return (
    <video
      ref={videoRef}
      style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }}
      muted
      playsInline
    />
  );
};

export default VideoPlayer;
