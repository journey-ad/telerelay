import aesjs from 'aes-js'
import {
  authKeyId,
  concatBytes,
  decryptMtprotoMessage,
  encryptMtprotoMessage,
  randomBytes,
} from './telegramMtprotoCrypto'

const CONSTRUCTOR = {
  rpcResult: 0xf35c6d01,
  rpcError: 0x2144ca19,
  messageContainer: 0x73f1f8dc,
  gzipPacked: 0x3072cfa1,
  badMessage: 0xa7eff811,
  badServerSalt: 0xedab447b,
  newSession: 0x9ec20908,
  uploadFile: 0x096a18d5,
  uploadCdnRedirect: 0xf18cda44,
  msgsAck: 0x62d6b459,
  vector: 0x1cb5c415,
} as const

const METHOD = {
  invokeWithLayer: 0xda9b0d0d,
  initConnection: 0xc1cd5ea9,
  uploadGetFile: 0xbe5335be,
  inputDocumentFileLocation: 0xbad07584,
  inputPhotoFileLocation: 0x40181ffe,
  inputPeerPhotoFileLocation: 0x37257e99,
  inputPeerUser: 0xdde8a54c,
  inputPeerChat: 0x35a95cb9,
  inputPeerChannel: 0x27bcbbfc,
} as const

const REQUEST_TIMEOUT_MS = 15_000

type PeerRef = {
  type: 'user' | 'chat' | 'channel'
  id: string
  access_hash?: string
}

export type FileLocation =
  | {
      location_type: 'document'
      id: string
      access_hash: string
      file_reference: string
      thumb_size?: string
    }
  | {
      location_type: 'photo'
      id: string
      access_hash: string
      file_reference: string
      thumb_size?: string
    }
  | {
      location_type: 'peer_photo'
      peer: PeerRef
      photo_id: string
      dc_id: number
    }

type ClientOptions = {
  apiId: number
  apiLayer: number
  dcId: number
  authKey: Uint8Array
  expectedAuthKeyId: bigint
  serverSalt: bigint
  sessionId: bigint
  timeOffset: number
}

type PendingRequest = {
  resolve: (bytes: Uint8Array) => void
  reject: (error: Error) => void
  timer: ReturnType<typeof setTimeout>
  parse: (reader: TlReader) => Uint8Array
}

class RetryRequestError extends Error {}

export class TlWriter {
  private parts: Uint8Array[] = []

  int(value: number) {
    const bytes = new Uint8Array(4)
    new DataView(bytes.buffer).setUint32(0, value >>> 0, true)
    this.parts.push(bytes)
    return this
  }

  long(value: bigint | number | string) {
    const bytes = new Uint8Array(8)
    new DataView(bytes.buffer).setBigInt64(0, BigInt.asIntN(64, BigInt(value)), true)
    this.parts.push(bytes)
    return this
  }

  raw(value: Uint8Array) {
    this.parts.push(value)
    return this
  }

  bytes(value: Uint8Array) {
    const header =
      value.length < 254
        ? new Uint8Array([value.length])
        : new Uint8Array([
            254,
            value.length & 0xff,
            (value.length >> 8) & 0xff,
            (value.length >> 16) & 0xff,
          ])
    const padding = (4 - ((header.length + value.length) % 4)) % 4
    this.parts.push(header, value)
    if (padding) this.parts.push(new Uint8Array(padding))
    return this
  }

  string(value: string) {
    return this.bytes(new TextEncoder().encode(value))
  }

  build() {
    return concatBytes(...this.parts)
  }
}

export class TlReader {
  private offset = 0

  constructor(private readonly data: Uint8Array) {}

  get position() {
    return this.offset
  }

  private require(length: number) {
    if (this.offset + length > this.data.length)
      throw new Error('Telegram returned a truncated TL object')
  }

  int() {
    this.require(4)
    const value = new DataView(this.data.buffer, this.data.byteOffset + this.offset, 4).getInt32(
      0,
      true,
    )
    this.offset += 4
    return value
  }

  uint() {
    return this.int() >>> 0
  }

  long() {
    this.require(8)
    const value = new DataView(this.data.buffer, this.data.byteOffset + this.offset, 8).getBigInt64(
      0,
      true,
    )
    this.offset += 8
    return value
  }

  raw(length: number) {
    this.require(length)
    const value = this.data.slice(this.offset, this.offset + length)
    this.offset += length
    return value
  }

