import type { TelegramResourceSession } from '../api/telegramResource'

const READ_CHUNK_SIZE = 512 * 1024
const HEAD_SCAN_SIZE = 2 * 1024 * 1024
const TAIL_SCAN_SIZE = 8 * 1024 * 1024

type Box = {
  type: string
  start: number
  dataStart: number
  end: number
}

export interface Mp4TechnicalInfo {
  container: string
  videoCodec: string | null
  audioCodec: string | null
  frameRate: number | null
  width: number | null
  height: number | null
}

function uint32(bytes: Uint8Array, offset: number) {
  return new DataView(bytes.buffer, bytes.byteOffset + offset, 4).getUint32(0)
}

function uint64(bytes: Uint8Array, offset: number) {
  const value = new DataView(bytes.buffer, bytes.byteOffset + offset, 8).getBigUint64(0)
  return value <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(value) : Number.MAX_SAFE_INTEGER
}

function uint16(bytes: Uint8Array, offset: number) {
  return new DataView(bytes.buffer, bytes.byteOffset + offset, 2).getUint16(0)
}

function text(bytes: Uint8Array, offset: number, length: number) {
  return String.fromCharCode(...bytes.subarray(offset, offset + length))
}

function boxes(bytes: Uint8Array, start: number, end: number): Box[] {
  const result: Box[] = []
  let offset = start
  while (offset + 8 <= end) {
    let size = uint32(bytes, offset)
    const type = text(bytes, offset + 4, 4)
    let headerSize = 8
    if (size === 1) {
      if (offset + 16 > end) break
      size = uint64(bytes, offset + 8)
      headerSize = 16
    } else if (size === 0) {
      size = end - offset
    }
    if (size < headerSize || offset + size > end) break
    result.push({ type, start: offset, dataStart: offset + headerSize, end: offset + size })
    offset += size
  }
  return result
}

function child(parent: Box, bytes: Uint8Array, type: string) {
  return boxes(bytes, parent.dataStart, parent.end).find((item) => item.type === type) ?? null
}

function path(parent: Box, bytes: Uint8Array, types: string[]) {
  let current: Box | null = parent
  for (const type of types) {
    if (!current) return null
    current = child(current, bytes, type)
  }
  return current
}

function validatedMoov(bytes: Uint8Array, start: number, end: number) {
  const candidate = boxes(bytes, start, end).find((item) => item.type === 'moov')
  return candidate && child(candidate, bytes, 'trak') ? candidate : null
}

function findMoov(bytes: Uint8Array) {
  const parsed = validatedMoov(bytes, 0, bytes.length)
  if (parsed) return parsed
  for (let typeOffset = 4; typeOffset + 4 <= bytes.length; typeOffset += 1) {
    if (text(bytes, typeOffset, 4) !== 'moov') continue
    const start = typeOffset - 4
    const size = uint32(bytes, start)
    if (size >= 8 && start + size <= bytes.length) {
      const candidate = validatedMoov(bytes, start, start + size)
      if (candidate) return candidate
    }
  }
  return null
}

function codecName(sampleEntry: string) {
  const names: Record<string, string> = {
    avc1: 'H.264 / AVC (avc1)',
    avc3: 'H.264 / AVC (avc3)',
    hvc1: 'H.265 / HEVC (hvc1)',
    hev1: 'H.265 / HEVC (hev1)',
    vp09: 'VP9 (vp09)',
    av01: 'AV1 (av01)',
    mp4v: 'MPEG-4 Visual (mp4v)',
    mp4a: 'AAC (mp4a)',
    Opus: 'Opus',
    ac_3: 'Dolby Digital (ac-3)',
    ec_3: 'Dolby Digital Plus (ec-3)',
  }
  return names[sampleEntry] ?? sampleEntry
}

function handlerType(trak: Box, bytes: Uint8Array) {
  const hdlr = path(trak, bytes, ['mdia', 'hdlr'])
  return hdlr && hdlr.dataStart + 12 <= hdlr.end ? text(bytes, hdlr.dataStart + 8, 4) : ''
}

