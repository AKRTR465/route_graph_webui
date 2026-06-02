import { readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const targetDirs = ['src', 'tests']
const extensions = new Set(['.css', '.json', '.ts', '.vue'])
const issues = []

function collectFiles(path) {
  const stat = statSync(path)
  if (stat.isDirectory()) {
    for (const entry of readdirSync(path)) {
      collectFiles(join(path, entry))
    }
    return
  }
  if (extensions.has(extname(path))) {
    checkFile(path)
  }
}

function checkFile(path) {
  const text = readFileSync(path, 'utf8')
  const relative = path.slice(root.length).replaceAll('\\', '/')
  if (text.includes('<<<<<<<') || text.includes('=======') || text.includes('>>>>>>>')) {
    issues.push(`${relative}: contains merge conflict markers`)
  }
  if (/\bdebugger\b/.test(text)) {
    issues.push(`${relative}: contains debugger statement`)
  }
  if (/\b(?:describe|it|test)\.only\s*\(/.test(text)) {
    issues.push(`${relative}: contains focused test`)
  }
}

for (const dir of targetDirs) {
  collectFiles(join(root, dir))
}

if (issues.length > 0) {
  console.error(issues.join('\n'))
  process.exit(1)
}
