import { createReadStream, existsSync, statSync } from "node:fs";
import http from "node:http";
import https from "node:https";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = __dirname;
const apiOrigin = process.env.MAPS_API_ORIGIN || "http://127.0.0.1:8000";
const port = Number(process.env.PORT || 4173);

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
};

const server = http.createServer(async (request, response) => {
  if (!request.url) {
    response.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Missing request URL.");
    return;
  }

  const requestUrl = new URL(request.url, `http://${request.headers.host || "localhost"}`);

  if (requestUrl.pathname.startsWith("/api/")) {
    proxyRequest(request, response, requestUrl);
    return;
  }

  try {
    await serveStatic(requestUrl.pathname, response);
  } catch (error) {
    response.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    response.end(`Failed to serve UI: ${error instanceof Error ? error.message : String(error)}`);
  }
});

server.listen(port, () => {
  console.log(`Maps UI dev server listening on http://127.0.0.1:${port}`);
  console.log(`Proxying /api/* to ${apiOrigin}`);
});

function proxyRequest(request, response, requestUrl) {
  const upstream = new URL(requestUrl.pathname + requestUrl.search, apiOrigin);
  const transport = upstream.protocol === "https:" ? https : http;
  const proxyRequest = transport.request(
    upstream,
    {
      method: request.method,
      headers: {
        ...request.headers,
        host: upstream.host,
      },
    },
    (proxyResponse) => {
      response.writeHead(proxyResponse.statusCode || 502, proxyResponse.headers);
      proxyResponse.pipe(response);
    }
  );

  proxyRequest.on("error", (error) => {
    response.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    response.end(
      JSON.stringify({
        status: "error",
        error: "upstream_unavailable",
        detail: error.message,
      })
    );
  });

  request.pipe(proxyRequest);
}

async function serveStatic(pathname, response) {
  const safePath = normalizePath(pathname);
  const filePath = resolveFilePath(safePath);
  const extension = path.extname(filePath);
  const contentType = contentTypes[extension] || "application/octet-stream";

  response.writeHead(200, { "Content-Type": contentType });
  createReadStream(filePath).pipe(response);
}

function normalizePath(pathname) {
  const decodedPath = decodeURIComponent(pathname);
  if (decodedPath === "/") {
    return "/index.html";
  }
  return decodedPath;
}

function resolveFilePath(pathname) {
  const candidate = path.resolve(rootDir, "." + pathname);
  if (!candidate.startsWith(rootDir)) {
    return path.join(rootDir, "index.html");
  }

  if (existsSync(candidate)) {
    const stats = statSync(candidate);
    if (stats.isDirectory()) {
      const nestedIndex = path.join(candidate, "index.html");
      if (existsSync(nestedIndex)) {
        return nestedIndex;
      }
    } else {
      return candidate;
    }
  }

  return path.join(rootDir, "index.html");
}