function sampleEntry(trak: Box, bytes: Uint8Array) {
  const stsd = path(trak, bytes, ['mdia', 'minf', 'stbl', 'stsd'])
  const start = stsd ? stsd.dataStart + 8 : 0
  if (!stsd || start + 8 > stsd.end) return null
  const size = uint32(bytes, start)
  if (size < 8 || start + size > stsd.end) return null
  return { type: text(bytes, start + 4, 4), start, end: start + size }
}

function trackFrameRate(trak: Box, bytes: Uint8Array) {
  const mdhd = path(trak, bytes, ['mdia', 'mdhd'])
  const stts = path(trak, bytes, ['mdia', 'minf', 'stbl', 'stts'])
  if (!mdhd || !stts || mdhd.dataStart + 4 > mdhd.end || stts.dataStart + 8 > stts.end) {
    return null
  }
  const version = bytes[mdhd.dataStart]
  const timescaleOffset = mdhd.dataStart + (version === 1 ? 20 : 12)
  if (timescaleOffset + 4 > mdhd.end) return null
  const timescale = uint32(bytes, timescaleOffset)
  const entryCount = uint32(bytes, stts.dataStart + 4)
  let sampleCount = 0
  let duration = 0
  let offset = stts.dataStart + 8
  for (let index = 0; index < entryCount && offset + 8 <= stts.end; index += 1) {
    const count = uint32(bytes, offset)
    const delta = uint32(bytes, offset + 4)
    sampleCount += count
    duration += count * delta
    offset += 8
  }
  const frameRate = duration > 0 ? (sampleCount * timescale) / duration : 0
  return frameRate > 0 && Number.isFinite(frameRate) ? frameRate : null
}

async function readRange(session: TelegramResourceSession, offset: number, length: number) {
  const output = new Uint8Array(length)
  let written = 0
  while (written < length) {
    const bytes = await session.read(
      offset + written,
      Math.min(READ_CHUNK_SIZE, length - written),
      'metadata',
    )
    if (!bytes.length) break
    output.set(bytes, written)
    written += bytes.length
  }
  return output.slice(0, written)
}

export async function readMp4TechnicalInfo(
  session: TelegramResourceSession,
): Promise<Mp4TechnicalInfo | null> {
  const size = session.size ?? 0
  if (!size || !session.mimeType.toLowerCase().startsWith('video/mp4')) return null
  const head = await readRange(session, 0, Math.min(size, HEAD_SCAN_SIZE))
  let source = head
  let moov = findMoov(source)
  if (!moov && size > head.length) {
    const maximumTailLength = Math.min(size, TAIL_SCAN_SIZE)
    let tailLength = Math.min(maximumTailLength, READ_CHUNK_SIZE)
    while (!moov) {
      source = await readRange(session, size - tailLength, tailLength)
      moov = findMoov(source)
      if (moov || tailLength === maximumTailLength) break
      tailLength = Math.min(maximumTailLength, tailLength * 2)
    }
  }
  if (!moov) return null

  let videoCodec: string | null = null
  let audioCodec: string | null = null
  let frameRate: number | null = null
  let width: number | null = null
  let height: number | null = null
  for (const trak of boxes(source, moov.dataStart, moov.end).filter(
    (item) => item.type === 'trak',
  )) {
    const handler = handlerType(trak, source)
    const entry = sampleEntry(trak, source)
    if (!entry) continue
    if (handler === 'vide') {
      videoCodec = codecName(entry.type)
      if (entry.start + 36 <= entry.end) {
        width = uint16(source, entry.start + 32)
        height = uint16(source, entry.start + 34)
      }
      frameRate = trackFrameRate(trak, source)
    } else if (handler === 'soun') {
      audioCodec = codecName(entry.type)
    }
  }
  return { container: 'MP4', videoCodec, audioCodec, frameRate, width, height }
}
