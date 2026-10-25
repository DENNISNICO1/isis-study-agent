// Liefert die Podcast-Site aus den Static Assets und ergänzt HTTP-Range-Anfragen (206),
// die Static Assets selbst nicht beantworten. Der iOS-Player braucht sie zum Streamen und Spulen.

const RANGE_RE = /^bytes=(\d*)-(\d*)$/;

export function parseRange(header, size) {
  const match = RANGE_RE.exec((header || "").trim());
  if (!match || (match[1] === "" && match[2] === "")) return null;
  let start;
  let end;
  if (match[1] === "") {
    start = Math.max(0, size - Number(match[2]));
    end = size - 1;
  } else {
    start = Number(match[1]);
    end = match[2] === "" ? size - 1 : Math.min(Number(match[2]), size - 1);
  }
  if (start >= size || start > end) return { unsatisfiable: true };
  return { start, end };
}

export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const range = request.headers.get("Range");
    if (response.status !== 200) return response;

    const headers = new Headers(response.headers);
    headers.set("Accept-Ranges", "bytes");
    if (!range || request.method !== "GET") {
      return new Response(response.body, { status: 200, headers });
    }

    const body = await response.arrayBuffer();
    const size = body.byteLength;
    const parsed = parseRange(range, size);
    if (parsed === null) return new Response(body, { status: 200, headers });
    if (parsed.unsatisfiable) {
      return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    }
    headers.set("Content-Range", `bytes ${parsed.start}-${parsed.end}/${size}`);
    headers.set("Content-Length", String(parsed.end - parsed.start + 1));
    return new Response(body.slice(parsed.start, parsed.end + 1), { status: 206, headers });
  },
};
