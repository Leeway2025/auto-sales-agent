#!/usr/bin/env node
import http from 'node:http'
import https from 'node:https'
import { readFile, stat } from 'node:fs/promises'
import { createReadStream } from 'node:fs'
import { extname, join, normalize } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const distDir = join(__dirname, 'dist')

const args = process.argv.slice(2)
const getArg = (name, d) => {
  const i = args.indexOf(`--${name}`)
  if (i !== -1 && args[i + 1]) return args[i + 1]
  return process.env[name.toUpperCase()] || d
}

const host = getArg('host', '127.0.0.1')
const port = parseInt(getArg('port', '5174'), 10)
const apiTarget = new URL(getArg('api', 'http://127.0.0.1:8000'))

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.ttf': 'font/ttf',
  '.wasm': 'application/wasm',
}

function send(res, code, headers, body) {
  res.writeHead(code, headers)
  if (body && res.method !== 'HEAD') res.end(body)
  else res.end()
}

async function serveFile(res, filePath) {
  const ext = extname(filePath)
  const type = mime[ext] || 'application/octet-stream'
  try {
    const s = await stat(filePath)
    const headers = {
      'Content-Type': type,
      'Content-Length': String(s.size),
    }
    // Cache immutable assets under /assets
    if (filePath.includes('/assets/')) headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    else headers['Cache-Control'] = 'no-cache'
    res.writeHead(200, headers)
    if (res.method === 'HEAD') return res.end()
    createReadStream(filePath).pipe(res)
  } catch (e) {
    send(res, 404, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Not Found')
  }
}

function proxyApi(req, res, p) {
  const client = apiTarget.protocol === 'https:' ? https : http
  const headers = { ...req.headers, host: apiTarget.host }
  const options = {
    protocol: apiTarget.protocol,
    hostname: apiTarget.hostname,
    port: apiTarget.port || (apiTarget.protocol === 'https:' ? 443 : 80),
    path: p,
    method: req.method,
    headers,
  }
  const r = client.request(options, (pr) => {
    res.writeHead(pr.statusCode || 502, pr.headers)
    pr.pipe(res)
  })
  r.on('error', () => {
    send(res, 502, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Bad Gateway')
  })
  req.pipe(r)
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`)
    let p = decodeURIComponent(url.pathname)
    // basic security: prevent path traversal
    if (p.includes('..')) return send(res, 400, { 'Content-Type': 'text/plain' }, 'Bad Request')
    // proxy /api/* to backend target
    if (p.startsWith('/api')) {
      return proxyApi(req, res, url.pathname + url.search)
    }
    let filePath = normalize(join(distDir, p))
    if (p === '/' || !extname(p)) {
      // SPA fallback to index.html
      filePath = join(distDir, 'index.html')
    }
    await serveFile(res, filePath)
  } catch (e) {
    send(res, 500, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Internal Server Error')
  }
})

server.listen(port, host, () => {
  console.log(`[serve-dist] Serving ${distDir} at http://${host}:${port}`)
})
