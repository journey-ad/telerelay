declare module 'aes-js' {
  class EcbMode {
    constructor(key: Uint8Array)
    encrypt(data: Uint8Array): Uint8Array
    decrypt(data: Uint8Array): Uint8Array
  }

  class CtrMode {
    constructor(key: Uint8Array, counter: Uint8Array)
    encrypt(data: Uint8Array): Uint8Array
    decrypt(data: Uint8Array): Uint8Array
  }

  const aesjs: {
    ModeOfOperation: {
      ecb: typeof EcbMode
      ctr: typeof CtrMode
    }
  }

  export default aesjs
}
