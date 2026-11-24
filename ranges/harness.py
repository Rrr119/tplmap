"""Locate real template runtimes and spawn the three local target ranges.

The benchmark and the unittest module share this harness so the ranges can
be started on ephemeral ports and torn down deterministically. Runtime
locations can be overridden with environment variables:

TPLMAP_PHP   path to a PHP (>=8.0) binary with Twig installed
TPLMAP_JAVA  path to a Java (>=11) binary
TPLMAP_FM_JAR path to freemarker.jar
"""

import contextlib
import glob
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIMES = os.path.join(ROOT, ".runtimes")


def free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def php_binary():
    env = os.environ.get("TPLMAP_PHP")
    if env:
        return env
    bundled = os.path.join(RUNTIMES, "php")
    if os.path.exists(bundled) and os.access(bundled, os.X_OK):
        return bundled
    return shutil.which("php")


def java_binary():
    env = os.environ.get("TPLMAP_JAVA")
    if env:
        return env
    matches = sorted(glob.glob(os.path.join(RUNTIMES, "jdk*", "bin", "java")))
    # Prefer a full JDK (sibling javac present) over a JRE-only tarball.
    for candidate in matches:
        if os.path.exists(os.path.join(os.path.dirname(candidate), "javac")):
            return candidate
    if matches:
        return matches[0]
    return shutil.which("java")


def javac_binary():
    env = os.environ.get("TPLMAP_JAVAC")
    if env:
        return env
    matches = sorted(glob.glob(os.path.join(RUNTIMES, "jdk*", "bin", "javac")))
    if matches:
        return matches[0]
    return shutil.which("javac")


def freemarker_jar():
    env = os.environ.get("TPLMAP_FM_JAR")
    if env:
        return env
    bundled = os.path.join(RUNTIMES, "freemarker.jar")
    return bundled if os.path.exists(bundled) else None


FREEMARKER_SOURCE = os.path.join(
    ROOT, "ranges", "freemarker_range", "FreemarkerRange.java"
)
FREEMARKER_CLASSES = os.path.join(RUNTIMES, "classes")


def ensure_freemarker_compiled():
    """Compile the FreeMarker range when needed; return the classes dir."""

    class_file = os.path.join(FREEMARKER_CLASSES, "FreemarkerRange.class")
    needs_compile = not os.path.exists(class_file) or (
        os.path.exists(FREEMARKER_SOURCE)
        and os.path.getmtime(FREEMARKER_SOURCE) > os.path.getmtime(class_file)
    )

    if needs_compile:
        javac = javac_binary()
        jar = freemarker_jar()
        if not javac or not jar:
            raise RuntimeError("javac and freemarker.jar are required to build the range")
        os.makedirs(FREEMARKER_CLASSES, exist_ok=True)
        subprocess.check_call(
            [javac, "-cp", jar, "-d", FREEMARKER_CLASSES, FREEMARKER_SOURCE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    return FREEMARKER_CLASSES


def twig_autoload():
    path = os.path.join(ROOT, "ranges", "twig_range", "vendor", "autoload.php")
    return path if os.path.exists(path) else None


def jinja2_available():
    try:
        import jinja2  # noqa: F401

        return True
    except ImportError:
        return False


def availability():
    """Report which of the three ranges can run on this machine."""

    php = php_binary()
    java = java_binary()
    jar = freemarker_jar()
    return {
        "jinja2": jinja2_available(),
        "twig": bool(php and twig_autoload()),
        "freemarker": bool(java and jar),
        "php_binary": php,
        "java_binary": java,
        "freemarker_jar": jar,
        "twig_autoload": twig_autoload(),
    }


def wait_health(base_url, timeout=90.0):
    deadline = time.time() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_error = None
    while time.time() < deadline:
        try:
            with opener.open(base_url + "/health", timeout=2) as response:
                if response.status == 200 and response.read().decode().strip() == "ok":
                    return True
        except Exception as error:  # server not up yet
            last_error = error
            time.sleep(0.4)
    raise RuntimeError("range at %s did not become healthy: %s" % (base_url, last_error))


class RangeProcess:
    def __init__(self, name, argv, port, log_path=None, cwd=None):
        self.name = name
        self.argv = argv
        self.port = port
        self.base_url = "http://127.0.0.1:%i" % port
        self.log_path = log_path or os.path.join(tempfile.gettempdir(), "tplmap_range_%s.log" % name)
        self.cwd = cwd
        self._proc = None
        self._log = None

    def start(self):
        self._log = open(self.log_path, "ab")
        self._proc = subprocess.Popen(
            self.argv,
            cwd=self.cwd,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        wait_health(self.base_url)
        return self

    def stop(self):
        if self._proc is None:
            return
        if self._proc.poll() is None:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                self._proc.terminate()
            try:
                self._proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    self._proc.kill()
        if self._log:
            self._log.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def spawn_jinja2(port=None):
    if not jinja2_available():
        raise RuntimeError("jinja2 is not installed for %s" % sys.executable)
    port = port or free_port()
    script = os.path.join(ROOT, "ranges", "jinja2_range.py")
    return RangeProcess(
        "jinja2",
        [sys.executable, script, "--port", str(port)],
        port,
        cwd=ROOT,
    )


def spawn_twig(port=None):
    php = php_binary()
    autoload = twig_autoload()
    if not php or not autoload:
        raise RuntimeError("PHP/Twig runtime is not available")
    port = port or free_port()
    router = os.path.join(ROOT, "ranges", "twig_range", "router.php")
    return RangeProcess(
        "twig",
        [php, "-S", "127.0.0.1:%i" % port, router],
        port,
        cwd=os.path.dirname(router),
    )


def spawn_freemarker(port=None):
    java = java_binary()
    jar = freemarker_jar()
    if not java or not jar:
        raise RuntimeError("Java/FreeMarker runtime is not available")
    port = port or free_port()

    # Prefer precompiled classes (fast startup, works on a JRE too); fall
    # back to single-file source launch which requires a full JDK.
    argv = [java, "-Dfile.encoding=UTF-8"]
    try:
        classes = ensure_freemarker_compiled()
        classpath = jar + os.pathsep + classes
        argv += ["-cp", classpath, "FreemarkerRange", "--port", str(port)]
    except Exception:
        argv += ["-cp", jar, FREEMARKER_SOURCE, "--port", str(port)]

    return RangeProcess("freemarker", argv, port, cwd=ROOT)


SPAWNERS = {
    "jinja2": spawn_jinja2,
    "twig": spawn_twig,
    "freemarker": spawn_freemarker,
}


@contextlib.contextmanager
def spawn_all(only=None):
    """Start available ranges, yielding {engine: RangeProcess}; stop on exit."""

    info = availability()
    names = only or ("jinja2", "twig", "freemarker")
    processes = {}
    try:
        for name in names:
            if not info.get(name):
                continue
            processes[name] = SPAWNERS[name]().start()
        yield processes
    finally:
        for process in processes.values():
            process.stop()
