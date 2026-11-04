import argparse
import asyncio
import json
import os
import re
import statistics
import time
from pathlib import Path

from playwright.async_api import Browser, Page, async_playwright


DEFAULT_BROWSER_PATHS = (
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

MEMORY_UNITS_TO_MIB = {
    "B": 1 / (1024 * 1024),
    "KB": 1000 / (1024 * 1024),
    "KIB": 1 / 1024,
    "MB": 1_000_000 / (1024 * 1024),
    "MIB": 1,
    "GB": 1_000_000_000 / (1024 * 1024),
    "GIB": 1024,
}


def find_browser_executable() -> Path:
    configured = os.getenv("WEBRTC_BROWSER_EXECUTABLE")
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
        raise FileNotFoundError(f"Configured browser does not exist: {path}")

    for path in DEFAULT_BROWSER_PATHS:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Chrome or Edge was not found. Set WEBRTC_BROWSER_EXECUTABLE."
    )


def parse_memory_mib(memory_usage: str) -> float:
    used = memory_usage.split("/", maxsplit=1)[0].strip()
    match = re.fullmatch(r"([0-9.]+)\s*([A-Za-z]+)", used)
    if not match:
        raise ValueError(f"Unrecognized Docker memory value: {memory_usage}")
    value = float(match.group(1))
    unit = match.group(2).upper()
    if unit not in MEMORY_UNITS_TO_MIB:
        raise ValueError(f"Unrecognized Docker memory unit: {unit}")
    return value * MEMORY_UNITS_TO_MIB[unit]


