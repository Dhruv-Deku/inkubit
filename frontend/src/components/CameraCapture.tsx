import { useEffect, useRef, useState } from 'react'

/** Take a photo of a sketch with the laptop or phone camera. */
export function CameraCapture({ onShot, onClose }: { onShot: (b: Blob) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let stream: MediaStream | null = null
    let cancelled = false
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This browser cannot use the camera here (it needs https or localhost). Upload a photo instead.')
      return
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } } })
      .then((s) => {
        if (cancelled) { s.getTracks().forEach((t) => t.stop()); return }
        stream = s
        if (video.current) {
          video.current.srcObject = s
          video.current.play().then(() => setReady(true)).catch(() => setReady(true))
        }
      })
      .catch((e: Error) => setError(`Camera unavailable: ${e.message}. Upload a photo instead.`))
    return () => { cancelled = true; stream?.getTracks().forEach((t) => t.stop()) }
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const snap = () => {
    const v = video.current
    if (!v || !v.videoWidth) return
    const c = document.createElement('canvas')
    c.width = v.videoWidth
    c.height = v.videoHeight
    c.getContext('2d')?.drawImage(v, 0, 0)
    c.toBlob((b) => b && onShot(b), 'image/jpeg', 0.92)
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Take a photo of your sketch" onClick={onClose}>
      <div className="panel modal-body" onClick={(e) => e.stopPropagation()}>
        <div className="panel-head"><h2>Take a photo of your sketch</h2><span className="spacer" />
          <button className="btn small ghost" onClick={onClose}>Close</button>
        </div>
        {error ? <div className="notice error">{error}</div> : (
          <>
            <video ref={video} playsInline muted className="camera" />
            <div className="sub" style={{ margin: '8px 0 12px' }}>Fill the frame with the drawing, keep it flat and evenly lit.</div>
            <button className="btn primary big" disabled={!ready} onClick={snap}>{ready ? 'Capture and read' : 'Starting camera…'}</button>
          </>
        )}
      </div>
    </div>
  )
}