  bytes() {
    this.require(1)
    const marker = this.data[this.offset++]
    let length = marker
    let headerLength = 1
    if (marker === 254) {
      this.require(3)
      length =
        this.data[this.offset] |
        (this.data[this.offset + 1] << 8) |
        (this.data[this.offset + 2] << 16)
      this.offset += 3
      headerLength = 4
    }
    const value = this.raw(length)
    const padding = (4 - ((headerLength + length) % 4)) % 4
    this.raw(padding)
    return value
  }

  string() {
    return new TextDecoder().decode(this.bytes())
  }
}

export function decodeBase64Url(value: string): Uint8Array {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
  const binary = atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '='))
  return Uint8Array.from(binary, (character) => character.charCodeAt(0))
}

function writeFileLocation(writer: TlWriter, location: FileLocation): TlWriter {
  if (location.location_type === 'peer_photo') {
    // inputPeerPhotoFileLocation: constructor + flags(4) + peer + photo_id(8)
    // big=false is flags.0 = 0; dc_id only selects the DC host and is not
    // serialized into the location.
    writer.int(METHOD.inputPeerPhotoFileLocation).int(0)
    if (location.peer.type === 'user') {
      writer
        .int(METHOD.inputPeerUser)
        .long(location.peer.id)
        .long(location.peer.access_hash ?? 0)
    } else if (location.peer.type === 'chat') {
      writer.int(METHOD.inputPeerChat).long(location.peer.id)
    } else {
      writer
        .int(METHOD.inputPeerChannel)
        .long(location.peer.id)
        .long(location.peer.access_hash ?? 0)
    }
    return writer.long(location.photo_id)
  }
  const constructor =
    location.location_type === 'photo'
      ? METHOD.inputPhotoFileLocation
      : METHOD.inputDocumentFileLocation
  return writer
    .int(constructor)
    .long(location.id)
    .long(location.access_hash)
    .bytes(decodeBase64Url(location.file_reference))
    .string(location.thumb_size || '')
}

function createGetFile(location: FileLocation, offset: number, limit: number) {
  const writer = new TlWriter().int(METHOD.uploadGetFile).int(0)
  writeFileLocation(writer, location)
  return writer.long(offset).int(limit).build()
}

function createInitializedQuery(apiId: number, apiLayer: number, query: Uint8Array) {
  const connection = new TlWriter()
    .int(METHOD.initConnection)
    .int(0)
    .int(apiId)
    .string('TeleRelay video preview')
    .string('Browser')
    .string('2.0')
    .string('en')
    .string('')
    .string('en')
    .raw(query)
    .build()
  return new TlWriter().int(METHOD.invokeWithLayer).int(apiLayer).raw(connection).build()
}

function createAck(messageIds: bigint[]) {
  const writer = new TlWriter()
    .int(CONSTRUCTOR.msgsAck)
    .int(CONSTRUCTOR.vector)
    .int(messageIds.length)
  for (const messageId of messageIds) writer.long(messageId)
  return writer.build()
}

function packetHeader(payloadLength: number) {
  const words = payloadLength >> 2
  if (payloadLength % 4 !== 0) throw new Error('MTProto transport payload is not word-aligned')
  if (words < 127) return new Uint8Array([words])
  return new Uint8Array([0x7f, words & 0xff, (words >> 8) & 0xff, (words >> 16) & 0xff])
}

export class ObfuscatedAbridgedSocket {
  private socket: WebSocket | null = null
  private encryptor: InstanceType<typeof aesjs.ModeOfOperation.ctr> | null = null
  private decryptor: InstanceType<typeof aesjs.ModeOfOperation.ctr> | null = null
  private received = new Uint8Array()
  private receiveChain = Promise.resolve()

  constructor(
    private readonly dcId: number,
    private readonly onPacket: (packet: Uint8Array) => Promise<void>,
    private readonly onClose: (error: Error) => void,
  ) {}