async def collect_docker_stats(
    container_names: list[str],
    stop_event: asyncio.Event,
    stage_state: dict,
    interval_seconds: float = 1,
) -> list[dict]:
    samples = []
    started = time.perf_counter()
    last_sampled_at = {}
    process = await asyncio.create_subprocess_exec(
        "docker",
        "stats",
        "--format",
        "{{json .}}",
        *container_names,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        while True:
            line_task = asyncio.create_task(process.stdout.readline())
            stop_task = asyncio.create_task(stop_event.wait())
            done, pending = await asyncio.wait(
                (line_task, stop_task), return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            if stop_task in done and stop_task.result():
                break

            line = line_task.result()
            if not line:
                stderr = (await process.stderr.read()).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"docker stats stopped unexpectedly with code {process.returncode}: {stderr}"
                )

            decoded = line.decode("utf-8", errors="replace").strip()
            json_start = decoded.find("{")
            json_end = decoded.rfind("}")
            if json_start < 0 or json_end < json_start:
                continue
            item = json.loads(decoded[json_start : json_end + 1])
            elapsed_seconds = time.perf_counter() - started
            container_name = item["Name"]
            previous_sample = last_sampled_at.get(container_name)
            if (
                previous_sample is not None
                and elapsed_seconds - previous_sample < interval_seconds * 0.9
            ):
                continue
            last_sampled_at[container_name] = elapsed_seconds
            samples.append(
                {
                    "elapsed_seconds": round(elapsed_seconds, 2),
                    "phase": stage_state.get("phase", "idle"),
                    "peer_count": stage_state.get("peer_count"),
                    "repeat": stage_state.get("repeat"),
                    "containers": {
                        container_name: {
                            "cpu_percent": float(item["CPUPerc"].rstrip("%")),
                            "memory_mib": round(parse_memory_mib(item["MemUsage"]), 3),
                        }
                    },
                }
            )
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()

    sampled_names = {
        name for sample in samples for name in sample["containers"].keys()
    }
    missing = sorted(set(container_names) - sampled_names)
    if missing:
        raise RuntimeError(f"Docker stats missing containers: {', '.join(missing)}")
    if not samples:
        raise RuntimeError("Docker stats produced no samples")

    return samples


def summarize_docker_stats(samples: list[dict]) -> dict:
    container_names = sorted(
        {
            name
            for sample in samples
            for name in sample.get("containers", {}).keys()
        }
    )
    summaries = {}
    for name in container_names:
        cpu_values = [
            sample["containers"][name]["cpu_percent"]
            for sample in samples
            if name in sample["containers"]
        ]
        memory_values = [
            sample["containers"][name]["memory_mib"]
            for sample in samples
            if name in sample["containers"]
        ]
        named_samples = [
            sample for sample in samples if name in sample["containers"]
        ]
        intervals = [
            current["elapsed_seconds"] - previous["elapsed_seconds"]
            for previous, current in zip(named_samples, named_samples[1:])
            if current.get("phase") == previous.get("phase")
            and current.get("repeat") == previous.get("repeat")
            and current.get("peer_count") == previous.get("peer_count")
        ]
        summaries[name] = {
            "sample_count": len(cpu_values),
            "sample_interval_average_seconds": (
                round(statistics.mean(intervals), 2) if intervals else None
            ),
            "cpu_average_percent": round(statistics.mean(cpu_values), 2),
            "cpu_max_percent": round(max(cpu_values), 2),
            "memory_average_mib": round(statistics.mean(memory_values), 2),
            "memory_max_mib": round(max(memory_values), 2),
        }
    return summaries


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction


def build_comparison_summary(stages: list[dict], samples: list[dict]) -> list[dict]:
    summaries = []
    peer_counts = sorted({stage["peer_count"] for stage in stages})
    for peer_count in peer_counts:
        matching_stages = [
            stage for stage in stages if stage["peer_count"] == peer_count
        ]
        peers = [peer for stage in matching_stages for peer in stage["peers"]]
        successful_peers = [peer for peer in peers if peer["success"]]
        first_frame_values = [
            peer["first_frame_ms"] for peer in successful_peers
        ]
        matching_samples = [
            sample
            for sample in samples
            if sample.get("phase") == "measurement"
            and sample.get("peer_count") == peer_count
        ]
        resource_summary = (
            summarize_docker_stats(matching_samples) if matching_samples else {}
        )
        summaries.append(
            {
                "peer_count": peer_count,
                "repeat_count": len(matching_stages),
                "attempt_count": len(peers),
                "success_count": len(successful_peers),
                "failure_count": len(peers) - len(successful_peers),
                "success_rate_percent": round(
                    len(successful_peers) / len(peers) * 100, 1
                ),
                "first_frame_median_ms": (
                    round(statistics.median(first_frame_values), 1)
                    if first_frame_values
                    else None
                ),
                "first_frame_p95_ms": (
                    round(percentile(first_frame_values, 0.95), 1)
                    if first_frame_values
                    else None
                ),
                "resource_summary": resource_summary,
            }
        )
    return summaries


async def wait_for_video_playback(page: Page, timeout_ms: int) -> None:
    await page.wait_for_selector("video", state="attached", timeout=timeout_ms)
    await page.wait_for_function(
        """
        () => {
          const video = document.querySelector('video');
          return video && !video.paused && video.readyState >= 2 && video.currentTime > 0;
        }
        """,
        timeout=timeout_ms,
    )


async def verify_peer(
    browser: Browser,
    peer_number: int,
    url: str,
    timeout_ms: int,
    playback_seconds: float,
) -> dict:
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    started = time.perf_counter()

    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if response is None or not response.ok:
            status = None if response is None else response.status
            raise RuntimeError(f"player page returned HTTP {status}")

        await wait_for_video_playback(page, timeout_ms)
        first_frame_ms = round((time.perf_counter() - started) * 1000, 1)
        initial = await page.locator("video").evaluate(
            "video => ({ currentTime: video.currentTime, readyState: video.readyState, paused: video.paused })"
        )
        await page.wait_for_timeout(playback_seconds * 1000)
        final = await page.locator("video").evaluate(
            "video => ({ currentTime: video.currentTime, readyState: video.readyState, paused: video.paused })"
        )

        progress = final["currentTime"] - initial["currentTime"]
        minimum_progress = max(0.5, playback_seconds * 0.5)
        if final["paused"] or final["readyState"] < 2 or progress < minimum_progress:
            raise RuntimeError(
                f"video did not keep playing: progress={progress:.2f}s, "
                f"readyState={final['readyState']}, paused={final['paused']}"
            )

        return {
            "peer": peer_number,
            "url": url,
            "success": True,
            "first_frame_ms": first_frame_ms,
            "playback_progress_seconds": round(progress, 2),
            "ready_state": final["readyState"],
        }
    except Exception as exc:
        return {
            "peer": peer_number,
            "url": url,
            "success": False,
            "error": str(exc),
        }
    finally:
        await context.close()


async def run_stage(
    browser: Browser,
    peer_count: int,
    base_url: str,
    stream_keys: list[str],
    timeout_ms: int,
    playback_seconds: float,
) -> dict:
    tasks = []
    for index in range(peer_count):
        stream_key = stream_keys[index % len(stream_keys)]
        url = f"{base_url.rstrip('/')}/live/{stream_key}/"
        tasks.append(
            verify_peer(
                browser,
                peer_number=index + 1,
                url=url,
                timeout_ms=timeout_ms,
                playback_seconds=playback_seconds,
            )
        )

    started = time.perf_counter()
    peers = await asyncio.gather(*tasks)
    elapsed_seconds = round(time.perf_counter() - started, 2)
    successful = [peer for peer in peers if peer["success"]]
    first_frame_values = [peer["first_frame_ms"] for peer in successful]

    return {
        "peer_count": peer_count,
        "success_count": len(successful),
        "failure_count": peer_count - len(successful),
        "success_rate_percent": round(len(successful) / peer_count * 100, 1),
        "first_frame_average_ms": (
            round(statistics.mean(first_frame_values), 1)
            if first_frame_values
            else None
        ),
        "first_frame_max_ms": max(first_frame_values) if first_frame_values else None,
        "stage_elapsed_seconds": elapsed_seconds,
        "peers": peers,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify real MediaMTX WebRTC playback with concurrent browser peers."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8889")
    parser.add_argument("--stream-keys", nargs="+", required=True)
    parser.add_argument("--peer-counts", nargs="+", type=int, default=[1, 3, 5])
    parser.add_argument("--repeat-count", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=20)
    parser.add_argument("--playback-seconds", type=float, default=2)
    parser.add_argument("--docker-containers", nargs="+")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    if any(count < 1 for count in args.peer_counts):
        parser.error("peer counts must be positive")
    if args.repeat_count < 1:
        parser.error("repeat count must be positive")
    if args.playback_seconds <= 0 or args.timeout_seconds <= 0:
        parser.error("timeouts must be positive")

    browser_path = find_browser_executable()
    report = {
        "browser": str(browser_path),
        "base_url": args.base_url,
        "stream_keys": args.stream_keys,
        "repeat_count": args.repeat_count,
        "stages": [],
    }

    stats_stop_event = asyncio.Event()
    stage_state = {"phase": "idle", "peer_count": None, "repeat": None}
    stats_task = None
    if args.docker_containers:
        stats_task = asyncio.create_task(
            collect_docker_stats(
                args.docker_containers, stats_stop_event, stage_state
            )
        )

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=str(browser_path),
                headless=True,
                args=[
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                ],
            )
            try:
                warmup_peer_count = min(args.peer_counts)
                stage_state.update(
                    phase="warmup", peer_count=warmup_peer_count, repeat=0
                )
                report["warmup"] = await run_stage(
                    browser=browser,
                    peer_count=warmup_peer_count,
                    base_url=args.base_url,
                    stream_keys=args.stream_keys,
                    timeout_ms=int(args.timeout_seconds * 1000),
                    playback_seconds=args.playback_seconds,
                )
                stage_state.update(phase="idle", peer_count=None, repeat=None)
                print(
                    f"warmup peers={warmup_peer_count} "
                    f"success={report['warmup']['success_count']}/{warmup_peer_count}"
                )

                peer_counts = list(dict.fromkeys(args.peer_counts))
                for repeat_index in range(1, args.repeat_count + 1):
                    offset = (repeat_index - 1) % len(peer_counts)
                    ordered_peer_counts = peer_counts[offset:] + peer_counts[:offset]
                    for peer_count in ordered_peer_counts:
                        stage_state.update(
                            phase="measurement",
                            peer_count=peer_count,
                            repeat=repeat_index,
                        )
                        stage = await run_stage(
                            browser=browser,
                            peer_count=peer_count,
                            base_url=args.base_url,
                            stream_keys=args.stream_keys,
                            timeout_ms=int(args.timeout_seconds * 1000),
                            playback_seconds=args.playback_seconds,
                        )
                        stage["repeat"] = repeat_index
                        report["stages"].append(stage)
                        stage_state.update(
                            phase="idle", peer_count=None, repeat=None
                        )
                        print(
                            f"repeat={repeat_index} peers={peer_count} "
                            f"success={stage['success_count']}/{peer_count} "
                            f"first_frame_avg={stage['first_frame_average_ms']}ms "
                            f"first_frame_max={stage['first_frame_max_ms']}ms"
                        )
                        for peer in stage["peers"]:
                            if not peer["success"]:
                                print(
                                    f"  peer {peer['peer']} failed: {peer['error']}"
                                )
            finally:
                stage_state.update(phase="idle", peer_count=None, repeat=None)
                await browser.close()
    finally:
        if stats_task:
            stats_stop_event.set()
            samples = await stats_task
            report["resource_samples"] = samples
            report["resource_summary"] = summarize_docker_stats(samples)
            report["comparison_summary"] = build_comparison_summary(
                report["stages"], samples
            )
            print("resource summary:")
            for name, summary in report["resource_summary"].items():
                print(
                    f"  {name}: samples={summary['sample_count']} "
                    f"interval_avg={summary['sample_interval_average_seconds']}s "
                    f"cpu_avg={summary['cpu_average_percent']}% "
                    f"cpu_max={summary['cpu_max_percent']}% "
                    f"memory_avg={summary['memory_average_mib']}MiB "
                    f"memory_max={summary['memory_max_mib']}MiB"
                )
            print("comparison summary:")
            for comparison in report["comparison_summary"]:
                resource = next(
                    iter(comparison["resource_summary"].values()), {}
                )
                print(
                    f"  peers={comparison['peer_count']} "
                    f"success={comparison['success_count']}/{comparison['attempt_count']} "
                    f"median={comparison['first_frame_median_ms']}ms "
                    f"p95={comparison['first_frame_p95_ms']}ms "
                    f"cpu_avg={resource.get('cpu_average_percent')}% "
                    f"cpu_max={resource.get('cpu_max_percent')}% "
                    f"memory_avg={resource.get('memory_average_mib')}MiB "
                    f"memory_max={resource.get('memory_max_mib')}MiB"
                )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    all_stages_passed = all(
        stage["failure_count"] == 0 for stage in report["stages"]
    )
    warmup_passed = report.get("warmup", {}).get("failure_count", 1) == 0
    return 0 if all_stages_passed and warmup_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
