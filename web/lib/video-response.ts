import fs from 'node:fs';

function commonHeaders(size: number, filename?: string) {
  return {
    'Accept-Ranges': 'bytes',
    'Cache-Control': 'no-cache',
    'Content-Type': 'video/mp4',
    ...(filename ? { 'Content-Disposition': `inline; filename="${filename.replace(/["\r\n]/g, '')}"` } : {}),
    'X-Content-Type-Options': 'nosniff',
    'Content-Length': String(size),
  };
}

export function videoFileResponse(request: Request, filePath: string, filename?: string): Response {
  const stat = fs.statSync(filePath);
  const range = request.headers.get('range');
  if (!range) {
    const stream = fs.createReadStream(filePath);
    return new Response(stream as unknown as ReadableStream, { headers: commonHeaders(stat.size, filename) });
  }

  const match = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
  if (!match || (!match[1] && !match[2])) {
    return new Response(null, {
      status: 416,
      headers: { ...commonHeaders(0, filename), 'Content-Range': `bytes */${stat.size}` },
    });
  }

  let start: number;
  let end: number;
  if (!match[1]) {
    const suffixLength = Number(match[2]);
    if (!Number.isSafeInteger(suffixLength) || suffixLength <= 0) {
      return new Response(null, { status: 416, headers: { ...commonHeaders(0, filename), 'Content-Range': `bytes */${stat.size}` } });
    }
    start = Math.max(0, stat.size - suffixLength);
    end = stat.size - 1;
  } else {
    start = Number(match[1]);
    end = match[2] ? Math.min(Number(match[2]), stat.size - 1) : stat.size - 1;
  }

  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || start >= stat.size || end < start) {
    return new Response(null, {
      status: 416,
      headers: { ...commonHeaders(0, filename), 'Content-Range': `bytes */${stat.size}` },
    });
  }

  const length = end - start + 1;
  const stream = fs.createReadStream(filePath, { start, end });
  return new Response(stream as unknown as ReadableStream, {
    status: 206,
    headers: {
      ...commonHeaders(length, filename),
      'Content-Range': `bytes ${start}-${end}/${stat.size}`,
    },
  });
}