  async connect(connectionType: 'client' | 'download' = 'download') {
    const suffix = connectionType === 'client' ? '' : '-1'
    const url = `wss://kws${this.dcId}${suffix}.web.telegram.org/apiws`
    const socket = new WebSocket(url, 'binary')
    socket.binaryType = 'arraybuffer'
    this.socket = socket
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error('Telegram WebSocket connection timed out')),
        10_000,
      )
      socket.onopen = () => {
        clearTimeout(timer)
        try {
          socket.send(this.createHeader())
          resolve()
        } catch (error) {
          reject(error)
        }
      }
      socket.onerror = () => {
        clearTimeout(timer)
        reject(new Error('Telegram WebSocket connection failed'))
      }
    })
    socket.onmessage = (event) => {
      this.receiveChain = this.receiveChain
        .then(async () => {
          const data =
            event.data instanceof ArrayBuffer
              ? event.data
              : await new Response(event.data).arrayBuffer()
          this.receive(new Uint8Array(data))
        })
        .catch((error: unknown) => this.fail(error))
    }
    socket.onclose = () => this.fail(new Error('Telegram WebSocket connection closed'))
  }

  private createHeader() {
    let header: Uint8Array
    do {
      header = randomBytes(64)
      const view = new DataView(header.buffer)
      const first = view.getUint32(0, true)
      const second = view.getUint32(4, true)
      if (
        header[0] !== 0xef &&
        first !== 0x44414548 &&
        first !== 0x54534f50 &&
        first !== 0x20544547 &&
        first !== 0x4954504f &&
        first !== 0xeeeeeeee &&
        first !== 0xdddddddd &&
        second !== 0
      )
        break
    } while (true)

    const reversed = header.slice(8, 56).reverse()
    this.encryptor = new aesjs.ModeOfOperation.ctr(header.slice(8, 40), header.slice(40, 56))
    this.decryptor = new aesjs.ModeOfOperation.ctr(reversed.slice(0, 32), reversed.slice(32, 48))
    header.set([0xef, 0xef, 0xef, 0xef], 56)
    const encrypted = this.encryptor.encrypt(header.slice())
    header.set(encrypted.slice(56, 64), 56)
    return header
  }

  send(payload: Uint8Array) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN || !this.encryptor) {
      throw new Error('Telegram WebSocket is not connected')
    }
    this.socket.send(this.encryptor.encrypt(concatBytes(packetHeader(payload.length), payload)))
  }

  private receive(encrypted: Uint8Array) {
    if (!this.decryptor) throw new Error('Telegram transport is not initialized')
    this.received = new Uint8Array(concatBytes(this.received, this.decryptor.decrypt(encrypted)))
    while (this.received.length) {
      const marker = this.received[0]
      const headerLength = marker === 0x7f ? 4 : 1
      if (marker > 0x7f) throw new Error('Telegram returned an invalid abridged packet')
      if (this.received.length < headerLength) return
      const words =
        marker === 0x7f
          ? this.received[1] | (this.received[2] << 8) | (this.received[3] << 16)
          : marker
      const length = words * 4
      if (this.received.length < headerLength + length) return
      const packet = this.received.slice(headerLength, headerLength + length)
      this.received = this.received.slice(headerLength + length)
      void this.onPacket(packet).catch((error: unknown) => this.fail(error))
    }
  }

  private fail(error: unknown) {
    const failure = error instanceof Error ? error : new Error(String(error))
    this.close()
    this.onClose(failure)
  }

  close() {
    const socket = this.socket
    this.socket = null
    if (socket) {
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
      socket.close()
    }
    this.encryptor = null
    this.decryptor = null
    this.received = new Uint8Array()
  }
}

export function randomSessionId() {
  const bytes = randomBytes(8)
  return new DataView(bytes.buffer).getBigInt64(0, true)
}

export class TelegramMtprotoClient {
  private readonly authKey: Uint8Array
  private readonly sessionId: bigint
  private keyId = new Uint8Array()
  private keyIdValue = 0n
  private salt: bigint
  private sequence = 0
  private lastMessageId = 0n
  private timeOffset = 0
  private initialized = false
  private closed = false
  private sendChain: Promise<void> = Promise.resolve()
  private readonly pending = new Map<bigint, PendingRequest>()
  private readonly socket: ObfuscatedAbridgedSocket

  constructor(private readonly options: ClientOptions) {
    this.authKey = options.authKey
    this.sessionId = options.sessionId
    this.salt = options.serverSalt
    this.timeOffset = options.timeOffset ?? 0
    this.socket = new ObfuscatedAbridgedSocket(
      options.dcId,
      (packet) => this.receivePacket(packet),
      (error) => this.rejectAll(error),
    )
  }

