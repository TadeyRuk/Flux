"""Process monitoring — CPU, RAM, GPU usage per process."""

import os
import psutil
import subprocess

# Prime the CPU percent baseline on import so first real call has data
psutil.cpu_percent(interval=None)
for proc in psutil.process_iter(["cpu_percent"]):
    pass


def get_top_processes(count=20):
    """Get top processes sorted by CPU usage.
    Returns list of dicts: {pid, name, cpu, mem}.
    Filters out kernel threads (no exe or pid 0).
    """
    procs = []
    for proc in psutil.process_iter(["pid", "name", "ppid", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
            pid = info["pid"]
            if pid <= 2 or info["cpu_percent"] is None:
                continue
            # Skip kernel threads (children of kthreadd, pid 2)
            if info.get("ppid") == 2:
                continue
            # Skip processes with no exe (zombie/kernel)
            try:
                if not proc.exe():
                    continue
            except (psutil.AccessDenied, psutil.ZombieProcess):
                pass
            procs.append({
                "pid": pid,
                "name": info["name"] or "unknown",
                "cpu": info["cpu_percent"],
                "mem": info["memory_percent"] or 0.0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort by CPU, take top N
    procs.sort(key=lambda p: p["cpu"], reverse=True)
    return procs[:count]


def get_nvidia_gpu_processes():
    """Get per-process GPU memory from nvidia-smi.
    Returns dict {pid: gpu_mem_mb}.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {}
        usage = {}
        for line in result.stdout.strip().splitlines():
            parts = line.split(",")
            if len(parts) == 2:
                pid = int(parts[0].strip())
                mem = float(parts[1].strip())
                usage[pid] = mem
        return usage
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return {}


def get_system_usage():
    """Get overall system usage."""
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()

    return {
        "cpu_percent": cpu,
        "cpu_per_core": psutil.cpu_percent(percpu=True),
        "mem_total_gb": mem.total / (1024 ** 3),
        "mem_used_gb": mem.used / (1024 ** 3),
        "mem_percent": mem.percent,
        "swap_percent": psutil.swap_memory().percent,
    }


def is_os_process(pid):
    """Check if a process is tied to the OS or crucial to the system."""
    if pid <= 2:
        return True
    try:
        p = psutil.Process(pid)
        # Check parent is kthreadd (pid 2)
        if p.ppid() == 2:
            return True
        # Check run as root and systemd child (pid 1)
        if p.uids().real == 0 and p.ppid() == 1:
            return True
        # List of critical process names
        name = p.name().lower()
        if name in ('systemd', 'gnome-shell', 'xorg', 'wayland', 'dbus-daemon', 'sddm', 'gdm3', 'kwin_wayland', 'pipewire'):
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # Default to safe side if we can't inspect it
        pass
    return False

def suspend_process(pid):
    """Send SIGSTOP to a process."""
    try:
        p = psutil.Process(pid)
        p.suspend()
        return True, ""
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        return False, str(e)


def resume_process(pid):
    """Send SIGCONT to a process."""
    try:
        p = psutil.Process(pid)
        p.resume()
        return True, ""
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        return False, str(e)


def kill_process(pid):
    """Send SIGTERM, then SIGKILL if needed."""
    try:
        p = psutil.Process(pid)
        p.terminate()
        try:
            p.wait(timeout=3)
        except psutil.TimeoutExpired:
            p.kill()
        return True, ""
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        return False, str(e)
