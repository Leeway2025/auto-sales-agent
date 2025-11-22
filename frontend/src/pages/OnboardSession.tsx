import { useMemo, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, Typography, TextField, Button, Box, Stack, Paper, Grid, Chip, Divider, LinearProgress, Alert } from '@mui/material'
import { Send, CheckCircle, PlayArrow, Mic, Stop } from '@mui/icons-material'
import { api } from '../api'
import ChatBubble from '../components/ChatBubble'

type SessionState = {
  session_id: string
  user_id: string
  created_at: number
  fields: Record<string, string | null>
  missing: string[]
  history: { role: string; text: string }[]
}

export default function OnboardSession() {
  const [seed, setSeed] = useState('')
  const [session, setSession] = useState<SessionState | null>(null)
  const [msgs, setMsgs] = useState<{ role: 'assistant' | 'user', text: string }[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [created, setCreated] = useState<{ agentId: string, prompt: string } | null>(null)
  const [isRecording, setIsRecording] = useState(false)
  const [hasVoiceTemplate, setHasVoiceTemplate] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const nav = useNavigate()

  const canStart = useMemo(() => !session && !loading, [session, loading])

  const start = async () => {
    setLoading(true)
    try {
      const data = await api.startSession(seed)
      setSession(data.session)
      setMsgs([{ role: 'assistant', text: data.reply }])
      setDone((data.session.missing || []).length === 0)
    } catch (e: any) {
      alert(e.message || '启动失败')
    } finally { setLoading(false) }
  }

  const send = async () => {
    if (!session || !input.trim()) return
    setLoading(true)
    const sid = session.session_id
    const userText = input
    setMsgs(m => [...m, { role: 'user', text: userText }])
    setInput('')
    try {
      const data = await api.sendMessageToSession(sid, userText)
      setSession(data.session)
      setMsgs(m => [...m, { role: 'assistant', text: data.reply }])
      setDone(!!data.done)
    } catch (e: any) {
      alert(e.message || '发送失败')
    } finally { setLoading(false) }
  }

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      chunksRef.current = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      mediaRecorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/wav' })
        if (session) {
          try {
            await api.uploadVoiceTemplate(session.session_id, blob)
            setHasVoiceTemplate(true)
            alert('声音模板已上传！')
          } catch (e: any) {
            alert('上传失败: ' + e.message)
          }
        }
        stream.getTracks().forEach(track => track.stop())
      }

      mediaRecorderRef.current = mediaRecorder
      mediaRecorder.start()
      setIsRecording(true)

      // Auto-stop after 5 seconds
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop()
          setIsRecording(false)
        }
      }, 5000)
    } catch (error) {
      alert('无法访问麦克风')
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
    }
  }

  const finalize = async () => {
    if (!session) return
    setLoading(true)
    try {
      const data = await api.finalizeSession(session.session_id)
      setCreated({ agentId: data.agent_id, prompt: data.prompt })
      const msg = data.has_voice_template
        ? '已为你生成 Agent（含声音模板），并创建成功。你可以前往聊天页进行测试。'
        : '已为你生成 Agent，并创建成功。你可以前往聊天页进行测试。'
      setMsgs(m => [...m, { role: 'assistant', text: msg }])
    } catch (e: any) {
      alert(e.message || '生成失败')
    } finally { setLoading(false) }
  }

  const fieldsView = () => {
    if (!session) return null
    const f = session.fields || {}
    const kv = Object.entries(f).filter(([_, v]) => v) // Only show collected
    if (kv.length === 0) return null

    return (
      <Box sx={{ mt: 3, p: 2, bgcolor: 'rgba(255,255,255,0.05)', borderRadius: 1 }}>
        <Typography variant="subtitle2" gutterBottom sx={{ opacity: 0.7 }}>Agent Notes (Collected Info)</Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
          {kv.map(([k, v]) => (
            <Chip key={k} label={`${k}: ${v}`} size="small" variant="outlined" />
          ))}
        </Box>
      </Box>
    )
  }

  return (
    <Card>
      <CardContent sx={{ p: 4 }}>
        <Typography variant="h4" gutterBottom fontWeight="bold">向导式上架（多轮收集）</Typography>

        {!session && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body1" color="text.secondary" paragraph>
              可先粘贴一段大概描述作为起点，系统会一步步询问并补全品牌、行业、受众、渠道等关键信息。
            </Typography>
            <TextField
              fullWidth
              multiline
              rows={4}
              placeholder="可选：粘贴一个粗略描述作为起点"
              value={seed}
              onChange={e => setSeed(e.target.value)}
              sx={{ mb: 3 }}
            />
            <Button variant="contained" size="large" onClick={start} disabled={!canStart}>
              开始向导
            </Button>
          </Box>
        )}

        {session && (
          <Box sx={{ mt: 2 }}>
            <Paper sx={{ maxHeight: '50vh', overflow: 'auto', p: 2, mb: 3, bgcolor: 'rgba(0,0,0,0.2)' }}>
              <Stack spacing={2}>
                {msgs.map((m, i) => (
                  <ChatBubble key={i} role={m.role} text={m.text} />
                ))}
              </Stack>
            </Paper>

            <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
              <TextField
                fullWidth
                placeholder="输入你的补充信息…"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
              />
              <Button variant="contained" onClick={send} disabled={loading} endIcon={<Send />}>发送</Button>
              {done && !created && (
                <>
                  {!isRecording ? (
                    <Button
                      variant={hasVoiceTemplate ? "outlined" : "contained"}
                      color={hasVoiceTemplate ? "success" : "secondary"}
                      onClick={startRecording}
                      disabled={loading}
                      startIcon={<Mic />}
                    >
                      {hasVoiceTemplate ? '✓ 已录制' : '录制声音'}
                    </Button>
                  ) : (
                    <Button variant="contained" color="warning" onClick={stopRecording} startIcon={<Stop />}>
                      停止录制
                    </Button>
                  )}
                  <Button variant="contained" color="success" onClick={finalize} disabled={loading} startIcon={<CheckCircle />}>
                    确认生成
                  </Button>
                </>
              )}
            </Stack>

            {loading && <LinearProgress sx={{ mb: 2 }} />}

            <Divider />
            {fieldsView()}
          </Box>
        )}

        {created && (
          <Box sx={{ mt: 4 }}>
            <Alert severity="success" sx={{ mb: 3 }}>Agent 已创建成功！</Alert>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="h6" gutterBottom>Agent ID</Typography>
                <Paper sx={{ p: 2, bgcolor: 'rgba(0,0,0,0.2)', fontFamily: 'monospace' }}>{created.agentId}</Paper>
                <Button variant="contained" color="success" sx={{ mt: 2 }} onClick={() => nav(`/chat/${created.agentId}`)} startIcon={<PlayArrow />}>
                  前往聊天测试
                </Button>
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="h6" gutterBottom>系统提示词</Typography>
                <Paper sx={{ p: 2, bgcolor: 'rgba(0,0,0,0.2)', maxHeight: 300, overflow: 'auto' }}>
                  <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>{created.prompt}</Typography>
                </Paper>
              </Grid>
            </Grid>
          </Box>
        )}
      </CardContent>
    </Card>
  )
}

