/** Page-level "single voice" mutex shared by video and audio players so only one sound plays at a time */

let activeAudioElement: HTMLAudioElement | null = null

export function setActiveAudio(element: HTMLAudioElement | null): void {
  activeAudioElement = element
}

export function clearActiveAudio(element: HTMLAudioElement): void {
  if (activeAudioElement === element) activeAudioElement = null
}

export function pauseActiveAudio(): void {
  activeAudioElement?.pause()
}
