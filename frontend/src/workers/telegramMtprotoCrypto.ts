import aesjs from 'aes-js'

export function concatBytes(...parts: Uint8Array[]): Uint8Array {
  const result = new Uint8Array(parts.reduce((size, part) => size + part.length, 0))
  let offset = 0
  for (const part of parts) {
    result.set(part, offset)
    offset += part.length
  }
  return result
}

async function digest(algorithm: 'SHA-1' | 'SHA-256', value: Uint8Array): Promise<Uint8Array> {
  const input = value.slice().buffer
  return new Uint8Array(await crypto.subtle.digest(algorithm, input))
}

export function randomBytes(length: number): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(length))
}

export async function authKeyId(authKey: Uint8Array): Promise<Uint8Array> {
  return (await digest('SHA-1', authKey)).slice(-8)
}

async function deriveAesKeyIv(authKey: Uint8Array, messageKey: Uint8Array, incoming: boolean) {
  const x = incoming ? 8 : 0
  const [shaA, shaB] = await Promise.all([
    digest('SHA-256', concatBytes(messageKey, authKey.slice(x, x + 36))),
    digest('SHA-256', concatBytes(authKey.slice(40 + x, 76 + x), messageKey)),
  ])
  return {
    key: concatBytes(shaA.slice(0, 8), shaB.slice(8, 24), shaA.slice(24, 32)),
    iv: concatBytes(shaB.slice(0, 8), shaA.slice(8, 24), shaB.slice(24, 32)),
  }
}

function xorBlock(left: Uint8Array, right: Uint8Array): Uint8Array {
  const result = new Uint8Array(16)
  for (let index = 0; index < 16; index += 1) result[index] = left[index] ^ right[index]
  return result
}

export function aesIgeEncrypt(data: Uint8Array, key: Uint8Array, iv: Uint8Array): Uint8Array {
  if (data.length % 16 !== 0 || iv.length !== 32) throw new Error('Invalid AES-IGE input')
  const cipher = new aesjs.ModeOfOperation.ecb(key)
  const result = new Uint8Array(data.length)
  let previousCipher = iv.slice(0, 16)
  let previousPlain = iv.slice(16, 32)
  for (let offset = 0; offset < data.length; offset += 16) {
    const plain = data.slice(offset, offset + 16)
    const encrypted = cipher.encrypt(xorBlock(plain, previousCipher))
    const block = xorBlock(encrypted, previousPlain)
    result.set(block, offset)
    previousPlain = plain
    previousCipher = new Uint8Array(block)
  }
  return result
}

export function aesIgeDecrypt(data: Uint8Array, key: Uint8Array, iv: Uint8Array): Uint8Array {
  if (data.length % 16 !== 0 || iv.length !== 32) throw new Error('Invalid AES-IGE input')
  const cipher = new aesjs.ModeOfOperation.ecb(key)
  const result = new Uint8Array(data.length)
  let previousCipher = iv.slice(0, 16)
  let previousPlain = iv.slice(16, 32)
  for (let offset = 0; offset < data.length; offset += 16) {
    const encrypted = data.slice(offset, offset + 16)
    const decrypted = cipher.decrypt(xorBlock(encrypted, previousPlain))
    const block = xorBlock(decrypted, previousCipher)
    result.set(block, offset)
    previousCipher = encrypted
    previousPlain = new Uint8Array(block)
  }
  return result
}

function equalBytes(left: Uint8Array, right: Uint8Array): boolean {
  if (left.length !== right.length) return false
  let difference = 0
  for (let index = 0; index < left.length; index += 1) difference |= left[index] ^ right[index]
  return difference === 0
}

export async function encryptMtprotoMessage(
  authKey: Uint8Array,
  keyId: Uint8Array,
  plaintext: Uint8Array,
): Promise<Uint8Array> {
  const largeKey = await digest('SHA-256', concatBytes(authKey.slice(88, 120), plaintext))
  const messageKey = largeKey.slice(8, 24)
  const { key, iv } = await deriveAesKeyIv(authKey, messageKey, false)
  return concatBytes(keyId, messageKey, aesIgeEncrypt(plaintext, key, iv))
}

export async function decryptMtprotoMessage(
  authKey: Uint8Array,
  expectedKeyId: Uint8Array,
  packet: Uint8Array,
): Promise<Uint8Array> {
  if (packet.length < 40 || (packet.length - 24) % 16 !== 0) throw new Error('Invalid MTProto packet')
  if (!equalBytes(packet.slice(0, 8), expectedKeyId)) throw new Error('Telegram returned an invalid auth key')
  const messageKey = packet.slice(8, 24)
  const { key, iv } = await deriveAesKeyIv(authKey, messageKey, true)
  const plaintext = aesIgeDecrypt(packet.slice(24), key, iv)
  const expectedMessageKey = (await digest('SHA-256', concatBytes(authKey.slice(96, 128), plaintext))).slice(8, 24)
  if (!equalBytes(messageKey, expectedMessageKey)) throw new Error('Telegram message integrity check failed')
  return plaintext
}
