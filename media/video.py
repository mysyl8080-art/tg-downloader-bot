"""Video tools: convert, compress, trim, gif, merge, remove/replace audio, speed."""
import os

from .ffmpeg_base import run, safe_out, parse_time, MediaError

CONTAINERS = {"mp4": [], "mkv": [], "avi": ["-c:v", "mpeg4", "-q:v", "5"]}


def convert(src, workdir, container):
    out = safe_out(workdir, f"converted.{container}")
    if container == "avi":
        run(["ffmpeg", "-y", "-i", src] + CONTAINERS["avi"] + ["-c:a", "libmp3lame", out])
    else:
        run(["ffmpeg", "-y", "-i", src, "-c", "copy", out])
    return out


def trim(src, workdir, start, end=None):
    # Re-encode: stream-copy trimming snaps to keyframes and can cut seconds off-target.
    st = parse_time(start)
    out = safe_out(workdir, "trimmed.mp4")
    cmd = ["ffmpeg", "-y", "-ss", f"{st:.3f}", "-i", src]
    if end is not None:
        dur = parse_time(end) - st
        if dur <= 0:
            raise MediaError("badtime")
        cmd += ["-t", f"{dur:.3f}"]
    run(cmd + ["-c:v", "libx264", "-preset", "fast", "-crf", "20",
               "-c:a", "aac", "-b:a", "128k", out])
    return out


def compress(src, workdir, target_height=480, crf=28):
    out = safe_out(workdir, "compressed.mp4")
    run(["ffmpeg", "-y", "-i", src,
         "-vf", f"scale=-2:{int(target_height)}", "-c:v", "libx264",
         "-preset", "fast", "-crf", str(crf), "-c:a", "aac", "-b:a", "96k", out])
    return out


def to_gif(src, workdir, start=0.0, dur=5.0, width=480):
    out = safe_out(workdir, "clip.gif")
    run(["ffmpeg", "-y", "-ss", f"{float(start):.3f}", "-t", f"{float(dur):.3f}", "-i", src,
         "-vf", f"fps=12,scale={int(width)}:-1:flags=lanczos", "-loop", "0", out])
    return out


def merge_audio_video(video, audio, workdir):
    out = safe_out(workdir, "merged.mp4")
    run(["ffmpeg", "-y", "-i", video, "-i", audio,
         "-c:v", "copy", "-c:a", "aac", "-shortest", out])
    return out


def remove_audio(src, workdir):
    out = safe_out(workdir, "muted" + os.path.splitext(src)[1])
    run(["ffmpeg", "-y", "-i", src, "-an", "-c:v", "copy", out])
    return out


def replace_audio(video, audio, workdir):
    return merge_audio_video(video, audio, workdir)


def change_speed(src, workdir, factor):
    factor = float(factor)
    if not (0.25 <= factor <= 4.0):
        raise ValueError("speed 0.25-4")
    out = safe_out(workdir, "speed.mp4")
    atempo = factor
    # atempo supports 0.5-100; chain for <0.5
    af = f"atempo={atempo}" if atempo >= 0.5 else "atempo=0.5,atempo=" + str(atempo / 0.5)
    run(["ffmpeg", "-y", "-i", src, "-filter_complex",
         f"[0:v]setpts=PTS/{factor}[v];[0:a]{af}[a]",
         "-map", "[v]", "-map", "[a]", out])
    return out
