import { api } from './api'

const TARGET_SAMPLE_RATE = 16000
const VOICE_THRESHOLD = 0.018
const SILENCE_AFTER_SPEECH_MS = 1300
const NO_SPEECH_TIMEOUT_MS = 8000
const MAX_RECORDING_MS = 15000

export type Recording = { wavBase64: string; durationMs: number; speechStartMs: number }

function mergeAndDownsample(chunks: Float32Array[], inputRate: number): Int16Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0)
  const merged = new Float32Array(length)
  let offset = 0
  for (const chunk of chunks) {
    merged.set(chunk, offset)
    offset += chunk.length
  }
  const ratio = inputRate / TARGET_SAMPLE_RATE
  const output = new Int16Array(Math.floor(merged.length / ratio))
  for (let i = 0; i < output.length; i++) {
    const start = Math.floor(i * ratio)
    const end = Math.min(merged.length, Math.floor((i + 1) * ratio))
    let sum = 0
    for (let j = start; j < end; j++) sum += merged[j]
    const sample = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)))
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  return output
}

function encodeWav(samples: Int16Array): Uint8Array {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const writeText = (offset: number, text: string) => [...text].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)))
  writeText(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, TARGET_SAMPLE_RATE, true)
  view.setUint32(28, TARGET_SAMPLE_RATE * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeText(36, 'data')
  view.setUint32(40, samples.length * 2, true)
  new Int16Array(buffer, 44).set(samples)
  return new Uint8Array(buffer)
}

function toBase64(bytes: Uint8Array): string {
  let binary = ''
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  }
  return btoa(binary)
}

/** Records one spoken reply and stops automatically when the student stops talking. */
export class UtteranceRecorder {
  private stream?: MediaStream
  private context?: AudioContext
  private processor?: ScriptProcessorNode
  private chunks: Float32Array[] = []
  private resolve?: (recording: Recording | null) => void
  private startedAt = 0
  private lastVoiceAt = 0
  private firstVoiceAt = 0
  private heardSpeech = false

  async start(onLevel: (level: number) => void): Promise<Recording | null> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
    this.context = new AudioContext()
    const source = this.context.createMediaStreamSource(this.stream)
    this.processor = this.context.createScriptProcessor(4096, 1, 1)
    this.startedAt = performance.now()

    this.processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0)
      event.outputBuffer.getChannelData(0).fill(0)
      this.chunks.push(new Float32Array(input))
      let sum = 0
      for (const sample of input) sum += sample * sample
      const rms = Math.sqrt(sum / input.length)
      onLevel(Math.min(1, rms * 9))

      const now = performance.now()
      if (rms > VOICE_THRESHOLD) {
        if (!this.heardSpeech) this.firstVoiceAt = now
        this.heardSpeech = true
        this.lastVoiceAt = now
      }
      if (this.heardSpeech && now - this.lastVoiceAt > SILENCE_AFTER_SPEECH_MS) this.finish(true)
      else if (!this.heardSpeech && now - this.startedAt > NO_SPEECH_TIMEOUT_MS) this.finish(false)
      else if (now - this.startedAt > MAX_RECORDING_MS) this.finish(true)
    }
    source.connect(this.processor)
    this.processor.connect(this.context.destination)
    return new Promise((resolve) => {
      this.resolve = resolve
    })
  }

  /** Student tapped the mic again to finish speaking. */
  stop() {
    this.finish(performance.now() - this.startedAt > 400)
  }

  cancel() {
    this.finish(false)
  }

  private finish(keep: boolean) {
    const resolve = this.resolve
    if (!resolve) return
    this.resolve = undefined
    const sampleRate = this.context?.sampleRate ?? 48000
    this.processor?.disconnect()
    this.stream?.getTracks().forEach((track) => track.stop())
    void this.context?.close()
    if (!keep || this.chunks.length === 0) {
      resolve(null)
      return
    }
    const samples = mergeAndDownsample(this.chunks, sampleRate)
    const speechStartMs = this.heardSpeech ? this.firstVoiceAt - this.startedAt : 0
    resolve({ wavBase64: toBase64(encodeWav(samples)), durationMs: performance.now() - this.startedAt, speechStartMs })
  }
}

type BrowserRecognition = {
  lang: string
  interimResults: boolean
  maxAlternatives: number
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}
type RecognitionConstructor = new () => BrowserRecognition

