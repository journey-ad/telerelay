import type { TelegramResourceStats } from '../../api/telegramResource'
import type { TelegramPreviewMessage } from '../../types'
import type { Mp4TechnicalInfo } from '../../utils/mp4TechnicalInfo'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

const CHART_WIDTH = 300
const CHART_HEIGHT = 11
const SAMPLE_WIDTH = 2
const ACTIVITY_SLOTS = CHART_WIDTH / SAMPLE_WIDTH
const SAMPLES_PER_UPDATE = 2

const BANDWIDTH_THRESHOLDS = [
  0, 18_750, 37_500, 81_250, 128_000, 256_000, 512_000, 2_048_000, 8_192_000, 32_768_000,
  131_072_000,
]
const BANDWIDTH_COLORS = [
  '#000000',
  '#d53e4f',
  '#f46d43',
  '#fdae61',
  '#fee08b',
  '#e6f598',
  '#abdda4',
  '#66c2a5',
  '#3288bd',
  '#124588',
  '#ffffff',
]
const NETWORK_THRESHOLDS = BANDWIDTH_THRESHOLDS.map((value) => value / 4)
const BUFFER_THRESHOLDS = [0, 5, 10, 30, 40, 60]
const BUFFER_COLORS = ['#000000', '#fdae61', '#e6f598', '#66c2a5', '#3288bd', '#ffffff']
const emptyHistory = () => Array<number | null>(ACTIVITY_SLOTS).fill(null)

export interface VideoPlaybackStats {
  naturalWidth: number
  naturalHeight: number
  displayWidth: number
  displayHeight: number
  currentTime: number
  duration: number
  bufferedAhead: number
  bufferedRanges: number
  totalFrames: number
  droppedFrames: number
  currentFps: number | null
  readyState: number
  networkState: number
  waitingEvents: number
  stalledEvents: number
  volume: number
  muted: boolean
}

function bytes(value: number | null | undefined) {
  if (!value || value < 1) return '0 KB'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)))
  const amount = value / 1024 ** index
  return `${amount >= 100 || index === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[index]}`
}

function bitrate(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 Kbps'
  return value >= 1_000_000
    ? `${(value / 1_000_000).toFixed(2)} Mbps`
    : `${(value / 1_000).toFixed(0)} Kbps`
}

function seconds(value: number) {
  return Number.isFinite(value) ? `${value.toFixed(2)}s` : '0.00s'
}

function connectionHealth(
  playback: VideoPlaybackStats | null,
  transport: TelegramResourceStats | null,
  waiting: boolean,
) {
  if (!transport?.connected || transport.errors) return 'error'
  const atEnd = playback && playback.duration > 0 && playback.duration - playback.currentTime < 0.5
  if (waiting || (!atEnd && (playback?.bufferedAhead ?? 0) < 1)) return 'buffering'
  const dropRatio = playback?.totalFrames ? playback.droppedFrames / playback.totalFrames : 0
  if (dropRatio > 0.02 || transport.averageLatencyMs > 1_500) return 'unstable'
  return 'healthy'
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid min-h-[15px] grid-cols-[122px_minmax(0,1fr)] gap-2">
      <dt className="text-right font-medium whitespace-nowrap text-white">{label}</dt>
      <dd className="min-w-0 break-words text-white">{children}</dd>
    </div>
  )
}

function HistoryMeter({
  samples,
  cursor,
  thresholds,
  colors,
}: {
  samples: Array<number | null>
  cursor: number
  thresholds: readonly number[]
  colors: readonly string[]
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const pixelRatio = Math.max(1, window.devicePixelRatio || 1)
    canvas.width = Math.round(CHART_WIDTH * pixelRatio)
    canvas.height = Math.round(CHART_HEIGHT * pixelRatio)
    const context = canvas.getContext('2d')
    if (!context) return
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
    context.imageSmoothingEnabled = false
    context.clearRect(0, 0, CHART_WIDTH, CHART_HEIGHT)

    samples.forEach((rawValue, index) => {
      if (rawValue === null) return
      const value = Math.max(0, Number.isFinite(rawValue) ? rawValue : 0)
      let band = 0
      while (band + 2 < thresholds.length && thresholds[band + 1] < value) band += 1
      const lower = thresholds[band] ?? 0
      const upper = thresholds[band + 1] ?? lower
      const ratio = upper > lower ? Math.min(1, Math.max(0, (value - lower) / (upper - lower))) : 0
      const x = index * SAMPLE_WIDTH

      context.fillStyle = colors[band] ?? colors.at(-1) ?? '#000000'
      context.fillRect(x, 0, SAMPLE_WIDTH, CHART_HEIGHT)
      if (ratio > 0) {
        context.fillStyle = colors[band + 1] ?? colors.at(-1) ?? '#ffffff'
        context.fillRect(x, CHART_HEIGHT * (1 - ratio), SAMPLE_WIDTH, CHART_HEIGHT * ratio)
      }
    })

    context.clearRect(cursor * SAMPLE_WIDTH, 0, SAMPLE_WIDTH, CHART_HEIGHT)
  }, [colors, cursor, samples, thresholds])

  return (
    <canvas
      ref={canvasRef}
      className="block h-[11px] min-w-0 w-full"
      width={CHART_WIDTH}
      height={CHART_HEIGHT}
      aria-hidden="true"
    />
  )
}

