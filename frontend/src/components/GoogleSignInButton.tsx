import { useEffect, useRef } from 'react'

type GoogleAccountsId = {
  initialize: (config: { client_id: string; callback: (response: { credential: string }) => void }) => void
  renderButton: (parent: HTMLElement, options: { theme: string; size: string; text: string; shape: string; width: number }) => void
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } }
  }
}

let loading: Promise<GoogleAccountsId> | null = null
let initializedFor: string | null = null
// Google Identity Services is initialised once per page, so its callback forwards to whichever button is mounted.
let deliverCredential: ((credential: string) => void) | null = null

function loadGoogleIdentity(): Promise<GoogleAccountsId> {
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.onload = () => (window.google ? resolve(window.google.accounts.id) : reject(new Error('Google sign-in did not load.')))
    script.onerror = () => {
      script.remove()
      loading = null
      reject(new Error('Could not load Google sign-in. Check your internet connection and reload the page.'))
    }
    document.head.appendChild(script)
  })
  return loading
}

export function GoogleSignInButton({ clientId, onCredential, onError }: {
  clientId: string
  onCredential: (credential: string) => void
  onError: (message: string) => void
}) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    deliverCredential = onCredential
    return () => {
      deliverCredential = null
    }
  }, [onCredential])

  useEffect(() => {
    let active = true
    loadGoogleIdentity()
      .then((googleId) => {
        const element = container.current
        if (!active || !element) return
        if (initializedFor !== clientId) {
          googleId.initialize({ client_id: clientId, callback: ({ credential }) => deliverCredential?.(credential) })
          initializedFor = clientId
        }
        googleId.renderButton(element, {
          theme: 'outline',
          size: 'large',
          text: 'continue_with',
          shape: 'rectangular',
          width: Math.min(400, Math.max(200, element.clientWidth)),
        })
      })
      .catch((err: Error) => {
        if (active) onError(err.message)
      })
    return () => {
      active = false
    }
  }, [clientId, onError])

  return <div ref={container} className="google-button" />
}