function recognitionConstructor(): RecognitionConstructor | undefined {
  const scope = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor }
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition
}

export const browserRecognitionAvailable = () => Boolean(recognitionConstructor())

/** Fallback speech-to-text when Gemini is not configured (Chrome / Edge / Safari). */
export function recognizeOnce(): { result: Promise<string>; stop: () => void } {
  const Recognition = recognitionConstructor()
  if (!Recognition) return { result: Promise.reject(new Error('Speech recognition is not supported in this browser.')), stop: () => {} }
  const recognition = new Recognition()
  recognition.lang = 'en-US'
  recognition.interimResults = false
  recognition.maxAlternatives = 1
  const result = new Promise<string>((resolve, reject) => {
    let transcript = ''
    recognition.onresult = (event) => {
      transcript = Array.from(event.results).map((alternatives) => alternatives[0].transcript).join(' ')
    }
    recognition.onerror = (event) => {
      if (event.error === 'no-speech' || event.error === 'aborted') resolve('')
      else reject(new Error(event.error === 'not-allowed' ? 'Microphone permission was denied.' : `Speech recognition error: ${event.error}`))
    }
    recognition.onend = () => resolve(transcript)
  })
  recognition.start()
  return { result, stop: () => recognition.stop() }
}

const PREFERRED_VOICES = ['Google UK English Female', 'Google US English', 'Samantha', 'Microsoft Aria Online (Natural)', 'Microsoft Jenny Online (Natural)', 'Karen', 'Moira']

function pickBrowserVoice(): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis.getVoices().filter((voice) => voice.lang.toLowerCase().startsWith('en'))
  for (const name of PREFERRED_VOICES) {
    const match = voices.find((voice) => voice.name === name)
    if (match) return match
  }
  return voices.find((voice) => /natural|neural|enhanced|premium/i.test(voice.name)) ?? voices.find((voice) => voice.localService) ?? voices[0]
}

function sentences(text: string): string[] {
  return text.match(/[^.!?]+[.!?]*/g)?.map((part) => part.trim()).filter(Boolean) ?? [text]
}

/** Speaks tutor lines with Gemini TTS, falling back to the best local browser voice. */
export class TutorVoice {
  private onSpeakingChange: (speaking: boolean) => void
  private token = 0
  private audio?: HTMLAudioElement
  private objectUrl?: string
  private release?: () => void

  constructor(onSpeakingChange: (speaking: boolean) => void) {
    this.onSpeakingChange = onSpeakingChange
  }

  /** Resolves true when the line was spoken to the end, false when it was stopped or replaced. */
  async speak(text: string, useGemini: boolean): Promise<boolean> {
    this.stop()
    const token = ++this.token
    this.onSpeakingChange(true)
    try {
      if (useGemini) {
        try {
          const blob = await api.synthesize(text)
          if (token !== this.token) return false
          await this.playBlob(blob)
          return token === this.token
        } catch {
          if (token !== this.token) return false
        }
      }
      await this.speakWithBrowser(text, token)
      return token === this.token
    } finally {
      if (token === this.token) this.onSpeakingChange(false)
    }
  }

  stop() {
    this.token++
    this.release?.()
    this.release = undefined
    this.audio?.pause()
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl)
    this.audio = undefined
    this.objectUrl = undefined
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    this.onSpeakingChange(false)
  }

  private playBlob(blob: Blob): Promise<void> {
    this.objectUrl = URL.createObjectURL(blob)
    const audio = new Audio(this.objectUrl)
    this.audio = audio
    return new Promise((resolve) => {
      this.release = resolve
      audio.onended = () => resolve()
      audio.onerror = () => resolve()
      audio.play().catch(() => resolve())
    })
  }

  private async speakWithBrowser(text: string, token: number) {
    if (!('speechSynthesis' in window)) return
    const voice = pickBrowserVoice()
    for (const sentence of sentences(text)) {
      if (token !== this.token) return
      await new Promise<void>((resolve) => {
        const utterance = new SpeechSynthesisUtterance(sentence)
        if (voice) utterance.voice = voice
        utterance.rate = 0.95
        utterance.pitch = 1.05
        utterance.onend = () => resolve()
        utterance.onerror = () => resolve()
        this.release = resolve
        window.speechSynthesis.speak(utterance)
      })
    }
  }
}

if ('speechSynthesis' in window) window.speechSynthesis.getVoices()