  async connect() {
    this.keyId = new Uint8Array(await authKeyId(this.authKey))
    this.keyIdValue = new DataView(
      this.keyId.buffer,
      this.keyId.byteOffset,
      this.keyId.byteLength,
    ).getBigUint64(0, true)
    if (this.keyIdValue !== this.options.expectedAuthKeyId) {
      throw new Error('Telegram auth key ID does not match its ticket')
    }
    await this.socket.connect()
  }

  async getFile(location: FileLocation, offset: number, limit: number) {
    const query = createGetFile(location, offset, limit)
    const body = this.initialized
      ? query
      : createInitializedQuery(this.options.apiId, this.options.apiLayer, query)
    const result = await this.invoke(body, (reader) => this.parseFileResult(reader))
    this.initialized = true
    return result
  }

  private newMessageId() {
    const now = Date.now()
    const seconds = BigInt(Math.floor(now / 1000) + this.timeOffset)
    const milliseconds = BigInt(now % 1000)
    const random = randomBytes(2)
    const random16 = BigInt(random[0] | (random[1] << 8))
    let messageId = (seconds << 32n) | (milliseconds << 21n) | (random16 << 3n) | 4n
    if (messageId <= this.lastMessageId) messageId = this.lastMessageId + 4n
    this.lastMessageId = messageId
    return messageId
  }

