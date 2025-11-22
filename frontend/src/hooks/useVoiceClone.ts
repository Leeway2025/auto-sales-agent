import { useState, useRef, useCallback } from 'react'
import { api } from '../api'

export interface VoiceCloneState {
    referenceAudio: Blob | null
    isRecording: boolean
    hasReference: boolean
}

export function useVoiceClone() {
    const [state, setState] = useState<VoiceCloneState>({
        referenceAudio: null,
        isRecording: false,
        hasReference: false,
    })

    const mediaRecorderRef = useRef<MediaRecorder | null>(null)
    const chunksRef = useRef<Blob[]>([])

    // Start recording reference audio
    const startRecording = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
            const mediaRecorder = new MediaRecorder(stream)

            chunksRef.current = []

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    chunksRef.current.push(e.data)
                }
            }

            mediaRecorder.onstop = () => {
                const blob = new Blob(chunksRef.current, { type: 'audio/wav' })
                setState({
                    referenceAudio: blob,
                    isRecording: false,
                    hasReference: true,
                })

                // Stop all tracks
                stream.getTracks().forEach(track => track.stop())
            }

            mediaRecorderRef.current = mediaRecorder
            mediaRecorder.start()

            setState(prev => ({ ...prev, isRecording: true }))

            // Auto-stop after 5 seconds
            setTimeout(() => {
                if (mediaRecorder.state === 'recording') {
                    mediaRecorder.stop()
                }
            }, 5000)
        } catch (error) {
            console.error('Failed to start recording:', error)
            alert('无法访问麦克风，请检查权限设置')
        }
    }, [])

    // Stop recording manually
    const stopRecording = useCallback(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
            mediaRecorderRef.current.stop()
        }
    }, [])

    // Clear reference audio
    const clearReference = useCallback(() => {
        setState({
            referenceAudio: null,
            isRecording: false,
            hasReference: false,
        })
    }, [])

    // Synthesize speech with cloned voice
    const speak = useCallback(async (text: string, speed: number = 1.0) => {
        if (!state.referenceAudio) {
            throw new Error('No reference audio available')
        }

        try {
            const audioBlob = await api.cloneVoice(text, state.referenceAudio, speed)
            const audioUrl = URL.createObjectURL(audioBlob)
            const audio = new Audio(audioUrl)

            return new Promise<void>((resolve, reject) => {
                audio.onended = () => {
                    URL.revokeObjectURL(audioUrl)
                    resolve()
                }
                audio.onerror = () => {
                    URL.revokeObjectURL(audioUrl)
                    reject(new Error('Audio playback failed'))
                }
                audio.play()
            })
        } catch (error) {
            console.error('Voice cloning failed:', error)
            throw error
        }
    }, [state.referenceAudio])

    // Synthesize speech with preset speaker (fallback)
    const speakWithPreset = useCallback(async (text: string, speaker: string = 'default', speed: number = 1.0) => {
        try {
            const audioBlob = await api.synthesizeSpeech(text, speaker, speed)
            const audioUrl = URL.createObjectURL(audioBlob)
            const audio = new Audio(audioUrl)

            return new Promise<void>((resolve, reject) => {
                audio.onended = () => {
                    URL.revokeObjectURL(audioUrl)
                    resolve()
                }
                audio.onerror = () => {
                    URL.revokeObjectURL(audioUrl)
                    reject(new Error('Audio playback failed'))
                }
                audio.play()
            })
        } catch (error) {
            console.error('TTS failed:', error)
            throw error
        }
    }, [])

    return {
        ...state,
        startRecording,
        stopRecording,
        clearReference,
        speak,
        speakWithPreset,
    }
}
