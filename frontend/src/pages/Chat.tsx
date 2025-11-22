import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card, CardContent, Typography, Box, TextField, Button, IconButton, FormControlLabel, Switch, Paper, Stack, LinearProgress } from '@mui/material'
import { Send, Mic, Stop } from '@mui/icons-material'
import { api } from '../api'
import { useSpeechSDK } from '../hooks/useSpeechSDK'
import ChatBubble from '../components/ChatBubble'

export default function Chat() {
  const { id } = useParams()
  const [msgs, setMsgs] = useState<{ role: 'user' | 'assistant', text: string }[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [threadId, setThreadId] = useState<string | undefined>(undefined)
  const greetedRef = useRef<boolean>(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const { startRecognition, stopRecognition, speak, isRecording, ready } = useSpeechSDK()

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs])

  // 初次进入对话时，由 Agent 主动开场问候与了解情况
  useEffect(() => {
    if (!id || greetedRef.current) return
    greetedRef.current = true
      ; (async () => {
        try {
          setLoading(true)
          const initMsg = '系统事件：用户已接入。'
          const data = await api.chatWithAgent(id, initMsg)
          const reply = data.reply || ''
          if (data.thread_id) setThreadId(data.thread_id)
          if (reply) {
            setMsgs(m => [...m, { role: 'assistant', text: reply }])
            speak(reply)
          }
        } catch (e) {
          // 忽略初次加载错误
        } finally {
          setLoading(false)
        }
      })()
  }, [id, speak])

  const send = async () => {
    if (!input.trim() || !id) return
    setLoading(true)
    const userMessage = input
    setInput('')  // Clear input immediately
    setMsgs(m => [...m, { role: 'user', text: userMessage }])

    // Add placeholder for assistant message
    const assistantIndex = msgs.length + 1
    setMsgs(m => [...m, { role: 'assistant', text: '' }])

    // Track streaming text
    let streamedText = ''

    try {
      // Use streaming API
      api.chatWithAgentStream(
        id,
        userMessage,
        threadId,
        // onChunk: append content in real-time
        (content) => {
          streamedText += content
          setMsgs(m => {
            const newMsgs = [...m]
            if (newMsgs[assistantIndex]) {
              newMsgs[assistantIndex] = {
                ...newMsgs[assistantIndex],
                text: streamedText
              }
            }
            return newMsgs
          })
        },
        // onComplete: save thread_id and speak
        (newThreadId) => {
          setThreadId(newThreadId)
          setLoading(false)
          // TTS: speak the complete message
          if (streamedText) speak(streamedText)
        },
        // onError: show error
        (error) => {
          setLoading(false)
          alert(error || '发送失败')
        }
      )
    } catch (e: any) {
      setLoading(false)
      alert(e.message || '发送失败')
    }
  }

  const handleStartRec = () => {
    if (!ready) return
    startRecognition(
      (text) => { // recognized
        setInput(text)
      },
      (text) => { // recognizing
        if (streaming) {
          setInput(text)
        }
      }
    )
  }

  const handleStopRec = () => {
    stopRecognition()
  }

  return (
    <Card sx={{ height: '80vh', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ flex: 1, display: 'flex', flexDirection: 'column', p: 0 }}>
        <Box sx={{ p: 3, borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          <Typography variant="h5" fontWeight="bold">与 Agent 对话</Typography>
          {!ready && <Typography variant="caption" color="text.secondary">正在加载语音引擎...</Typography>}
        </Box>

        <Box sx={{ flex: 1, overflow: 'auto', p: 3, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {msgs.map((m, i) => (
            <ChatBubble key={i} role={m.role} text={m.text} />
          ))}
          {loading && <LinearProgress sx={{ width: '50%', alignSelf: 'flex-start', borderRadius: 2 }} />}
          <div ref={messagesEndRef} />
        </Box>

        <Box sx={{ p: 3, bgcolor: 'rgba(0,0,0,0.2)', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
          <Stack direction="row" spacing={2} alignItems="center">
            <TextField
              fullWidth
              variant="outlined"
              placeholder="说点什么..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
              multiline
              maxRows={3}
              sx={{ bgcolor: 'rgba(255,255,255,0.05)' }}
            />
            <IconButton color="primary" onClick={send} disabled={loading || !input.trim()} sx={{ bgcolor: 'rgba(124,58,237,0.1)', '&:hover': { bgcolor: 'rgba(124,58,237,0.2)' } }}>
              <Send />
            </IconButton>
          </Stack>

          <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 2 }}>
            <FormControlLabel
              control={<Switch checked={streaming} onChange={e => setStreaming(e.target.checked)} />}
              label="流式识别"
              sx={{ color: 'text.secondary' }}
            />
            {!isRecording ? (
              <Button
                variant={streaming ? "outlined" : "text"}
                startIcon={<Mic />}
                onClick={handleStartRec}
                color="secondary"
                disabled={!ready}
              >
                说话
              </Button>
            ) : (
              <Button variant="contained" color="warning" startIcon={<Stop />} onClick={handleStopRec}>
                停止
              </Button>
            )}
          </Stack>
        </Box>
      </CardContent>
    </Card>
  )
}