export function TelegramVideoStats({
  accountId,
  message,
  endpoint,
  dcId,
  playback,
  transport,
  technical,
  waiting,
  onClose,
}: {
  accountId: string
  message: TelegramPreviewMessage
  endpoint: string
  dcId: number
  playback: VideoPlaybackStats | null
  transport: TelegramResourceStats | null
  technical: Mp4TechnicalInfo | null
  waiting: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const media = message.media
  const averageBitrate =
    media?.size && playback?.duration ? (media.size * 8) / playback.duration : 0
  const measuredThroughputBps = transport?.throughputBps ?? 0
  const sourceWidth = playback?.naturalWidth || technical?.width
  const sourceHeight = playback?.naturalHeight || technical?.height
  const optimalWidth = technical?.width || sourceWidth
  const optimalHeight = technical?.height || sourceHeight
  const currentFps =
    playback?.currentFps !== null && playback?.currentFps !== undefined
      ? playback.currentFps.toFixed(1)
      : '-'
  const sourceFps = technical?.frameRate ? technical.frameRate.toFixed(2) : '-'
  const health = t(`telegramPreview.stats.health.${connectionHealth(playback, transport, waiting)}`)
  const previousDownloadedRef = useRef<number | null>(null)
  const latestBufferRef = useRef(0)
  latestBufferRef.current = playback?.bufferedAhead ?? latestBufferRef.current
  const [charts, setCharts] = useState(() => ({
    connection: emptyHistory(),
    network: emptyHistory(),
    buffer: emptyHistory(),
    cursor: 0,
    currentConnectionBps: 0,
    currentNetworkBytes: 0,
  }))
  const throughput = charts.currentConnectionBps * 8

  useEffect(() => {
    previousDownloadedRef.current = null
    latestBufferRef.current = 0
    setCharts({
      connection: emptyHistory(),
      network: emptyHistory(),
      buffer: emptyHistory(),
      cursor: 0,
      currentConnectionBps: 0,
      currentNetworkBytes: 0,
    })
  }, [accountId, message.chat_id, message.id])

  useEffect(() => {
    if (!transport) return
    const previous = previousDownloadedRef.current
    const current = transport.bytesDownloaded
    const downloaded = previous === null || current < previous ? 0 : current - previous
    previousDownloadedRef.current = current
    setCharts((state) => {
      const reset = current < (previous ?? current)
      const connection = reset ? emptyHistory() : [...state.connection]
      const network = reset ? emptyHistory() : [...state.network]
      const buffer = reset ? emptyHistory() : [...state.buffer]
      const currentConnectionBps =
        measuredThroughputBps > 0 ? measuredThroughputBps : state.currentConnectionBps
      const networkBytesPerSample = downloaded / SAMPLES_PER_UPDATE
      for (let offset = 0; offset < SAMPLES_PER_UPDATE; offset += 1) {
        const index = (state.cursor + offset) % ACTIVITY_SLOTS
        connection[index] = currentConnectionBps
        network[index] = networkBytesPerSample
        buffer[index] = latestBufferRef.current
      }
      return {
        connection,
        network,
        buffer,
        cursor: (state.cursor + SAMPLES_PER_UPDATE) % ACTIVITY_SLOTS,
        currentConnectionBps,
        currentNetworkBytes: downloaded,
      }
    })
  }, [transport])

  return (
    <section
      className="absolute top-2 left-2 z-40 max-h-[calc(100%-16px)] w-[min(500px,calc(100%-16px))] overflow-x-hidden overflow-y-auto rounded-[3px] px-2 py-1.5 text-[11px] leading-[15px] text-white shadow-lg"
      style={{
        backgroundColor: 'rgba(28, 28, 28, 0.8)',
        fontFamily: 'Roboto, Arial, Helvetica, sans-serif',
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      <button
        type="button"
        className="absolute top-1 right-2 h-5 text-[11px] text-white hover:text-white/70 focus-visible:outline-1 focus-visible:outline-white"
        title={t('telegramPreview.stats.close')}
        aria-label={t('telegramPreview.stats.close')}
        onClick={onClose}
      >
        [X]
      </button>
      <dl>
        <Row label={t('telegramPreview.stats.videoIdAccount')}>
          <span className="block truncate pr-7">
            {message.chat_id}:{message.id} / {accountId}
          </span>
        </Row>
        <Row label={t('telegramPreview.stats.viewportFrames')}>
          {playback
            ? `${playback.displayWidth}x${playback.displayHeight} / ${t(
                'telegramPreview.stats.framesValue',
                {
                  dropped: playback.droppedFrames,
                  total: playback.totalFrames,
                },
              )}`
            : '-'}
        </Row>
        <Row label={t('telegramPreview.stats.currentOptimalResolution')}>
          {sourceWidth && sourceHeight
            ? `${sourceWidth}x${sourceHeight}@${currentFps} / ${optimalWidth}x${optimalHeight}@${sourceFps}`
            : '-'}
        </Row>
        <Row label={t('telegramPreview.stats.volumeNormalized')}>
          {playback ? `${playback.muted ? 0 : Math.round(playback.volume * 100)}% / 100%` : '-'}
        </Row>
        <Row label={t('telegramPreview.stats.codecDetails')}>
          {technical?.videoCodec ?? media?.mime_type ?? '-'} / {technical?.audioCodec ?? '-'}
        </Row>
        <Row label={t('telegramPreview.stats.connectionSpeed')}>
          <span className="grid grid-cols-[minmax(0,1fr)_84px] items-center gap-2">
            <HistoryMeter
              samples={charts.connection}
              cursor={charts.cursor}
              thresholds={BANDWIDTH_THRESHOLDS}
              colors={BANDWIDTH_COLORS}
            />
            <span className="text-right whitespace-nowrap">{bitrate(throughput)}</span>
          </span>
        </Row>
        <Row label={t('telegramPreview.stats.networkActivity')}>
          <span className="grid grid-cols-[minmax(0,1fr)_84px] items-center gap-2">
            <HistoryMeter
              samples={charts.network}
              cursor={charts.cursor}
              thresholds={NETWORK_THRESHOLDS}
              colors={BANDWIDTH_COLORS}
            />
            <span className="text-right whitespace-nowrap">
              {bytes(charts.currentNetworkBytes)}
            </span>
          </span>
        </Row>
        <Row label={t('telegramPreview.stats.bufferHealth')}>
          <span className="grid grid-cols-[minmax(0,1fr)_84px] items-center gap-2">
            <HistoryMeter
              samples={charts.buffer}
              cursor={charts.cursor}
              thresholds={BUFFER_THRESHOLDS}
              colors={BUFFER_COLORS}
            />
            <span className="text-right whitespace-nowrap">
              {seconds(playback?.bufferedAhead ?? 0)}
            </span>
          </span>
        </Row>
        <Row label={t('telegramPreview.stats.liveLatency')}>
          {seconds((transport?.lastLatencyMs ?? 0) / 1_000)} /{' '}
          {seconds((transport?.averageLatencyMs ?? 0) / 1_000)} /{' '}
          {seconds((transport?.maxLatencyMs ?? 0) / 1_000)}
        </Row>
        <Row label={t('telegramPreview.stats.liveMode')}>
          {health} · {t('telegramPreview.stats.directDc', { dcId })} · {endpoint}
        </Row>
        <Row label={t('telegramPreview.stats.mysteryText')}>
          rs:{playback?.readyState ?? '-'}, ns:{playback?.networkState ?? '-'}, active:
          {transport?.activeRequests ?? 0}, ranges:{transport?.rangeRequests ?? 0}, reqs:
          {transport?.networkRequests ?? 0}, bitrate:
          {bitrate(averageBitrate).replace(' ', '')}, cache:{transport?.cacheChunks ?? 0}/
          {bytes(transport?.cachedBytes).replace(' ', '')}, hits:
          {transport?.cacheHits ?? 0}, merged:{transport?.deduplicatedRequests ?? 0}, waiting:
          {playback?.waitingEvents ?? 0}, stalled:{playback?.stalledEvents ?? 0}, errors:
          {transport?.errors ?? 0}
        </Row>
        <Row label={t('telegramPreview.stats.date')}>{new Date().toString()}</Row>
      </dl>
    </section>
  )
}
