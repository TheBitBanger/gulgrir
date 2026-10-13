// Passes every request through to Django untouched, except /healthz (decision 0005).
import { createServer, request, type Server } from "node:http";

export function createFrontDoor(djangoOrigin: string): Server {
  const { hostname, port } = new URL(djangoOrigin);

  return createServer((req, res) => {
    if (req.method === "GET" && req.url === "/healthz") {
      const probe = request({ hostname, port, path: "/login/" }, (answer) => {
        answer.resume();
        const status = answer.statusCode ?? 500;
        res.writeHead(status < 500 ? 200 : 503, { "content-type": "text/plain" });
        res.end(status < 500 ? "ok\n" : `django answered ${status}\n`);
      });
      probe.on("error", (error) => {
        res.writeHead(503, { "content-type": "text/plain" });
        res.end(`django is down: ${error.message}\n`);
      });
      probe.end();
      return;
    }

    // Raw headers keep the client's Host, duplicates and order; Node adds no Host of its own.
    const headers = req.headers["x-forwarded-proto"]
      ? req.rawHeaders
      : [...req.rawHeaders, "X-Forwarded-Proto", "http"];
    const upstream = request(
      { hostname, port, method: req.method, path: req.url, headers },
      (answer) => {
        res.writeHead(answer.statusCode ?? 502, answer.statusMessage, answer.rawHeaders);
        answer.pipe(res);
      },
    );
    upstream.on("error", () => {
      if (res.headersSent) res.destroy();
      else res.writeHead(502).end();
    });
    req.pipe(upstream);
  });
}

if (import.meta.main) {
  const [listenPort, djangoOrigin] = process.argv.slice(2);
  createFrontDoor(djangoOrigin ?? "").listen(Number(listenPort), () =>
    console.error(`Front door listening on ${listenPort}, passing through to ${djangoOrigin}`),
  );
  // As PID 1, Node ignores SIGTERM unless it handles it.
  process.once("SIGTERM", () => process.exit(0));
}
