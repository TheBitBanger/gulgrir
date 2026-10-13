import {
  createServer,
  type IncomingMessage,
  request,
  type Server,
  type ServerResponse,
} from "node:http";
import type { AddressInfo } from "node:net";
import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it } from "vitest";
import { createFrontDoor } from "../src/front-door.ts";

interface Seen {
  method: string;
  url: string;
  headers: IncomingMessage["headers"];
  body: string;
}

const open: Server[] = [];

afterEach(async () => {
  await Promise.all(open.splice(0).map((s) => new Promise((done) => s.close(done))));
});

const listen = async (server: Server): Promise<number> => {
  open.push(server);
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  return (server.address() as AddressInfo).port;
};

// A stand-in for Django: records what reached it and answers with `answer`.
const fakeDjango = async (answer: (res: ServerResponse) => void) => {
  const seen: Seen[] = [];
  const port = await listen(
    createServer((req, res) => {
      const chunks: Buffer[] = [];
      req.on("data", (c: Buffer) => chunks.push(c));
      req.on("end", () => {
        seen.push({
          method: req.method!,
          url: req.url!,
          headers: req.headers,
          body: Buffer.concat(chunks).toString(),
        });
        answer(res);
      });
    }),
  );
  return { seen, origin: `http://127.0.0.1:${port}` };
};

// A port nothing listens on.
const closedOrigin = async () => {
  const server = createServer();
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  const { port } = server.address() as AddressInfo;
  await new Promise((done) => server.close(done));
  return `http://127.0.0.1:${port}`;
};

const frontDoor = (djangoOrigin: string) => listen(createFrontDoor(djangoOrigin));

// node:http on the client side too: fetch would follow redirects and decompress bodies.
const send = (
  port: number,
  opts: { method?: string; path: string; headers?: Record<string, string>; body?: string },
) =>
  new Promise<{ status: number; headers: IncomingMessage["headers"]; body: Buffer }>(
    (done, fail) => {
      const req = request(
        {
          host: "127.0.0.1",
          port,
          method: opts.method ?? "GET",
          path: opts.path,
          headers: opts.headers,
        },
        (res) => {
          const chunks: Buffer[] = [];
          res.on("data", (c: Buffer) => chunks.push(c));
          res.on("end", () =>
            done({ status: res.statusCode!, headers: res.headers, body: Buffer.concat(chunks) }),
          );
        },
      );
      req.on("error", fail);
      req.end(opts.body);
    },
  );

describe("a path the new app does not serve reaches Django (SYS-V8)", () => {
  it("passes method, path, query, headers and body through, and Django's answer back", async () => {
    const django = await fakeDjango((res) => {
      res.writeHead(201, { "content-type": "text/plain", "x-django": "yes" });
      res.end("created");
    });
    const port = await frontDoor(django.origin);

    const res = await send(port, {
      method: "POST",
      path: "/library/42/?q=a%20b&tag=x",
      headers: { "content-type": "application/x-www-form-urlencoded", "x-client": "c1" },
      body: "title=Dune&year=1965",
    });

    expect(django.seen).toHaveLength(1);
    const [seen] = django.seen;
    expect(seen!.method).toBe("POST");
    expect(seen!.url).toBe("/library/42/?q=a%20b&tag=x");
    expect(seen!.headers["content-type"]).toBe("application/x-www-form-urlencoded");
    expect(seen!.headers["x-client"]).toBe("c1");
    expect(seen!.body).toBe("title=Dune&year=1965");

    expect(res.status).toBe(201);
    expect(res.headers["content-type"]).toBe("text/plain");
    expect(res.headers["x-django"]).toBe("yes");
    expect(res.body.toString()).toBe("created");
  });

  it("keeps every Set-Cookie header separate", async () => {
    const django = await fakeDjango((res) => {
      res.writeHead(200, {
        "set-cookie": ["sessionid=abc; HttpOnly; Path=/", "csrftoken=xyz; Path=/"],
      });
      res.end();
    });
    const port = await frontDoor(django.origin);

    const res = await send(port, { path: "/login/" });

    expect(res.headers["set-cookie"]).toEqual([
      "sessionid=abc; HttpOnly; Path=/",
      "csrftoken=xyz; Path=/",
    ]);
  });

  it("hands redirects to the client instead of following them", async () => {
    const django = await fakeDjango((res) => {
      if (res.req.url === "/login/") res.writeHead(302, { location: "/library/" });
      res.end();
    });
    const port = await frontDoor(django.origin);

    const res = await send(port, { method: "POST", path: "/login/", body: "u=a&p=b" });

    expect(res.status).toBe(302);
    expect(res.headers.location).toBe("/library/");
    expect(django.seen).toHaveLength(1);
  });

  it("passes a compressed body through byte for byte", async () => {
    const gzipped = gzipSync("<html>library</html>");
    const django = await fakeDjango((res) => {
      res.writeHead(200, { "content-encoding": "gzip", "content-type": "text/html" });
      res.end(gzipped);
    });
    const port = await frontDoor(django.origin);

    const res = await send(port, { path: "/library/", headers: { "accept-encoding": "gzip" } });

    expect(res.headers["content-encoding"]).toBe("gzip");
    expect(res.body.equals(gzipped)).toBe(true);
  });
});

describe("Django sees the request as the client sent it (SYS-V9)", () => {
  const ok = (res: ServerResponse) => res.end();

  it("keeps the client's Host and X-Forwarded-Proto", async () => {
    const django = await fakeDjango(ok);
    const port = await frontDoor(django.origin);

    await send(port, {
      path: "/",
      headers: { host: "gulgrir.example.org", "x-forwarded-proto": "https" },
    });

    expect(django.seen[0]!.headers.host).toBe("gulgrir.example.org");
    expect(django.seen[0]!.headers["x-forwarded-proto"]).toBe("https");
  });

  it("sets X-Forwarded-Proto to http when the client sent none", async () => {
    const django = await fakeDjango(ok);
    const port = await frontDoor(django.origin);

    await send(port, { path: "/" });

    expect(django.seen[0]!.headers["x-forwarded-proto"]).toBe("http");
  });
});

describe("Django not answering (SYS-V10)", () => {
  it("gives the client a 502 at once when Django refuses the connection", async () => {
    const port = await frontDoor(await closedOrigin());

    const started = Date.now();
    const res = await send(port, { path: "/library/" });

    expect(res.status).toBe(502);
    expect(Date.now() - started).toBeLessThan(1000);
  });
});

describe("GET /healthz (SYS-V11)", () => {
  it("is answered by the new app with 200 while Django answers", async () => {
    // Django answers every path, /healthz included, with 418; a 200 can only come from the new app.
    const django = await fakeDjango((res) => {
      res.writeHead(418);
      res.end();
    });
    const port = await frontDoor(django.origin);

    const res = await send(port, { path: "/healthz" });

    expect(res.status).toBe(200);
    expect(django.seen.map((s) => s.url)).not.toContain("/healthz");
  });

  it("answers 503 naming Django when Django answers 5xx", async () => {
    const django = await fakeDjango((res) => {
      res.writeHead(500);
      res.end();
    });
    const port = await frontDoor(django.origin);

    const res = await send(port, { path: "/healthz" });

    expect(res.status).toBe(503);
    expect(res.body.toString().toLowerCase()).toContain("django");
  });

  it("answers 503 naming Django when Django is down", async () => {
    const port = await frontDoor(await closedOrigin());

    const res = await send(port, { path: "/healthz" });

    expect(res.status).toBe(503);
    expect(res.body.toString().toLowerCase()).toContain("django");
  });
});