  private async invoke(
    body: Uint8Array,
    parse: (reader: TlReader) => Uint8Array,
    forcedMessageId?: bigint,
  ) {
    let lastError: Error | null = null
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        return await this.sendRequest(body, parse, forcedMessageId)
      } catch (error) {
        if (!(error instanceof RetryRequestError)) throw error
        lastError = error
      }
    }
    throw lastError ?? new Error('Telegram request failed')
  }

  private async sendRequest(
    body: Uint8Array,
    parse: (reader: TlReader) => Uint8Array,
    forcedMessageId?: bigint,
  ) {
    if (this.closed) throw new Error('Telegram media connection is closed')
    const messageId = forcedMessageId ?? this.newMessageId()
    if (messageId > this.lastMessageId) this.lastMessageId = messageId
    const seqNo = this.sequence * 2 + 1
    this.sequence += 1
    const envelope = new TlWriter()
      .long(this.salt)
      .long(this.sessionId)
      .long(messageId)
      .int(seqNo)
      .int(body.length)
      .raw(body)
      .build()
    const paddingLength = 16 - (envelope.length % 16) + 16 * (1 + (randomBytes(1)[0] % 5))
    const packet = encryptMtprotoMessage(
      this.authKey,
      this.keyId,
      concatBytes(envelope, randomBytes(paddingLength)),
    )
    return new Promise<Uint8Array>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(messageId)
        reject(new Error('Telegram file request timed out'))
      }, REQUEST_TIMEOUT_MS)
      this.pending.set(messageId, { resolve, reject, timer, parse })
      void this.enqueuePacket(packet).catch((error: unknown) => {
        this.rejectPending(messageId, error instanceof Error ? error : new Error(String(error)))
      })
    })
  }

  private enqueuePacket(packet: Promise<Uint8Array>) {
    const send = this.sendChain.then(async () => {
      const encrypted = await packet
      if (this.closed) throw new Error('Telegram media connection is closed')
      this.socket.send(encrypted)
    })
    this.sendChain = send.catch(() => undefined)
    return send
  }

  private async sendAck(messageIds: bigint[]) {
    if (!messageIds.length || this.closed) return
    const body = createAck(messageIds)
    const messageId = this.newMessageId()
    const envelope = new TlWriter()
      .long(this.salt)
      .long(this.sessionId)
      .long(messageId)
      .int(this.sequence * 2)
      .int(body.length)
      .raw(body)
      .build()
    const paddingLength = 16 - (envelope.length % 16) + 16 * (1 + (randomBytes(1)[0] % 5))
    const packet = encryptMtprotoMessage(
      this.authKey,
      this.keyId,
      concatBytes(envelope, randomBytes(paddingLength)),
    )
    await this.enqueuePacket(packet)
  }

  private async receivePacket(packet: Uint8Array) {
    if (packet.length === 4) {
      const code = new DataView(packet.buffer, packet.byteOffset, 4).getInt32(0, true)
      throw new Error(`Telegram transport error (${code}, auth_key_id=${this.keyIdValue})`)
    }
    const plaintext = await decryptMtprotoMessage(this.authKey, this.keyId, packet)
    const reader = new TlReader(plaintext)
    reader.long()
    const sessionId = reader.long()
    if (sessionId !== this.sessionId) throw new Error('Telegram returned an invalid session')
    const messageId = reader.long()
    const seqNo = reader.int()
    const length = reader.int()
    if (length < 4 || length > plaintext.length - 32)
      throw new Error('Telegram returned an invalid message length')
    const body = reader.raw(length)
    const acknowledgements: bigint[] = []
    if (seqNo & 1) acknowledgements.push(messageId)
    this.processObject(body, messageId, acknowledgements)
    await this.sendAck(acknowledgements)
  }

  private processObject(body: Uint8Array, remoteMessageId: bigint, acknowledgements: bigint[]) {
    const reader = new TlReader(body)
    const constructor = reader.uint()
    if (constructor === CONSTRUCTOR.messageContainer) {
      const count = reader.int()
      if (count < 0 || count > 1000)
        throw new Error('Telegram returned an invalid message container')
      for (let index = 0; index < count; index += 1) {
        const messageId = reader.long()
        const seqNo = reader.int()
        const length = reader.int()
        if (seqNo & 1) acknowledgements.push(messageId)
        this.processObject(reader.raw(length), messageId, acknowledgements)
      }
      return
    }
    if (constructor === CONSTRUCTOR.rpcResult) {
      const requestId = reader.long()
      const pending = this.pending.get(requestId)
      if (!pending) return
      this.pending.delete(requestId)
      clearTimeout(pending.timer)
      try {
        pending.resolve(pending.parse(reader))
      } catch (error) {
        pending.reject(error instanceof Error ? error : new Error(String(error)))
      }
      return
    }
    if (constructor === CONSTRUCTOR.newSession) {
      reader.long()
      reader.long()
      this.salt = reader.long()
      return
    }
    if (constructor === CONSTRUCTOR.badServerSalt) {
      const requestId = reader.long()
      reader.int()
      reader.int()
      this.salt = reader.long()
      this.retryPending(requestId, 'Telegram updated the server salt')
      return
    }
    if (constructor === CONSTRUCTOR.badMessage) {
      const requestId = reader.long()
      reader.int()
      const code = reader.int()
      if (code === 16 || code === 17) {
        this.timeOffset = Number(remoteMessageId >> 32n) - Math.floor(Date.now() / 1000)
        this.lastMessageId = 0n
        this.retryPending(requestId, 'Telegram corrected the client clock')
        return
      }
      this.rejectPending(requestId, new Error(`Telegram rejected the MTProto message (${code})`))
      return
    }
    if (constructor === CONSTRUCTOR.msgsAck) return
  }

  private parseFileResult(reader: TlReader) {
    const constructor = reader.uint()
    if (constructor === CONSTRUCTOR.rpcError) {
      const code = reader.int()
      const message = reader.string()
      throw new Error(`Telegram file request failed: ${message} (${code})`)
    }
    if (constructor === CONSTRUCTOR.gzipPacked) {
      throw new Error('Telegram returned an unsupported compressed response')
    }
    if (constructor === CONSTRUCTOR.uploadCdnRedirect) {
      throw new Error('Telegram returned an unsupported CDN redirect')
    }
    if (constructor !== CONSTRUCTOR.uploadFile) {
      throw new Error(
        `Telegram returned an unexpected file response (0x${constructor.toString(16)})`,
      )
    }
    reader.uint()
    reader.int()
    return reader.bytes()
  }

  private retryPending(messageId: bigint, message: string) {
    this.rejectPending(messageId, new RetryRequestError(message))
  }

  private rejectPending(messageId: bigint, error: Error) {
    const pending = this.pending.get(messageId)
    if (!pending) return
    this.pending.delete(messageId)
    clearTimeout(pending.timer)
    pending.reject(error)
  }

  private rejectAll(error: Error) {
    for (const [messageId] of this.pending) this.rejectPending(messageId, error)
  }

  close() {
    if (this.closed) return
    this.closed = true
    this.rejectAll(new Error('Telegram media connection was closed'))
    this.socket.close()
    this.authKey.fill(0)
    this.keyId.fill(0)
    this.keyIdValue = 0n
  }
}
